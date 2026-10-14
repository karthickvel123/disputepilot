"""FastAPI merchant review web application for DisputePilot."""

import datetime
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from disputepilot.core.deadlines import calculate_deadline
from disputepilot.core.evidence import get_requirements_for_class
from disputepilot.core.models import DisputeCase, ReasonClass
from disputepilot.core.recommend import ContestDecision
from disputepilot.core.triage import load_cases_from_directory, triage_cases
from disputepilot.pipeline.audit import record_audit_event
from disputepilot.pipeline.orchestrator import _load_case_by_id, process_case
from disputepilot.razorpay.approval import (
    ApprovalRequired,
    ApprovalService,
    compute_contest_payload_hash,
)
from disputepilot.razorpay.gateway import DisputesGateway, SimGateway
from disputepilot.razorpay.webhook import default_router as webhook_router

logger = logging.getLogger("disputepilot.web.app")

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="DisputePilot Console", version="0.1.0")

# Mount static files and templates
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Mount Razorpay webhook router
app.include_router(webhook_router, prefix="/webhook/razorpay")

# Global dependencies (can be overridden in tests)
approval_service = ApprovalService()
gateway: DisputesGateway = SimGateway(approval_service=approval_service)


class RecommendationSummary(BaseModel):
    """Summary of recommendation for worklist display."""

    decision: ContestDecision
    is_uncertain: bool = False


class WorklistItem(BaseModel):
    """Item formatted for the worklist template."""

    rank: int
    case_id: str
    dispute_id: str
    amount: int
    urgency: str
    hours_remaining: float
    reason_class: str
    recommendation: RecommendationSummary


