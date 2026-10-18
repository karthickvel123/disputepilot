"""Real-payload compatibility of the models, plus config / PDF / summary / locker units."""

import hashlib
from pathlib import Path

import pytest

from disputepilot.config import load_settings
from disputepilot.core.models import DisputePhase, DisputeStatus, RazorpayDispute
from disputepilot.live.locker import EvidenceLocker
from disputepilot.live.pdf import text_to_pdf
from disputepilot.live.summary import short_summary
from tests.live_fakes import dispute_body


def test_dispute_parses_real_shape_with_null_evidence_and_structured_others() -> None:
    body = dispute_body(evidence={"shipping_proof": ["doc_A"], "others": [{"type": "receipt", "document_ids": ["doc_B"]}]})
    d = RazorpayDispute.model_validate(body)
    assert d.evidence.billing_proof == []  # null -> []
    assert d.evidence.document_ids() == {"shipping_proof": ["doc_A"]}
    assert d.evidence.others[0]["document_ids"] == ["doc_B"]
    assert d.amount_deducted == 0


def test_dispute_tolerates_null_evidence_object_and_unknown_enums() -> None:
    body = dispute_body(status="action_required")
    body["phase"] = "something_new"
    body["evidence"] = None
    d = RazorpayDispute.model_validate(body)
    assert d.status is DisputeStatus.UNKNOWN and d.phase is DisputePhase.UNKNOWN
    assert RazorpayDispute.model_validate({**dispute_body(), "phase": "fraud"}).phase is DisputePhase.FRAUD


def test_settings_guard_live_keys_and_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "ALLOW_LIVE_KEYS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DATA_MODE", "live")
    assert load_settings().razorpay_problems()
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live_abc")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "SECRETVALUE123")
    assert any("rzp_live_" in p for p in load_settings().razorpay_problems())
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_abc")
    assert load_settings().razorpay_problems() == []
    assert "SECRETVALUE123" not in repr(load_settings())  # secrets never appear in repr/logs


def test_pdf_is_valid_and_multi_page() -> None:
    pdf = text_to_pdf("\n".join(f"line {i} \u20b9 (x)" for i in range(200)))
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    assert pdf.count(b"/Type /Page ") >= 3
    assert text_to_pdf("same") == text_to_pdf("same")  # deterministic -> dedupe by hash works


def test_short_summary_limit_and_citation_stripping() -> None:
    md = "## Summary\n" + "\n".join(f"- Delivery fact number {i} confirmed by courier. [fact_{i}]" for i in range(80)) + "\n## Timeline\n- x"
    out = short_summary(md)
    assert len(out) <= 1000 and "[fact_" not in out and "Timeline" not in out


def test_locker_roundtrip_and_hash_dedupe(tmp_path: Path) -> None:
    lk = EvidenceLocker(tmp_path / "l.db")
    lk.add("disp_1", "billing_proof", "inv.pdf", "application/pdf", 3, hashlib.sha256(b"a").hexdigest(), "rev", razorpay_doc_id="doc_1")
    lk.add("disp_1", "shipping_proof", "pod.png", "image/png", 3, "x", "rev")  # not uploaded
    assert lk.evidence_ids("disp_1") == {"billing_proof": ["doc_1"]}
    assert lk.find_uploaded_by_hash(hashlib.sha256(b"a").hexdigest()).razorpay_doc_id == "doc_1"
    with pytest.raises(ValueError):
        lk.add("disp_1", "nope", "f", "x", 1, "h", "rev")


def test_secure_cookie_defaults_on_in_production_and_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production deployments default to Secure cookies while local development stays usable."""
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    assert load_settings().cookie_secure is True

    monkeypatch.setenv("COOKIE_SECURE", "false")
    assert load_settings().cookie_secure is False

    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    assert load_settings().cookie_secure is False


def test_production_sim_mode_does_not_fall_back_to_known_demo_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public production demo must require explicitly configured reviewer credentials."""
    from disputepilot.web.auth import (
        DEFAULT_HASH,
        DEFAULT_REVIEWER_USER,
        get_configured_credentials,
    )

    monkeypatch.setenv("DATA_MODE", "sim")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("REVIEWER_USER", raising=False)
    monkeypatch.delenv("REVIEWER_PASSWORD_HASH", raising=False)
    assert get_configured_credentials() == ("", "")

    monkeypatch.setenv("APP_ENV", "development")
    assert get_configured_credentials() == (DEFAULT_REVIEWER_USER, DEFAULT_HASH)
