"""REST API router for DisputePilot frontend SPA.

All endpoints return JSON.  Mutations require a valid session cookie and CSRF token.
Read endpoints require a valid session cookie only.
"""

import datetime
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from disputepilot.config import load_settings
from disputepilot.core.deadlines import calculate_deadline
from disputepilot.core.evidence import get_requirements_for_class
from disputepilot.core.models import DisputeCase, DisputeStatus, ReasonClass
from disputepilot.core.triage import load_cases_from_directory, triage_cases
from disputepilot.live.locker import ALLOWED_MIME, EVIDENCE_CATEGORIES
from disputepilot.live.pdf import text_to_pdf
from disputepilot.live.source import (
    CaseNotFound,
    SourceError,
    describe_error,
)
from disputepilot.live.summary import short_summary
from disputepilot.pipeline.audit import (
    get_all_audit_events,
    get_audit_events,
    record_audit_event,
    verify_audit_trail,
)
from disputepilot.pipeline.orchestrator import (
    CASE_ID_PATTERN,
    CaseProcessingResult,
    _load_case_by_id,
    process_case,
)
from disputepilot.razorpay.approval import (
    ApprovalRequired,
    compute_accept_payload_hash,
    compute_contest_payload_hash,
)
from disputepilot.razorpay.gateway import (
    DisputesGateway,
    RazorpayAPIError,
)
from disputepilot.safety.ingest import ingest_document
from disputepilot.web.auth import (
    SESSION_COOKIE_NAME,
    create_session_cookie_value,
    get_configured_credentials,
    get_session,
    validate_csrf,
    verify_password,
)

logger = logging.getLogger("disputepilot.web.api")

router = APIRouter(prefix="/api/v1", tags=["api"])

# These will be set by the app module during startup
_settings = None
_gateway = None
_live_source = None
_llm_client = None
_approval_service = None
_locker = None
_razorpay_problems = []
_auth_problems = []


def configure_api(
    settings,
    gateway,
    live_source,
    llm_client,
    approval_service,
    locker,
    razorpay_problems,
    auth_problems,
):
    """Called from app.py to inject runtime dependencies."""
    global _settings, _gateway, _live_source, _llm_client
    global _approval_service, _locker, _razorpay_problems, _auth_problems
    _settings = settings
    _gateway = gateway
    _live_source = live_source
    _llm_client = llm_client
    _approval_service = approval_service
    _locker = locker
    _razorpay_problems = razorpay_problems
    _auth_problems = auth_problems


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _require_session(request: Request) -> dict[str, Any]:
    """Validate session cookie.  Returns session dict or raises 401."""
    session = get_session(request)
    if not session or not session.get("user"):
        raise HTTPException(status_code=401, detail="Authentication required.")
    return session


def _require_csrf(request: Request, session: dict[str, Any], token: str | None = None) -> None:
    """Validate CSRF on mutations."""
    csrf = token or request.headers.get("x-csrf-token")
    if not validate_csrf(session, csrf):
        raise HTTPException(status_code=403, detail="CSRF validation failed.")


def _get_gateway() -> DisputesGateway | None:
    if _gateway is not None:
        return _gateway
    from disputepilot.web import app as _app_module
    return getattr(_app_module, "gateway", None)


def _get_settings():
    if _settings is not None:
        return _settings
    from disputepilot.web import app as _app_module
    return getattr(_app_module, "settings", load_settings())


def _get_live_source():
    if _live_source is not None:
        return _live_source
    from disputepilot.web import app as _app_module
    return getattr(_app_module, "live_source", None)


def _get_approval_service():
    if _approval_service is not None:
        return _approval_service
    from disputepilot.web import app as _app_module
    return getattr(_app_module, "approval_service", None)


def _get_locker():
    if _locker is not None:
        return _locker
    from disputepilot.web import app as _app_module
    return getattr(_app_module, "locker", None)


def _require_gateway() -> DisputesGateway:
    gw = _get_gateway()
    if gw is None:
        raise HTTPException(status_code=503, detail="Razorpay is not configured: " + " ".join(_razorpay_problems))
    return gw


def _upstream_error(exc: Exception) -> HTTPException:
    code = 400 if isinstance(exc, RazorpayAPIError) and exc.status_code in (400, 404, 409, 422) else 502
    return HTTPException(status_code=code, detail=describe_error(exc))