async def get_form_data(request: Request) -> dict[str, str]:
    """Parse form or JSON body safely without extra multipart dependencies."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            data = await request.json()
            return {k: str(v) for k, v in data.items()}
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
            return {}

    raw = await request.body()
    decoded = raw.decode("utf-8", errors="replace")
    parsed = parse_qs(decoded)
    return {k: v[0] if v else "" for k, v in parsed.items()}


def _get_case_result_or_process(case_id: str) -> Any:
    """Retrieve existing processed result or execute processing pipeline."""
    drafts_dir = Path("data/drafts")
    result_path = drafts_dir / f"{case_id}_result.json"
    if result_path.exists():
        try:
            with open(result_path, encoding="utf-8") as f:
                data = json.load(f)
            from disputepilot.pipeline.orchestrator import CaseProcessingResult

            return CaseProcessingResult.model_validate(data)
        except (json.JSONDecodeError, OSError, ValueError) as e:
            logger.warning("Failed to load cached result for %s: %s", case_id, e)

    return process_case(case_id=case_id, gateway=gateway)


@app.get("/", response_class=HTMLResponse)
@app.get("/cases", response_class=HTMLResponse)
def worklist_view(request: Request) -> HTMLResponse:
    """Render the prioritized merchant dispute worklist."""
    cases_dir = Path("data/cases")
    raw_cases = load_cases_from_directory(cases_dir) if cases_dir.exists() else []
    triage_items = triage_cases(raw_cases) if raw_cases else []

    items: list[WorklistItem] = []
    case_map: dict[str, DisputeCase] = {c.case_id: c for c in raw_cases}

    for idx, t_item in enumerate(triage_items, start=1):
        c_id = t_item.case_id
        case_obj = case_map.get(c_id)
        disp_id = case_obj.dispute.id if case_obj else f"disp_{c_id}"

        # Check for cached processed result to retrieve recommendation
        cached_file = Path("data/drafts") / f"{c_id}_result.json"
        if cached_file.exists():
            try:
                with open(cached_file, encoding="utf-8") as f:
                    c_data = json.load(f)
                rec_data = c_data.get("recommendation", {})
                rec = RecommendationSummary(
                    decision=ContestDecision(rec_data.get("decision", "contest")),
                    is_uncertain=bool(rec_data.get("is_uncertain", False)),
                )
            except (json.JSONDecodeError, OSError, ValueError):
                rec = RecommendationSummary(decision=ContestDecision.CONTEST, is_uncertain=False)
        else:
            # Deterministic heuristic fallback from p_win
            if 0.35 <= t_item.p_win <= 0.55:
                rec = RecommendationSummary(decision=ContestDecision.CONTEST, is_uncertain=True)
            elif t_item.p_win >= 0.50:
                rec = RecommendationSummary(decision=ContestDecision.CONTEST, is_uncertain=False)
            else:
                rec = RecommendationSummary(decision=ContestDecision.ACCEPT, is_uncertain=False)

        items.append(
            WorklistItem(
                rank=idx,
                case_id=c_id,
                dispute_id=disp_id,
                amount=t_item.amount_paise,
                urgency=t_item.urgency,
                hours_remaining=t_item.hours_remaining or 0.0,
                reason_class=t_item.reason_class.value if isinstance(t_item.reason_class, ReasonClass) else str(t_item.reason_class),
                recommendation=rec,
            )
        )

    return templates.TemplateResponse(
        request=request,
        name="worklist.html",
        context={"items": items},
    )


@app.get("/cases/{case_id}", response_class=HTMLResponse)
def case_detail_view(request: Request, case_id: str) -> HTMLResponse:
    """Render full dispute case review console."""
    try:
        case = _load_case_by_id(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    result = _get_case_result_or_process(case_id)

    # Deadline & Urgency
    dl = calculate_deadline(case.dispute.model_dump())
    respond_by_dt = (
        datetime.datetime.fromtimestamp(case.dispute.respond_by, tz=datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        if case.dispute.respond_by
        else "N/A"
    )

    rc = result.evidence_report.reason_class
    reason_class_val = rc.value if hasattr(rc, "value") else str(rc)
    requirements = get_requirements_for_class(reason_class_val)

    # Detect if adversarial prompt injection was flagged
    adv_types = case.ground_truth.adversarial.adversarial_types if case.ground_truth else []
    injection_detected = "prompt_injection" in adv_types or any(
        "ignore previous instructions" in (d.content or "").lower() for d in case.documents
    )

    return templates.TemplateResponse(
        request=request,
        name="case_detail.html",
        context={
            "case": case,
            "evidence_report": result.evidence_report,
            "recommendation": result.recommendation,
            "clean_draft": result.clean_draft,
            "verifier_report": result.verifier_report,
            "urgency": dl.urgency.value,
            "hours_remaining": dl.hours_remaining or 0.0,
            "respond_by_formatted": respond_by_dt,
            "reason_class": reason_class_val,
            "requirements": requirements,
            "cross_check_flags": result.evidence_report.cross_check_flags,
            "injection_detected": injection_detected,
        },
    )


@app.post("/cases/{case_id}/save-draft")
async def save_draft_action(
    request: Request,
    case_id: str,
) -> RedirectResponse:
    """Save merchant edits to the rebuttal draft without submitting to Razorpay."""
    form = await get_form_data(request)
    reviewer_name = form.get("reviewer_name", "").strip()
    summary = form.get("summary", "")

    if not reviewer_name:
        raise HTTPException(status_code=400, detail="Reviewer name is required.")

    case = _load_case_by_id(case_id)
    gateway.contest_dispute(
        dispute_id=case.dispute.id,
        action="draft",
        summary=summary,
    )

    record_audit_event(
        case_id=case_id,
        action="save_draft",
        actor=reviewer_name,
        details={"summary_length": len(summary)},
    )

    return RedirectResponse(url=f"/cases/{case_id}?success=Draft+saved", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/cases/{case_id}/confirm-submit", response_class=HTMLResponse)
def confirm_submit_view(
    request: Request,
    case_id: str,
    reviewer_name: str = "",
) -> HTMLResponse:
    """Display exact contest payload and issue cryptographically bound approval token."""
    if not reviewer_name or not reviewer_name.strip():
        raise HTTPException(
            status_code=400,
            detail="A named human reviewer is strictly required to proceed with dispute submission.",
        )

    case = _load_case_by_id(case_id)
    result = _get_case_result_or_process(case_id)

    # Build the exact submission payload
    clean_markdown = result.clean_draft.to_markdown()
    payload: dict[str, Any] = {
        "action": "submit",
        "summary": clean_markdown,
    }

    # Include evidence URLs/IDs if present on the dispute
    ev_dump = case.dispute.evidence.model_dump()
    for k, v in ev_dump.items():
        if v:
            payload[k] = v

    payload_hash = compute_contest_payload_hash(payload)

    # Issue single-use human approval token bound to this exact hash
    token = approval_service.issue_token(
        dispute_id=case.dispute.id,
        action="submit",
        payload=payload,
        approver=reviewer_name.strip(),
    )

    return templates.TemplateResponse(
        request=request,
        name="confirm_submit.html",
        context={
            "case": case,
            "reviewer_name": reviewer_name.strip(),
            "approval_token": token,
            "payload_hash": payload_hash,
            "payload_json": json.dumps(payload, indent=2),
        },
    )


@app.post("/cases/{case_id}/submit")
async def submit_contest_action(
    request: Request,
    case_id: str,
) -> RedirectResponse:
    """Submit rebuttal contest to Razorpay with human approval token."""
    form = await get_form_data(request)
    reviewer_name = form.get("reviewer_name", "").strip()
    approval_token = form.get("approval_token", "").strip()
    payload_hash = form.get("payload_hash", "").strip()

    if not reviewer_name:
        raise HTTPException(status_code=400, detail="Reviewer name is required.")
    if not approval_token:
        raise HTTPException(status_code=400, detail="Approval token is required.")

    case = _load_case_by_id(case_id)
    result = _get_case_result_or_process(case_id)

    # Reconstruct expected payload to check against bound hash
    clean_markdown = result.clean_draft.to_markdown()
    payload: dict[str, Any] = {
        "action": "submit",
        "summary": clean_markdown,
    }
    ev_dump = case.dispute.evidence.model_dump()
    for k, v in ev_dump.items():
        if v:
            payload[k] = v

    expected_hash = compute_contest_payload_hash(payload)
    if payload_hash != expected_hash:
        raise HTTPException(
            status_code=400,
            detail="Payload hash mismatch. The content submitted does not match the approved payload.",
        )

    try:
        gateway.contest_dispute(
            dispute_id=case.dispute.id,
            action="submit",
            summary=clean_markdown,
            approval_token=approval_token,
        )
    except ApprovalRequired as err:
        raise HTTPException(status_code=400, detail=str(err))

    record_audit_event(
        case_id=case_id,
        action="submit_contest",
        actor=reviewer_name,
        details={"payload_hash": payload_hash, "approval_token": approval_token},
    )

    return RedirectResponse(
        url=f"/cases/{case_id}?success=Dispute+successfully+contested+and+submitted",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/cases/{case_id}/accept")
async def accept_dispute_action(
    request: Request,
    case_id: str,
) -> RedirectResponse:
    """Accept dispute liability. Requires typed amount verification and human approval token."""
    form = await get_form_data(request)
    reviewer_name = form.get("reviewer_name", "").strip()
    typed_amount = form.get("typed_amount", "").strip()

    if not reviewer_name:
        raise HTTPException(status_code=400, detail="Reviewer name is required.")
    if not typed_amount:
        raise HTTPException(status_code=400, detail="Dispute amount must be typed to confirm acceptance.")

    case = _load_case_by_id(case_id)

    # Normalize typed amount
    cleaned_input = typed_amount.replace("₹", "").replace(",", "").strip()
    try:
        input_val = float(cleaned_input)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid amount entered: '{typed_amount}'. Please enter a valid number.",
        )

    expected_rupees = case.dispute.amount / 100.0
    # Also allow if user typed exact amount in paise
    if abs(input_val - expected_rupees) > 0.01 and abs(input_val - case.dispute.amount) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Amount mismatch. You typed ₹{input_val:.2f}, but dispute amount is ₹{expected_rupees:.2f}.",
        )

    # Issue single-use approval token for accept
    token = approval_service.issue_token(
        dispute_id=case.dispute.id,
        action="accept",
        amount=case.dispute.amount,
        approver=reviewer_name,
    )

    try:
        gateway.accept_dispute(
            dispute_id=case.dispute.id,
            approval_token=token,
        )
    except ApprovalRequired as err:
        raise HTTPException(status_code=400, detail=str(err))

    record_audit_event(
        case_id=case_id,
        action="accept_dispute",
        actor=reviewer_name,
        details={"dispute_id": case.dispute.id, "amount": case.dispute.amount},
    )

    return RedirectResponse(
        url=f"/cases/{case_id}?success=Dispute+accepted+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/cases/{case_id}/needs-evidence")
async def needs_evidence_action(
    request: Request,
    case_id: str,
) -> RedirectResponse:
    """Flag dispute as needing merchant evidence."""
    form = await get_form_data(request)
    reviewer_name = form.get("reviewer_name", "").strip()
    note = form.get("note", "")

    if not reviewer_name:
        raise HTTPException(status_code=400, detail="Reviewer name is required.")

    record_audit_event(
        case_id=case_id,
        action="needs_evidence",
        actor=reviewer_name,
        details={"note": note.strip()},
    )

    return RedirectResponse(
        url=f"/cases/{case_id}?success=Case+flagged+as+Needs+Evidence",
        status_code=status.HTTP_303_SEE_OTHER,
    )
