"""FastAPI merchant review web application for DisputePilot."""

import datetime
import hashlib
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
from disputepilot.pipeline.orchestrator import (
    CASE_ID_PATTERN,
    _load_case_by_id,
    process_case,
)
from disputepilot.razorpay.approval import (
    ApprovalRequired,
    ApprovalService,
    compute_accept_payload_hash,
    compute_contest_payload_hash,
)
from disputepilot.razorpay.gateway import DisputesGateway, SimGateway
from disputepilot.razorpay.webhook import default_router as webhook_router
from disputepilot.safety.ingest import ingest_document
from disputepilot.web.auth import (
    SESSION_COOKIE_NAME,
    create_session_cookie_value,
    get_configured_credentials,
    get_missing_auth_env_vars,
    get_session,
    is_auth_configured,
    validate_csrf,
    verify_password,
)

logger = logging.getLogger("disputepilot.web.app")

# Startup fail-closed check: log warning naming missing auth variables
_missing_auth = get_missing_auth_env_vars()
if _missing_auth:
    logger.warning(
        "Authentication is not configured at startup: missing %s. "
        "Reviewer login will be rejected and authenticated actions will fail closed.",
        ", ".join(_missing_auth),
    )


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


async def require_auth_and_csrf(request: Request) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate reviewer session and CSRF token on mutating requests."""
    if not is_auth_configured():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is not configured on this server.",
        )

    session = get_session(request)
    if not session or not session.get("user"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in as an authorized reviewer.",
        )

    form = await get_form_data(request)
    csrf_token = form.get("csrf_token") or request.headers.get("x-csrf-token")
    if not validate_csrf(session, csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed or token missing.",
        )

    return session, form


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


@app.get("/login", response_class=HTMLResponse)
def login_view(request: Request, next: str | None = None) -> Any:
    """Render reviewer login form."""
    session = get_session(request)
    if session and session.get("user"):
        return RedirectResponse(url=next or "/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"next": next or "/"},
    )


@app.post("/login")
async def login_action(request: Request) -> Any:
    """Authenticate single reviewer and issue signed session cookie with CSRF token."""
    form = await get_form_data(request)
    username = form.get("username", "").strip()
    password = form.get("password", "")
    next_url = form.get("next", "/").strip() or "/"

    expected_user, expected_hash = get_configured_credentials()
    content_type = request.headers.get("content-type", "")
    is_json = "application/json" in content_type

    if (
        not is_auth_configured()
        or not expected_user
        or not expected_hash
        or username != expected_user
        or not verify_password(password, expected_hash)
    ):
        if is_json:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Invalid reviewer username or password.", "next": next_url},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    cookie_val, _ = create_session_cookie_value(user=username)
    response = RedirectResponse(url=next_url, status_code=status.HTTP_303_SEE_OTHER)
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_val,
        httponly=True,
        samesite="lax",
        secure=is_https,
        max_age=8 * 3600,
    )
    return response


@app.get("/logout")
@app.post("/logout")
def logout_action() -> RedirectResponse:
    """Terminate reviewer session."""
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get("/", response_class=HTMLResponse)
@app.get("/cases", response_class=HTMLResponse)
def worklist_view(request: Request) -> HTMLResponse:
    """Render the prioritized merchant dispute worklist."""
    session = get_session(request)
    reviewer_name = session.get("user") if session else None
    csrf_token = session.get("csrf_token") if session else None

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
        context={
            "items": items,
            "reviewer_name": reviewer_name,
            "csrf_token": csrf_token,
        },
    )


@app.get("/cases/{case_id}", response_class=HTMLResponse)
def case_detail_view(request: Request, case_id: str) -> HTMLResponse:
    """Render full dispute case review console."""
    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    try:
        case = _load_case_by_id(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    session = get_session(request)
    reviewer_name = session.get("user") if session else None
    csrf_token = session.get("csrf_token") if session else None

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

    # Compute safety findings per document
    protected_ids = {
        case.order.id if case.order else "",
        case.dispute.id,
        case.dispute.payment_id,
        case.order.tracking_number if case.order else "",
    }
    known_names = [case.order.customer_name] if case.order and case.order.customer_name else []

    safety_findings: list[dict[str, Any]] = []
    for doc in case.documents:
        ingest_res = ingest_document(
            doc.content or "",
            case_id=case.case_id,
            known_names=known_names,
            protected_ids=protected_ids,
        )
        card_findings = [f for f in ingest_res.findings if f.type == "card_number"]
        card_count = len(card_findings)
        last_4_list = [f.masked[-4:] for f in card_findings]

        if card_count == 1:
            card_str = f"1 card number redacted (last 4: {last_4_list[0]})"
        elif card_count > 1:
            card_str = f"{card_count} card numbers redacted (last 4: {', '.join(last_4_list)})"
        else:
            card_str = "0 card numbers redacted"

        inj_count = len(ingest_res.injection_flags)
        if inj_count > 0:
            inj_str = f"{inj_count} injection indicator(s) detected: {', '.join(ingest_res.injection_flags)}"
        else:
            inj_str = "0 injection indicators detected"

        pii_count = len(ingest_res.vault)
        pii_str = f"{pii_count} PII token(s) replaced"

        safety_findings.append({
            "doc_id": doc.doc_id,
            "doc_type": doc.doc_type,
            "file_name": doc.file_name,
            "card_count": card_count,
            "card_str": card_str,
            "last_4": last_4_list,
            "injection_count": inj_count,
            "injection_str": inj_str,
            "injection_flags": ingest_res.injection_flags,
            "pii_count": pii_count,
            "pii_str": pii_str,
        })

    return templates.TemplateResponse(
        request=request,
        name="case_detail.html",
        context={
            "case": case,
            "reviewer_name": reviewer_name,
            "csrf_token": csrf_token,
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
            "safety_findings": safety_findings,
        },
    )


@app.post("/cases/{case_id}/save-draft")
async def save_draft_action(
    request: Request,
    case_id: str,
) -> RedirectResponse:
    """Save merchant edits to the rebuttal draft without submitting to Razorpay."""
    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    session, form = await require_auth_and_csrf(request)
    reviewer_name = session["user"]
    summary = form.get("summary", "")

    try:
        case = _load_case_by_id(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

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


@app.post("/cases/{case_id}/review", response_class=HTMLResponse)
@app.post("/cases/{case_id}/confirm-submit", response_class=HTMLResponse)
async def review_and_confirm_submit_view(
    request: Request,
    case_id: str,
) -> HTMLResponse:
    """Display exact contest payload and issue cryptographically bound approval token via POST."""
    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    session, _form = await require_auth_and_csrf(request)
    reviewer_name = session["user"]

    try:
        case = _load_case_by_id(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

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
        approver=reviewer_name,
    )

    return templates.TemplateResponse(
        request=request,
        name="confirm_submit.html",
        context={
            "case": case,
            "reviewer_name": reviewer_name,
            "csrf_token": session.get("csrf_token"),
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
    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    session, form = await require_auth_and_csrf(request)
    reviewer_name = session["user"]
    approval_token = form.get("approval_token", "").strip()
    payload_hash = form.get("payload_hash", "").strip()

    if not approval_token:
        raise HTTPException(status_code=400, detail="Approval token is required.")

    try:
        case = _load_case_by_id(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

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

    token_hash = hashlib.sha256(approval_token.encode("utf-8")).hexdigest()
    record_audit_event(
        case_id=case_id,
        action="submit_contest",
        actor=reviewer_name,
        details={"payload_hash": payload_hash, "approval_token_hash": token_hash},
    )

    return RedirectResponse(
        url=f"/cases/{case_id}?success=Dispute+successfully+contested+and+submitted",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/cases/{case_id}/accept-review", response_class=HTMLResponse)
async def accept_review_view(
    request: Request,
    case_id: str,
) -> HTMLResponse:
    """Show acceptance confirmation page and issue approval token bound to accept payload hash."""
    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    session, form = await require_auth_and_csrf(request)
    reviewer_name = session["user"]
    typed_amount = form.get("typed_amount", "").strip()

    if not typed_amount:
        raise HTTPException(status_code=400, detail="Dispute amount must be typed to confirm acceptance.")

    try:
        case = _load_case_by_id(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

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
    if abs(input_val - expected_rupees) > 0.01 and abs(input_val - case.dispute.amount) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Amount mismatch. You typed ₹{input_val:.2f}, but dispute amount is ₹{expected_rupees:.2f}.",
        )

    payload_hash = compute_accept_payload_hash(case.dispute.id, case.dispute.amount)

    # Issue single-use human approval token bound to exact accept payload hash
    token = approval_service.issue_token(
        dispute_id=case.dispute.id,
        action="accept",
        amount=case.dispute.amount,
        approver=reviewer_name,
    )

    return templates.TemplateResponse(
        request=request,
        name="confirm_accept.html",
        context={
            "case": case,
            "reviewer_name": reviewer_name,
            "csrf_token": session.get("csrf_token"),
            "approval_token": token,
            "payload_hash": payload_hash,
            "amount_rupees": expected_rupees,
            "amount_paise": case.dispute.amount,
        },
    )


@app.post("/cases/{case_id}/accept")
async def accept_dispute_action(
    request: Request,
    case_id: str,
) -> RedirectResponse:
    """Accept dispute liability. Requires approval token bound to accept payload hash."""
    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    session, form = await require_auth_and_csrf(request)
    reviewer_name = session["user"]
    approval_token = form.get("approval_token", "").strip()
    payload_hash = form.get("payload_hash", "").strip()

    if not approval_token:
        raise HTTPException(status_code=400, detail="Approval token is required.")

    try:
        case = _load_case_by_id(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    expected_hash = compute_accept_payload_hash(case.dispute.id, case.dispute.amount)
    if payload_hash and payload_hash != expected_hash:
        raise HTTPException(
            status_code=400,
            detail="Payload hash mismatch. The acceptance request does not match the approved dispute.",
        )

    try:
        gateway.accept_dispute(
            dispute_id=case.dispute.id,
            approval_token=approval_token,
        )
    except ApprovalRequired as err:
        raise HTTPException(status_code=400, detail=str(err))

    token_hash = hashlib.sha256(approval_token.encode("utf-8")).hexdigest()
    record_audit_event(
        case_id=case_id,
        action="accept_dispute",
        actor=reviewer_name,
        details={
            "dispute_id": case.dispute.id,
            "amount": case.dispute.amount,
            "approval_token_hash": token_hash,
        },
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
    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    session, form = await require_auth_and_csrf(request)
    reviewer_name = session["user"]
    note = form.get("note", "")

    try:
        _load_case_by_id(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

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