DRAFTS_DIR_NAME = "drafts"
LETTER_PREFIX = "rebuttal-letter-"


def _drafts_dir() -> Path:
    st = _get_settings()
    return st.data_dir / DRAFTS_DIR_NAME


def _load_case(case_id: str) -> DisputeCase:
    st = _get_settings()
    if st.is_sim:
        return _load_case_by_id(case_id)
    ls = _get_live_source()
    if ls is None:
        _require_gateway()
        raise HTTPException(status_code=503, detail="Razorpay is not configured.")
    try:
        return ls.get_case(case_id)
    except CaseNotFound as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except SourceError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err



def _ensure_actionable(case: DisputeCase) -> None:
    st = _get_settings()
    if st.is_sim:
        return
    d = case.dispute
    if d.status != DisputeStatus.OPEN:
        raise HTTPException(
            status_code=400,
            detail=f"Dispute is '{d.status.value}'; Razorpay only accepts responses while it is 'open'.",
        )
    if d.respond_by and d.respond_by <= int(time.time()):
        raise HTTPException(status_code=400, detail="The response deadline for this dispute has passed.")


def _is_actionable(case: DisputeCase) -> bool:
    try:
        _ensure_actionable(case)
        return True
    except HTTPException:
        return False



def _letter_pdf(case: DisputeCase, clean_markdown: str) -> bytes:
    return text_to_pdf(clean_markdown, title=f"Rebuttal {case.dispute.id}")


def _build_contest_payload(case: DisputeCase, clean_markdown: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"action": "submit"}
    if _settings.is_sim:
        payload["summary"] = clean_markdown
        for k, v in case.dispute.evidence.model_dump().items():
            if v:
                payload[k] = v
        return payload

    payload["summary"] = short_summary(clean_markdown)
    evidence = {k: list(v) for k, v in case.dispute.evidence.document_ids().items()}
    if _locker:
        for doc in _locker.list_for_dispute(case.dispute.id):
            if doc.razorpay_doc_id and not doc.file_name.startswith(LETTER_PREFIX):
                bucket = evidence.setdefault(doc.category, [])
                if doc.razorpay_doc_id not in bucket:
                    bucket.append(doc.razorpay_doc_id)
        letter = _locker.find_uploaded_by_hash(hashlib.sha256(_letter_pdf(case, clean_markdown)).hexdigest())
        if letter and letter.razorpay_doc_id:
            bucket = evidence.setdefault("explanation_letter", [])
            if letter.razorpay_doc_id not in bucket:
                bucket.append(letter.razorpay_doc_id)
    payload.update({k: v for k, v in evidence.items() if v})
    return payload


def _ensure_letter_uploaded(case: DisputeCase, clean_markdown: str, reviewer: str) -> None:
    if _settings.is_sim or not _locker:
        return
    pdf = _letter_pdf(case, clean_markdown)
    digest = hashlib.sha256(pdf).hexdigest()
    if _locker.find_uploaded_by_hash(digest):
        return
    name = f"{LETTER_PREFIX}{case.dispute.id}.pdf"
    import httpx
    try:
        uploaded = _require_gateway().upload_document(pdf, name, purpose="dispute_evidence")
    except (httpx.HTTPError, ValueError) as err:
        raise _upstream_error(err) from err
    _locker.add(
        dispute_id=case.dispute.id,
        category="explanation_letter",
        file_name=name,
        mime="application/pdf",
        size=len(pdf),
        sha256=digest,
        uploaded_by=reviewer,
        razorpay_doc_id=str(uploaded.get("id", "")) or None,
    )


_MAGIC: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}



# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user: str
    csrf_token: str


@router.post("/auth/login")
async def api_login(request: Request, body: LoginRequest) -> JSONResponse:
    """Authenticate and return session cookie + CSRF token."""
    expected_user, expected_hash = get_configured_credentials()
    if body.username != expected_user or not verify_password(body.password, expected_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    cookie_val, csrf_token = create_session_cookie_value(user=body.username)
    response = JSONResponse(
        content={"user": body.username, "csrf_token": csrf_token},
        status_code=200,
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_val,
        httponly=True,
        samesite="lax",
        max_age=86400,
        secure=_settings.cookie_secure if _settings else False,
    )
    return response


@router.post("/auth/logout")
async def api_logout(request: Request) -> JSONResponse:
    session = _require_session(request)
    _require_csrf(request, session)
    response = JSONResponse(content={"ok": True})
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        httponly=True,
        secure=_settings.cookie_secure if _settings else False,
        samesite="lax",
    )
    return response


