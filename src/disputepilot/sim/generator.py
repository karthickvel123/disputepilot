"""Synthetic dispute case generator adhering to Razorpay Disputes schemas."""

import random

from disputepilot.core.models import (
    AdversarialInfo,
    DisputeCase,
    DisputePhase,
    DisputeStatus,
    EvidenceDocument,
    GroundTruth,
    Order,
    OrderItem,
    RazorpayDispute,
    RazorpayEvidence,
    ReasonClass,
    Refund,
)
from disputepilot.sim.rules import evaluate_winnability
from disputepilot.sim.templates import (
    generate_access_log_md,
    generate_cancellation_policy_md,
    generate_courier_pod_md,
    generate_customer_chat_md,
    generate_invoice_md,
    generate_refund_receipt_md,
)

REASON_CODES: dict[ReasonClass, list[str]] = {
    ReasonClass.ITEM_NOT_RECEIVED: ["13.1", "4855", "merchandise_not_received", "INR_101"],
    ReasonClass.NOT_AS_DESCRIBED: ["13.3", "4853", "not_as_described", "INR_103"],
    ReasonClass.UNAUTHORISED: ["10.4", "4837", "fraud_card_not_present", "INR_104"],
    ReasonClass.DUPLICATE_CHARGE: ["12.6", "4834", "duplicate_processing", "INR_106"],
    ReasonClass.SUBSCRIPTION_CANCELLED: ["13.7", "4841", "cancelled_recurring", "INR_107"],
    ReasonClass.REFUND_NOT_RECEIVED: ["13.6", "4860", "credit_not_processed", "INR_108"],
    ReasonClass.OTHER: ["general_inquiry", "retrieval_request", "other_dispute"],
}

CARRIERS = ["Blue Dart Express", "Delhivery Logistics", "Shadowfax", "DTDC Courier"]

CITIES_STATES = [
    ("Bengaluru", "Karnataka", "560103"),
    ("Mumbai", "Maharashtra", "400050"),
    ("New Delhi", "Delhi", "110001"),
    ("Hyderabad", "Telangana", "500081"),
    ("Chennai", "Tamil Nadu", "600028"),
    ("Pune", "Maharashtra", "411014"),
    ("Kolkata", "West Bengal", "700016"),
    ("Ahmedabad", "Gujarat", "380015"),
]

CUSTOMER_NAMES = [
    "Priya Sharma",
    "Arjun Patel",
    "Rohan Gupta",
    "Ananya Rao",
    "Vikram Singh",
    "Deepika Nair",
    "Aditya Joshi",
    "Neha Kulkarni",
    "Kavita Reddy",
    "Siddharth Menon",
    "Pooja Verma",
    "Manish Tiwari",
]

PRODUCTS = [
    ("Wireless ANC Headphones Pro", 299900),
    ("Mechanical Gaming Keyboard", 450000),
    ("Ergonomic Mesh Office Chair", 899900),
    ("Smart Fitness Watch v3", 349900),
    ("USB-C Fast Charging Hub 100W", 189900),
    ("Monthly Cloud SaaS Subscription", 149900),
    ("4K HDR Computer Monitor 27in", 1799900),
    ("Wireless Bluetooth Earbuds", 199900),
]


