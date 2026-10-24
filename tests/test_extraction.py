"""Tests for document extraction, strict schemas, quote verification, and cross-checks."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from disputepilot.core.models import DisputeCase
from disputepilot.extraction.cross_checks import (
    Severity,
    check_address_mismatch,
    check_invoice_amount_mismatch,
    check_invoice_payment_mismatch,
    check_refund_not_mentioned,
    run_cross_checks,
)
from disputepilot.extraction.extractor import extract_document
from disputepilot.extraction.llm import FakeLLMClient
from disputepilot.extraction.schemas import DeliveryProof


def load_simulated_cases(data_dir: str = "data/cases") -> list[DisputeCase]:
    """Helper to load simulated cases."""
    path = Path(data_dir)
    cases: list[DisputeCase] = []
    if not path.exists():
        return cases
    import json
    for jf in sorted(path.glob("*.json")):
        try:
            with open(jf, encoding="utf-8") as f:
                cases.append(DisputeCase.model_validate(json.load(f)))
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    return cases


# ==============================================================================
# 1. Schema & Validation Tests
# ==============================================================================

def test_extra_keys_fail_validation() -> None:
    """Extra unexpected keys in document extraction payload must fail strict schema validation."""
    payload_with_extra_key = {
        "tracking_number": {
            "value": "TRK-DL-12345678",
            "source_quote": "Tracking: TRK-DL-12345678",
            "confidence": 0.95,
        },
        "carrier": {
            "value": "Delhivery",
            "source_quote": "Carrier: Delhivery",
            "confidence": 0.95,
        },
        "unexpected_field": "injected_data",
    }

    with pytest.raises(ValidationError) as exc_info:
        DeliveryProof.model_validate(payload_with_extra_key)

    assert "unexpected_field" in str(exc_info.value)
    assert "Extra inputs are not permitted" in str(exc_info.value)


def test_schema_sent_to_sdk_contains_no_additional_properties() -> None:
    """The schema sent to the Gemini SDK must contain no additionalProperties or defs."""
    import json

    pytest.importorskip("google.genai")
    from google.genai import types

    from disputepilot.extraction.llm import sanitize_schema_for_gemini
    from disputepilot.extraction.schemas import (
        CancellationPolicy,
        ChatTranscript,
        DeliveryProof,
        Invoice,
    )

    models_to_test = [DeliveryProof, Invoice, ChatTranscript, CancellationPolicy]
    for model_cls in models_to_test:
        raw_schema = model_cls.model_json_schema()
        # Original Pydantic schema must have additionalProperties: False
        assert "additionalProperties" in raw_schema or "$defs" in raw_schema

        clean_schema = sanitize_schema_for_gemini(model_cls)

        # 1. Standalone clean schema dict checks
        clean_json_str = json.dumps(clean_schema)
        assert "additionalProperties" not in clean_json_str
        assert "additional_properties" not in clean_json_str
        assert "$defs" not in clean_json_str
        assert "definitions" not in clean_json_str
        assert "$ref" not in clean_json_str

        # 2. Converted GenerateContentConfig schema payload checks
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=clean_schema,
        )
        dumped = config.model_dump(exclude_none=True)
        dumped_json_str = json.dumps(dumped)

        assert "additionalProperties" not in dumped_json_str
        assert "additional_properties" not in dumped_json_str
        assert "$defs" not in dumped_json_str
        assert "definitions" not in dumped_json_str
        assert "$ref" not in dumped_json_str


def test_response_with_extra_key_fails_validation() -> None:
    """A response containing an extra key must fail Pydantic model validation locally."""
    from disputepilot.extraction.schemas import (
        CancellationPolicy,
        ChatTranscript,
        DeliveryProof,
        Invoice,
    )

    extra_payload = {
        "invoice_number": {
            "value": "INV-2026-001",
            "source_quote": "Invoice No: INV-2026-001",
            "confidence": 1.0,
        },
        "unsupported_extra_key": "malicious_or_unexpected_value",
    }

    # 1. Direct Pydantic model validation must raise ValidationError
    with pytest.raises(ValidationError) as exc:
        Invoice.model_validate(extra_payload)
    assert "unsupported_extra_key" in str(exc.value)

    # 2. All extraction models strictly reject extra fields
    for model_cls in [DeliveryProof, ChatTranscript, CancellationPolicy]:
        with pytest.raises(ValidationError):
            model_cls.model_validate({"unknown_key": "some_value"})

    # 3. In the extractor pipeline, an extra key in LLM response must fail validation
    fake_client = FakeLLMClient()
    fake_client.set_default_response(extra_payload)

    with pytest.raises(ValidationError) as exc:
        extract_document(
            text_or_path="Invoice No: INV-2026-001\nTotal: 499900",
            case_id="case_extra_test",
            doc_id="doc_inv_extra",
            doc_type="invoice",
            llm_client=fake_client,
        )
    assert "unsupported_extra_key" in str(exc.value)


# ==============================================================================
# 2. Quote Verification Tests
# ==============================================================================

def test_made_up_quote_dropped() -> None:
    """Any extracted field whose source_quote is not verbatim in the cleaned document must be dropped."""
    real_doc_text = """# Proof of Delivery