@router.get("/auth/me")
async def api_me(request: Request) -> dict[str, Any]:
    """Return current session user info or 401."""
    session = _require_session(request)
    return {
        "user": session["user"],
        "csrf_token": session.get("csrf_token", ""),
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard/metrics")
async def api_dashboard_metrics(request: Request) -> dict[str, Any]:
    """Database-backed dashboard metrics.  No hardcoded numbers."""
    _require_session(request)

    # Gather disputes
    disputes = []
    list_error = None
    if _settings.is_sim:
        cases_dir = Path("data/cases")
        if cases_dir.exists():
            raw = load_cases_from_directory(cases_dir)
            disputes = list(raw)
    else:
        if _live_source is not None:
            live_disputes, list_error = _live_source.list_disputes()
            # Convert to DisputeCase-like wrappers for uniform processing
            disputes = live_disputes

    now = int(time.time())
    total_disputes = len(disputes)
    open_count = 0
    urgent_count = 0
    won_count = 0
    lost_count = 0
    under_review = 0
    total_amount_paise = 0
    won_amount_paise = 0
    lost_amount_paise = 0
    reason_breakdown: dict[str, int] = {}
    approaching_deadline = 0  # within 48 hours

    for d in disputes:
        # Handle both DisputeCase (sim) and RazorpayDispute (live) objects
        disp = d.dispute if hasattr(d, "dispute") else d
        st_val = getattr(disp.status, "value", str(disp.status))
        amount = disp.amount

        total_amount_paise += amount

        if st_val == "open":
            open_count += 1
            respond_by = disp.respond_by
            if respond_by and 0 < (respond_by - now) <= 48 * 3600:
                approaching_deadline += 1
                urgent_count += 1
        elif st_val == "won":
            won_count += 1
            won_amount_paise += amount
        elif st_val == "lost":
            lost_count += 1
            lost_amount_paise += amount
        elif st_val == "under_review":
            under_review += 1

        # Reason breakdown
        rc = disp.reason_code if hasattr(disp, "reason_code") else "unknown"
        reason_breakdown[rc] = reason_breakdown.get(rc, 0) + 1

    # Draft metrics
    drafts_dir = _drafts_dir()
    drafts_pending_review = 0
    if drafts_dir.exists():
        for f in drafts_dir.glob("*_result.json"):
            drafts_pending_review += 1

    # Win rate calculation (only if we have outcomes)
    resolved = won_count + lost_count
    win_rate = round(won_count / resolved * 100, 1) if resolved > 0 else None

    return {
        "total_disputes": total_disputes,
        "open_disputes": open_count,
        "urgent_disputes": urgent_count,
        "approaching_deadline": approaching_deadline,
        "under_review": under_review,
        "won": won_count,
        "lost": lost_count,
        "drafts_pending_review": drafts_pending_review,
        "total_amount_paise": total_amount_paise,
        "won_amount_paise": won_amount_paise,
        "lost_amount_paise": lost_amount_paise,
        "win_rate_percent": win_rate,
        "reason_breakdown": reason_breakdown,
        "data_mode": _settings.data_mode,
        "has_llm": _settings.has_llm,
        "list_error": list_error,
        "has_sufficient_data": total_disputes > 0,
    }


# ---------------------------------------------------------------------------
# Disputes list
# ---------------------------------------------------------------------------

@router.get("/disputes")
async def api_list_disputes(
    request: Request,
    page: int = 1,
    per_page: int = 25,
    status_filter: str | None = None,
    reason_filter: str | None = None,
    search: str | None = None,
    sort_by: str = "urgency",
) -> dict[str, Any]:
    """Paginated, filterable dispute list."""
    _require_session(request)

    list_error = None
    if _settings.is_sim:
        cases_dir = Path("data/cases")
        raw_cases = load_cases_from_directory(cases_dir) if cases_dir.exists() else []
        triage_input = list(raw_cases)
        case_map = {c.case_id: c for c in raw_cases}
    else:
        if _live_source is None:
            raise HTTPException(status_code=503, detail="Razorpay not configured.")
        live_disputes, list_error = _live_source.list_disputes()
        triage_input = [_triage_dict(d) for d in live_disputes]
        case_map = {}

    triage_items = triage_cases(triage_input) if triage_input else []

    items = []
    drafts_dir = _drafts_dir()

    for idx, t in enumerate(triage_items, start=1):
        case_obj = case_map.get(t.case_id)
        disp_id = case_obj.dispute.id if case_obj else (t.case_id if not _settings.is_sim else f"disp_{t.case_id}")
        amount = t.amount_paise
        reason = t.reason_class.value if isinstance(t.reason_class, ReasonClass) else str(t.reason_class)

        # Recommendation from cache
        cached = drafts_dir / f"{t.case_id}_result.json"
        rec_decision = "contest"
        rec_uncertain = False
        if cached.exists():
            try:
                data = json.loads(cached.read_text(encoding="utf-8"))
                rec_data = data.get("recommendation", {})
                rec_decision = rec_data.get("decision", "contest")
                rec_uncertain = bool(rec_data.get("is_uncertain", False))
            except (json.JSONDecodeError, OSError):
                pass
        else:
            if 0.35 <= t.p_win <= 0.55:
                rec_uncertain = True
            elif t.p_win < 0.50:
                rec_decision = "accept"

        item = {
            "rank": idx,
            "case_id": t.case_id,
            "dispute_id": disp_id,
            "amount_paise": amount,
            "amount_display": f"₹{amount / 100:,.2f}",
            "urgency": t.urgency,
            "hours_remaining": round(t.hours_remaining or 0.0, 1),
            "reason_class": reason,
            "p_win": round(t.p_win, 3),
            "recommendation": {
                "decision": rec_decision,
                "is_uncertain": rec_uncertain,
            },
            "has_analysis": cached.exists(),
        }

        # Apply filters
        if status_filter and status_filter != "all":
            if status_filter == "analyzed" and not cached.exists():
                continue
            if status_filter == "pending" and cached.exists():
                continue

        if reason_filter and reason_filter != "all" and reason != reason_filter:
            continue

        if search:
            s = search.lower()
            if s not in t.case_id.lower() and s not in disp_id.lower() and s not in reason.lower():
                continue

        items.append(item)

    # Pagination
    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = items[start:end]

    return {
        "items": paginated,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "list_error": list_error,
    }


def _triage_dict(d) -> dict[str, Any]:
    dump = d.model_dump()
    dump["reason_code"] = " ".join(x for x in (d.reason_code, d.reason_description) if x)
    return {"case_id": d.id, "dispute": dump}


# ---------------------------------------------------------------------------
# Dispute detail
# ---------------------------------------------------------------------------

@router.get("/disputes/{case_id}")
async def api_dispute_detail(request: Request, case_id: str) -> dict[str, Any]:
    """Full dispute detail with analysis results."""
    _require_session(request)

    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    try:
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    # Deadline info
    dl = calculate_deadline(case.dispute.model_dump())
    respond_by_dt = (
        datetime.datetime.fromtimestamp(case.dispute.respond_by, tz=datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        if case.dispute.respond_by
        else "N/A"
    )

    # Check for cached analysis
    result_path = _drafts_dir() / f"{case_id}_result.json"
    if result_path.exists():
        try:
            analysis = json.loads(result_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # Evidence requirements
    rc = analysis.get("evidence_report", {}).get("reason_class", "unclassified") if analysis else "unclassified"
    requirements = get_requirements_for_class(rc)

    # Evidence locker docs (live mode)
    locker_docs = []
    if not _settings.is_sim and _locker:
        for doc in _locker.list_for_dispute(case.dispute.id):
            locker_docs.append({
                "id": doc.id,
                "category": doc.category,
                "file_name": doc.file_name,
                "mime": doc.mime,
                "size": doc.size,
                "uploaded_by": doc.uploaded_by,
                "created_at": doc.created_at,
                "razorpay_doc_id": doc.razorpay_doc_id,
            })

    # Safety findings
    safety_findings = []
    protected_ids = {
        case.order.id if case.order else "",
        case.dispute.id,
        case.dispute.payment_id,
        case.order.tracking_number if case.order else "",
    }
    known_names = [case.order.customer_name] if case.order and case.order.customer_name else []

    for doc in case.documents:
        ingest_res = ingest_document(
            doc.content or "",
            case_id=case.case_id,
            known_names=known_names,
            protected_ids=protected_ids,
        )
        safety_findings.append({
            "doc_id": doc.doc_id,
            "doc_type": doc.doc_type,
            "file_name": doc.file_name,
            "card_count": len([f for f in ingest_res.findings if f.type == "card_number"]),
            "injection_count": len(ingest_res.injection_flags),
            "pii_count": len(ingest_res.vault),
        })

    return {
        "case_id": case.case_id,
        "dispute": case.dispute.model_dump(),
        "order": case.order.model_dump() if case.order else None,
        "refund": case.refund.model_dump() if case.refund else None,
        "documents": [d.model_dump() for d in case.documents],
        "metadata": case.metadata,
        "deadline": {
            "urgency": dl.urgency.value,
            "hours_remaining": round(dl.hours_remaining or 0.0, 1),
            "respond_by": respond_by_dt,
        },
        "analysis": analysis,
        "requirements": requirements,
        "evidence_locker": locker_docs,
        "evidence_categories": list(EVIDENCE_CATEGORIES),
        "safety_findings": safety_findings,
        "actionable": _is_actionable(case),
        "data_mode": _settings.data_mode,
        "data_gaps": case.metadata.get("data_gaps", []),
    }


# ---------------------------------------------------------------------------
# AI Analysis
# ---------------------------------------------------------------------------

@router.post("/disputes/{case_id}/analyze")
async def api_analyze_dispute(request: Request, case_id: str) -> dict[str, Any]:
    """Trigger AI analysis pipeline for a dispute."""
    session = _require_session(request)
    _require_csrf(request, session)

    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    try:
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    try:
        if _settings.is_sim:
            result = process_case(case_id=case_id, gateway=_gateway)
        else:
            result = process_case(
                case_id=case_id,
                gateway=_require_gateway(),
                llm_client=_llm_client,
                case=case,
                drafts_dir=_drafts_dir(),
                push_draft=_settings.push_draft_on_process,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Analysis failed for %s", case_id)
        raise HTTPException(
            status_code=502,
            detail=f"Analysis failed ({type(exc).__name__}). Check LLM configuration.",
        ) from exc

    record_audit_event(
        case_id=case_id,
        action="ai_analysis",
        actor=session["user"],
        details={"recommendation": result.recommendation.model_dump()},
    )

    return {
        "case_id": case_id,
        "status": "completed",
        "recommendation": result.recommendation.model_dump(),
        "evidence_report": result.evidence_report.model_dump(),
        "verifier_report": result.verifier_report.model_dump(),
        "clean_draft": result.clean_draft.model_dump(),
    }


# ---------------------------------------------------------------------------
# Draft management
# ---------------------------------------------------------------------------

class SaveDraftRequest(BaseModel):
    summary: str
    csrf_token: str


@router.post("/disputes/{case_id}/draft")
async def api_save_draft(request: Request, case_id: str, body: SaveDraftRequest) -> dict[str, Any]:
    """Save edited rebuttal draft."""
    session = _require_session(request)
    _require_csrf(request, session, body.csrf_token)

    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    try:
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    import httpx
    try:
        _require_gateway().contest_dispute(
            dispute_id=case.dispute.id,
            action="draft",
            summary=body.summary if _settings.is_sim else short_summary(body.summary),
        )
    except (httpx.HTTPError, ValueError) as err:
        raise _upstream_error(err) from err

    record_audit_event(
        case_id=case_id,
        action="save_draft",
        actor=session["user"],
        details={"summary_length": len(body.summary)},
    )

    return {"case_id": case_id, "status": "saved"}


# ---------------------------------------------------------------------------
# Approval workflow
# ---------------------------------------------------------------------------

class SubmitContestRequest(BaseModel):
    approval_token: str
    payload_hash: str
    csrf_token: str


class RequestAcceptRequest(BaseModel):
    typed_amount: str
    csrf_token: str


class AcceptDisputeRequest(BaseModel):
    approval_token: str
    payload_hash: str
    csrf_token: str


@router.post("/disputes/{case_id}/request-approval")
async def api_request_approval(request: Request, case_id: str) -> dict[str, Any]:
    """Issue approval token for contest submission."""
    session = _require_session(request)
    _require_csrf(request, session)

    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    try:
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    _ensure_actionable(case)

    result_path = _drafts_dir() / f"{case_id}_result.json"
    if not result_path.exists():
        raise HTTPException(status_code=400, detail="Analysis must be run before requesting approval.")

    result_data = json.loads(result_path.read_text(encoding="utf-8"))

    result = CaseProcessingResult.model_validate(result_data)
    clean_markdown = result.clean_draft.to_markdown()

    if not _settings.is_sim:
        _ensure_letter_uploaded(case, clean_markdown, session["user"])

    payload = _build_contest_payload(case, clean_markdown)
    payload_hash = compute_contest_payload_hash(payload)

    token = _approval_service.issue_token(
        dispute_id=case.dispute.id,
        action="submit",
        payload=payload,
        approver=session["user"],
    )

    return {
        "approval_token": token,
        "payload_hash": payload_hash,
        "payload": payload,
        "dispute_id": case.dispute.id,
    }


@router.post("/disputes/{case_id}/submit")
async def api_submit_contest(request: Request, case_id: str, body: SubmitContestRequest) -> dict[str, Any]:
    """Submit rebuttal contest to Razorpay with human approval token."""
    session = _require_session(request)
    _require_csrf(request, session, body.csrf_token)

    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    if not body.approval_token:
        raise HTTPException(status_code=400, detail="Approval token is required.")

    try:
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    _ensure_actionable(case)

    result_path = _drafts_dir() / f"{case_id}_result.json"
    if not result_path.exists():
        raise HTTPException(status_code=400, detail="Case analysis results not found.")

    result_data = json.loads(result_path.read_text(encoding="utf-8"))


    result = CaseProcessingResult.model_validate(result_data)
    clean_markdown = result.clean_draft.to_markdown()
    payload = _build_contest_payload(case, clean_markdown)

    expected_hash = compute_contest_payload_hash(payload)
    if body.payload_hash != expected_hash:
        raise HTTPException(
            status_code=400,
            detail="Payload hash mismatch. The content submitted does not match the approved payload.",
        )

    import httpx
    try:
        if _settings.is_sim:
            updated = _require_gateway().contest_dispute(
                dispute_id=case.dispute.id,
                action="submit",
                summary=clean_markdown,
                approval_token=body.approval_token,
            )
        else:
            evidence = {k: v for k, v in payload.items() if k not in ("action", "summary")}
            updated = _require_gateway().contest_dispute(
                dispute_id=case.dispute.id,
                action="submit",
                summary=payload["summary"],
                evidence=evidence,
                approval_token=body.approval_token,
            )
    except ApprovalRequired as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except (httpx.HTTPError, ValueError) as err:
        raise _upstream_error(err) from err

    if _live_source is not None:
        _live_source.invalidate()

    token_hash = hashlib.sha256(body.approval_token.encode("utf-8")).hexdigest()
    record_audit_event(
        case_id=case_id,
        action="submit_contest",
        actor=session["user"],
        details={
            "payload_hash": body.payload_hash,
            "approval_token_hash": token_hash,
            "razorpay_status": updated.status.value,
        },
    )

    return {
        "case_id": case_id,
        "status": updated.status.value,
        "message": f"Contest submitted to Razorpay. Dispute status: {updated.status.value}",
    }


@router.post("/disputes/{case_id}/request-accept")
async def api_request_accept(request: Request, case_id: str, body: RequestAcceptRequest) -> dict[str, Any]:
    """Verify typed amount and issue approval token bound to acceptance payload."""
    session = _require_session(request)
    _require_csrf(request, session, body.csrf_token)

    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    typed = body.typed_amount.strip()
    if not typed:
        raise HTTPException(status_code=400, detail="Dispute amount must be typed to confirm acceptance.")

    try:
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    _ensure_actionable(case)

    cleaned_input = typed.replace("₹", "").replace(",", "").strip()
    try:
        input_val = float(cleaned_input)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid amount entered: '{typed}'. Please enter a valid number.",
        )

    expected_rupees = case.dispute.amount / 100.0
    if abs(input_val - expected_rupees) > 0.01 and abs(input_val - case.dispute.amount) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Amount mismatch. You typed ₹{input_val:.2f}, but dispute amount is ₹{expected_rupees:.2f}.",
        )

    payload_hash = compute_accept_payload_hash(case.dispute.id, case.dispute.amount)

    token = _approval_service.issue_token(
        dispute_id=case.dispute.id,
        action="accept",
        amount=case.dispute.amount,
        approver=session["user"],
    )

    return {
        "approval_token": token,
        "payload_hash": payload_hash,
        "amount_rupees": expected_rupees,
        "amount_paise": case.dispute.amount,
        "dispute_id": case.dispute.id,
    }


@router.post("/disputes/{case_id}/accept")
async def api_accept_dispute(request: Request, case_id: str, body: AcceptDisputeRequest) -> dict[str, Any]:
    """Accept dispute liability with human approval token."""
    session = _require_session(request)
    _require_csrf(request, session, body.csrf_token)

    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    if not body.approval_token:
        raise HTTPException(status_code=400, detail="Approval token is required.")

    try:
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    expected_hash = compute_accept_payload_hash(case.dispute.id, case.dispute.amount)
    if body.payload_hash and body.payload_hash != expected_hash:
        raise HTTPException(
            status_code=400,
            detail="Payload hash mismatch. The acceptance request does not match the approved dispute.",
        )

    _ensure_actionable(case)

    import httpx
    try:
        updated = _require_gateway().accept_dispute(
            dispute_id=case.dispute.id,
            approval_token=body.approval_token,
        )
    except ApprovalRequired as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except httpx.HTTPError as err:
        raise _upstream_error(err) from err

    if _live_source is not None:
        _live_source.invalidate()

    token_hash = hashlib.sha256(body.approval_token.encode("utf-8")).hexdigest()
    record_audit_event(
        case_id=case_id,
        action="accept_dispute",
        actor=session["user"],
        details={
            "dispute_id": case.dispute.id,
            "amount": case.dispute.amount,
            "approval_token_hash": token_hash,
            "razorpay_status": updated.status.value,
        },
    )

    return {
        "case_id": case_id,
        "status": updated.status.value,
        "message": f"Dispute accepted. Razorpay status: {updated.status.value}",
    }


# ---------------------------------------------------------------------------
# Evidence upload
# ---------------------------------------------------------------------------

@router.post("/disputes/{case_id}/evidence")
async def api_upload_evidence(
    request: Request,
    case_id: str,
    file: UploadFile = File(...),  # noqa: B008
    category: str = Form(...),
    attest_no_card_data: str = Form(...),
    excerpt: str = Form(""),
    csrf_token: str = Form(""),
) -> dict[str, Any]:
    """Upload evidence file: PCI card scan on excerpt, validation, locker store, Razorpay upload."""
    session = _require_session(request)
    _require_csrf(request, session, csrf_token)

    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    if category not in EVIDENCE_CATEGORIES:
        raise HTTPException(status_code=400, detail="Choose a valid evidence category.")

    if attest_no_card_data.lower() != "yes":
        raise HTTPException(
            status_code=400,
            detail="You must confirm the file contains no card number, CVV or card track data.",
        )

    file_name = Path(str(file.filename or "evidence")).name
    ext = Path(file_name).suffix.lower()
    if ext not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Razorpay accepts only PDF, PNG or JPEG evidence files.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    if _settings and len(data) > _settings.max_upload_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds the {_settings.max_upload_bytes // (1024 * 1024)} MB limit.",
        )

    if not any(data.startswith(sig) for sig in _MAGIC.get(ext, ())):
        raise HTTPException(status_code=400, detail="File content does not match its extension.")

    try:
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    _ensure_actionable(case)

    # Scan any pasted excerpt for card numbers / CVV
    clean_excerpt = excerpt.strip()[:20000]
    if clean_excerpt:
        scan = ingest_document(
            clean_excerpt,
            case_id=case.case_id,
            known_names=[case.order.customer_name] if case.order and case.order.customer_name else [],
            protected_ids={case.order.id if case.order else "", case.dispute.id, case.dispute.payment_id},
        )
        if scan.findings:
            raise HTTPException(
                status_code=400,
                detail="A card number or CVV was detected in the pasted text. Remove it before uploading.",
            )

    digest = hashlib.sha256(data).hexdigest()
    doc_id = None
    if not _settings.is_sim:
        existing = _locker.find_uploaded_by_hash(digest) if _locker else None
        if existing and existing.razorpay_doc_id:
            doc_id = existing.razorpay_doc_id
        else:
            import httpx
            try:
                uploaded = _require_gateway().upload_document(data, file_name, purpose="dispute_evidence")
            except (httpx.HTTPError, ValueError) as err:
                raise _upstream_error(err) from err
            doc_id = str(uploaded.get("id", "")) or None
            if not doc_id:
                raise HTTPException(status_code=502, detail="Razorpay accepted upload but returned no doc ID.")

    if _locker:
        _locker.add(
            dispute_id=case.dispute.id,
            category=category,
            file_name=file_name,
            mime=ALLOWED_MIME[ext],
            size=len(data),
            sha256=digest,
            uploaded_by=session["user"],
            razorpay_doc_id=doc_id,
            excerpt=clean_excerpt or None,
        )

    # Drop cached draft to trigger re-audit on next review
    result_path = _drafts_dir() / f"{case_id}_result.json"
    result_path.unlink(missing_ok=True)

    record_audit_event(
        case_id=case_id,
        action="upload_evidence",
        actor=session["user"],
        details={
            "category": category,
            "file_name": file_name,
            "size": len(data),
            "sha256": digest,
            "razorpay_document_id": doc_id,
            "attested_no_card_data": True,
        },
    )

    return {
        "status": "uploaded",
        "file_name": file_name,
        "category": category,
        "size": len(data),
        "sha256": digest,
        "razorpay_doc_id": doc_id,
    }


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

@router.get("/disputes/{case_id}/audit")
async def api_dispute_audit(request: Request, case_id: str) -> dict[str, Any]:
    """Return audit trail for a specific dispute."""
    _require_session(request)

    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    events = get_audit_events(case_id)

    formatted = []
    for e in events:
        ts = e.get("timestamp", 0)
        formatted.append({
            **e,
            "timestamp_display": datetime.datetime.fromtimestamp(ts, tz=datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC") if ts else "N/A",
        })

    return {
        "case_id": case_id,
        "events": formatted,
        "chain_valid": verify_audit_trail(),
    }


@router.get("/audit")
async def api_list_audit(
    request: Request,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """Global tamper-evident ledger across all dispute cases."""
    _require_session(request)

    offset = (page - 1) * per_page
    events, total = get_all_audit_events(limit=per_page, offset=offset)

    formatted = []
    for e in events:
        ts = e.get("timestamp", 0)
        formatted.append({
            **e,
            "timestamp_display": datetime.datetime.fromtimestamp(ts, tz=datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC") if ts else "N/A",
        })

    return {
        "events": formatted,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "chain_valid": verify_audit_trail(),
    }


@router.get("/audit/verify")
async def api_verify_audit(request: Request) -> dict[str, Any]:
    """Cryptographic audit chain verification endpoint."""
    _require_session(request)
    is_valid = verify_audit_trail()
    return {
        "chain_valid": is_valid,
        "verified_at": int(time.time()),
        "verified_at_display": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "hash_algorithm": "SHA-256",
        "genesis_root": "GENESIS_ROOT_00000000000000000000",
    }


# ---------------------------------------------------------------------------
# Settings & status
# ---------------------------------------------------------------------------

@router.get("/settings")
async def api_settings(request: Request) -> dict[str, Any]:
    """System configuration status (no secrets)."""
    _require_session(request)

    return {
        "data_mode": _settings.data_mode if _settings else "sim",
        "key_mode": _settings.key_mode if _settings else "test",
        "razorpay_base_url": _settings.razorpay_base_url if _settings else "https://api.razorpay.com",
        "has_razorpay": _settings.has_razorpay_credentials if _settings else False,
        "has_llm": _settings.has_llm if _settings else False,
        "has_webhook_secret": bool(_settings.razorpay_webhook_secret) if _settings else False,
        "max_upload_bytes": _settings.max_upload_bytes if _settings else 10 * 1024 * 1024,
        "problems": _razorpay_problems + _auth_problems,
        "evidence_categories": list(EVIDENCE_CATEGORIES),
    }


@router.get("/health")
async def api_health() -> dict[str, Any]:
    """Public health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": int(time.time()),
        "version": "0.2.0",
    }

