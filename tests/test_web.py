"""Tests for the DisputePilot web interface and approval workflows."""

import pytest
from fastapi.testclient import TestClient

from disputepilot.pipeline.orchestrator import process_case
from disputepilot.razorpay.approval import compute_contest_payload_hash
from disputepilot.web.app import app, approval_service, gateway


@pytest.fixture
def client() -> TestClient:
    """Create FastAPI TestClient."""
    return TestClient(app)


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


def test_case_detail_404_for_unknown_case(client: TestClient) -> None:
    """Unknown case ID returns 404 Not Found."""
    response = client.get("/cases/case_non_existent_999999")
    assert response.status_code == 404


def test_confirm_submit_page_loads(client: TestClient, sample_case_id: str) -> None:
    """Confirm submit page must load and display payload, hash, and approval token."""
    response = client.get(f"/cases/{sample_case_id}/confirm-submit?reviewer_name=Priya+Sharma")
    assert response.status_code == 200
    assert "Submission Payload Review" in response.text
    assert "Priya Sharma" in response.text
    assert "appr_" in response.text  # Token issued


def test_confirm_submit_rejects_missing_reviewer(client: TestClient, sample_case_id: str) -> None:
    """Confirm submit page rejects when reviewer name is missing."""
    response = client.get(f"/cases/{sample_case_id}/confirm-submit")
    assert response.status_code == 400
    assert "reviewer is strictly required" in response.text.lower()


def test_submit_without_approval_fails(client: TestClient, sample_case_id: str) -> None:
    """Submitting contest without an approval token must fail with 400."""
    response = client.post(
        f"/cases/{sample_case_id}/submit",
        data={
            "reviewer_name": "Priya Sharma",
            "approval_token": "",
            "payload_hash": "somehash",
        },
    )
    assert response.status_code == 400


def test_submit_with_tampered_payload_hash_fails(client: TestClient, sample_case_id: str) -> None:
    """Submitting with a mismatched payload hash must fail."""
    # Issue a real token for a dummy hash
    token = approval_service.issue_token(
        dispute_id="disp_test",
        action="submit",
        payload_hash="fakehash123",
        approver="Priya Sharma",
    )

    response = client.post(
        f"/cases/{sample_case_id}/submit",
        data={
            "reviewer_name": "Priya Sharma",
            "approval_token": token,
            "payload_hash": "tampered_fake_hash",
        },
    )
    assert response.status_code == 400
    assert "mismatch" in response.text.lower()


def test_submit_with_valid_approval_succeeds(client: TestClient, sample_case_id: str) -> None:
    """Submitting with a valid, bound approval token succeeds and redirects."""
    # First get the confirm-submit page to issue token
    reviewer = "Aarav Mehta"
    get_resp = client.get(f"/cases/{sample_case_id}/confirm-submit?reviewer_name={reviewer}")
    assert get_resp.status_code == 200

    # Extract clean draft to get exact payload hash
    from disputepilot.pipeline.orchestrator import _load_case_by_id
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
        approver=reviewer,
    )

    post_resp = client.post(
        f"/cases/{sample_case_id}/submit",
        data={
            "reviewer_name": reviewer,
            "approval_token": valid_token,
            "payload_hash": valid_hash,
        },
        follow_redirects=False,
    )
    assert post_resp.status_code == 303
    assert "success=" in post_resp.headers["location"]


def test_accept_requires_typed_amount(client: TestClient, sample_case_id: str) -> None:
    """Accepting a dispute requires typing the exact amount to prevent accidental liability."""
    from disputepilot.pipeline.orchestrator import _load_case_by_id
    case = _load_case_by_id(sample_case_id)
    correct_rupees = case.dispute.amount / 100.0

    # 1. Wrong amount
    bad_resp = client.post(
        f"/cases/{sample_case_id}/accept",
        data={
            "reviewer_name": "Priya Sharma",
            "typed_amount": "999999.00",
        },
    )
    assert bad_resp.status_code == 400
    assert "Amount mismatch" in bad_resp.text

    # 2. Correct amount with ₹ symbol and spaces
    good_resp = client.post(
        f"/cases/{sample_case_id}/accept",
        data={
            "reviewer_name": "Priya Sharma",
            "typed_amount": f"₹ {correct_rupees:.2f}",
        },
        follow_redirects=False,
    )
    assert good_resp.status_code == 303
    assert "success=" in good_resp.headers["location"]


def test_missing_reviewer_name_is_rejected(client: TestClient, sample_case_id: str) -> None:
    """All state mutating actions strictly reject missing reviewer name."""
    # Save draft missing reviewer
    r1 = client.post(
        f"/cases/{sample_case_id}/save-draft",
        data={"reviewer_name": "", "summary": "Custom draft"},
    )
    assert r1.status_code == 400

    # Accept missing reviewer
    r2 = client.post(
        f"/cases/{sample_case_id}/accept",
        data={"reviewer_name": "", "typed_amount": "100.00"},
    )
    assert r2.status_code == 400

    # Needs evidence missing reviewer
    r3 = client.post(
        f"/cases/{sample_case_id}/needs-evidence",
        data={"reviewer_name": "", "note": "Missing POD"},
    )
    assert r3.status_code == 400


def test_save_draft_and_needs_evidence_actions(client: TestClient, sample_case_id: str) -> None:
    """Saving draft and flagging needs-evidence succeed and redirect."""
    r_draft = client.post(
        f"/cases/{sample_case_id}/save-draft",
        data={"reviewer_name": "Devi Prasad", "summary": "Custom merchant drafted text."},
        follow_redirects=False,
    )
    assert r_draft.status_code == 303

    r_ev = client.post(
        f"/cases/{sample_case_id}/needs-evidence",
        data={"reviewer_name": "Devi Prasad", "note": "Awaiting customer cancellation log."},
        follow_redirects=False,
    )
    assert r_ev.status_code == 303


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