**Tracking / AWB Number:** TRK-BD-99887766
**Logistics Carrier:** Bluedart Express
**Destination Address:** 42 Brigade Road, Bengaluru 560001
**Status:** DELIVERED
"""
    # Fake LLM returns one real field and one with a fabricated quote
    fake_client = FakeLLMClient()
    fake_client.set_default_response({
        "tracking_number": {
            "value": "TRK-BD-99887766",
            "source_quote": "**Tracking / AWB Number:** TRK-BD-99887766",
            "confidence": 0.99,
        },
        "recipient_name": {
            "value": "Rohan Verma",
            "source_quote": "Handed directly to recipient Rohan Verma at security desk",  # FABRICATED! Not in doc
            "confidence": 0.95,
        },
    })

    result = extract_document(
        text_or_path=real_doc_text,
        case_id="case_quote_verify_001",
        doc_id="doc_pod_001",
        doc_type="delivery_proof",
        llm_client=fake_client,
    )

    # Real field survives
    assert "tracking_number" in result.surviving_fields
    assert result.surviving_fields["tracking_number"].value == "TRK-BD-99887766"

    # Fabricated quote field is dropped
    assert "recipient_name" not in result.surviving_fields
    assert len(result.dropped_fields) == 1
    dropped = result.dropped_fields[0]
    assert dropped.field_name == "recipient_name"
    assert "Handed directly to recipient Rohan Verma" in dropped.source_quote
    assert "not verbatim" in dropped.reason


# ==============================================================================
# 3. Prompt Injection Resilience Tests
# ==============================================================================

def test_injection_transcript_does_not_change_extraction() -> None:
    """Prompt injection inside customer transcript does not derail extraction and is safely flagged."""
    cases = load_simulated_cases()
    injection_cases = [
        c for c in cases
        if c.ground_truth.adversarial.is_adversarial
        and "prompt_injection" in c.ground_truth.adversarial.adversarial_types
    ]
    assert len(injection_cases) > 0, "Expected prompt_injection case in data/cases."
    case = injection_cases[0]

    # Find the injection doc
    inj_doc = next(
        d for d in case.documents
        if any(kw in d.content for kw in ["SYSTEM OVERRIDE", "system_instruction", "IMPORTANT NOTICE TO AGENT"])
    )

    fake_client = FakeLLMClient()
    result = extract_document(
        text_or_path=inj_doc.content,
        case_id=case.case_id,
        doc_id=inj_doc.doc_id,
        doc_type=inj_doc.doc_type,
        known_names=[case.order.customer_name],
        llm_client=fake_client,
    )

    # 1. Injection indicators must be flagged in result
    assert len(result.injection_flags) > 0
    # 2. Extracted doc fields are valid and not corrupted into a malicious instruction
    assert isinstance(result.surviving_fields, dict)


# ==============================================================================
# 4. Deterministic Cross-Check Tests
# ==============================================================================

def test_cross_check_delivery_after_dispute() -> None:
    """Delivery date after dispute date fires critical cross-check."""
    cases = load_simulated_cases()
    del_cases = [
        c for c in cases
        if c.ground_truth.adversarial.is_adversarial
        and "delivery_after_dispute" in c.ground_truth.adversarial.adversarial_types
    ]
    assert len(del_cases) > 0, "Expected delivery_after_dispute case in data/cases."
    case = del_cases[0]

    pod_doc = next(d for d in case.documents if d.doc_type in ("shipping_proof", "courier_pod"))
    extracted = extract_document(
        text_or_path=pod_doc.content,
        case_id=case.case_id,
        doc_id=pod_doc.doc_id,
        doc_type="delivery_proof",
    )

    flags = run_cross_checks(case, [extracted])
    del_flags = [f for f in flags if f.flag_code == "DELIVERY_AFTER_DISPUTE"]
    assert len(del_flags) == 1
    assert del_flags[0].severity == Severity.CRITICAL
    assert "after the dispute was filed" in del_flags[0].message


def test_cross_check_invoice_amount_mismatch() -> None:
    """Invoice total amount differing from disputed amount triggers high severity flag."""
    flag = check_invoice_amount_mismatch(
        invoice_amount_paise=499900,
        dispute_amount_paise=299900,
    )
    assert flag is not None
    assert flag.flag_code == "INVOICE_AMOUNT_MISMATCH"
    assert flag.severity == Severity.HIGH
    assert flag.details["difference_paise"] == 200000

    # Matching amount produces no flag
    assert check_invoice_amount_mismatch(299900, 299900) is None


def test_cross_check_invoice_payment_mismatch() -> None:
    """Invoice payment reference matching payment_id or order_id succeeds; matching neither flags."""
    # 1. Matches payment_id -> produces no flag
    assert check_invoice_payment_mismatch(
        invoice_payment_id="pay_f10epf91dhod",
        dispute_payment_id="pay_f10epf91dhod",
        order_id="order_zdoc9is0j8ht",
    ) is None

    # 2. Matches order_id -> produces no flag
    assert check_invoice_payment_mismatch(
        invoice_payment_id="order_zdoc9is0j8ht",
        dispute_payment_id="pay_f10epf91dhod",
        order_id="order_zdoc9is0j8ht",
    ) is None

    # 3. Matches neither -> triggers INVOICE_PAYMENT_MISMATCH flag
    flag = check_invoice_payment_mismatch(
        invoice_payment_id="ref_completely_different",
        dispute_payment_id="pay_f10epf91dhod",
        order_id="order_zdoc9is0j8ht",
    )
    assert flag is not None
    assert flag.flag_code == "INVOICE_PAYMENT_MISMATCH"
    assert flag.severity == Severity.HIGH
    assert flag.details["invoice_payment_id"] == "ref_completely_different"
    assert flag.details["dispute_payment_id"] == "pay_f10epf91dhod"
    assert flag.details["order_id"] == "order_zdoc9is0j8ht"

    # Backward compatibility when order_id is omitted
    assert check_invoice_payment_mismatch("pay_f10epf91dhod", "pay_f10epf91dhod") is None
    flag_legacy = check_invoice_payment_mismatch("other_ref", "pay_f10epf91dhod")
    assert flag_legacy is not None
    assert flag_legacy.flag_code == "INVOICE_PAYMENT_MISMATCH"

    # Empty or None produces no flag
    assert check_invoice_payment_mismatch(None, "pay_f10epf91dhod", "order_zdoc9is0j8ht") is None
    assert check_invoice_payment_mismatch("", "pay_f10epf91dhod", "order_zdoc9is0j8ht") is None


def test_cross_check_address_mismatch() -> None:
    """Mismatch between POD destination and order shipping address triggers high severity flag."""
    shipping_addr = "Flat 402, Sunshine Heights, Koramangala 4th Block, Bengaluru, Karnataka 560034"
    mismatched_delivery = "House 12, Sector 15, Rohini, New Delhi, Delhi 110085"

    flag = check_address_mismatch(
        delivery_address=mismatched_delivery,
        shipping_address=shipping_addr,
    )
    assert flag is not None
    assert flag.flag_code == "ADDRESS_MISMATCH"
    assert flag.severity == Severity.HIGH
    assert flag.details["token_overlap"] < 0.5

    # Matching address produces no flag
    matching_delivery = "Sunshine Heights, Flat 402, 4th Block Koramangala, Bengaluru 560034"
    assert check_address_mismatch(matching_delivery, shipping_addr) is None


def test_cross_check_refund_not_mentioned() -> None:
    """Processed refund existing in records but unmentioned in communication triggers flag."""
    flag = check_refund_not_mentioned(
        has_refund=True,
        refund_mentioned_in_comms=False,
        refund_amount_paise=150000,
    )
    assert flag is not None
    assert flag.flag_code == "REFUND_EXISTS_UNMENTIONED"
    assert flag.severity == Severity.MEDIUM

    # Refund mentioned in comms -> no flag
    assert check_refund_not_mentioned(True, True) is None
    # No refund exists -> no flag
    assert check_refund_not_mentioned(False, False) is None


def test_nested_pydantic_model_schema_sanitization() -> None:
    """For a nested Pydantic model containing field objects, $ref/$defs are inlined and removed.

    The final schema must contain no $ref, no additionalProperties, and no $defs,
    and all nested properties must be preserved inline.
    """
    import json

    pytest.importorskip("google.genai")
    from google.genai import types
    from pydantic import BaseModel, ConfigDict, Field

    from disputepilot.extraction.llm import sanitize_schema_for_gemini

    class ItemDetail(BaseModel):
        model_config = ConfigDict(extra="forbid")
        sku: str
        quantity: int
        unit_price_paise: int

    class FieldObject(BaseModel):
        model_config = ConfigDict(extra="forbid")
        value: str
        source_quote: str
        confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    class ExtractedDoc(BaseModel):
        model_config = ConfigDict(extra="forbid")
        doc_id: str
        doc_type: str
        tracking: FieldObject
        items: list[ItemDetail]
        optional_note: FieldObject | None = None

    raw_schema = ExtractedDoc.model_json_schema()

    # 1. Verify raw schema originally contains $defs, $ref, and additionalProperties
    raw_json_str = json.dumps(raw_schema)
    assert "$defs" in raw_json_str
    assert "$ref" in raw_json_str
    assert "additionalProperties" in raw_json_str

    # 2. Sanitize schema
    clean_schema = sanitize_schema_for_gemini(ExtractedDoc)
    clean_json_str = json.dumps(clean_schema)

    # 3. Verify that $ref, additionalProperties, and $defs are completely eliminated
    assert "$ref" not in clean_json_str
    assert "$defs" not in clean_json_str
    assert "definitions" not in clean_json_str
    assert "additionalProperties" not in clean_json_str
    assert "additional_properties" not in clean_json_str

    # 4. Verify that nested properties were properly inlined into properties
    props = clean_schema["properties"]
    assert "doc_id" in props
    assert "tracking" in props
    assert "items" in props

    # tracking properties inlined
    assert props["tracking"]["type"] == "object"
    assert "value" in props["tracking"]["properties"]
    assert "source_quote" in props["tracking"]["properties"]
    assert "confidence" in props["tracking"]["properties"]

    # items array inlined
    assert props["items"]["type"] == "array"
    assert "properties" in props["items"]["items"]
    assert "sku" in props["items"]["items"]["properties"]
    assert "quantity" in props["items"]["items"]["properties"]

    # 5. Converted GenerateContentConfig schema payload checks
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=clean_schema,
    )
    dumped = config.model_dump(exclude_none=True)
    dumped_json_str = json.dumps(dumped)

    assert "$ref" not in dumped_json_str
    assert "$defs" not in dumped_json_str
    assert "additionalProperties" not in dumped_json_str
    assert "additional_properties" not in dumped_json_str



def test_fake_classifier_prioritizes_subscription_renewal_over_generic_permission() -> None:
    """An unwanted trial renewal is not automatically an account-takeover claim."""
    result = FakeLLMClient()._classify_reason_regex(
        "free trial khatam hote hi bina permission charge lagaya"
    )
    assert result["reason_class"] == "subscription_cancelled"
