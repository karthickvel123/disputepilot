import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from disputepilot.pipeline.orchestrator import _load_case_by_id, process_case
from disputepilot.razorpay.approval import (
    compute_accept_payload_hash,
    compute_contest_payload_hash,
)
from disputepilot.web.app import app, approval_service, gateway
from disputepilot.web.auth import (
    SESSION_COOKIE_NAME,
    create_session_cookie_value,
    hash_password,
)


@pytest.fixture
def client() -> TestClient:
    """Create FastAPI TestClient."""
    return TestClient(app)


@pytest.fixture
def auth_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, str]:
    """Create authenticated TestClient with reviewer session and valid CSRF token."""
    secret = "test_session_hmac_secret_key_at_least_32_chars_long"
    user = "Priya Sharma"
    pwd_hash = hash_password("password123")
    monkeypatch.setenv("REVIEWER_USER", user)
    monkeypatch.setenv("REVIEWER_PASSWORD_HASH", pwd_hash)
    monkeypatch.setenv("SESSION_SECRET", secret)
    c = TestClient(app)
    cookie_val, csrf_token = create_session_cookie_value(user=user)
    c.cookies.set(SESSION_COOKIE_NAME, cookie_val)
    return c, csrf_token


@pytest.fixture
def sample_case_id() -> str:
    """Ensure at least one sample case is processed and available."""
    c_id = "disp_0001_hbrpoi"
    process_case(case_id=c_id, gateway=gateway)
    return c_id


