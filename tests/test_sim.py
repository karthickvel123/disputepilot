"""Tests for dispute simulation and case generator."""

import json
import re
from pathlib import Path

from disputepilot.core.models import DisputeCase, DisputePhase, ReasonClass
from disputepilot.sim.generate import save_cases
from disputepilot.sim.generator import generate_cases
from disputepilot.sim.rules import evaluate_winnability


def test_seed_determinism() -> None:
    """Verify that using the same seed produces byte-for-byte identical output."""
    cases_run1 = generate_cases(n=25, seed=42)
    cases_run2 = generate_cases(n=25, seed=42)

    assert len(cases_run1) == len(cases_run2) == 25

    for c1, c2 in zip(cases_run1, cases_run2, strict=True):
        assert c1.case_id == c2.case_id
        assert c1.dispute.payment_id == c2.dispute.payment_id
        assert c1.dispute.amount == c2.dispute.amount
        assert c1.dispute.created_at == c2.dispute.created_at
        assert c1.dispute.respond_by == c2.dispute.respond_by
        assert c1.ground_truth.reason_class == c2.ground_truth.reason_class
        assert c1.ground_truth.winnable == c2.ground_truth.winnable
        assert c1.ground_truth.available_evidence == c2.ground_truth.available_evidence
        assert c1.ground_truth.adversarial.is_adversarial == c2.ground_truth.adversarial.is_adversarial
        assert len(c1.documents) == len(c2.documents)
        for d1, d2 in zip(c1.documents, c2.documents, strict=True):
            assert d1.file_name == d2.file_name
            assert d1.content == d2.content

    # A different seed should yield different cases
    cases_diff = generate_cases(n=25, seed=99)
    assert cases_run1[0].case_id != cases_diff[0].case_id


def test_label_distribution_roughly_balanced() -> None:
    """Verify that reason classes are roughly balanced across all 7 categories."""
    n = 150
    cases = generate_cases(n=n, seed=42)
    assert len(cases) == n

    counts: dict[ReasonClass, int] = {}
    winnable_count = 0

    for case in cases:
        rc = case.ground_truth.reason_class
        counts[rc] = counts.get(rc, 0) + 1
        if case.ground_truth.winnable:
            winnable_count += 1

    # All 7 categories must be represented
    assert len(counts) == 7
    expected_per_class = n / 7  # ~21.4

    for r_class, count in counts.items():
        # Each class should be within a balanced range (e.g. 18 to 25 cases)
        assert 18 <= count <= 25, f"Class {r_class} count {count} is not balanced (expected ~{expected_per_class:.1f})"

    # Winnable cases should also be reasonably balanced (between 30% and 70%)
    winnable_pct = (winnable_count / n) * 100
    assert 30 <= winnable_pct <= 70, f"Winnable ratio {winnable_pct:.1f}% is out of balanced bounds"


def test_adversarial_cases_present() -> None:
    """Verify that ~10% of cases are adversarial and all 3 types are present."""
    cases = generate_cases(n=150, seed=42)
    adversarial_cases = [c for c in cases if c.ground_truth.adversarial.is_adversarial]

    # About 10% (between 8% and 15% in 150 cases = 12 to 22 cases)
    adv_count = len(adversarial_cases)
    adv_pct = (adv_count / len(cases)) * 100
    assert 8 <= adv_pct <= 16, f"Adversarial count {adv_count} ({adv_pct:.1f}%) not near target ~10%"

    types_found: set[str] = set()
    has_prompt_injection = False
    has_card_number = False
    has_delivery_after_dispute = False

    card_pattern = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")

    for case in adversarial_cases:
        for t in case.ground_truth.adversarial.adversarial_types:
            types_found.add(t)

        all_doc_content = "\n".join(d.content for d in case.documents)

        if "prompt_injection" in case.ground_truth.adversarial.adversarial_types:
            has_prompt_injection = True
            # Document must contain prompt injection keywords
            assert any(
                phrase in all_doc_content
                for phrase in ["SYSTEM OVERRIDE", "system_instruction", "IMPORTANT NOTICE TO AGENT", "debug mode"]
            )

        if "card_number" in case.ground_truth.adversarial.adversarial_types:
            has_card_number = True
            # Document must contain a 16-digit card-number-like string
            assert card_pattern.search(all_doc_content) is not None

        if "delivery_after_dispute" in case.ground_truth.adversarial.adversarial_types:
            has_delivery_after_dispute = True
            assert case.order.delivered_at is not None
            assert case.order.delivered_at > case.dispute.created_at

    assert "prompt_injection" in types_found
    assert "card_number" in types_found
    assert "delivery_after_dispute" in types_found
    assert has_prompt_injection
    assert has_card_number
    assert has_delivery_after_dispute


