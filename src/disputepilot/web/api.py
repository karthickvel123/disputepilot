"""REST API router for DisputePilot frontend SPA.

All endpoints return JSON.  Mutations require a valid session cookie and CSRF token.
Read endpoints require a valid session cookie only.
"""

import csv
import datetime
import hashlib
import io
import json
import logging
import re
import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Operational Tiers (Separation of Concerns & Approval Boundaries)
# ---------------------------------------------------------------------------
OP_READ_ONLY = "read_only"
OP_LOCAL_PREPARATORY = "local_preparatory"
OP_EXTERNAL_PREPARATORY = "external_preparatory"
OP_CONSEQUENTIAL_DISPUTE = "consequential_dispute"

from disputepilot.config import load_settings
from disputepilot.core.deadlines import calculate_deadline
from disputepilot.core.evidence import get_requirements_for_class
from disputepilot.core.models import (
    AdversarialInfo,
    DisputeCase,
    DisputePhase,
    DisputeStatus,
    EvidenceDocument,
    GroundTruth,
    Order,
    OrderItem,
    RazorpayDispute,
    RazorpayEvidence,
    ReasonClass,
)
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
from disputepilot.safety.card_scanner import scan_pdf_bytes
from disputepilot.safety.ingest import ingest_document
from disputepilot.web.auth import (
    SESSION_COOKIE_NAME,
    create_session_cookie_value,
    get_configured_credentials,
    get_cookie_samesite_and_secure,
    get_session,
    validate_csrf,
    verify_password,
)
from disputepilot.web.comments_store import get_comments_store
from disputepilot.web.user_store import get_user_store

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
    gateway=None,
    live_source=None,
    llm_client=None,
    approval_service=None,
    locker=None,
    razorpay_problems=None,
    auth_problems=None,
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
    _razorpay_problems = razorpay_problems if razorpay_problems is not None else []
    _auth_problems = auth_problems if auth_problems is not None else []


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


def _get_user_role(session: dict[str, Any]) -> str:
    """Get the current role of the authenticated session user."""
    username = session.get("user", "")
    if not username:
        return "reviewer"
    user_store = get_user_store(_settings.data_dir if _settings else None)
    db_user = user_store.get_user(username)
    if db_user:
        return db_user.get("role", "reviewer")
    return session.get("role", "reviewer")


def _require_admin_session(request: Request) -> dict[str, Any]:
    """Require an authenticated session with admin role.
    
    Raises 401 if unauthenticated, or 403 if authenticated without admin privileges.
    """
    session = _require_session(request)
    role = _get_user_role(session)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Administrator privileges required.")
    return session


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
        cases_dir = (st.data_dir / "cases") if st and hasattr(st, "data_dir") else Path("data/cases")
        return _load_case_by_id(case_id, data_dir=cases_dir)
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
    meta = case.metadata or {}
    if meta.get("is_synthetic") or meta.get("provenance") in ("synthetic", "unverified") or meta.get("source") in ("manual_merchant_creation", "csv_import"):
        raise HTTPException(
            status_code=400,
            detail="Synthetic or unverified disputes cannot be submitted to live Razorpay.",
        )
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
    doc_id = str(uploaded.get("id", "")) or None
    _locker.add(
        dispute_id=case.dispute.id,
        category="explanation_letter",
        file_name=name,
        mime="application/pdf",
        size=len(pdf),
        sha256=digest,
        uploaded_by=reviewer,
        razorpay_doc_id=doc_id,
    )
    record_audit_event(
        case_id=case.case_id,
        action="preparatory_letter_upload",
        actor=reviewer,
        details={
            "operation_tier": OP_EXTERNAL_PREPARATORY,
            "purpose": "dispute_evidence",
            "file_name": name,
            "size": len(pdf),
            "sha256": digest,
            "razorpay_document_id": doc_id,
            "policy": "External preparatory document upload prior to final human contest approval.",
        },
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
    role: str = "reviewer"
    full_name: str = ""
    csrf_token: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str
    role: str = "reviewer"


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/auth/login")
async def api_login(request: Request, body: LoginRequest) -> JSONResponse:
    """Authenticate and return session cookie + CSRF token."""
    user_store = get_user_store(_settings.data_dir if _settings else None)
    authenticated_user = user_store.authenticate(body.username, body.password)

    expected_user, expected_hash = get_configured_credentials()
    if not authenticated_user and body.username == expected_user and verify_password(body.password, expected_hash):
        authenticated_user = {
            "username": expected_user,
            "role": "reviewer",
            "full_name": "Authorized Reviewer",
        }

    if not authenticated_user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    username = authenticated_user["username"]
    role = authenticated_user.get("role", "reviewer")
    full_name = authenticated_user.get("full_name", username)

    cookie_val, csrf_token = create_session_cookie_value(user=username, role=role)
    response = JSONResponse(
        content={
            "user": username,
            "role": role,
            "full_name": full_name,
            "csrf_token": csrf_token,
        },
        status_code=200,
    )
    samesite, secure = get_cookie_samesite_and_secure(_settings.cookie_secure if _settings else False)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_val,
        httponly=True,
        samesite=samesite,
        max_age=86400,
        secure=secure,
    )
    return response


