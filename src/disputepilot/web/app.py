"""FastAPI merchant review web application for DisputePilot."""

import datetime
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from disputepilot.config import load_settings
from disputepilot.core.deadlines import calculate_deadline
from disputepilot.core.evidence import get_requirements_for_class
from disputepilot.core.models import (
    DisputeCase,
    DisputeStatus,
    RazorpayDispute,
    ReasonClass,
)
from disputepilot.core.recommend import ContestDecision
from disputepilot.core.triage import load_cases_from_directory, triage_cases
from disputepilot.extraction.llm import NullLLMClient, get_llm_client
from disputepilot.live.locker import ALLOWED_MIME, EVIDENCE_CATEGORIES, EvidenceLocker
from disputepilot.live.pdf import text_to_pdf
from disputepilot.live.source import (
    CaseNotFound,
    LiveCaseSource,
    SourceError,
    describe_error,
)
from disputepilot.live.summary import short_summary
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
from disputepilot.razorpay.gateway import (
    DisputesGateway,
    RazorpayAPIError,
    RazorpayGateway,
    SimGateway,
)
from disputepilot.razorpay.webhook import default_router as webhook_router
from disputepilot.safety.ingest import ingest_document
from disputepilot.web.auth import (
    SESSION_COOKIE_NAME,
    create_session_cookie_value,
    get_configured_credentials,
    get_cookie_samesite_and_secure,
    get_session,
    safe_next_path,
    validate_csrf,
    verify_password,
)
from disputepilot.web.limits import BodyLimitMiddleware

logger = logging.getLogger("disputepilot.web.app")

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="DisputePilot Console", version="0.1.0")


