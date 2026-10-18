"""LiveCaseSource against the fake Razorpay API: assembly, partial failure, caching, errors."""

from pathlib import Path

import pytest

from disputepilot.live.locker import EvidenceLocker
from disputepilot.live.source import CaseNotFound, LiveCaseSource, SourceError
from disputepilot.razorpay.gateway import RazorpayGateway
from tests.live_fakes import DISPUTE_ID, ORDER_ID, PAYMENT_ID, FakeRazorpay


def make_source(fake: FakeRazorpay, tmp_path: Path, ttl: int = 30, clock=lambda: 1000.0) -> LiveCaseSource:
    gw = RazorpayGateway("rzp_test_x", "secret", client=fake.client(), backoff_factor=0.0)
    return LiveCaseSource(gw, EvidenceLocker(tmp_path / "l.db"), cache_ttl=ttl, clock=clock)


def test_get_case_assembles_dispute_payment_order(tmp_path: Path) -> None:
    case = make_source(FakeRazorpay(), tmp_path).get_case(DISPUTE_ID)
    assert case.case_id == DISPUTE_ID and case.ground_truth is None
    assert case.order.id == ORDER_ID and case.order.customer_email == "buyer@example.com"
    assert case.order.customer_name == "Asha Rao" and case.order.tracking_number == "AWB123456"
    gaps = " ".join(case.metadata["data_gaps"])
    assert "shipping_address" in gaps and "No evidence files" in gaps  # gaps are reported, not invented
    assert "customer_name" not in gaps


def test_partial_failure_still_returns_a_case_with_gaps(tmp_path: Path) -> None:
    fake = FakeRazorpay()
    fake.fail[f"/v1/payments/{PAYMENT_ID}"] = 500
    case = make_source(fake, tmp_path).get_case(DISPUTE_ID)
    assert case.dispute.id == DISPUTE_ID
    assert any("Payment" in g and "could not be loaded" in g for g in case.metadata["data_gaps"])


def test_unknown_dispute_is_case_not_found_and_server_error_is_source_error(tmp_path: Path) -> None:
    src = make_source(FakeRazorpay(), tmp_path)
    with pytest.raises(CaseNotFound):
        src.get_case("disp_DOESNOTEXIST01")
    fake = FakeRazorpay()
    fake.fail["/v1/disputes"] = 401
    with pytest.raises(SourceError) as exc:
        make_source(fake, tmp_path).get_case(DISPUTE_ID)
    assert "credentials" in str(exc.value)


def test_list_uses_cache_then_serves_stale_on_failure(tmp_path: Path) -> None:
    now = [1000.0]
    fake = FakeRazorpay()
    src = make_source(fake, tmp_path, ttl=30, clock=lambda: now[0])
    first, err = src.list_disputes()
    assert len(first) == 1 and err is None
    src.list_disputes()
    assert fake.disputes_list_calls == 1  # within TTL: no second API call
    now[0] += 31
    fake.fail["/v1/disputes"] = 503
    stale, err = src.list_disputes()
    assert len(stale) == 1 and err and "last successful sync" in err


def test_list_with_no_cache_and_failure_returns_empty_with_message(tmp_path: Path) -> None:
    fake = FakeRazorpay()
    fake.fail["/v1/disputes"] = 401
    items, err = make_source(fake, tmp_path).list_disputes()
    assert items == [] and err and "credentials" in err