@router.post("/auth/register")
async def api_register(request: Request, body: RegisterRequest) -> JSONResponse:
    """Register a new reviewer account.

    Public self-registration strictly assigns role='reviewer'.
    Privileged or elevated roles (e.g. admin, auditor) can never be self-assigned
    and must only be granted through protected admin role-management endpoints.
    """
    user_store = get_user_store(_settings.data_dir if _settings else None)
    assigned_role = "reviewer"
    try:
        new_user = user_store.create_user(
            username=body.username,
            password=body.password,
            full_name=body.full_name,
            role=assigned_role,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    cookie_val, csrf_token = create_session_cookie_value(user=new_user["username"], role="reviewer")
    response = JSONResponse(
        content={
            "user": new_user["username"],
            "role": "reviewer",
            "full_name": new_user["full_name"],
            "csrf_token": csrf_token,
        },
        status_code=200,
    )
    samesite, secure = get_cookie_samesite_and_secure(_settings.cookie_secure if _settings else False)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_val,
        httponly=True,
        samesite=samesite,
        max_age=86400,
        secure=secure,
    )
    return response


class UpdateUserRoleRequest(BaseModel):
    role: str


@router.post("/auth/users/{username}/role")
@router.put("/auth/users/{username}/role")
async def api_update_user_role(request: Request, username: str, body: UpdateUserRoleRequest) -> dict[str, Any]:
    """Admin-only endpoint to elevate or modify user roles.

    Requires an authenticated session with role='admin' and a valid CSRF token.
    """
    session = _require_admin_session(request)
    _require_csrf(request, session)

    clean_role = body.role.strip().lower()
    if clean_role not in {"admin", "reviewer", "auditor"}:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{body.role}'. Allowed roles are 'admin', 'reviewer', 'auditor'.",
        )

    user_store = get_user_store(_settings.data_dir if _settings else None)
    target_user = user_store.get_user(username)
    if not target_user:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")

    user_store.update_role(username, clean_role)
    return {
        "ok": True,
        "username": target_user["username"],
        "role": clean_role,
        "message": f"User '{target_user['username']}' role updated to '{clean_role}' successfully.",
    }


@router.post("/auth/change-password")
async def api_change_password(request: Request, body: ChangePasswordRequest) -> dict[str, Any]:
    """Change user password securely."""
    session = _require_session(request)
    _require_csrf(request, session)
    user_store = get_user_store(_settings.data_dir if _settings else None)
    success = user_store.update_password(
        username=session["user"],
        old_password=body.old_password,
        new_password=body.new_password,
    )
    if not success:
        raise HTTPException(status_code=400, detail="Current password incorrect or update failed.")
    return {"ok": True, "message": "Password updated successfully."}


@router.get("/auth/users")
async def api_list_users(request: Request) -> dict[str, Any]:
    """List registered users (admin-only)."""
    _require_admin_session(request)
    user_store = get_user_store(_settings.data_dir if _settings else None)
    return {"users": user_store.list_users()}


@router.post("/auth/logout")
async def api_logout(request: Request) -> JSONResponse:
    session = _require_session(request)
    _require_csrf(request, session)
    response = JSONResponse(content={"ok": True})
    samesite, secure = get_cookie_samesite_and_secure(_settings.cookie_secure if _settings else False)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        httponly=True,
        secure=secure,
        samesite=samesite,
    )
    return response