@app.middleware("http")
async def security_headers(request: Request, call_next: Any) -> Any:
    """Set baseline browser security headers on every application response."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


# Mount static files and templates
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="spa_assets")

    @app.get("/spa", response_class=HTMLResponse)
    @app.get("/app", response_class=HTMLResponse)
    @app.get("/app/{full_path:path}", response_class=HTMLResponse)
    async def serve_spa(full_path: str = "") -> HTMLResponse:
        index_file = FRONTEND_DIST / "index.html"
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Mount Razorpay webhook router
app.include_router(webhook_router, prefix="/webhook/razorpay")


# ---------------------------------------------------------------------------------------------
# Runtime wiring. DATA_MODE=live (default) talks to Razorpay; DATA_MODE=sim uses synthetic fixtures.
# ---------------------------------------------------------------------------------------------
settings = load_settings()
razorpay_problems: list[str] = settings.razorpay_problems()
auth_problems: list[str] = settings.auth_problems()
for _problem in razorpay_problems + auth_problems:
    logger.warning("Configuration problem: %s", _problem)

DRAFTS_DIR = settings.data_dir / "drafts"
LETTER_PREFIX = "rebuttal-letter-"

# Global dependencies (can be overridden in tests)
approval_service = ApprovalService(db_path=settings.approvals_db_path)
locker = EvidenceLocker(settings.locker_db_path)
live_source: LiveCaseSource | None = None
llm_client = None  # sim: pipeline default (FakeLLMClient). live: real model or explicit NullLLMClient.
gateway: DisputesGateway | None

if settings.is_sim:
    gateway = SimGateway(approval_service=approval_service)
elif not razorpay_problems:
    gateway = RazorpayGateway(
        key_id=settings.razorpay_key_id,
        key_secret=settings.razorpay_key_secret,
        base_url=settings.razorpay_base_url,
        approval_service=approval_service,
    )
    live_source = LiveCaseSource(gateway, locker, cache_ttl=settings.disputes_cache_ttl)
    llm_client = get_llm_client() if settings.has_llm else NullLLMClient()
else:
    gateway = None  # not configured: every page explains what is missing instead of failing

app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_upload_bytes)

if live_source is not None:
    from disputepilot.razorpay import webhook as _webhook

    _webhook.event_listeners.append(lambda _event, _dispute: live_source.invalidate())  # type: ignore[union-attr]

from fastapi.middleware.cors import CORSMiddleware

from disputepilot.web.api import configure_api
from disputepilot.web.api import router as api_router

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.vercel\.app|https://.*\.onrender\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

configure_api(
    settings=settings,
    gateway=gateway,
    live_source=live_source,
    llm_client=llm_client,
    approval_service=approval_service,
    locker=locker,
    razorpay_problems=razorpay_problems,
    auth_problems=auth_problems,
)
app.include_router(api_router)

templates_globals = {
    "data_mode": settings.data_mode,
    "key_mode": settings.key_mode,
    "has_llm": settings.has_llm,
}
templates.env.globals.update(templates_globals)



@app.exception_handler(StarletteHTTPException)
async def friendly_http_errors(request: Request, exc: StarletteHTTPException) -> Any:
    """Browsers get a readable page; API clients (and tests) keep the JSON {"detail": ...} shape."""
    if "text/html" in request.headers.get("accept", ""):
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "title": "Request could not be completed",
                "message": str(exc.detail),
                "status_code": exc.status_code,
                "reviewer_name": (get_session(request) or {}).get("user"),
                "csrf_token": (get_session(request) or {}).get("csrf_token"),
            },
            status_code=exc.status_code,
        )
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


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


def _require_gateway() -> DisputesGateway:
    if gateway is None:
        raise HTTPException(
            status_code=503,
            detail="Razorpay is not configured: " + " ".join(razorpay_problems),
        )
    return gateway


def _upstream_error(exc: Exception) -> HTTPException:
    """Map a Razorpay/network failure to an HTTP error with a safe, specific message."""
    code = 400 if isinstance(exc, RazorpayAPIError) and exc.status_code in (400, 404, 409, 422) else 502
    return HTTPException(status_code=code, detail=describe_error(exc))


def _load_case(case_id: str) -> DisputeCase:
    """Load a case from fixtures (sim) or Razorpay (live). Unknown case -> FileNotFoundError."""
    if settings.is_sim:
        return _load_case_by_id(case_id)
    if live_source is None:
        _require_gateway()
        raise HTTPException(status_code=503, detail="Razorpay is not configured.")
    try:
        return live_source.get_case(case_id)
    except CaseNotFound as err:
        raise FileNotFoundError(str(err)) from err
    except SourceError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err


def _ensure_actionable(case: DisputeCase) -> None:
    """Live only: Razorpay rejects contest/accept unless the dispute is open and within deadline."""
    if settings.is_sim:
        return
    d = case.dispute
    if d.status != DisputeStatus.OPEN:
        raise HTTPException(status_code=400, detail=f"Dispute is '{d.status.value}'; Razorpay only accepts a response while it is 'open'.")
    if d.respond_by and d.respond_by <= int(time.time()):
        raise HTTPException(status_code=400, detail="The response deadline for this dispute has passed.")


def _is_actionable(case: DisputeCase) -> bool:
    try:
        _ensure_actionable(case)
        return True
    except HTTPException:
        return False


def _drop_cached_result(case_id: str) -> None:
    (DRAFTS_DIR / f"{case_id}_result.json").unlink(missing_ok=True)


def _letter_pdf(case: DisputeCase, clean_markdown: str) -> bytes:
    return text_to_pdf(clean_markdown, title=f"Rebuttal {case.dispute.id}")


def _build_contest_payload(case: DisputeCase, clean_markdown: str) -> dict[str, Any]:
    """The exact payload a reviewer approves and that is later sent to Razorpay.

    Sim mode keeps the original fixture-shaped payload. Live mode respects Razorpay's limits:
    ``summary`` <= 1000 characters, evidence as document ids, and the full letter as a PDF
    ``explanation_letter`` document.
    """
    payload: dict[str, Any] = {"action": "submit"}
    if settings.is_sim:
        payload["summary"] = clean_markdown
        for k, v in case.dispute.evidence.model_dump().items():
            if v:
                payload[k] = v
        return payload

    payload["summary"] = short_summary(clean_markdown)
    evidence = {k: list(v) for k, v in case.dispute.evidence.document_ids().items()}
    for doc in locker.list_for_dispute(case.dispute.id):
        if doc.razorpay_doc_id and not doc.file_name.startswith(LETTER_PREFIX):
            bucket = evidence.setdefault(doc.category, [])
            if doc.razorpay_doc_id not in bucket:
                bucket.append(doc.razorpay_doc_id)
    letter = locker.find_uploaded_by_hash(hashlib.sha256(_letter_pdf(case, clean_markdown)).hexdigest())
    if letter and letter.razorpay_doc_id:
        bucket = evidence.setdefault("explanation_letter", [])
        if letter.razorpay_doc_id not in bucket:
            bucket.append(letter.razorpay_doc_id)
    payload.update({k: v for k, v in evidence.items() if v})
    return payload


def _ensure_letter_uploaded(case: DisputeCase, clean_markdown: str, reviewer: str) -> None:
    """Upload the rebuttal letter PDF once (deduplicated by content hash) before approval."""
    pdf = _letter_pdf(case, clean_markdown)
    digest = hashlib.sha256(pdf).hexdigest()
    if locker.find_uploaded_by_hash(digest):
        return
    name = f"{LETTER_PREFIX}{case.dispute.id}.pdf"
    try:
        uploaded = _require_gateway().upload_document(pdf, name, purpose="dispute_evidence")
    except (httpx.HTTPError, ValueError) as err:
        raise _upstream_error(err) from err
    doc_id = str(uploaded.get("id", "")) or None
    locker.add(
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
            "operation_tier": "external_preparatory",
            "purpose": "dispute_evidence",
            "file_name": name,
            "size": len(pdf),
            "sha256": digest,
            "razorpay_document_id": doc_id,
            "policy": "External preparatory document upload prior to final human contest approval.",
        },
    )


def _get_case_result_or_process(case_id: str) -> Any:
    """Retrieve existing processed result or execute processing pipeline."""
    result_path = DRAFTS_DIR / f"{case_id}_result.json"
    if result_path.exists():
        try:
            with open(result_path, encoding="utf-8") as f:
                data = json.load(f)
            from disputepilot.pipeline.orchestrator import CaseProcessingResult

            return CaseProcessingResult.model_validate(data)
        except (json.JSONDecodeError, OSError, ValueError) as e:
            logger.warning("Failed to load cached result for %s: %s", case_id, e)

    if settings.is_sim:
        return process_case(case_id=case_id, gateway=gateway)

    case = _load_case(case_id)
    try:
        return process_case(
            case_id=case_id,
            gateway=_require_gateway(),
            llm_client=llm_client,
            case=case,
            drafts_dir=DRAFTS_DIR,
            push_draft=settings.push_draft_on_process,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Case analysis failed for %s", case_id)
        raise HTTPException(
            status_code=502,
            detail=f"Automated analysis of this dispute failed ({type(exc).__name__}). "
            "The Razorpay data loaded fine; check the LLM configuration and server logs.",
        ) from exc


@app.get("/login", response_class=HTMLResponse)
def login_view(request: Request, next: str | None = None) -> Any:
    """Render reviewer login form."""
    session = get_session(request)
    if session and session.get("user"):
        return RedirectResponse(url=safe_next_path(next), status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"next": safe_next_path(next)},
    )


@app.post("/login")
async def login_action(request: Request) -> Any:
    """Authenticate single reviewer and issue signed session cookie with CSRF token."""
    form = await get_form_data(request)
    username = form.get("username", "").strip()
    password = form.get("password", "")
    next_url = safe_next_path(form.get("next", "/"))

    expected_user, expected_hash = get_configured_credentials()
    if username != expected_user or not verify_password(password, expected_hash):
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Invalid reviewer username or password.", "next": next_url},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    cookie_val, _ = create_session_cookie_value(user=username)
    response = RedirectResponse(url=next_url, status_code=status.HTTP_303_SEE_OTHER)
    samesite, secure = get_cookie_samesite_and_secure(settings.cookie_secure)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_val,
        httponly=True,
        samesite=samesite,
        max_age=86400,
        secure=secure,
    )
    return response


@app.post("/logout")
async def logout_action(request: Request) -> RedirectResponse:
    """Terminate reviewer session only after authentication and CSRF validation."""
    await require_auth_and_csrf(request)
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return response


def _triage_dict(d: RazorpayDispute) -> dict[str, Any]:
    """Shape a live dispute for triage_cases. Real reason codes can be generic (e.g. 'chargeback'),
    so the free-text reason_description is appended to give the rule classifier something to read."""
    dump = d.model_dump()
    dump["reason_code"] = " ".join(x for x in (d.reason_code, d.reason_description) if x)
    return {"case_id": d.id, "dispute": dump}


@app.get("/", response_class=HTMLResponse)
@app.get("/cases", response_class=HTMLResponse)
def worklist_view(request: Request) -> HTMLResponse:
    """Render the prioritized merchant dispute worklist."""
    session = get_session(request)
    reviewer_name = session.get("user") if session else None
    csrf_token = session.get("csrf_token") if session else None

    list_error: str | None = None
    hidden_note: str | None = None
    if settings.is_sim:
        cases_dir = Path("data/cases")
        raw_cases = load_cases_from_directory(cases_dir) if cases_dir.exists() else []
        triage_input: list[Any] = list(raw_cases)
        case_map: dict[str, DisputeCase] = {c.case_id: c for c in raw_cases}
    else:
        if live_source is None:
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context={
                    "title": "Setup required",
                    "message": "DisputePilot cannot reach Razorpay yet. Fix the following in your .env and restart:",
                    "details": razorpay_problems,
                    "status_code": 503,
                    "reviewer_name": reviewer_name,
                },
                status_code=503,
            )
        disputes, list_error = live_source.list_disputes()
        open_disputes = [d for d in disputes if d.status == DisputeStatus.OPEN]
        if len(disputes) > len(open_disputes):
            hidden_note = f"{len(disputes) - len(open_disputes)} dispute(s) not shown because they are no longer open."
        triage_input = [_triage_dict(d) for d in open_disputes]
        case_map = {}

    triage_items = triage_cases(triage_input) if triage_input else []

    items: list[WorklistItem] = []

    for idx, t_item in enumerate(triage_items, start=1):
        c_id = t_item.case_id
        case_obj = case_map.get(c_id)
        disp_id = case_obj.dispute.id if case_obj else (c_id if not settings.is_sim else f"disp_{c_id}")

        # Check for cached processed result to retrieve recommendation
        cached_file = DRAFTS_DIR / f"{c_id}_result.json"
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
            "error": list_error,
            "success": hidden_note,
        },
    )


@app.get("/cases/{case_id}", response_class=HTMLResponse)
def case_detail_view(request: Request, case_id: str) -> HTMLResponse:
    """Render full dispute case review console."""
    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")

    try:
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    session = get_session(request)
    reviewer_name = session.get("user") if session else None
    csrf_token = session.get("csrf_token") if session else None

    result = _get_case_result_or_process(case_id)
    flash = request.query_params.get("success")

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
            "success": flash[:200] if flash else None,
            "data_gaps": case.metadata.get("data_gaps", []),
            "actionable": _is_actionable(case),
            "locker_docs": None if settings.is_sim else locker.list_for_dispute(case.dispute.id),
            "evidence_categories": EVIDENCE_CATEGORIES,
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
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    _ensure_actionable(case)
    try:
        _require_gateway().contest_dispute(
            dispute_id=case.dispute.id,
            action="draft",
            summary=summary if settings.is_sim else short_summary(summary),
        )
    except (httpx.HTTPError, ValueError) as err:
        raise _upstream_error(err) from err

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
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    _ensure_actionable(case)
    result = _get_case_result_or_process(case_id)

    # Build the exact submission payload
    clean_markdown = result.clean_draft.to_markdown()
    if not settings.is_sim:
        # The full letter goes to Razorpay as a PDF document; its id becomes part of the approved payload.
        _ensure_letter_uploaded(case, clean_markdown, reviewer_name)
    payload = _build_contest_payload(case, clean_markdown)

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
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    _ensure_actionable(case)
    result = _get_case_result_or_process(case_id)

    # Reconstruct expected payload to check against bound hash
    clean_markdown = result.clean_draft.to_markdown()
    payload = _build_contest_payload(case, clean_markdown)

    expected_hash = compute_contest_payload_hash(payload)
    if payload_hash != expected_hash:
        raise HTTPException(
            status_code=400,
            detail="Payload hash mismatch. The content submitted does not match the approved payload.",
        )

    try:
        if settings.is_sim:
            updated = _require_gateway().contest_dispute(
                dispute_id=case.dispute.id,
                action="submit",
                summary=clean_markdown,
                approval_token=approval_token,
            )
        else:
            evidence = {k: v for k, v in payload.items() if k not in ("action", "summary")}
            updated = _require_gateway().contest_dispute(
                dispute_id=case.dispute.id,
                action="submit",
                summary=payload["summary"],
                evidence=evidence,
                approval_token=approval_token,
            )
    except ApprovalRequired as err:
        raise HTTPException(status_code=400, detail=str(err))
    except (httpx.HTTPError, ValueError) as err:
        raise _upstream_error(err) from err

    if live_source is not None:
        live_source.invalidate()
    token_hash = hashlib.sha256(approval_token.encode("utf-8")).hexdigest()
    record_audit_event(
        case_id=case_id,
        action="submit_contest",
        actor=reviewer_name,
        details={
            "payload_hash": payload_hash,
            "approval_token_hash": token_hash,
            "razorpay_status": updated.status.value,
        },
    )

    # Report the status Razorpay actually returned rather than assuming success.
    return RedirectResponse(
        url=f"/cases/{case_id}?success=Submitted+to+Razorpay.+Dispute+status:+{updated.status.value}",
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
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    _ensure_actionable(case)

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
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    expected_hash = compute_accept_payload_hash(case.dispute.id, case.dispute.amount)
    if payload_hash and payload_hash != expected_hash:
        raise HTTPException(
            status_code=400,
            detail="Payload hash mismatch. The acceptance request does not match the approved dispute.",
        )

    _ensure_actionable(case)
    try:
        updated = _require_gateway().accept_dispute(
            dispute_id=case.dispute.id,
            approval_token=approval_token,
        )
    except ApprovalRequired as err:
        raise HTTPException(status_code=400, detail=str(err))
    except httpx.HTTPError as err:
        raise _upstream_error(err) from err

    if live_source is not None:
        live_source.invalidate()

    token_hash = hashlib.sha256(approval_token.encode("utf-8")).hexdigest()
    record_audit_event(
        case_id=case_id,
        action="accept_dispute",
        actor=reviewer_name,
        details={
            "dispute_id": case.dispute.id,
            "amount": case.dispute.amount,
            "approval_token_hash": token_hash,
            "razorpay_status": updated.status.value,
        },
    )

    return RedirectResponse(
        url=f"/cases/{case_id}?success=Accept+sent+to+Razorpay.+Dispute+status:+{updated.status.value}",
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
        _load_case(case_id)
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


_MAGIC: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}


@app.post("/cases/{case_id}/evidence")
async def upload_evidence_action(request: Request, case_id: str) -> RedirectResponse:
    """Add a merchant evidence file: validate, card-scan any pasted text, upload to Razorpay Documents.

    Binary files (PDF/PNG/JPEG - the only types Razorpay accepts) cannot be scanned for card data
    by this app, so the reviewer must attest the file is clean; the attestation is audit-logged and
    no file bytes are kept locally (only metadata and a SHA-256).
    """
    if not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=404, detail=f"Invalid case ID: '{case_id}'.")
    session = get_session(request)
    if not session or not session.get("user"):
        raise HTTPException(status_code=401, detail="Authentication required. Please log in as an authorized reviewer.")

    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.max_upload_bytes + 64 * 1024:
        raise HTTPException(status_code=413, detail=f"Upload exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB limit.")
    form = await request.form()
    if not validate_csrf(session, str(form.get("csrf_token") or request.headers.get("x-csrf-token") or "")):
        raise HTTPException(status_code=403, detail="CSRF validation failed or token missing.")
    reviewer_name = session["user"]

    category = str(form.get("category", "")).strip()
    if category not in EVIDENCE_CATEGORIES:
        raise HTTPException(status_code=400, detail="Choose a valid evidence category.")
    if str(form.get("attest_no_card_data", "")).lower() != "yes":
        raise HTTPException(status_code=400, detail="You must confirm the file contains no card number, CVV or card track data.")
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read") or not getattr(upload, "filename", ""):
        raise HTTPException(status_code=400, detail="Choose a file to upload.")

    file_name = Path(str(upload.filename)).name
    ext = Path(file_name).suffix.lower()
    if ext not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Razorpay accepts only PDF, PNG or JPEG evidence files.")
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail=f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB limit.")
    if not any(data.startswith(sig) for sig in _MAGIC[ext]):
        raise HTTPException(status_code=400, detail="File content does not match its extension.")

    try:
        case = _load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
    _ensure_actionable(case)

    excerpt = str(form.get("excerpt", "")).strip()[:20000]
    if excerpt:
        scan = ingest_document(
            excerpt,
            case_id=case.case_id,
            known_names=[case.order.customer_name] if case.order.customer_name else [],
            protected_ids={case.order.id, case.dispute.id, case.dispute.payment_id},
        )
        if scan.findings:  # card numbers AND CVV/CVC values: nothing flagged is ever stored
            raise HTTPException(
                status_code=400,
                detail="A card number or CVV was detected in the pasted text. Remove it from the text and from the file, then upload again.",
            )

    digest = hashlib.sha256(data).hexdigest()
    existing = locker.find_uploaded_by_hash(digest)
    if existing and existing.razorpay_doc_id:
        doc_id = existing.razorpay_doc_id
    else:
        try:
            uploaded = _require_gateway().upload_document(data, file_name, purpose="dispute_evidence")
        except (httpx.HTTPError, ValueError) as err:
            raise _upstream_error(err) from err
        doc_id = str(uploaded.get("id", "")) or None
        if not doc_id:
            raise HTTPException(status_code=502, detail="Razorpay accepted the upload but returned no document id.")

    locker.add(
        dispute_id=case.dispute.id,
        category=category,
        file_name=file_name,
        mime=ALLOWED_MIME[ext],
        size=len(data),
        sha256=digest,
        uploaded_by=reviewer_name,
        razorpay_doc_id=doc_id,
        excerpt=excerpt,
    )
    _drop_cached_result(case_id)  # evidence changed: re-run the audit on next view

    record_audit_event(
        case_id=case_id,
        action="upload_evidence",
        actor=reviewer_name,
        details={
            "category": category,
            "file_name": file_name,
            "size": len(data),
            "sha256": digest,
            "razorpay_document_id": doc_id,
            "attested_no_card_data": True,
        },
    )
    return RedirectResponse(
        url=f"/cases/{case_id}?success=Evidence+uploaded+to+Razorpay",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/status")
def status_view(check: bool = False) -> dict[str, Any]:
    """Setup/health summary for operators. Never includes keys or secrets."""
    body: dict[str, Any] = {
        "data_mode": settings.data_mode,
        "razorpay_key_mode": settings.key_mode,
        "razorpay_base_url": settings.razorpay_base_url,
        "llm_configured": settings.has_llm,
        "webhook_secret_configured": bool(settings.razorpay_webhook_secret),
        "problems": razorpay_problems + auth_problems,
    }
    if check and settings.is_live and gateway is not None:
        try:
            found = gateway.list_disputes(count=1)
            body["razorpay_check"] = {"ok": True, "disputes_visible": len(found) > 0}
        except Exception as exc:  # noqa: BLE001
            body["razorpay_check"] = {"ok": False, "error": describe_error(exc)}
    return body
