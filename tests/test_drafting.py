import json
from pathlib import Path

from disputepilot.core.models import DisputeCase
from disputepilot.drafting import (
    DraftSentence,
    RebuttalDraft,
    RebuttalDrafter,
    build_fact_set,
    verify_rebuttal,
)
from disputepilot.extraction.extractor import extract_document
from disputepilot.extraction.llm import FakeLLMClient


def load_simulated_cases(data_dir: str = "data/cases") -> list[DisputeCase]:
    """Load simulated cases from disk."""
    path = Path(data_dir)
    cases: list[DisputeCase] = []
    if not path.exists():
        return cases
    for jf in sorted(path.glob("*.json")):
        try:
            with open(jf, encoding="utf-8") as f:
                cases.append(DisputeCase.model_validate(json.load(f)))
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    return cases



def test_clean_draft_passes_untouched() -> None:
    """A clean draft where all numbers, dates, and IDs match cited facts passes verification."""
    cases = load_simulated_cases()
    case = cases[0]
    facts = build_fact_set(case=case, extracted_docs=[])

    disp_id = case.dispute.id
    disp_amt = case.dispute.amount
    order_id = case.order.id
    customer_name = case.order.customer_name

    draft = RebuttalDraft(
        case_id=case.case_id,
        dispute_id=disp_id,
        summary=[
            DraftSentence(
                sentence=f"We formally contest dispute {disp_id} for the transaction of {disp_amt} paise.",
                cited_fact_ids=["fact_dispute_id", "fact_dispute_amount"],
            ),
            DraftSentence(
                sentence=f"The legitimate cardholder {customer_name} placed order {order_id}.",
                cited_fact_ids=["fact_order_id", "fact_customer_name"],
            ),
        ],
        timeline=[
            DraftSentence(
                sentence=f"The order was placed at epoch {case.order.created_at}.",
                cited_fact_ids=["fact_order_created_at"],
            )
        ],
        evidence_list=[],
        conclusion=[
            DraftSentence(
                sentence=f"Merchant requests dismissal of dispute {disp_id}.",
                cited_fact_ids=["fact_dispute_id"],
            )
        ],
    )

    clean_draft, report = verify_rebuttal(draft, facts)
    assert report.is_clean is True
    assert report.stripped_count == 0
    assert report.valid_sentences == 4
    assert len(clean_draft.all_sentences()) == 4


def test_invented_delivery_date_is_stripped() -> None:
    """A draft containing an invented or hallucinated delivery date is stripped."""
    cases = load_simulated_cases()
    case = cases[0]
    facts = build_fact_set(case=case, extracted_docs=[])

    disp_id = case.dispute.id
    invented_date = "2026-11-28"

    draft = RebuttalDraft(
        case_id=case.case_id,
        dispute_id=disp_id,
        summary=[
            DraftSentence(
                sentence=f"Dispute {disp_id} was received.",
                cited_fact_ids=["fact_dispute_id"],
            )
        ],
        timeline=[
            DraftSentence(
                sentence=f"Package was successfully delivered to destination on {invented_date}.",
                cited_fact_ids=["fact_order_delivered_at"] if "fact_order_delivered_at" in facts.fact_ids() else ["fact_dispute_id"],
            )
        ],
        evidence_list=[],
        conclusion=[],
    )

    clean_draft, report = verify_rebuttal(draft, facts)
    assert report.is_clean is False
    assert report.stripped_count == 1
    assert report.valid_sentences == 1

    stripped = report.stripped_sentences[0]
    assert stripped.section == "timeline"
    assert invented_date in stripped.ungrounded_entities
    assert any("Fabricated date" in r for r in stripped.reasons)

    # Verify zero fabricated claims survived
    for s in clean_draft.all_sentences():
        assert invented_date not in s.sentence