def test_worklist_page_loads(client: TestClient) -> None:
    """Worklist page must load with HTTP 200 and display triage items."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Dispute Triage Worklist" in response.text
    assert "DisputePilot" in response.text

    response_cases = client.get("/cases")
    assert response_cases.status_code == 200


def test_case_detail_page_loads(client: TestClient, sample_case_id: str) -> None:
    """Case detail page must load with HTTP 200 and display all audit cards."""
    response = client.get(f"/cases/{sample_case_id}")
    assert response.status_code == 200
    assert sample_case_id in response.text
    assert "Recommendation Engine" in response.text
    assert "Evidence Checklist" in response.text
    assert "Rebuttal Letter Draft" in response.text
    assert "Deterministic Verifier Report" in response.text
    assert "Verifier: 0 sentence(s) removed. Remaining sentences cite verified facts." in response.text


def test_case_detail_safety_findings_card_redaction(client: TestClient) -> None:
    """Case detail displays Safety Findings panel with redacted card details and no raw digits."""
    case_id = "disp_0008_6hymqc"
    response = client.get(f"/cases/{case_id}")
    assert response.status_code == 200
    assert "Safety Findings" in response.text
    assert "1 card number redacted" in response.text
    assert "4448" in response.text
    # Ensure no raw 16-digit card number or full prefix is displayed
    assert "4111 2222 3333 4448" not in response.text
    assert "4111222233334448" not in response.text
    assert "4111" not in response.text


def test_case_detail_404_for_unknown_case(client: TestClient) -> None:
    """Unknown case ID returns 404 Not Found."""
    response = client.get("/cases/case_non_existent_999999")
    assert response.status_code == 404


def test_confirm_submit_page_loads(auth_client: tuple[TestClient, str], sample_case_id: str) -> None:
    """Confirm submit page must load from POST and display payload, hash, and approval token."""
    client, csrf = auth_client
    response = client.post(
        f"/cases/{sample_case_id}/review",
        data={"csrf_token": csrf},
    )
    assert response.status_code == 200
    assert "Submission Payload Review" in response.text
    assert "Priya Sharma" in response.text
    assert "appr_" in response.text  # Token issued


def test_confirm_submit_rejects_get(client: TestClient, sample_case_id: str) -> None:
    """Approval token cannot be issued from a GET request (405 Method Not Allowed)."""
    response = client.get(f"/cases/{sample_case_id}/review?reviewer_name=Priya+Sharma")
    assert response.status_code == 405
    response_alias = client.get(f"/cases/{sample_case_id}/confirm-submit?reviewer_name=Priya+Sharma")
    assert response_alias.status_code == 405


def test_submit_without_approval_fails(auth_client: tuple[TestClient, str], sample_case_id: str) -> None:
    """Submitting contest without an approval token must fail with 400."""
    client, csrf = auth_client
    response = client.post(
        f"/cases/{sample_case_id}/submit",
        data={
            "csrf_token": csrf,
            "approval_token": "",
            "payload_hash": "somehash",
        },
    )
    assert response.status_code == 400


def test_submit_with_tampered_payload_hash_fails(auth_client: tuple[TestClient, str], sample_case_id: str) -> None:
    """Submitting with a mismatched payload hash must fail."""
    client, csrf = auth_client
    token = approval_service.issue_token(
        dispute_id="disp_test",
        action="submit",
        payload_hash="fakehash123",
        approver="Priya Sharma",
    )

    response = client.post(
        f"/cases/{sample_case_id}/submit",
        data={
            "csrf_token": csrf,
            "approval_token": token,
            "payload_hash": "tampered_fake_hash",
        },
    )
    assert response.status_code == 400
    assert "mismatch" in response.text.lower()


def test_submit_with_valid_approval_succeeds(auth_client: tuple[TestClient, str], sample_case_id: str) -> None:
    """Submitting with a valid, bound approval token succeeds and redirects."""
    client, csrf = auth_client
    post_review_resp = client.post(
        f"/cases/{sample_case_id}/review",
        data={"csrf_token": csrf},
    )
    assert post_review_resp.status_code == 200

    # Extract clean draft to get exact payload hash
    case = _load_case_by_id(sample_case_id)
    result = process_case(case_id=sample_case_id, gateway=gateway)
    clean_markdown = result.clean_draft.to_markdown()
    payload = {"action": "submit", "summary": clean_markdown}
    ev_dump = case.dispute.evidence.model_dump()
    for k, v in ev_dump.items():
        if v:
            payload[k] = v
    valid_hash = compute_contest_payload_hash(payload)

    valid_token = approval_service.issue_token(
        dispute_id=case.dispute.id,
        action="submit",
        payload=payload,
        approver="Priya Sharma",
    )

    post_resp = client.post(
        f"/cases/{sample_case_id}/submit",
        data={
            "csrf_token": csrf,
            "approval_token": valid_token,
            "payload_hash": valid_hash,
        },
        follow_redirects=False,
    )
    assert post_resp.status_code == 303
    assert "success=" in post_resp.headers["location"]


def test_accept_two_step_flow_succeeds(auth_client: tuple[TestClient, str], sample_case_id: str) -> None:
    """Accepting a dispute is a two-step flow: review shows confirm page & issues token, then accept consumes it."""
    client, csrf = auth_client
    case = _load_case_by_id(sample_case_id)
    correct_rupees = case.dispute.amount / 100.0

    # Step 1: POST /accept-review
    review_resp = client.post(
        f"/cases/{sample_case_id}/accept-review",
        data={
            "csrf_token": csrf,
            "typed_amount": f"₹ {correct_rupees:.2f}",
        },
    )
    assert review_resp.status_code == 200
    assert "Dispute Acceptance Review" in review_resp.text
    assert "appr_" in review_resp.text

    # Step 2: POST /accept with token
    expected_hash = compute_accept_payload_hash(case.dispute.id, case.dispute.amount)
    token = approval_service.issue_token(
        dispute_id=case.dispute.id,
        action="accept",
        amount=case.dispute.amount,
        approver="Priya Sharma",
    )
    good_resp = client.post(
        f"/cases/{sample_case_id}/accept",
        data={
            "csrf_token": csrf,
            "approval_token": token,
            "payload_hash": expected_hash,
        },
        follow_redirects=False,
    )
    assert good_resp.status_code == 303
    assert "success=" in good_resp.headers["location"]


def test_accept_without_token_fails(auth_client: tuple[TestClient, str], sample_case_id: str) -> None:
    """POST /cases/{case_id}/accept without an approval token fails with 400."""
    client, csrf = auth_client
    resp = client.post(
        f"/cases/{sample_case_id}/accept",
        data={"csrf_token": csrf, "approval_token": ""},
    )
    assert resp.status_code == 400


def test_accept_with_token_for_different_dispute_fails(
    auth_client: tuple[TestClient, str], sample_case_id: str
) -> None:
    """Accepting with a token issued for a different dispute ID fails with 400."""
    client, csrf = auth_client
    diff_token = approval_service.issue_token(
        dispute_id="disp_other_999999",
        action="accept",
        amount=50000,
        approver="Priya Sharma",
    )
    resp = client.post(
        f"/cases/{sample_case_id}/accept",
        data={"csrf_token": csrf, "approval_token": diff_token},
    )
    assert resp.status_code == 400


def test_accept_with_reused_token_fails(auth_client: tuple[TestClient, str], sample_case_id: str) -> None:
    """Reusing an approval token for acceptance fails with 400."""
    client, csrf = auth_client
    case = _load_case_by_id(sample_case_id)
    token = approval_service.issue_token(
        dispute_id=case.dispute.id,
        action="accept",
        amount=case.dispute.amount,
        approver="Priya Sharma",
    )
    # First acceptance succeeds
    r1 = client.post(
        f"/cases/{sample_case_id}/accept",
        data={"csrf_token": csrf, "approval_token": token},
        follow_redirects=False,
    )
    assert r1.status_code == 303

    # Second acceptance with same token fails
    r2 = client.post(
        f"/cases/{sample_case_id}/accept",
        data={"csrf_token": csrf, "approval_token": token},
    )
    assert r2.status_code == 400


def test_accept_review_requires_typed_amount(auth_client: tuple[TestClient, str], sample_case_id: str) -> None:
    """Accept review rejects mismatched or missing typed amount."""
    client, csrf = auth_client

    # Wrong amount
    bad_resp = client.post(
        f"/cases/{sample_case_id}/accept-review",
        data={
            "csrf_token": csrf,
            "typed_amount": "999999.00",
        },
    )
    assert bad_resp.status_code == 400
    assert "Amount mismatch" in bad_resp.text

    # Missing amount
    missing_resp = client.post(
        f"/cases/{sample_case_id}/accept-review",
        data={"csrf_token": csrf, "typed_amount": ""},
    )
    assert missing_resp.status_code == 400


def test_post_without_login_fails(client: TestClient, sample_case_id: str) -> None:
    """Every mutating POST route strictly requires a reviewer login session (401)."""
    routes = [
        f"/cases/{sample_case_id}/save-draft",
        f"/cases/{sample_case_id}/review",
        f"/cases/{sample_case_id}/confirm-submit",
        f"/cases/{sample_case_id}/submit",
        f"/cases/{sample_case_id}/accept-review",
        f"/cases/{sample_case_id}/accept",
        f"/cases/{sample_case_id}/needs-evidence",
    ]
    for r in routes:
        resp = client.post(r, data={"summary": "test", "reviewer_name": "attacker"})
        assert resp.status_code == 401, f"Route {r} failed to reject unauthenticated POST"


def test_post_without_csrf_fails(client: TestClient, sample_case_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Logged in reviewer POSTing without valid CSRF token strictly fails with 403."""
    secret = "test_session_hmac_secret_key_at_least_32_chars_long"
    user = "Priya Sharma"
    pwd_hash = hash_password("password123")
    monkeypatch.setenv("REVIEWER_USER", user)
    monkeypatch.setenv("REVIEWER_PASSWORD_HASH", pwd_hash)
    monkeypatch.setenv("SESSION_SECRET", secret)

    cookie_val, _ = create_session_cookie_value(user=user)
    client.cookies.set(SESSION_COOKIE_NAME, cookie_val)

    # Missing CSRF
    r1 = client.post(f"/cases/{sample_case_id}/save-draft", data={"summary": "test"})
    assert r1.status_code == 403

    # Tampered CSRF
    r2 = client.post(
        f"/cases/{sample_case_id}/save-draft",
        data={"summary": "test", "csrf_token": "tampered_fake_token"},
    )
    assert r2.status_code == 403


