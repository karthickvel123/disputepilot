"""End-to-end live-mode flow through the real web app against a fake Razorpay HTTP API.

Covers the demo path: worklist -> case -> evidence upload -> review (approval token) -> submit,
plus accept, gating of non-actionable disputes, and the "never a blank page" failure modes.
"""

import dataclasses
import importlib
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from disputepilot.extraction.llm import NullLLMClient
from disputepilot.live.locker import EvidenceLocker
from disputepilot.live.source import LiveCaseSource
from disputepilot.razorpay.gateway import RazorpayGateway
from disputepilot.web.auth import (
    SESSION_COOKIE_NAME,
    create_session_cookie_value,
    parse_session_cookie,
    safe_next_path,
)
from tests.live_fakes import DISPUTE_ID, FakeRazorpay

# NB: `from disputepilot.web import app` yields the FastAPI instance, not the module.
webapp = importlib.import_module("disputepilot.web.app")

Setup = Callable[..., tuple[TestClient, str, FakeRazorpay]]


@pytest.fixture
def setup_live(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Setup:
    def _setup(**fake_kwargs) -> tuple[TestClient, str, FakeRazorpay]:
        fake = FakeRazorpay(**fake_kwargs)
        gw = RazorpayGateway(
            "rzp_test_x", "secret", client=fake.client(),
            approval_service=webapp.approval_service, backoff_factor=0.0,
        )
        locker = EvidenceLocker(tmp_path / "locker.db")
        monkeypatch.setattr(webapp, "settings", dataclasses.replace(webapp.settings, data_mode="live", data_dir=tmp_path))
        monkeypatch.setattr(webapp, "gateway", gw)
        monkeypatch.setattr(webapp, "locker", locker)
        monkeypatch.setattr(webapp, "live_source", LiveCaseSource(gw, locker, cache_ttl=0))
        monkeypatch.setattr(webapp, "llm_client", NullLLMClient())
        monkeypatch.setattr(webapp, "DRAFTS_DIR", tmp_path / "drafts")
        monkeypatch.setattr(webapp, "razorpay_problems", [])
        monkeypatch.setitem(webapp.templates.env.globals, "data_mode", "live")
        client = TestClient(webapp.app)
        cookie, csrf = create_session_cookie_value(user="Priya Sharma")
        client.cookies.set(SESSION_COOKIE_NAME, cookie)
        return client, csrf, fake

    return _setup


def _hidden(html: str, name: str) -> str:
    m = re.search(rf'name="{name}" value="([^"]+)"', html)
    assert m, f"{name} not found"
    return m.group(1)


def _patches(fake: FakeRazorpay) -> list[dict]:
    return [w[2] for w in fake.writes if w[0] == "PATCH"]


def test_worklist_and_case_page_render_from_razorpay(setup_live: Setup) -> None:
    client, _csrf, _fake = setup_live()
    page = client.get("/")
    assert page.status_code == 200 and DISPUTE_ID in page.text
    case = client.get(f"/cases/{DISPUTE_ID}")
    assert case.status_code == 200
    assert "Recommendation Engine" in case.text and "shipping_address" in case.text  # gap is visible


def test_full_contest_flow_respects_razorpay_limits_and_binds_approval(setup_live: Setup) -> None:
    client, csrf, fake = setup_live()
    pdf = b"%PDF-1.4\n%fake evidence\n%%EOF"
    up = client.post(
        f"/cases/{DISPUTE_ID}/evidence",
        data={"csrf_token": csrf, "category": "shipping_proof", "attest_no_card_data": "yes", "excerpt": "Delivered 12 Mar, OTP verified."},
        files={"file": ("pod.pdf", pdf, "application/pdf")},
        follow_redirects=False,
    )
    assert up.status_code == 303
    assert "pod.pdf" in client.get(f"/cases/{DISPUTE_ID}").text

    review = client.post(f"/cases/{DISPUTE_ID}/review", data={"csrf_token": csrf}, follow_redirects=False)
    assert review.status_code == 200
    token, phash = _hidden(review.text, "approval_token"), _hidden(review.text, "payload_hash")
    assert not _patches(fake), "reviewing must not submit anything"

    done = client.post(
        f"/cases/{DISPUTE_ID}/submit",
        data={"csrf_token": csrf, "approval_token": token, "payload_hash": phash},
        follow_redirects=False,
    )
    assert done.status_code == 303 and "under_review" in done.headers["location"]
    submit = [p for p in _patches(fake) if p["action"] == "submit"]
    assert len(submit) == 1
    body = submit[0]
    assert len(body["summary"]) <= 1000
    assert body["shipping_proof"] and body["explanation_letter"]  # evidence + letter, as document ids

    replay = client.post(
        f"/cases/{DISPUTE_ID}/submit",
        data={"csrf_token": csrf, "approval_token": token, "payload_hash": phash},
        follow_redirects=False,
    )
    assert replay.status_code == 400  # single-use token


def test_submit_without_token_never_reaches_razorpay(setup_live: Setup) -> None:
    client, csrf, fake = setup_live()
    r = client.post(f"/cases/{DISPUTE_ID}/submit", data={"csrf_token": csrf, "approval_token": "", "payload_hash": "x"}, follow_redirects=False)
    assert r.status_code == 400 and not _patches(fake)


def test_accept_flow_reports_real_status(setup_live: Setup) -> None:
    client, csrf, fake = setup_live()
    review = client.post(f"/cases/{DISPUTE_ID}/accept-review", data={"csrf_token": csrf, "typed_amount": "4500.00"})
    assert review.status_code == 200
    done = client.post(
        f"/cases/{DISPUTE_ID}/accept",
        data={"csrf_token": csrf, "approval_token": _hidden(review.text, "approval_token"), "payload_hash": _hidden(review.text, "payload_hash")},
        follow_redirects=False,
    )
    assert done.status_code == 303 and "closed" in done.headers["location"]
    assert any(w[1].endswith("/accept") for w in fake.writes)


def test_non_open_dispute_blocks_actions_but_page_still_renders(setup_live: Setup) -> None:
    client, csrf, fake = setup_live(status="under_review")
    page = client.get(f"/cases/{DISPUTE_ID}")
    assert page.status_code == 200 and "Actions are disabled" in page.text
    r = client.post(f"/cases/{DISPUTE_ID}/review", data={"csrf_token": csrf})
    assert r.status_code == 400 and "under_review" in r.json()["detail"]
    assert not fake.writes


def test_razorpay_rejection_is_shown_not_swallowed(setup_live: Setup) -> None:
    client, csrf, fake = setup_live()
    review = client.post(f"/cases/{DISPUTE_ID}/accept-review", data={"csrf_token": csrf, "typed_amount": "4500"})
    fake.fail[f"/v1/disputes/{DISPUTE_ID}/accept"] = 400
    r = client.post(
        f"/cases/{DISPUTE_ID}/accept",
        data={"csrf_token": csrf, "approval_token": _hidden(review.text, "approval_token"), "payload_hash": ""},
    )
    assert r.status_code in (400, 502) and "forced failure" in r.json()["detail"]


def test_evidence_upload_validation(setup_live: Setup) -> None:
    client, csrf, fake = setup_live()
    base = {"csrf_token": csrf, "category": "billing_proof", "attest_no_card_data": "yes"}
    ok_pdf = ("a.pdf", b"%PDF-1.4 x", "application/pdf")
    no_attest = client.post(f"/cases/{DISPUTE_ID}/evidence", data={**base, "attest_no_card_data": ""}, files={"file": ok_pdf})
    fake_pdf = client.post(f"/cases/{DISPUTE_ID}/evidence", data=base, files={"file": ("a.pdf", b"MZ not a pdf", "application/pdf")})
    wrong_type = client.post(f"/cases/{DISPUTE_ID}/evidence", data=base, files={"file": ("a.exe", b"%PDF-1.4", "application/octet-stream")})
    card = client.post(f"/cases/{DISPUTE_ID}/evidence", data={**base, "excerpt": "paid with 4111 1111 1111 1111"}, files={"file": ok_pdf})
    assert [r.status_code for r in (no_attest, fake_pdf, wrong_type, card)] == [400, 400, 400, 400]
    assert not fake.writes, "rejected uploads must never reach Razorpay"


def test_unconfigured_live_mode_shows_setup_page_not_a_crash(setup_live: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _csrf, _fake = setup_live()
    monkeypatch.setattr(webapp, "live_source", None)
    monkeypatch.setattr(webapp, "razorpay_problems", ["RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are not set."])
    r = client.get("/")
    assert r.status_code == 503 and "Setup required" in r.text and "RAZORPAY_KEY_ID" in r.text


def test_worklist_survives_razorpay_outage(setup_live: Setup) -> None:
    client, _csrf, fake = setup_live()
    fake.fail["/v1/disputes"] = 503
    r = client.get("/")
    assert r.status_code == 200 and "Dispute Triage Worklist" in r.text and "alert-danger" in r.text


def test_cvv_and_card_text_are_rejected_and_never_stored(setup_live: Setup) -> None:
    client, csrf, fake = setup_live()
    base = {"csrf_token": csrf, "category": "billing_proof", "attest_no_card_data": "yes"}
    for text in ("customer paid, CVV 123", "card 4111 1111 1111 1111"):
        r = client.post(f"/cases/{DISPUTE_ID}/evidence", data={**base, "excerpt": text}, files={"file": ("a.pdf", b"%PDF-1.4 x", "application/pdf")})
        assert r.status_code == 400
    assert not fake.writes
    assert webapp.locker.list_for_dispute(DISPUTE_ID) == []


def test_expired_or_undated_sessions_are_rejected() -> None:
    cookie, _ = create_session_cookie_value(user="Priya Sharma")
    assert parse_session_cookie(cookie) is not None
    assert parse_session_cookie(cookie, now=10**11) is None  # far past the 24h lifetime


@pytest.mark.parametrize("bad", ["//evil.example", "https://evil.example", "/\\evil.example", "javascript:alert(1)", "/ok\nSet-Cookie:x=1", ""])
def test_login_next_is_restricted_to_local_paths(bad: str) -> None:
    assert safe_next_path(bad) == "/"
    assert safe_next_path("/cases/disp_1") == "/cases/disp_1"


def test_webhook_health_is_minimal(setup_live: Setup) -> None:
    client, _csrf, _fake = setup_live()
    body = client.get("/webhook/razorpay/health").json()
    assert set(body) == {"armed", "events_received"}
