"""Ambiguous single words must not produce confident rule matches (they go to the LLM or a human)."""

from disputepilot.core.reasons import classify_reason


def test_fake_in_unrelated_context_is_not_a_confident_match():
    text = "ARN number fake nikla bank bola koi refund nahi aaya"
    assert classify_reason(text).reason_class.value == "unclassified"


def test_duplicate_meaning_a_copied_product_is_not_a_duplicate_charge():
    text = "jo picture me tha wo nahi bheja duplicate piece lag raha"
    assert classify_reason(text).reason_class.value == "unclassified"


def test_explicit_duplicate_charge_still_matches():
    text = "Customer reports a duplicate charge on the same order"
    assert classify_reason(text).reason_class.value == "duplicate_charge"


def test_explicit_fake_product_still_matches():
    text = "The buyer says it is a fake product"
    assert classify_reason(text).reason_class.value == "not_as_described"