def test_sentence_with_no_citation_is_removed() -> None:
    """Any sentence without at least one cited fact ID is strictly removed."""
    cases = load_simulated_cases()
    case = cases[0]
    facts = build_fact_set(case=case, extracted_docs=[])

    draft = RebuttalDraft(
        case_id=case.case_id,
        dispute_id=case.dispute.id,
        summary=[
            DraftSentence(
                sentence="The customer contacted us claiming they were unsatisfied.",
                cited_fact_ids=[],  # Zero citations
            ),
            DraftSentence(
                sentence=f"Dispute {case.dispute.id} is invalid.",
                cited_fact_ids=["fact_dispute_id"],
            ),
        ],
        timeline=[],
        evidence_list=[],
        conclusion=[],
    )

    clean_draft, report = verify_rebuttal(draft, facts)
    assert report.stripped_count == 1
    assert report.valid_sentences == 1
    assert "Missing citation" in report.stripped_sentences[0].reasons[0]
    assert len(clean_draft.summary) == 1
    assert clean_draft.summary[0].sentence == f"Dispute {case.dispute.id} is invalid."


def test_sentence_with_invalid_fact_id_is_stripped() -> None:
    """A sentence citing a non-existent fact ID is removed with reason recorded."""
    cases = load_simulated_cases()
    case = cases[0]
    facts = build_fact_set(case=case, extracted_docs=[])

    draft = RebuttalDraft(
        case_id=case.case_id,
        dispute_id=case.dispute.id,
        summary=[
            DraftSentence(
                sentence="Merchant maintains an unconditional return policy.",
                cited_fact_ids=["fact_phantom_citation_9999"],
            )
        ],
        timeline=[],
        evidence_list=[],
        conclusion=[],
    )

    clean_draft, report = verify_rebuttal(draft, facts)
    assert report.is_clean is False
    assert report.stripped_count == 1
    assert any("Invalid citation" in r for r in report.stripped_sentences[0].reasons)
    assert len(clean_draft.all_sentences()) == 0


def test_fabricated_amount_and_awb_are_stripped() -> None:
    """Fabricated amounts or tracking IDs not in the cited facts are stripped."""
    cases = load_simulated_cases()
    case = cases[0]
    facts = build_fact_set(case=case, extracted_docs=[])

    disp_id = case.dispute.id
    fake_amount = "999999"
    fake_awb = "AWB9988776655"

    draft = RebuttalDraft(
        case_id=case.case_id,
        dispute_id=disp_id,
        summary=[
            # Cites real dispute id, but fabricates amount
            DraftSentence(
                sentence=f"Dispute {disp_id} concerns an unauthorized amount of {fake_amount} paise.",
                cited_fact_ids=["fact_dispute_id"],
            ),
            # Cites real order id, but fabricates AWB tracking ID
            DraftSentence(
                sentence=f"Order {case.order.id} was dispatched with courier tracking ID {fake_awb}.",
                cited_fact_ids=["fact_order_id"],
            ),
        ],
        timeline=[],
        evidence_list=[],
        conclusion=[],
    )

    clean_draft, report = verify_rebuttal(draft, facts)
    assert report.stripped_count == 2
    assert report.valid_sentences == 0
    assert len(clean_draft.all_sentences()) == 0

    stripped_reasons = " ".join([r for s in report.stripped_sentences for r in s.reasons])
    assert "Fabricated number/amount" in stripped_reasons
    assert "Fabricated ID" in stripped_reasons


def test_drafter_end_to_end_with_extracted_docs() -> None:
    """End-to-end drafting from case facts produces verifiable Markdown rebuttal."""
    cases = load_simulated_cases()
    case = cases[0]

    # Ingest document
    extracted_docs = []
    for doc in case.documents:
        ext = extract_document(
            text_or_path=doc.content,
            case_id=case.case_id,
            doc_id=doc.doc_id,
            doc_type=doc.doc_type,
            llm_client=FakeLLMClient(),
        )
        extracted_docs.append(ext)

    facts = build_fact_set(case=case, extracted_docs=extracted_docs)
    assert len(facts.facts) > 5

    drafter = RebuttalDrafter(llm_client=FakeLLMClient())
    draft = drafter.draft(case=case, facts=facts)

    clean_draft, report = verify_rebuttal(draft, facts)
    assert report.is_clean is True
    assert report.stripped_count == 0
    assert len(clean_draft.all_sentences()) > 0

    md = clean_draft.to_markdown()
    assert "# Dispute Contest Rebuttal" in md
    assert "## Summary" in md
    assert "## Timeline of Events" in md
    assert "## Evidence Submitted" in md
    assert "## Conclusion & Requested Action" in md