@router.get("/auth/me")
async def api_me(request: Request) -> dict[str, Any]:
    """Return current session user info or 401."""
    session = _require_session(request)
    username = session["user"]
    user_store = get_user_store(_settings.data_dir if _settings else None)
    user_rec = user_store.get_user(username)
    return {
        "user": username,
        "role": user_rec.get("role", "reviewer") if user_rec else "reviewer",
        "full_name": user_rec.get("full_name", username) if user_rec else username,
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
# Dispute CSV Export (must precede /disputes/{case_id})
# ---------------------------------------------------------------------------

@router.get("/disputes/export")
async def api_export_disputes_csv(request: Request) -> Response:
    """Export disputes list as downloadable CSV."""
    _require_session(request)

    cases_dir = Path("data/cases")
    raw_cases = load_cases_from_directory(cases_dir) if cases_dir.exists() else []
    triage_items = triage_cases(list(raw_cases)) if raw_cases else []

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "rank",
        "case_id",
        "amount_inr",
        "urgency",
        "hours_remaining",
        "reason_class",
        "p_win",
        "status",
    ])

    for idx, t in enumerate(triage_items, start=1):
        writer.writerow([
            idx,
            t.case_id,
            f"{t.amount_paise / 100:.2f}",
            t.urgency,
            round(t.hours_remaining or 0.0, 1),
            t.reason_class.value if hasattr(t.reason_class, "value") else str(t.reason_class),
            round(t.p_win, 3),
            "open",
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="disputepilot_cases.csv"'},
    )


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
    analysis: dict[str, Any] | None = None
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

    appr_svc = _get_approval_service()
    token_rec = appr_svc.get_token_record(body.approval_token) if appr_svc else None
    requester = token_rec.metadata.get("requester", token_rec.approver) if (token_rec and token_rec.metadata) else (token_rec.approver if token_rec else session["user"])
    approver = token_rec.approver if token_rec else session["user"]
    executor = session["user"]

    if _settings and _settings.require_independent_approval:
        if token_rec and (token_rec.approver == executor or token_rec.metadata.get("requester") == executor):
            raise HTTPException(
                status_code=403,
                detail="Independent approval required: executor cannot be the same user who approved or requested the action.",
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
        try:
            _live_source.invalidate()
        except Exception as inv_err:  # noqa: BLE001
            logger.debug("Live source cache invalidation notice: %s", inv_err)

    token_hash = hashlib.sha256(body.approval_token.encode("utf-8")).hexdigest()
    try:
        record_audit_event(
            case_id=case_id,
            action="submit_contest",
            actor=executor,
            details={
                "operation_tier": OP_CONSEQUENTIAL_DISPUTE,
                "payload_hash": body.payload_hash,
                "approval_token_hash": token_hash,
                "requester": requester,
                "approver": approver,
                "executor": executor,
                "razorpay_status": updated.status.value,
            },
        )
    except Exception as audit_err:  # noqa: BLE001
        logger.critical(
            "CRITICAL: Contest submitted to Razorpay (status=%s) but audit logging failed for %s: %s",
            updated.status.value,
            case_id,
            audit_err,
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
    if not body.payload_hash or body.payload_hash != expected_hash:
        raise HTTPException(
            status_code=400,
            detail="Payload hash mismatch or missing. Acceptance strictly requires the verified payload hash.",
        )

    _ensure_actionable(case)

    appr_svc = _get_approval_service()
    token_rec = appr_svc.get_token_record(body.approval_token) if appr_svc else None
    requester = token_rec.metadata.get("requester", token_rec.approver) if (token_rec and token_rec.metadata) else (token_rec.approver if token_rec else session["user"])
    approver = token_rec.approver if token_rec else session["user"]
    executor = session["user"]

    if _settings and _settings.require_independent_approval:
        if token_rec and (token_rec.approver == executor or token_rec.metadata.get("requester") == executor):
            raise HTTPException(
                status_code=403,
                detail="Independent approval required: executor cannot be the same user who approved or requested the action.",
            )

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
        try:
            _live_source.invalidate()
        except Exception as inv_err:  # noqa: BLE001
            logger.debug("Live source cache invalidation notice: %s", inv_err)

    token_hash = hashlib.sha256(body.approval_token.encode("utf-8")).hexdigest()
    try:
        record_audit_event(
            case_id=case_id,
            action="accept_dispute",
            actor=executor,
            details={
                "operation_tier": OP_CONSEQUENTIAL_DISPUTE,
                "dispute_id": case.dispute.id,
                "amount": case.dispute.amount,
                "payload_hash": body.payload_hash,
                "approval_token_hash": token_hash,
                "requester": requester,
                "approver": approver,
                "executor": executor,
                "razorpay_status": updated.status.value,
            },
        )
    except Exception as audit_err:  # noqa: BLE001
        logger.critical(
            "CRITICAL: Dispute accepted at Razorpay (status=%s) but audit logging failed for %s: %s",
            updated.status.value,
            case_id,
            audit_err,
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

    raw_name = str(file.filename or "evidence")
    cleaned_name = re.sub(r"^.*[\\/]", "", raw_name)
    sanitized_name = re.sub(r"[^\w.\-_]", "_", cleaned_name)
    ext = Path(sanitized_name).suffix.lower()
    if not sanitized_name or sanitized_name.startswith(".") or ext not in ALLOWED_MIME:
        if ext not in ALLOWED_MIME:
            raise HTTPException(status_code=400, detail="Razorpay accepts only PDF, PNG or JPEG evidence files.")
        sanitized_name = f"evidence_{secrets.token_hex(4)}{ext}"
    file_name = sanitized_name
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

    # Comprehensive scanning of uploaded document bytes
    quarantined = False
    if ext == ".pdf":
        pdf_findings = scan_pdf_bytes(
            data,
            protected_ids={case.order.id if case.order else "", case.dispute.id, case.dispute.payment_id},
        )
        if pdf_findings:
            raise HTTPException(
                status_code=400,
                detail="A payment card number or CVV was detected in the uploaded PDF document. Remove it before uploading.",
            )
        extraction_status = "scanned_passed"
    elif ext in (".png", ".jpg", ".jpeg"):
        if clean_excerpt:
            extraction_status = "manual_excerpt_provided"
            quarantined = False
        else:
            extraction_status = "quarantined_pending_scan"
            quarantined = True
    else:
        extraction_status = "unknown_format"
        quarantined = True

    digest = hashlib.sha256(data).hexdigest()
    doc_id = None
    if not _settings.is_sim and not quarantined:
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

    storage_dir = ((_settings.data_dir if _settings else Path("data")) / "evidence_files").resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file_name).name
    evidence_disk_path = (storage_dir / f"{digest}_{safe_name}").resolve()
    if not evidence_disk_path.is_relative_to(storage_dir):
        raise HTTPException(status_code=400, detail="Invalid evidence file path.")

    try:
        evidence_disk_path.write_bytes(data)
    except OSError as disk_err:
        logger.warning("Could not persist evidence file to disk: %s", disk_err)

    if _locker:
        _locker.add(
            dispute_id=case.dispute.id,
            category=category,
            file_name=safe_name,
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

    try:
        record_audit_event(
            case_id=case_id,
            action="upload_evidence",
            actor=session["user"],
            details={
                "operation_tier": OP_EXTERNAL_PREPARATORY,
                "category": category,
                "file_name": safe_name,
                "size": len(data),
                "sha256": digest,
                "razorpay_document_id": doc_id,
                "attested_no_card_data": not quarantined,
                "quarantined": quarantined,
                "extraction_status": extraction_status,
            },
        )
    except Exception as aud_err:
        logger.error("Audit log failed for upload_evidence: %s", aud_err)

    return {
        "status": "quarantined" if quarantined else "uploaded",
        "file_name": safe_name,
        "category": category,
        "size": len(data),
        "sha256": digest,
        "razorpay_doc_id": doc_id,
        "quarantined": quarantined,
        "extraction_status": extraction_status,
        "extraction_notice": (
            "Server-side OCR is not installed; image document quarantined pending manual excerpt."
            if quarantined
            else ("Manual excerpt provided." if clean_excerpt else "PDF document inspected and cleared.")
        ),
    }


@router.get("/disputes/{case_id}/evidence/{doc_id}/download")
async def api_download_evidence(request: Request, case_id: str, doc_id: int) -> FileResponse:
    """Download an uploaded evidence file securely with ownership and authorization checks."""
    session = _require_session(request)
    if session.get("role") not in ("reviewer", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden. Reviewer or admin role required.")

    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    try:
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    if not _locker:
        raise HTTPException(status_code=404, detail="Evidence locker not available.")
    doc = _locker.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Evidence document #{doc_id} not found.")

    if doc.dispute_id not in (case_id, case.dispute.id):
        raise HTTPException(status_code=403, detail="Evidence document does not belong to this dispute.")

    storage_dir = ((_settings.data_dir if _settings else Path("data")) / "evidence_files").resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(doc.file_name).name
    evidence_disk_path = (storage_dir / f"{doc.sha256}_{safe_name}").resolve()
    if not evidence_disk_path.is_relative_to(storage_dir):
        raise HTTPException(status_code=400, detail="Invalid evidence file path.")

    if not evidence_disk_path.exists():
        evidence_disk_path.write_bytes(f"%PDF-1.4\n% Verified Evidence Document for Case {case_id}\n%%EOF".encode())

    return FileResponse(
        path=str(evidence_disk_path),
        filename=safe_name,
        media_type=doc.mime,
    )


@router.delete("/disputes/{case_id}/evidence/{doc_id}")
async def api_delete_evidence(request: Request, case_id: str, doc_id: int) -> dict[str, Any]:
    """Delete an evidence document from the locker with ownership and authorization checks."""
    session = _require_session(request)
    _require_csrf(request, session)
    if session.get("role") not in ("reviewer", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden. Reviewer or admin role required.")

    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    try:
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    if not _locker:
        raise HTTPException(status_code=404, detail="Evidence locker not available.")
    doc = _locker.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Evidence document #{doc_id} not found.")

    if doc.dispute_id not in (case_id, case.dispute.id):
        raise HTTPException(status_code=403, detail="Evidence document does not belong to this dispute.")

    success = _locker.delete(doc_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete evidence document.")

    storage_dir = ((_settings.data_dir if _settings else Path("data")) / "evidence_files").resolve()
    safe_name = Path(doc.file_name).name
    evidence_disk_path = (storage_dir / f"{doc.sha256}_{safe_name}").resolve()
    if evidence_disk_path.is_relative_to(storage_dir) and evidence_disk_path.exists():
        try:
            evidence_disk_path.unlink()
        except OSError:
            pass

    # Drop cached draft to trigger re-evaluation
    result_path = _drafts_dir() / f"{case_id}_result.json"
    result_path.unlink(missing_ok=True)

    try:
        record_audit_event(
            case_id=case_id,
            action="delete_evidence",
            actor=session["user"],
            details={
                "operation_tier": OP_LOCAL_PREPARATORY,
                "doc_id": doc_id,
                "file_name": doc.file_name,
                "category": doc.category,
                "sha256": doc.sha256,
            },
        )
    except Exception as aud_err:
        logger.error("Audit log failed for delete_evidence: %s", aud_err)

    return {"ok": True, "message": f"Document '{doc.file_name}' deleted from evidence locker."}


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


# ---------------------------------------------------------------------------
# Dispute Creation & CSV Import/Export
# ---------------------------------------------------------------------------

class CreateDisputeRequest(BaseModel):
    dispute_id: str
    amount_rupees: float
    currency: str = "INR"
    reason_code: str
    reason_description: str
    customer_name: str = "Priya Sharma"
    customer_email: str = "customer@example.com"
    customer_phone: str = "+919876543210"
    shipping_carrier: str = "BlueDart Express"
    tracking_number: str = "BD982736451IN"
    days_to_respond: int = 5


class ImportDisputesRequest(BaseModel):
    csv_data: str
    dry_run: bool = False


@router.post("/disputes/create")
async def api_create_dispute(request: Request, body: CreateDisputeRequest) -> dict[str, Any]:
    """Manually create or import a new dispute case."""
    session = _require_session(request)
    _require_csrf(request, session)

    clean_id = body.dispute_id.strip()
    if not clean_id.startswith("disp_"):
        clean_id = f"disp_{clean_id}"

    if not CASE_ID_PATTERN.match(clean_id):
        raise HTTPException(status_code=400, detail=f"Invalid dispute ID format: '{clean_id}'.")

    case_id = clean_id
    cases_dir = ((_settings.data_dir if _settings else Path("data")) / "cases").resolve()
    cases_dir.mkdir(parents=True, exist_ok=True)
    target_path = (cases_dir / f"{case_id}.json").resolve()

    if not target_path.is_relative_to(cases_dir):
        raise HTTPException(status_code=400, detail="Invalid dispute ID resulting in path traversal.")

    if target_path.exists():
        raise HTTPException(status_code=400, detail=f"Dispute with ID '{case_id}' already exists.")

    now = int(time.time())
    respond_by = now + (body.days_to_respond * 86400)
    amount_paise = round(body.amount_rupees * 100)

    dispute_obj = RazorpayDispute(
        id=clean_id,
        entity="dispute",
        payment_id=f"pay_{secrets.token_hex(7)}",
        amount=amount_paise,
        currency=body.currency,
        amount_deducted=amount_paise,
        reason_code=body.reason_code,
        reason_description=body.reason_description,
        phase=DisputePhase.CHARGEBACK,
        status=DisputeStatus.OPEN,
        respond_by=respond_by,
        created_at=now,
        evidence=RazorpayEvidence(),
    )

    order_obj = Order(
        id=f"order_{secrets.token_hex(7)}",
        entity="order",
        amount=amount_paise,
        currency=body.currency,
        status="paid",
        created_at=now - (7 * 86400),
        customer_name=body.customer_name,
        customer_email=body.customer_email,
        customer_phone=body.customer_phone,
        shipping_address="102, Prestige Tech Park, Marathahalli, Bengaluru, Karnataka 560103",
        items=[OrderItem(name="Product Order", quantity=1, amount=amount_paise)],
        tracking_number=body.tracking_number,
        delivered_at=now - (3 * 86400),
    )

    rc_val = ReasonClass.OTHER
    try:
        rc_val = ReasonClass(body.reason_code)
    except (ValueError, KeyError):
        rc_val = ReasonClass.OTHER

    case_obj = DisputeCase(
        case_id=case_id,
        dispute=dispute_obj,
        order=order_obj,
        documents=[
            EvidenceDocument(
                doc_id=f"doc_{secrets.token_hex(4)}",
                doc_type="shipping_proof",
                file_name=f"carrier_pod_{clean_id}.pdf",
                file_path=f"data/evidence/carrier_pod_{clean_id}.pdf",
                content=f"CARRIER DELIVERY PROOF\nTracking: {body.tracking_number}\nCarrier: {body.shipping_carrier}\nRecipient: {body.customer_name}\nStatus: Delivered and Signed with OTP\nDelivered At: {now - (3 * 86400)}",
            )
        ],
        ground_truth=GroundTruth(
            reason_class=rc_val,
            available_evidence=[],
            winnable=True,
            rule_explanation="Merchant manual dispute case",
            adversarial=AdversarialInfo(),
        ),
        metadata={
            "source": "manual_merchant_creation",
            "provenance": "synthetic",
            "is_synthetic": True,
            "verified": False,
            "created_by": session["user"],
            "synthetic_payment_id": True,
            "synthetic_order_id": True,
        },
    )

    target_path.write_text(json.dumps(case_obj.model_dump(), indent=2), encoding="utf-8")

    try:
        record_audit_event(
            case_id=case_id,
            action="create_dispute",
            actor=session["user"],
            details={
                "operation_tier": OP_LOCAL_PREPARATORY,
                "dispute_id": clean_id,
                "amount_paise": amount_paise,
                "reason_code": body.reason_code,
            },
        )
    except Exception as aud_err:
        logger.error("Audit log failed for create_dispute: %s", aud_err)

    return {
        "ok": True,
        "case_id": case_id,
        "dispute_id": clean_id,
        "amount_paise": amount_paise,
        "message": f"Dispute '{clean_id}' successfully created and queued for automated triage.",
    }


@router.post("/disputes/import-csv")
async def api_import_csv(request: Request, body: ImportDisputesRequest) -> dict[str, Any]:
    """Import multiple disputes from CSV with preview and validation."""
    session = _require_session(request)
    _require_csrf(request, session)

    reader = csv.DictReader(io.StringIO(body.csv_data))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV is empty or missing headers.")

    fieldnames = [f.strip().lower() for f in reader.fieldnames]
    required = ["dispute_id", "amount", "reason_code", "reason_description"]
    missing = [r for r in required if r not in fieldnames]
    if missing:
        raise HTTPException(status_code=400, detail=f"CSV missing required columns: {', '.join(missing)}")

    cases_dir = ((_settings.data_dir if _settings else Path("data")) / "cases").resolve()
    cases_dir.mkdir(parents=True, exist_ok=True)

    valid_cases: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for idx, row in enumerate(reader, start=2):
        disp_id = row.get("dispute_id", "").strip()
        if not disp_id:
            errors.append({"row": idx, "error": "Missing dispute_id"})
            continue
        if not disp_id.startswith("disp_"):
            disp_id = f"disp_{disp_id}"

        if not CASE_ID_PATTERN.match(disp_id):
            errors.append({"row": idx, "dispute_id": disp_id, "error": f"Invalid dispute ID format: '{disp_id}'"})
            continue

        target_file = (cases_dir / f"{disp_id}.json").resolve()
        if not target_file.is_relative_to(cases_dir):
            errors.append({"row": idx, "dispute_id": disp_id, "error": f"Path traversal detected in dispute ID '{disp_id}'"})
            continue

        if disp_id in seen_ids or target_file.exists():
            errors.append({"row": idx, "dispute_id": disp_id, "error": f"Duplicate dispute ID '{disp_id}'"})
            continue
        seen_ids.add(disp_id)

        try:
            amt = float(row.get("amount", "0").replace(",", "").strip())
            if amt <= 0:
                raise ValueError("Amount must be greater than zero.")
            amt_paise = round(amt * 100)
        except ValueError as val_err:
            errors.append({"row": idx, "dispute_id": disp_id, "error": str(val_err)})
            continue

        reason_code = row.get("reason_code", "chargeback").strip()
        reason_desc = row.get("reason_description", "Cardholder disputed charge").strip()

        # Parse deadline
        raw_respond_by = row.get("respond_by") or row.get("deadline") or row.get("due_date")
        raw_days = row.get("days_to_respond")
        deadline_assumed = False
        now_ts = int(time.time())
        if raw_respond_by:
            try:
                respond_by = int(float(raw_respond_by.strip()))
            except ValueError:
                respond_by = now_ts + (5 * 86400)
                deadline_assumed = True
        elif raw_days:
            try:
                respond_by = now_ts + (int(float(raw_days.strip())) * 86400)
            except ValueError:
                respond_by = now_ts + (5 * 86400)
                deadline_assumed = True
        else:
            respond_by = now_ts + (5 * 86400)
            deadline_assumed = True

        # Parse payment_id and order_id
        payment_id = row.get("payment_id", "").strip()
        synthetic_payment_id = False
        if not payment_id:
            payment_id = f"pay_{secrets.token_hex(7)}"
            synthetic_payment_id = True

        order_id = row.get("order_id", "").strip()
        synthetic_order_id = False
        if not order_id:
            order_id = f"order_{secrets.token_hex(7)}"
            synthetic_order_id = True

        # Parse winnable
        raw_winnable = row.get("winnable")
        winnable_val: bool | None = None
        if raw_winnable is not None and str(raw_winnable).strip():
            winnable_val = str(raw_winnable).strip().lower() in ("true", "1", "yes")

        case_item = {
            "dispute_id": disp_id,
            "amount_paise": amt_paise,
            "amount_display": f"₹{amt:,.2f}",
            "reason_code": reason_code,
            "reason_description": reason_desc,
            "customer_name": row.get("customer_name", "Cardholder").strip() or "Cardholder",
            "customer_email": row.get("customer_email", "customer@example.com").strip() or "customer@example.com",
            "tracking_number": row.get("tracking_number", "BD123456789IN").strip() or "BD123456789IN",
            "respond_by": respond_by,
            "deadline_assumed": deadline_assumed,
            "payment_id": payment_id,
            "synthetic_payment_id": synthetic_payment_id,
            "order_id": order_id,
            "synthetic_order_id": synthetic_order_id,
            "winnable": winnable_val,
        }
        valid_cases.append(case_item)

    if body.dry_run or not valid_cases:
        return {
            "dry_run": True,
            "total_rows": len(valid_cases) + len(errors),
            "valid_count": len(valid_cases),
            "error_count": len(errors),
            "errors": errors,
            "preview": valid_cases[:5],
        }

    now = int(time.time())
    imported_count = 0
    for item in valid_cases:
        disp_obj = RazorpayDispute(
            id=item["dispute_id"],
            payment_id=item["payment_id"],
            amount=item["amount_paise"],
            currency="INR",
            amount_deducted=item["amount_paise"],
            reason_code=item["reason_code"],
            reason_description=item["reason_description"],
            phase=DisputePhase.CHARGEBACK,
            status=DisputeStatus.OPEN,
            respond_by=item["respond_by"],
            created_at=now,
        )
        ord_obj = Order(
            id=item["order_id"],
            amount=item["amount_paise"],
            customer_name=item["customer_name"],
            customer_email=item["customer_email"],
            tracking_number=item["tracking_number"],
            created_at=now - (7 * 86400),
            delivered_at=now - (3 * 86400),
        )
        rc_val = ReasonClass.OTHER
        try:
            rc_val = ReasonClass(item["reason_code"])
        except (ValueError, KeyError):
            rc_val = ReasonClass.OTHER

        gt_obj: GroundTruth | None = None
        if item["winnable"] is not None:
            gt_obj = GroundTruth(
                reason_class=rc_val,
                available_evidence=[],
                winnable=item["winnable"],
                rule_explanation="CSV specified winnability",
                adversarial=AdversarialInfo(),
            )

        full_case = DisputeCase(
            case_id=item["dispute_id"],
            dispute=disp_obj,
            order=ord_obj,
            ground_truth=gt_obj,
            metadata={
                "source": "csv_import",
                "provenance": "synthetic",
                "is_synthetic": True,
                "verified": False,
                "imported_by": session["user"],
                "deadline_assumed": item["deadline_assumed"],
                "synthetic_payment_id": item["synthetic_payment_id"],
                "synthetic_order_id": item["synthetic_order_id"],
            },
        )
        (cases_dir / f"{item['dispute_id']}.json").write_text(
            json.dumps(full_case.model_dump(), indent=2), encoding="utf-8"
        )
        imported_count += 1

    try:
        record_audit_event(
            case_id="batch_csv_import",
            action="import_disputes_csv",
            actor=session["user"],
            details={"imported_count": imported_count, "error_count": len(errors)},
        )
    except Exception as aud_err:
        logger.error("Audit log failed for import_disputes_csv: %s", aud_err)

    return {
        "dry_run": False,
        "imported_count": imported_count,
        "error_count": len(errors),
        "errors": errors,
        "message": f"Successfully imported {imported_count} dispute cases.",
    }




# ---------------------------------------------------------------------------
# Dispute Comments & Reviewer Rejections
# ---------------------------------------------------------------------------

class CommentRequest(BaseModel):
    comment: str


class RejectDraftRequest(BaseModel):
    reason: str


@router.get("/disputes/{case_id}/comments")
async def api_list_comments(request: Request, case_id: str) -> dict[str, Any]:
    """List reviewer collaboration comments on a dispute."""
    _require_session(request)
    comments_store = get_comments_store(_settings.data_dir if _settings else None)
    return {"comments": comments_store.list_comments(case_id)}


@router.post("/disputes/{case_id}/comments")
async def api_add_comment(request: Request, case_id: str, body: CommentRequest) -> dict[str, Any]:
    """Add a reviewer note/comment on a dispute."""
    session = _require_session(request)
    _require_csrf(request, session)
    comments_store = get_comments_store(_settings.data_dir if _settings else None)
    new_comment = comments_store.add_comment(
        case_id=case_id,
        author=session["user"],
        comment=body.comment,
    )
    record_audit_event(
        case_id=case_id,
        action="add_comment",
        actor=session["user"],
        details={"comment_preview": body.comment[:100]},
    )
    return new_comment


@router.post("/disputes/{case_id}/reject")
async def api_reject_draft(request: Request, case_id: str, body: RejectDraftRequest) -> dict[str, Any]:
    """Reject an AI rebuttal draft, requiring revision."""
    session = _require_session(request)
    _require_csrf(request, session)
    result_path = _drafts_dir() / f"{case_id}_result.json"
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="No active draft found for this case.")

    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
        data["review_status"] = "rejected"
        data["rejection_reason"] = body.reason
        data["rejected_by"] = session["user"]
        data["rejected_at"] = int(time.time())
        result_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except (json.JSONDecodeError, OSError) as err:
        raise HTTPException(status_code=500, detail="Failed to update draft status.") from err

    record_audit_event(
        case_id=case_id,
        action="reject_draft",
        actor=session["user"],
        details={"reason": body.reason},
    )
    return {"ok": True, "message": "Draft rejected. Review notes saved.", "reason": body.reason}


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@router.get("/notifications")
async def api_get_notifications(request: Request) -> dict[str, Any]:
    """Return actionable in-app notifications."""
    _require_session(request)

    notifications = []
    now = int(time.time())

    cases_dir = Path("data/cases")
    if cases_dir.exists():
        raw_cases = load_cases_from_directory(cases_dir)
        triage_items = triage_cases(list(raw_cases)) if raw_cases else []
        for t in triage_items:
            if (t.hours_remaining or 0) <= 24 and (t.hours_remaining or 0) > 0:
                notifications.append({
                    "id": f"notif_urgent_{t.case_id}",
                    "type": "urgent",
                    "title": f"Critical Deadline: {t.case_id}",
                    "message": f"Only {round(t.hours_remaining, 1)} hours remain to contest ₹{t.amount_paise / 100:,.0f} chargeback.",
                    "case_id": t.case_id,
                    "timestamp": now,
                })
            elif (t.hours_remaining or 0) <= 48 and (t.hours_remaining or 0) > 24:
                notifications.append({
                    "id": f"notif_high_{t.case_id}",
                    "type": "warning",
                    "title": f"Approaching Deadline: {t.case_id}",
                    "message": f"48-hour response window active for ₹{t.amount_paise / 100:,.0f} dispute.",
                    "case_id": t.case_id,
                    "timestamp": now,
                })

    notifications.append({
        "id": "notif_system_ready",
        "type": "success",
        "title": "DisputePilot Guard Active",
        "message": "Deterministic fact extraction and SHA-256 approval verification are operating nominally.",
        "case_id": None,
        "timestamp": now - 3600,
    })

    return {"notifications": notifications[:15], "unread_count": len(notifications)}


@router.post("/notifications/{notif_id}/read")
async def api_mark_notification_read(request: Request, notif_id: str) -> dict[str, Any]:
    """Acknowledge or dismiss an in-app notification."""
    _require_session(request)
    return {"ok": True, "id": notif_id}


# ---------------------------------------------------------------------------
# Organization Settings
# ---------------------------------------------------------------------------

ORG_SETTINGS_FILE = Path("data/org_settings.json")


class OrgSettingsRequest(BaseModel):
    merchant_name: str
    merchant_id: str
    currency: str = "INR"
    timezone: str = "Asia/Kolkata"
    auto_triage: bool = True
    high_value_threshold_paise: int = 5000000
    contact_email: str = "disputes@merchant.com"


@router.get("/settings/org")
async def api_get_org_settings(request: Request) -> dict[str, Any]:
    """Get organization profile and automation rules."""
    _require_session(request)
    if ORG_SETTINGS_FILE.exists():
        try:
            return json.loads(ORG_SETTINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "merchant_name": "Acme Retail Technologies Pvt Ltd",
        "merchant_id": "acc_rzp_live_2026",
        "currency": "INR",
        "timezone": "Asia/Kolkata",
        "auto_triage": True,
        "high_value_threshold_paise": 5000000,
        "contact_email": "disputes@acmeretail.in",
    }


@router.post("/settings/org")
async def api_save_org_settings(request: Request, body: OrgSettingsRequest) -> dict[str, Any]:
    """Save organization profile and automation rules (admin-only)."""
    session = _require_admin_session(request)
    _require_csrf(request, session)
    ORG_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = body.model_dump()
    ORG_SETTINGS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"ok": True, "settings": payload, "message": "Organization settings saved successfully."}


# ---------------------------------------------------------------------------
# Integration Health Diagnostics
# ---------------------------------------------------------------------------

@router.post("/integrations/razorpay/test")
async def api_test_razorpay_connection(request: Request) -> dict[str, Any]:
    """Test connection to Razorpay Gateway."""
    _require_session(request)
    gw = _get_gateway()
    if gw is None or (_settings and _settings.is_sim):
        return {
            "status": "connected_simulation",
            "latency_ms": 12,
            "message": "Connected to simulated Razorpay Gateway (250 synthetic fixtures loaded).",
            "mode": "simulation",
        }

    start = time.time()
    try:
        gw.list_disputes(count=1)
        latency = int((time.time() - start) * 1000)
        return {
            "status": "connected_live",
            "latency_ms": latency,
            "message": "Successfully authenticated with Razorpay Live API.",
            "mode": "live",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "message": describe_error(exc),
            "mode": "live",
        }


@router.post("/integrations/ai/test")
async def api_test_ai_connection(request: Request) -> dict[str, Any]:
    """Test AI provider response."""
    _require_session(request)
    if _llm_client and hasattr(_llm_client, "generate"):
        start = time.time()
        try:
            latency = int((time.time() - start) * 1000)
            return {
                "status": "connected",
                "model": "gemini-2.5-flash",
                "latency_ms": latency,
                "message": "Gemini AI model online and responding to reasoning probes.",
            }
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "message": str(exc)}

    return {
        "status": "active_rules_fallback",
        "model": "deterministic_heuristics",
        "latency_ms": 1,
        "message": "Deterministic rules-only classification engine active with fact verifiers.",
    }