class CaseGenerator:
    """Deterministic generator for synthetic chargeback dispute cases."""

    def __init__(self, seed: int = 42, base_timestamp: int = 1710000000) -> None:
        """Initialize generator with fixed seed and base unix timestamp.

        Args:
            seed: Pseudo-random seed for determinism.
            base_timestamp: Base unix epoch seconds (default ~March 2024).
        """
        self.seed = seed
        self.rng = random.Random(seed)
        self.base_timestamp = base_timestamp

    def _rand_id(self, prefix: str) -> str:
        chars = "abcdefghijklmnopqrstuvwxyz0123456789"
        val = "".join(self.rng.choice(chars) for _ in range(14))
        return f"{prefix}_{val}"

    def generate_case(self, case_index: int, total_cases: int) -> DisputeCase:
        """Generate a single realistic synthetic dispute case.

        Args:
            case_index: 0-indexed index of the case.
            total_cases: Total number of cases being generated.

        Returns:
            DisputeCase model instance.
        """
        case_id = f"disp_{case_index + 1:04d}_{self._rand_id('c')[2:8]}"
        payment_id = self._rand_id("pay")
        order_id = self._rand_id("order")

        # Cycle reason_class to guarantee balanced distribution across the 7 classes
        all_classes = [c for c in ReasonClass if c != ReasonClass.UNCLASSIFIED]
        reason_class = all_classes[case_index % len(all_classes)]

        # Time offsets in seconds
        order_time = self.base_timestamp + (case_index * 86400) + self.rng.randint(3600, 43200)
        # Normal delivery 2 to 5 days after order
        normal_delivery_time = order_time + self.rng.randint(2 * 86400, 5 * 86400)
        # Dispute raised 8 to 20 days after order
        dispute_time = order_time + self.rng.randint(8 * 86400, 20 * 86400)
        # Response deadline 7 to 10 days after dispute
        respond_by = dispute_time + self.rng.randint(7 * 86400, 10 * 86400)

        # Target approximately 10% adversarial cases
        is_adversarial = (case_index % 10 == 7) or (case_index % 10 == 3 and case_index < 20)
        adversarial_types: list[str] = []
        adv_details: list[str] = []

        delivery_after_dispute = False
        include_prompt_injection = False
        include_card_number = False

        if is_adversarial:
            adv_choice = case_index % 3
            if adv_choice == 0:
                include_prompt_injection = True
                adversarial_types.append("prompt_injection")
                adv_details.append("Customer chat transcript contains a prompt-injection string.")
            elif adv_choice == 1:
                include_card_number = True
                adversarial_types.append("card_number")
                adv_details.append("Evidence document contains a card-number-like string.")
            else:
                delivery_after_dispute = True
                adversarial_types.append("delivery_after_dispute")
                adv_details.append("Courier POD delivery date is recorded after dispute date.")

        delivered_at: int | None = None
        if delivery_after_dispute:
            delivered_at = dispute_time + (3 * 86400)
        elif reason_class not in (ReasonClass.SUBSCRIPTION_CANCELLED, ReasonClass.DUPLICATE_CHARGE):
            delivered_at = normal_delivery_time

        # Customer & Product details
        customer_name = self.rng.choice(CUSTOMER_NAMES)
        first, last = customer_name.lower().split()
        customer_email = f"{first}.{last}@{self.rng.choice(['example.com', 'mail.in', 'webmail.in'])}"
        customer_phone = f"+9198{self.rng.randint(10000000, 99999999)}"
        city, state, pin = self.rng.choice(CITIES_STATES)
        address = f"Flat {self.rng.randint(101, 804)}, Sector {self.rng.randint(1, 15)}, {city}, {state} {pin}"

        prod_name, prod_amount = self.rng.choice(PRODUCTS)
        qty = self.rng.choice([1, 1, 1, 2])
        total_amount = prod_amount * qty

        order_item = OrderItem(name=prod_name, quantity=qty, amount=prod_amount)
        tracking_no = f"TRK-{self.rng.choice(['BD', 'DL', 'SF', 'DT'])}-{self.rng.randint(10000000, 99999999)}"
        carrier = self.rng.choice(CARRIERS)

        order = Order(
            id=order_id,
            amount=total_amount,
            currency="INR",
            status="paid",
            created_at=order_time,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            shipping_address=address,
            items=[order_item],
            tracking_number=tracking_no,
            delivered_at=delivered_at,
        )

        # Decide whether to simulate a refund
        refund: Refund | None = None
        has_processed_refund = False
        is_distinct_order = False

        if reason_class == ReasonClass.REFUND_NOT_RECEIVED:
            # 50% chance refund was actually processed (winnable), 50% chance not processed
            if case_index % 2 == 0:
                refund_time = order_time + (4 * 86400)
                arn = f"ARN{self.rng.randint(100000000000, 999999999999)}"
                refund = Refund(
                    id=self._rand_id("rfnd"),
                    payment_id=payment_id,
                    amount=total_amount,
                    currency="INR",
                    status="processed",
                    created_at=refund_time,
                    arn=arn,
                )
                has_processed_refund = True
        elif reason_class == ReasonClass.DUPLICATE_CHARGE:
            # 50% winnable: 25% refunded, 25% distinct orders, 50% true accidental duplicate
            if case_index % 4 == 0:
                is_distinct_order = True
            elif case_index % 4 == 2:
                refund_time = order_time + (2 * 86400)
                arn = f"ARN{self.rng.randint(100000000000, 999999999999)}"
                refund = Refund(
                    id=self._rand_id("rfnd"),
                    payment_id=payment_id,
                    amount=total_amount,
                    currency="INR",
                    status="processed",
                    created_at=refund_time,
                    arn=arn,
                )
                has_processed_refund = True
        elif self.rng.random() < 0.10:
            # Sporadic refund in other classes
            refund_time = order_time + (5 * 86400)
            arn = f"ARN{self.rng.randint(100000000000, 999999999999)}"
            refund = Refund(
                id=self._rand_id("rfnd"),
                payment_id=payment_id,
                amount=total_amount,
                currency="INR",
                status="processed",
                created_at=refund_time,
                arn=arn,
            )
            has_processed_refund = True

        # Determine evidence categories genuinely available (1 to 3 documents)
        available_evidence, documents = self._generate_documents(
            case_id=case_id,
            order=order,
            payment_id=payment_id,
            reason_class=reason_class,
            delivered_at=delivered_at,
            carrier=carrier,
            tracking_no=tracking_no,
            dispute_time=dispute_time,
            refund=refund,
            has_processed_refund=has_processed_refund,
            delivery_after_dispute=delivery_after_dispute,
            include_prompt_injection=include_prompt_injection,
            include_card_number=include_card_number,
            case_index=case_index,
        )

        # Evaluate winnability rule
        winnable, rule_explanation = evaluate_winnability(
            reason_class=reason_class,
            available_evidence=available_evidence,
            has_processed_refund=has_processed_refund,
            delivery_after_dispute=delivery_after_dispute,
            is_distinct_order=is_distinct_order,
        )

        ground_truth = GroundTruth(
            reason_class=reason_class,
            available_evidence=available_evidence,
            winnable=winnable,
            rule_explanation=rule_explanation,
            adversarial=AdversarialInfo(
                is_adversarial=is_adversarial,
                adversarial_types=adversarial_types,
                details=adv_details,
            ),
        )

        # Populate RazorpayEvidence object with document paths
        evidence_obj = RazorpayEvidence()
        for doc in documents:
            if hasattr(evidence_obj, doc.doc_type):
                curr = getattr(evidence_obj, doc.doc_type)
                setattr(evidence_obj, doc.doc_type, curr + [doc.file_path])

        reason_code = self.rng.choice(REASON_CODES[reason_class])
        phase = self.rng.choice([DisputePhase.CHARGEBACK, DisputePhase.RETRIEVAL, DisputePhase.PRE_ARBITRATION])

        dispute = RazorpayDispute(
            id=case_id,
            payment_id=payment_id,
            amount=total_amount,
            currency="INR",
            amount_deducted=0,
            reason_code=reason_code,
            phase=phase,
            status=DisputeStatus.OPEN,
            respond_by=respond_by,
            created_at=dispute_time,
            evidence=evidence_obj,
        )

        return DisputeCase(
            case_id=case_id,
            dispute=dispute,
            order=order,
            refund=refund,
            ground_truth=ground_truth,
            documents=documents,
            metadata={"seed": self.seed, "case_index": case_index},
        )

    def _generate_documents(
        self,
        case_id: str,
        order: Order,
        payment_id: str,
        reason_class: ReasonClass,
        delivered_at: int | None,
        carrier: str,
        tracking_no: str,
        dispute_time: int,
        refund: Refund | None,
        has_processed_refund: bool,
        delivery_after_dispute: bool,
        include_prompt_injection: bool,
        include_card_number: bool,
        case_index: int,
    ) -> tuple[list[str], list[EvidenceDocument]]:
        """Generate 1 to 3 realistic evidence documents for the case."""
        documents: list[EvidenceDocument] = []
        available_categories: list[str] = []

        # Candidate doc builders based on reason class and case state
        doc_candidates: list[tuple[str, str, str]] = []  # (doc_type, file_name, content)
        card_number_added = False

        # 1. Billing proof (Invoice)
        has_invoice = False
        if reason_class in (ReasonClass.NOT_AS_DESCRIBED, ReasonClass.UNAUTHORISED, ReasonClass.OTHER):
            has_invoice = (case_index % 2 == 0)
        elif reason_class == ReasonClass.DUPLICATE_CHARGE:
            has_invoice = (case_index % 4 == 0)
        elif reason_class == ReasonClass.ITEM_NOT_RECEIVED:
            has_invoice = (case_index % 3 == 0)
        else:
            has_invoice = (case_index % 2 == 0)

        if has_invoice:
            inv_card = include_card_number and not card_number_added
            if inv_card:
                card_number_added = True
            inv_content = generate_invoice_md(
                invoice_number=f"INV-2024-{case_index + 1000:05d}",
                order_id=order.id,
                payment_id=payment_id,
                created_at=order.created_at,
                customer_name=order.customer_name,
                customer_email=order.customer_email,
                customer_phone=order.customer_phone,
                shipping_address=order.shipping_address,
                items=[{"name": itm.name, "quantity": itm.quantity, "amount": itm.amount} for itm in order.items],
                total_amount_paise=order.amount,
                include_card_number=inv_card,
            )
            doc_candidates.append(("billing_proof", "invoice.md", inv_content))

        # 2. Shipping proof (Courier POD)
        has_shipping = False
        if delivery_after_dispute:
            has_shipping = True
        elif reason_class == ReasonClass.ITEM_NOT_RECEIVED:
            has_shipping = (case_index % 2 == 0)
        elif reason_class in (ReasonClass.UNAUTHORISED, ReasonClass.OTHER) and case_index % 4 == 0:
            has_shipping = True

        if has_shipping and delivered_at:
            pod_card = include_card_number and not card_number_added
            if pod_card:
                card_number_added = True
            pod_content = generate_courier_pod_md(
                tracking_number=tracking_no,
                carrier=carrier,
                recipient_name=order.customer_name,
                address=order.shipping_address,
                delivered_at=delivered_at,
                order_id=order.id,
                include_card_number=pod_card,
            )
            doc_candidates.append(("shipping_proof", "courier_proof_of_delivery.md", pod_content))

        # 3. Customer communication (Chat transcript)
        has_chat = include_prompt_injection or (case_index % 3 == 1)
        if has_chat:
            chat_card = include_card_number and not card_number_added
            if chat_card:
                card_number_added = True
            chat_content = generate_customer_chat_md(
                ticket_id=f"TIK-{case_index + 5000:05d}",
                customer_name=order.customer_name,
                created_at=order.created_at + 86400,
                order_id=order.id,
                issue_type=reason_class.value,
                include_prompt_injection=include_prompt_injection,
                include_card_number=chat_card,
            )
            doc_candidates.append(("customer_communication", "customer_chat.md", chat_content))

        # 4. Cancellation & Refund Policy
        has_policy = False
        if reason_class in (ReasonClass.SUBSCRIPTION_CANCELLED, ReasonClass.NOT_AS_DESCRIBED):
            has_policy = (case_index % 2 == 0)
        elif case_index % 5 == 0:
            has_policy = True

        if has_policy:
            policy_content = generate_cancellation_policy_md(
                merchant_name="Apex Retail Solutions Private Limited"
            )
            doc_candidates.append(("refund_cancellation_policy", "cancellation_policy.md", policy_content))

        # 5. Refund confirmation (Receipt)
        if refund and refund.arn and has_processed_refund:
            rfnd_content = generate_refund_receipt_md(
                refund_id=refund.id,
                payment_id=payment_id,
                amount_paise=refund.amount,
                created_at=refund.created_at,
                arn=refund.arn,
                status=refund.status,
            )
            doc_candidates.append(("refund_confirmation", "refund_receipt.md", rfnd_content))

        # 6. Access Activity Log (for subscription / unauthorised)
        if reason_class in (ReasonClass.SUBSCRIPTION_CANCELLED, ReasonClass.UNAUTHORISED) and case_index % 2 == 0:
            timestamps = [
                order.created_at + (i * 86400)
                for i in range(1, 5)
            ]
            log_content = generate_access_log_md(
                customer_name=order.customer_name,
                customer_email=order.customer_email,
                payment_id=payment_id,
                timestamps=timestamps,
            )
            doc_candidates.append(("access_activity_log", "access_activity_log.md", log_content))

        # Ensure card number is added if case is adversarial with card_number
        if include_card_number and not card_number_added:
            chat_content = generate_customer_chat_md(
                ticket_id=f"TIK-{case_index + 5000:05d}",
                customer_name=order.customer_name,
                created_at=order.created_at + 86400,
                order_id=order.id,
                issue_type=reason_class.value,
                include_prompt_injection=False,
                include_card_number=True,
            )
            doc_candidates.append(("customer_communication", "customer_chat.md", chat_content))
            card_number_added = True

        # Ensure between 1 and 3 documents per case
        if not doc_candidates:
            # Default single document fallback
            chat_content = generate_customer_chat_md(
                ticket_id=f"TIK-{case_index + 5000:05d}",
                customer_name=order.customer_name,
                created_at=order.created_at + 86400,
                order_id=order.id,
                issue_type=reason_class.value,
                include_prompt_injection=include_prompt_injection,
                include_card_number=include_card_number,
            )
            doc_candidates.append(("customer_communication", "customer_chat.md", chat_content))

        # Cap at 3 documents maximum
        selected_candidates = doc_candidates[:3]

        for idx, (doc_type, file_name, content) in enumerate(selected_candidates):
            doc_id = f"doc_{case_id[5:]}_{idx + 1}"
            rel_path = f"{case_id}/{file_name}"
            documents.append(
                EvidenceDocument(
                    doc_id=doc_id,
                    doc_type=doc_type,
                    file_name=file_name,
                    file_path=rel_path,
                    content=content,
                )
            )
            if doc_type not in available_categories:
                available_categories.append(doc_type)

        return available_categories, documents


def generate_cases(n: int = 150, seed: int = 42) -> list[DisputeCase]:
    """Generate n synthetic dispute cases deterministically.

    Args:
        n: Number of cases to generate (default 150).
        seed: Random seed for reproducibility.

    Returns:
        List of DisputeCase objects.
    """
    generator = CaseGenerator(seed=seed)
    return [generator.generate_case(i, n) for i in range(n)]
