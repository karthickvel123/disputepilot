import logging
from typing import Any

from disputepilot.agent.models import EvidenceReport
from disputepilot.agent.tools import ReadOnlyToolRegistry
from disputepilot.core.evidence import CategoryStatus, EvidenceRole, audit_evidence
from disputepilot.core.reasons import ReasonClass, classify_reason
from disputepilot.extraction.cross_checks import run_cross_checks
from disputepilot.extraction.extractor import ExtractedDocument
from disputepilot.extraction.llm import LLMClient, get_llm_client

logger = logging.getLogger("disputepilot.agent.orchestrator")

RAZORPAY_EVIDENCE_CATEGORIES = [
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
]


class EvidenceAgent:
    """Bounded, read-only orchestrator for evidence discovery, classification, and audit."""

    def __init__(
        self,
        tool_registry: ReadOnlyToolRegistry,
        llm_client: LLMClient | None = None,
        max_steps: int = 10,
        rule_only_reasons: bool = False,
    ) -> None:
        self.tools = tool_registry
        self.llm = llm_client or get_llm_client()
        self.max_steps = max_steps
        self.rule_only_reasons = rule_only_reasons

    def audit_case(self, case_id: str) -> EvidenceReport:
        """Run bounded evidence audit over a dispute case using read-only tools."""
        steps_taken = 0
        tool_calls: list[str] = []

        def call(name: str, **kwargs: Any) -> Any:
            nonlocal steps_taken
            steps_taken += 1
            tool_calls.append(f"{name}({kwargs})")
            return self.tools.execute_tool(name, **kwargs)

        # 1. Fetch Dispute
        dispute_dict = call("get_dispute", case_id=case_id)
        if steps_taken >= self.max_steps:
            return self._build_early_exit_report(case_id, steps_taken, tool_calls)

        # 2. Fetch Order
        order_dict = call("get_order", case_id=case_id)
        if steps_taken >= self.max_steps:
            return self._build_early_exit_report(case_id, steps_taken, tool_calls)

        # 3. Fetch Refund
        call("get_refund", case_id=case_id)
        if steps_taken >= self.max_steps:
            return self._build_early_exit_report(case_id, steps_taken, tool_calls)

        # 4. List Documents
        doc_list = call("list_documents", case_id=case_id)
        if steps_taken >= self.max_steps:
            return self._build_early_exit_report(case_id, steps_taken, tool_calls)

        # 5. Classify Reason Class
        reason_input = dispute_dict.get("reason_code") or dispute_dict.get("reason_description") or ""
        reason_res = classify_reason(reason_input, llm_client=None if self.rule_only_reasons else self.llm)
        reason_class: ReasonClass = reason_res.reason_class

        # 6. Extract documents and map to Razorpay categories
        extracted_docs: list[ExtractedDocument] = []
        category_docs: dict[str, list[str]] = {cat: [] for cat in RAZORPAY_EVIDENCE_CATEGORIES}
        category_confidences: dict[str, list[float]] = {cat: [] for cat in RAZORPAY_EVIDENCE_CATEGORIES}

        for doc in doc_list:
            if steps_taken >= self.max_steps:
                logger.warning(
                    "Evidence agent reached hard step limit (%d) for case '%s'. Halting tool loop.",
                    self.max_steps,
                    case_id,
                )
                break

            doc_id = doc["doc_id"]
            extracted_dict = call("get_extracted_doc", case_id=case_id, doc_id=doc_id)
            if not extracted_dict:
                continue

            extracted_obj = ExtractedDocument.model_validate(extracted_dict)
            extracted_docs.append(extracted_obj)

            # Map to Razorpay category
            category = self._map_to_category(doc, extracted_obj)
            category_docs[category].append(doc_id)

            # Compute field confidences
            for field in extracted_obj.surviving_fields.values():
                if hasattr(field, "confidence"):
                    category_confidences[category].append(field.confidence)
                elif isinstance(field, dict) and "confidence" in field:
                    category_confidences[category].append(field["confidence"])

        # Compute average extraction confidence per category
        avg_confidence: dict[str, float] = {}
        for cat, confs in category_confidences.items():
            if confs:
                avg_confidence[cat] = round(sum(confs) / len(confs), 2)
            elif category_docs[cat]:
                avg_confidence[cat] = 0.90

        # 7. Core evidence audit
        audit_res = audit_evidence(
            reason_class=reason_class,
            available_evidence=category_docs,
        )

        category_status: dict[str, str] = {
            cat: eval_obj.status.value for cat, eval_obj in audit_res.categories.items()
        }

        # 8. Cross-check discrepancies
        # Reconstruct case for cross-check auditing
        case_obj = self.tools._resolve_case(case_id)
        cross_check_flags = run_cross_checks(case_obj, extracted_docs)

        # If delivery is after dispute date, degrade shipping_proof to partial
        if (
            any(f.flag_code == "DELIVERY_AFTER_DISPUTE" for f in cross_check_flags)
            and category_status.get("shipping_proof") == CategoryStatus.PRESENT.value
        ):
            category_status["shipping_proof"] = CategoryStatus.PARTIAL.value

        # 9. Generate specific asks for missing items
        specific_asks: dict[str, str] = {}
        for cat_name, eval_obj in audit_res.categories.items():
            if eval_obj.status == CategoryStatus.MISSING and eval_obj.role in (
                EvidenceRole.REQUIRED,
                EvidenceRole.HELPFUL,
            ):
                ask = self._generate_specific_ask(cat_name, order_dict, dispute_dict)
                specific_asks[cat_name] = ask

        return EvidenceReport(
            case_id=case_id,
            reason_class=reason_class.value,
            category_status=category_status,
            category_documents={k: v for k, v in category_docs.items() if v},
            extraction_confidence=avg_confidence,
            cross_check_flags=cross_check_flags,
            specific_asks=specific_asks,
            steps_taken=steps_taken,
            tool_calls=tool_calls,
        )

    def _map_to_category(self, doc_info: dict[str, Any], extracted: ExtractedDocument) -> str:
        """Map document to Razorpay evidence category using deterministic rules first, then LLM."""
        doc_type = doc_info.get("doc_type", "").lower()
        file_name = doc_info.get("file_name", "").lower()

        # Deterministic rules
        if any(kw in doc_type or kw in file_name for kw in ["shipping", "pod", "delivery", "courier"]):
            return "shipping_proof"
        if any(kw in doc_type or kw in file_name for kw in ["invoice", "billing", "bill", "receipt"]):
            return "billing_proof"
        if any(kw in doc_type or kw in file_name for kw in ["chat", "communication", "ticket", "email"]):
            return "customer_communication"
        if any(kw in doc_type or kw in file_name for kw in ["policy", "return_policy", "cancellation_policy"]):
            return "refund_cancellation_policy"
        if any(kw in doc_type or kw in file_name for kw in ["refund_confirmation", "arn", "credit_note"]):
            return "refund_confirmation"
        if any(kw in doc_type or kw in file_name for kw in ["service", "timesheet", "completion"]):
            return "proof_of_service"
        if any(kw in doc_type or kw in file_name for kw in ["activity", "login", "access_log"]):
            return "access_activity_log"
        if any(kw in doc_type or kw in file_name for kw in ["cancellation_proof", "cancel_request"]):
            return "cancellation_proof"
        if any(kw in doc_type or kw in file_name for kw in ["explanation", "cover_letter"]):
            return "explanation_letter"

        # Fallback to LLM categorization if deterministic rules cannot place the document
        return self._categorize_with_llm(doc_info, extracted)

    def _categorize_with_llm(self, doc_info: dict[str, Any], extracted: ExtractedDocument) -> str:
        """Use LLM to categorize ambiguous documents into Razorpay categories."""
        prompt = (
            f"Classify this evidence document into exactly ONE of the following categories:\n"
            f"{RAZORPAY_EVIDENCE_CATEGORIES}\n\n"
            f"Document Info: {doc_info}\n"
            f"Extracted Sample: {extracted.clean_text[:500]}\n\n"
            f"Respond with JSON: {{\"category\": \"category_name\"}}"
        )
        try:
            res = self.llm.generate_json(
                system="You categorize evidence documents into standard Razorpay chargeback categories.",
                user=prompt,
                json_schema={"type": "object", "properties": {"category": {"type": "string"}}},
            )
            cat = res.get("category", "others").lower().strip()
            return cat if cat in RAZORPAY_EVIDENCE_CATEGORIES else "others"
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            logger.debug("LLM document categorization failed: %s", exc)
            return "others"

    def _generate_specific_ask(
        self,
        category: str,
        order: dict[str, Any] | None,
        dispute: dict[str, Any] | None,
    ) -> str:
        """Generate tailored, actionable missing evidence request string."""
        tracking = order.get("tracking_number") if order else None
        order_id = order.get("id") if order else None
        customer_name = order.get("customer_name") if order else None
        payment_id = dispute.get("payment_id") if dispute else None

        if category == "shipping_proof":
            if tracking:
                return (
                    f"Upload courier proof of delivery for tracking/AWB {tracking} "
                    f"with delivery timestamp and recipient signature or OTP verification."
                )
            return "Upload courier proof of delivery (POD) confirming package delivery with recipient signature or OTP verification."

        if category == "billing_proof":
            if order_id:
                return f"Upload official tax invoice or itemized customer bill for order {order_id}."
            return "Upload official tax invoice or itemized billing receipt."

        if category == "customer_communication":
            if customer_name:
                return f"Upload customer support chat transcripts or email correspondence with customer {customer_name}."
            return "Upload customer communication records showing dispute or return discussions."

        if category == "refund_confirmation":
            if payment_id:
                return f"Upload bank ARN receipt or refund transaction confirmation for payment {payment_id}."
            return "Upload bank ARN receipt or refund transaction confirmation."

        if category == "refund_cancellation_policy":
            return "Upload merchant return & cancellation policy agreed to by customer at checkout."

        if category == "proof_of_service":
            if order_id:
                return f"Upload service delivery report or completion sign-off certificate for order {order_id}."
            return "Upload proof of service completion or digital delivery log."

        if category == "access_activity_log":
            email = order.get("customer_email") if order else "customer"
            return f"Upload account access logs or IP login audit history for {email}."

        if category == "cancellation_proof":
            return "Upload cancellation confirmation or proof showing customer did not cancel within allowed window."

        return f"Upload supporting merchant documentation for '{category}'."

    def _build_early_exit_report(
        self,
        case_id: str,
        steps_taken: int,
        tool_calls: list[str],
    ) -> EvidenceReport:
        """Construct a minimal report when execution is stopped by step limit."""
        return EvidenceReport(
            case_id=case_id,
            reason_class=ReasonClass.OTHER.value,
            category_status={},
            category_documents={},
            extraction_confidence={},
            cross_check_flags=[],
            specific_asks={},
            steps_taken=steps_taken,
            tool_calls=tool_calls,
        )
