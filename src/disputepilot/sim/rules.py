"""Documented winnability rules for simulated chargeback disputes.

Under card network dispute regulations (Visa Core Rules, Mastercard Dispute Resolution Rules,
and RuPay Operating Guidelines), a merchant can successfully contest a dispute if and only
if they provide specific required documentary evidence refuting the cardholder's claim.

Rules Summary:
--------------
1. item_not_received:
   - Winnable if 'shipping_proof' is present AND delivery date is on or before dispute date.
   - Unwinnable if shipping proof is absent or delivery date is after dispute date.

2. not_as_described:
   - Winnable if 'billing_proof' is present AND at least one of ('refund_cancellation_policy',
     'proof_of_service', 'customer_communication') is present.
   - Unwinnable otherwise.

3. unauthorised:
   - Winnable if 'billing_proof' (showing 3DS authentication) is present AND at least one
     of ('shipping_proof', 'proof_of_service', 'access_activity_log') is present.
   - Unwinnable otherwise.

4. duplicate_charge:
   - Winnable if 'billing_proof' is present showing distinct multi-order fulfillment,
     OR ('refund_confirmation' is present and a processed refund exists).
   - Unwinnable if charge was duplicate without refund proof.

5. subscription_cancelled:
   - Winnable if 'refund_cancellation_policy' is present AND at least one of
     ('access_activity_log' showing continued service usage, 'cancellation_proof'
     showing late cancellation request) is present.
   - Unwinnable if customer cancelled on time or merchant lacks terms/usage proof.

6. refund_not_received:
   - Winnable if and only if 'refund_confirmation' is present AND a processed refund record exists.
   - Unwinnable if refund is missing or pending/failed.

7. other:
   - Winnable if 'billing_proof' is present AND at least one of
     ('shipping_proof', 'proof_of_service', 'customer_communication') is present.
   - Unwinnable otherwise.
"""

from disputepilot.core.models import ReasonClass


def evaluate_winnability(
    reason_class: ReasonClass,
    available_evidence: list[str],
    has_processed_refund: bool = False,
    delivery_after_dispute: bool = False,
    is_distinct_order: bool = False,
) -> tuple[bool, str]:
    """Evaluate whether a dispute is winnable based on network rules.

    Args:
        reason_class: The 7-class dispute categorization.
        available_evidence: List of evidence keys available to the merchant.
        has_processed_refund: True if a refund was successfully processed with bank ARN.
        delivery_after_dispute: True if delivery date was recorded after dispute created date.
        is_distinct_order: True if merchant can prove two separate orders for duplicate claim.

    Returns:
        tuple[bool, str]: (winnable, explanation)
    """
    evidence_set = set(available_evidence)

    # Global disqualifier: Inconsistent delivery timeline for delivery-related disputes
    if delivery_after_dispute and reason_class in (
        ReasonClass.ITEM_NOT_RECEIVED,
        ReasonClass.NOT_AS_DESCRIBED,
    ):
        return (
            False,
            "Delivery timestamp is after the dispute date; merchant cannot prove timely fulfillment.",
        )

    if reason_class == ReasonClass.ITEM_NOT_RECEIVED:
        if "shipping_proof" in evidence_set and not delivery_after_dispute:
            return (
                True,
                "Valid courier proof of delivery with OTP/signature confirmed prior to dispute.",
            )
        return (
            False,
            "Missing courier proof of delivery or fulfillment unverified before dispute inception.",
        )

    if reason_class == ReasonClass.NOT_AS_DESCRIBED:
        has_billing = "billing_proof" in evidence_set
        has_policy_or_support = bool(
            evidence_set.intersection(
                {"refund_cancellation_policy", "proof_of_service", "customer_communication"}
            )
        )
        if has_billing and has_policy_or_support:
            return (
                True,
                "Detailed invoice confirms item specifications and policy/communication refutes defect claim.",
            )
        return (
            False,
            "Insufficient evidence proving product specifications and customer adherence to return terms.",
        )

    if reason_class == ReasonClass.UNAUTHORISED:
        has_billing_auth = "billing_proof" in evidence_set
        has_usage_or_delivery = bool(
            evidence_set.intersection({"shipping_proof", "proof_of_service", "access_activity_log"})
        )
        if has_billing_auth and has_usage_or_delivery:
            return (
                True,
                "3D-Secure authentication logs match cardholder details with verified delivery/activity.",
            )
        return (
            False,
            "Missing 3DS authentication records or delivery link to cardholder.",
        )

    if reason_class == ReasonClass.DUPLICATE_CHARGE:
        if is_distinct_order and "billing_proof" in evidence_set:
            return (
                True,
                "Documented separate orders and invoices confirm distinct legitimate transactions.",
            )
        if "refund_confirmation" in evidence_set and has_processed_refund:
            return (
                True,
                "Second charge was already refunded to cardholder with bank ARN confirmation.",
            )
        return (
            False,
            "Duplicate transaction unrefunded without proof of separate legitimate fulfillment.",
        )

    if reason_class == ReasonClass.SUBSCRIPTION_CANCELLED:
        has_policy = "refund_cancellation_policy" in evidence_set
        has_proof = bool(
            evidence_set.intersection({"access_activity_log", "cancellation_proof"})
        )
        if has_policy and has_proof:
            return (
                True,
                "Service access logs show active usage post-billing or cancellation requested outside SLA window.",
            )
        return (
            False,
            "Merchant failed to prove ongoing service usage or customer acknowledgement of renewal window.",
        )

    if reason_class == ReasonClass.REFUND_NOT_RECEIVED:
        if "refund_confirmation" in evidence_set and has_processed_refund:
            return (
                True,
                "Merchant successfully processed refund with traceable bank ARN reference.",
            )
        return (
            False,
            "No verified bank refund record found for customer's transaction.",
        )

    if reason_class == ReasonClass.OTHER:
        has_billing = "billing_proof" in evidence_set
        has_support = bool(
            evidence_set.intersection(
                {"shipping_proof", "proof_of_service", "customer_communication"}
            )
        )
        if has_billing and has_support:
            return (
                True,
                "Sufficient composite documentation of transaction legitimacy and fulfillment.",
            )
        return (
            False,
            "Insufficient documentation to counter general dispute inquiry.",
        )

    return False, "Default rule: insufficient documentary evidence."