def test_razorpay_dispute_schema_and_types() -> None:
    """Verify generated cases strictly follow Razorpay entity conventions and constraints."""
    cases = generate_cases(n=35, seed=42)

    required_evidence_keys = {
        "shipping_proof",
        "billing_proof",
        "cancellation_proof",
        "customer_communication",
        "proof_of_service",
        "explanation_letter",
        "refund_confirmation",
        "access_activity_log",
        "refund_cancellation_policy",
        "others",
    }

    for case in cases:
        disp = case.dispute
        # ID prefixes
        assert disp.id.startswith("disp_")
        assert disp.payment_id.startswith("pay_")
        assert disp.entity == "dispute"

        # Amounts are integers in paise
        assert isinstance(disp.amount, int)
        assert disp.amount > 0
        assert disp.currency == "INR"

        # Phase conforms to Razorpay dispute phases
        assert disp.phase in (
            DisputePhase.CHARGEBACK,
            DisputePhase.RETRIEVAL,
            DisputePhase.PRE_ARBITRATION,
        )

        # Timestamps are valid unix seconds
        assert isinstance(disp.created_at, int)
        assert isinstance(disp.respond_by, int)
        assert disp.respond_by > disp.created_at

        # Evidence object keys
        ev_dict = disp.evidence.model_dump()
        for req_key in required_evidence_keys:
            assert req_key in ev_dict

        # Order checks
        assert case.order.id.startswith("order_")
        assert case.order.amount == disp.amount
        assert case.order.created_at < disp.created_at

        # Evidence documents: 1 to 3 documents per case
        assert 1 <= len(case.documents) <= 3
        for doc in case.documents:
            assert doc.doc_type in required_evidence_keys
            assert doc.file_path.startswith(f"{case.case_id}/")
            assert len(doc.content) > 20


def test_winnability_rule_consistency() -> None:
    """Verify that winnability is evaluated consistently with documented rules."""
    cases = generate_cases(n=70, seed=42)

    for case in cases:
        has_processed_refund = case.refund is not None and case.refund.status == "processed"
        delivery_after_dispute = "delivery_after_dispute" in case.ground_truth.adversarial.adversarial_types
        is_distinct = (case.ground_truth.reason_class == ReasonClass.DUPLICATE_CHARGE) and (
            case.metadata.get("case_index", 0) % 2 == 0
        )

        expected_winnable, _ = evaluate_winnability(
            reason_class=case.ground_truth.reason_class,
            available_evidence=case.ground_truth.available_evidence,
            has_processed_refund=has_processed_refund,
            delivery_after_dispute=delivery_after_dispute,
            is_distinct_order=is_distinct,
        )

        assert case.ground_truth.winnable == expected_winnable


def test_save_cases_and_disk_artifacts(tmp_path: Path) -> None:
    """Verify that saving cases writes one JSON per case and documents on disk."""
    cases = generate_cases(n=5, seed=42)
    save_cases(cases=cases, out_dir=tmp_path)

    for case in cases:
        # Check primary JSON file: <case_id>.json
        json_file = tmp_path / f"{case.case_id}.json"
        assert json_file.exists()
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
        reloaded_case = DisputeCase.model_validate(data)
        assert reloaded_case.case_id == case.case_id

        # Check document files in <case_id>/<file_name>
        case_folder = tmp_path / case.case_id
        assert case_folder.is_dir()

        for doc in case.documents:
            doc_file = case_folder / doc.file_name
            assert doc_file.exists()
            assert doc_file.read_text(encoding="utf-8") == doc.content