def test_login_and_logout_flow(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reviewer authentication flow sets signed session cookie and terminates on logout."""
    secret = "test_session_hmac_secret_key_at_least_32_chars_long"
    user = "reviewer"
    pwd = "password123"
    pwd_hash = hash_password(pwd)
    monkeypatch.setenv("REVIEWER_USER", user)
    monkeypatch.setenv("REVIEWER_PASSWORD_HASH", pwd_hash)
    monkeypatch.setenv("SESSION_SECRET", secret)

    # Invalid password
    bad_login = client.post(
        "/login",
        data={"username": "reviewer", "password": "wrong_password"},
    )
    assert bad_login.status_code == 401

    # Valid credentials
    good_login = client.post(
        "/login",
        data={"username": "reviewer", "password": "password123"},
        follow_redirects=False,
    )
    assert good_login.status_code == 303
    assert SESSION_COOKIE_NAME in good_login.cookies

    # Logout
    logout_resp = client.get("/logout", follow_redirects=False)
    assert logout_resp.status_code == 303


def test_save_draft_and_needs_evidence_actions(
    auth_client: tuple[TestClient, str], sample_case_id: str
) -> None:
    """Saving draft and flagging needs-evidence succeed and redirect."""
    client, csrf = auth_client
    r_draft = client.post(
        f"/cases/{sample_case_id}/save-draft",
        data={"csrf_token": csrf, "summary": "Custom merchant drafted text."},
        follow_redirects=False,
    )
    assert r_draft.status_code == 303

    r_ev = client.post(
        f"/cases/{sample_case_id}/needs-evidence",
        data={"csrf_token": csrf, "note": "Awaiting customer cancellation log."},
        follow_redirects=False,
    )
    assert r_ev.status_code == 303


def test_case_id_validation_returns_404(client: TestClient, auth_client: tuple[TestClient, str]) -> None:
    """case_id must be validated against ^[a-zA-Z0-9_]+$ and return 404 for invalid IDs, including '../x'."""
    c, csrf = auth_client

    # Traversal test with '../x'
    r_trav = client.get("/cases/../x")
    assert r_trav.status_code == 404

    # Invalid characters in case ID
    r_inv = client.get("/cases/disp!invalid_chars")
    assert r_inv.status_code == 404

    # POST route with invalid case ID
    r_post = c.post(
        "/cases/../x/save-draft",
        data={"csrf_token": csrf, "summary": "draft"},
    )
    assert r_post.status_code == 404

    # _load_case_by_id raises FileNotFoundError for invalid formats
    with pytest.raises(FileNotFoundError):
        _load_case_by_id("../x")

    with pytest.raises(FileNotFoundError):
        _load_case_by_id("invalid/id")


def test_unclassified_case_shows_visible_banner(client: TestClient) -> None:
    """When a case has an unclassified reason, the case page displays a visible warning banner."""
    import json
    from pathlib import Path

    case_path = Path("data/cases/disp_0001_hbrpoi.json")
    if not case_path.exists():
        pytest.skip("data/cases not populated")
    with open(case_path, encoding="utf-8") as f:
        case_dict = json.load(f)
    case_dict["case_id"] = "disp_unclass_test"
    case_dict["dispute"]["reason_code"] = "RANDOM_UNRECOGNIZED_REASON_9999"
    test_case_file = Path("data/cases/disp_unclass_test.json")
    with open(test_case_file, "w", encoding="utf-8") as f:
        json.dump(case_dict, f)

    try:
        # Clear any cached draft
        draft_file = Path("data/drafts/disp_unclass_test_result.json")
        if draft_file.exists():
            draft_file.unlink()

        response = client.get("/cases/disp_unclass_test")
        assert response.status_code == 200
        assert 'id="unclassified-banner"' in response.text
        assert "Reason Could Not Be Classified" in response.text
        assert "reason could not be classified" in response.text
        # Assert p_win and expected value are rendered as 'n/a', not 0.0 or ₹0
        assert ">n/a</div>" in response.text
    finally:
        if test_case_file.exists():
            test_case_file.unlink()
        draft_file = Path("data/drafts/disp_unclass_test_result.json")
        if draft_file.exists():
            draft_file.unlink()


def test_login_rejected_when_auth_env_unset(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """When auth env vars are unset or empty, login is rejected (401/403) and no Set-Cookie is issued."""
    monkeypatch.delenv("REVIEWER_USER", raising=False)
    monkeypatch.delenv("REVIEWER_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)

    resp = client.post(
        "/login",
        data={"username": "reviewer", "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code in (401, 403)
    assert SESSION_COOKIE_NAME not in resp.cookies
    assert "set-cookie" not in resp.headers


def test_forged_cookie_rejected_when_auth_env_unset(
    client: TestClient, sample_case_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With all three auth env vars unset, a cookie forged with the old constant secret is rejected on POST (401)."""
    monkeypatch.delenv("REVIEWER_USER", raising=False)
    monkeypatch.delenv("REVIEWER_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)

    old_secret = b"disputepilot_session_hmac_secret_key_2026"
    payload = {
        "user": "attacker",
        "csrf_token": "forged_csrf_token_1234567890",
        "created_at": int(time.time()),
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii")
    sig = hmac.new(old_secret, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    forged_cookie = f"{payload_b64}.{sig}"

    client.cookies.set(SESSION_COOKIE_NAME, forged_cookie)
    resp = client.post(
        f"/cases/{sample_case_id}/needs-evidence",
        data={"csrf_token": "forged_csrf_token_1234567890", "note": "malicious POST"},
    )
    assert resp.status_code == 401


def test_wrong_password_rejected_and_correct_password_accepted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wrong password is rejected with 401; correct password is accepted with 303 and session cookie."""
    secret = "secure_test_session_secret_key_with_at_least_32_characters"
    user = "alice_reviewer"
    pwd = "CorrectHorseBatteryStaple99!"
    pwd_hash = hash_password(pwd)
    monkeypatch.setenv("REVIEWER_USER", user)
    monkeypatch.setenv("REVIEWER_PASSWORD_HASH", pwd_hash)
    monkeypatch.setenv("SESSION_SECRET", secret)

    # Wrong password
    bad_pwd = client.post(
        "/login",
        data={"username": user, "password": "WrongPassword123!"},
        follow_redirects=False,
    )
    assert bad_pwd.status_code == 401
    assert SESSION_COOKIE_NAME not in bad_pwd.cookies

    # Wrong username
    bad_user = client.post(
        "/login",
        data={"username": "wrong_username", "password": pwd},
        follow_redirects=False,
    )
    assert bad_user.status_code == 401
    assert SESSION_COOKIE_NAME not in bad_user.cookies

    # Correct password
    good_pwd = client.post(
        "/login",
        data={"username": user, "password": pwd},
        follow_redirects=False,
    )
    assert good_pwd.status_code == 303
    assert SESSION_COOKIE_NAME in good_pwd.cookies


def test_session_cookie_older_than_eight_hours_rejected(
    client: TestClient, sample_case_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session cookie older than 8 hours (created_at check) is rejected with 401."""
    secret = "secure_test_session_secret_key_with_at_least_32_characters"
    user = "Priya Sharma"
    pwd_hash = hash_password("password123")
    monkeypatch.setenv("REVIEWER_USER", user)
    monkeypatch.setenv("REVIEWER_PASSWORD_HASH", pwd_hash)
    monkeypatch.setenv("SESSION_SECRET", secret)

    csrf_token = "valid_csrf_token_for_test_123456"
    # Created 8 hours and 5 minutes ago
    expired_time = int(time.time()) - (8 * 3600 + 300)
    payload = {
        "user": user,
        "csrf_token": csrf_token,
        "created_at": expired_time,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii")
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    expired_cookie = f"{payload_b64}.{sig}"

    client.cookies.set(SESSION_COOKIE_NAME, expired_cookie)
    resp = client.post(
        f"/cases/{sample_case_id}/needs-evidence",
        data={"csrf_token": csrf_token, "note": "Action on expired session"},
    )
    assert resp.status_code == 401


def test_webhook_razorpay_hmac_authentication_without_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Razorpay webhook requires HMAC signature only, never reviewer session.

    - POST without signature returns webhook's own rejection (400, not login 401).
    - Correctly signed POST is accepted (200 OK) even with reviewer auth env unset.
    """
    webhook_secret = "test_razorpay_webhook_secret_key"
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", webhook_secret)
    # Ensure reviewer auth env is unset to guarantee webhook does not depend on reviewer session
    monkeypatch.delenv("REVIEWER_USER", raising=False)
    monkeypatch.delenv("REVIEWER_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)

    payload_bytes = json.dumps({
        "event": "dispute.created",
        "id": "evt_test_webhook_hmac_1",
        "payload": {
            "dispute": {
                "entity": {
                    "id": "disp_test_webhook_1",
                    "payment_id": "pay_test_webhook_1",
                }
            }
        },
    }).encode("utf-8")

    # 1. POST without signature returns webhook's own rejection (400, not login 401)
    unsigned_resp = client.post(
        "/webhook/razorpay/webhook",
        content=payload_bytes,
        headers={"Content-Type": "application/json"},
    )
    assert unsigned_resp.status_code == 400
    assert "Invalid webhook signature" in unsigned_resp.text

    # 2. Correctly signed POST is accepted (200 OK)
    valid_sig = hmac.new(webhook_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    signed_resp = client.post(
        "/webhook/razorpay/webhook",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": valid_sig,
            "X-Razorpay-Event-Id": "evt_test_webhook_hmac_1",
        },
    )
    assert signed_resp.status_code == 200
    assert signed_resp.json().get("status") in ("processed", "duplicate_ignored")