def test_verifier_regression_ungrounded_claims_and_token_boundaries() -> None:
    """Regression test for token-boundary number checks, negation guard, and content-word grounding.

    Given a fact:
      text="Courier tracking AWB 4829105 shows the parcel was delivered on 2026-03-10.", raw_value=450000
    Sentences a-e must be STRIPPED, and the passing sentence must PASS.
    """
    from disputepilot.drafting.facts import Fact, FactSet
    from disputepilot.drafting.verifier import verify_sentence

    fact = Fact(
        fact_id="fact_courier_awb",
        text="Courier tracking AWB 4829105 shows the parcel was delivered on 2026-03-10.",
        source="doc:delivery_proof",
        raw_value=450000,
        entities=["4829105", "2026-03-10"],
    )
    fact_set = FactSet(case_id="case_test_verifier", facts=[fact])

    # a) Negation guard check (uncited 'not')
    s_a = DraftSentence(
        sentence="The parcel was NOT delivered on 2026-03-10.",
        cited_fact_ids=["fact_courier_awb"],
    )
    is_valid_a, stripped_a = verify_sentence(s_a, "timeline", fact_set)
    assert is_valid_a is False
    assert stripped_a is not None
    assert any("Uncited negation" in r for r in stripped_a.reasons)

    # b) Ungrounded content word ('signed')
    s_b = DraftSentence(
        sentence="The customer signed for the parcel, which was delivered on 2026-03-10.",
        cited_fact_ids=["fact_courier_awb"],
    )
    is_valid_b, stripped_b = verify_sentence(s_b, "timeline", fact_set)
    assert is_valid_b is False
    assert stripped_b is not None
    assert any("Ungrounded claim: 'signed'" in r for r in stripped_b.reasons)

    # c) Token boundary number mismatch ('4' substring of 4829105) + ungrounded words
    s_c = DraftSentence(
        sentence="The order weighed 4 kg and was delivered on 2026-03-10.",
        cited_fact_ids=["fact_courier_awb"],
    )
    is_valid_c, stripped_c = verify_sentence(s_c, "timeline", fact_set)
    assert is_valid_c is False
    assert stripped_c is not None
    assert any("Fabricated number/amount: '4'" in r for r in stripped_c.reasons)

    # d) Token boundary number mismatch ('50' substring of 450000) + negation ('never')
    s_d = DraftSentence(
        sentence="The refund of 50 was never requested.",
        cited_fact_ids=["fact_courier_awb"],
    )
    is_valid_d, stripped_d = verify_sentence(s_d, "timeline", fact_set)
    assert is_valid_d is False
    assert stripped_d is not None
    assert any("Fabricated number/amount: '50'" in r for r in stripped_d.reasons)
    assert any("Uncited negation" in r for r in stripped_d.reasons)

    # e) Ungrounded content word ('father')
    s_e = DraftSentence(
        sentence="The parcel was delivered on 2026-03-10 to the customer's father.",
        cited_fact_ids=["fact_courier_awb"],
    )
    is_valid_e, stripped_e = verify_sentence(s_e, "timeline", fact_set)
    assert is_valid_e is False
    assert stripped_e is not None
    assert any("Ungrounded claim: 'father'" in r for r in stripped_e.reasons)

    # Passing sentence: completely grounded
    s_pass = DraftSentence(
        sentence="The parcel was delivered on 2026-03-10.",
        cited_fact_ids=["fact_courier_awb"],
    )
    is_valid_pass, stripped_pass = verify_sentence(s_pass, "timeline", fact_set)
    assert is_valid_pass is True
    assert stripped_pass is None

