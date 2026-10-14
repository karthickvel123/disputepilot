"""LLM client interface, Gemini integration, and FakeLLMClient for offline testing."""

import json
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("disputepilot.extraction.llm")


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for structured JSON generation via Large Language Models."""

    def generate_json(
        self,
        system: str,
        user: str,
        json_schema: dict[str, Any] | type,
    ) -> dict[str, Any]:
        """Generate structured JSON output adhering to a given schema.

        Args:
            system: System instructions.
            user: User input / wrapped document content.
            json_schema: Target schema dict or Pydantic model class.

        Returns:
            Dictionary matching the requested JSON structure.
        """
        ...


class GeminiClient:
    """Official Gemini client using the Google GenAI SDK (`google-genai`)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.5-flash",
        raw_output_path: Path | str | None = None,
    ) -> None:
        from google import genai

        resolved_key = api_key or os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise ValueError("GeminiClient requires LLM_API_KEY or GEMINI_API_KEY to be set.")

        self.client = genai.Client(api_key=resolved_key)
        self.model = model
        self.raw_output_path = Path(raw_output_path) if raw_output_path else None
        self.call_logs: list[dict[str, Any]] = []

    def generate_json(
        self,
        system: str,
        user: str,
        json_schema: dict[str, Any] | type,
    ) -> dict[str, Any]:
        """Call Gemini API requesting structured JSON output with exponential backoff on rate limits."""
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=json_schema,
            temperature=0.0,
        )

        max_retries = 5
        base_delay = 2.0
        start_time = time.perf_counter()
        last_error = None

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=user,
                    config=config,
                )
                latency = round(time.perf_counter() - start_time, 4)
                text = response.text or "{}"
                parsed_json = json.loads(text)

                usage = getattr(response, "usage_metadata", None)
                prompt_tokens = getattr(usage, "prompt_token_count", None) if usage else None
                candidates_tokens = getattr(usage, "candidates_token_count", None) if usage else None
                total_tokens = getattr(usage, "total_token_count", None) if usage else None

                log_entry = {
                    "timestamp": time.time(),
                    "model": self.model,
                    "latency_seconds": latency,
                    "tokens": {
                        "prompt_tokens": prompt_tokens,
                        "candidates_tokens": candidates_tokens,
                        "total_tokens": total_tokens,
                    },
                    "prompt": {"system": system, "user": user},
                    "raw_response": text,
                    "parsed_response": parsed_json,
                }
                self.call_logs.append(log_entry)

                if self.raw_output_path:
                    self.raw_output_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.raw_output_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(log_entry) + "\n")

                return parsed_json

            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                is_rate_limit = (
                    "429" in err_str
                    or "resourceexhausted" in err_str
                    or "quota" in err_str
                    or "rate" in err_str
                )
                if is_rate_limit and attempt < max_retries - 1:
                    sleep_time = min(60.0, base_delay * (2 ** attempt)) + random.uniform(0.1, 1.0)
                    logger.warning(
                        "Gemini rate limit encountered. Backing off for %.2fs (attempt %d/%d)...",
                        sleep_time,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(sleep_time)
                else:
                    logger.error("Gemini API call failed on attempt %d: %s", attempt + 1, e)
                    if not is_rate_limit:
                        raise

        if last_error:
            raise last_error
        return {}


class FakeLLMClient:
    """Deterministic, offline Fake LLM client for tests and simulated workflows.

    Returns canned responses keyed by document type, or parses realistic fields
    directly from document text so that source_quotes are verbatim.
    """

    def __init__(
        self,
        canned_responses: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._canned: dict[str, dict[str, Any]] = canned_responses or {}
        self._default_response: dict[str, Any] | None = None

    def set_canned_response(self, doc_type: str, response: dict[str, Any]) -> None:
        """Register a canned response for a specific document type."""
        self._canned[doc_type] = response

    def set_default_response(self, response: dict[str, Any]) -> None:
        """Set a default response returned for any document type."""
        self._default_response = response

    def generate_json(
        self,
        system: str,
        user: str,
        json_schema: dict[str, Any] | type,
    ) -> dict[str, Any]:
        """Generate structured response deterministically without network calls."""
        if self._default_response is not None:
            return self._default_response

        # Check if caller specified a doc_type or if registered in canned
        for key, resp in self._canned.items():
            if key.lower() in user.lower() or key.lower() in system.lower():
                return resp

        # Check if caller is requesting reason classification
        is_reason_classification = False
        if isinstance(json_schema, dict):
            props = json_schema.get("properties", {})
            if "reason_class" in props:
                is_reason_classification = True
        elif hasattr(json_schema, "__annotations__") and "reason_class" in json_schema.__annotations__:
            is_reason_classification = True

        if (
            is_reason_classification
            or "dispute reason" in system.lower()
            or "classify the dispute reason" in system.lower()
        ):
            return self._classify_reason_regex(user)

        # Intelligent extraction from text based on common patterns
        # 1. Delivery Proof (Courier POD)
        if "Tracking / AWB Number:" in user or "Proof of Delivery" in user:
            return self._extract_delivery_proof(user)

        # 2. Tax Invoice
        if "Tax Invoice" in user or "Invoice Number:" in user:
            return self._extract_invoice(user)

        # 3. Chat Transcript
        if any(
            kw in user
            for kw in [
                "Customer Support Chat Transcript",
                "Chat Transcript",
                "Customer Support Communication Record",
                "Support Ticket:",
            ]
        ):
            return self._extract_chat_transcript(user)

        # 4. Cancellation Policy
        if "Cancellation Policy" in user or "Return & Refund Policy" in user:
            return self._extract_cancellation_policy(user)

        # Fallback empty dict
        return {}

    def _classify_reason_regex(self, text: str) -> dict[str, Any]:
        """Regex and keyword baseline for reason classification (fake regex baseline, not a model result)."""
        lower = text.lower()

        # Item not received patterns (English and Hinglish)
        if any(
            kw in lower
            for kw in [
                "not received",
                "nahi mila",
                "parcel gayab",
                "empty",
                "lost",
                "handed over",
                "consignment lost",
                "door step",
                "package",
                "waiting since",
            ]
        ):
            return {
                "reason_class": "item_not_received",
                "confidence": 0.85,
                "quote": "parcel gayab" if "parcel gayab" in lower else "not received",
            }

        # Not as described patterns
        if any(
            kw in lower
            for kw in [
                "dusra maal",
                "damaged",
                "defective",
                "mismatched",
                "wrong variant",
                "cheap plastic",
                "shattered",
                "cloth quality",
                "accessories missing",
                "not as described",
                "torn stitching",
                "specification totally",
            ]
        ):
            return {
                "reason_class": "not_as_described",
                "confidence": 0.85,
                "quote": "dusra maal" if "dusra maal" in lower else "damaged",
            }

        # Unauthorised / fraud
        if any(
            kw in lower
            for kw in [
                "maine koi payment nahi kiya",
                "otp kisne dala",
                "wallet me tha",
                "permission",
                "skimmer",
                "unauthorized",
                "fraud",
                "unknown debit",
                "hospital",
                "sleep kar raha",
                "stranger purchased",
                "phone lost",
            ]
        ):
            return {
                "reason_class": "unauthorised",
                "confidence": 0.85,
                "quote": "koi payment nahi kiya" if "koi payment nahi kiya" in lower else "unauthorized",
            }

        # Duplicate charge
        if any(
            kw in lower
            for kw in [
                "do alag",
                "do bar",
                "twin debits",
                "deducted twice",
                "two debits",
                "double withdrawal",
                "two times",
                "duplicate",
                "charged twice",
                "screen freeze",
            ]
        ):
            return {
                "reason_class": "duplicate_charge",
                "confidence": 0.85,
                "quote": "do alag" if "do alag" in lower else "duplicate",
            }

        # Subscription cancelled
        if any(
            kw in lower
            for kw in [
                "service stop",
                "account delete",
                "opted out",
                "free trial",
                "unsubscribed",
                "auto debit stop",
                "whatsapp",
                "renewal",
                "subscription",
            ]
        ):
            return {
                "reason_class": "subscription_cancelled",
                "confidence": 0.85,
                "quote": "service stop" if "service stop" in lower else "subscription",
            }

        # Refund not received
        if any(
            kw in lower
            for kw in [
                "paise wapas",
                "refund",
                "reversal",
                "arn number fake",
                "promised compensation",
                "credit not",
                "return parcel pick",
            ]
        ):
            return {
                "reason_class": "refund_not_received",
                "confidence": 0.85,
                "quote": "paise wapas" if "paise wapas" in lower else "refund",
            }

        # Other
        if any(
            kw in lower
            for kw in [
                "branch manager",
                "split",
                "surcharge",
                "finance department",
                "compliance query",
                "dispute dalo",
                "need clarity",
            ]
        ):
            return {
                "reason_class": "other",
                "confidence": 0.70,
                "quote": "compliance query" if "compliance query" in lower else "split",
            }

        # Unclassified fallback (low confidence)
        return {
            "reason_class": "unclassified",
            "confidence": 0.30,
            "quote": "",
        }


    def _extract_delivery_proof(self, text: str) -> dict[str, Any]:
        """Extract delivery proof fields with verbatim quotes."""
        result: dict[str, Any] = {}

        # Tracking
        m = re.search(r"(\*\*Tracking / AWB Number:\*\*\s*(\S+))", text)
        if m:
            result["tracking_number"] = {
                "value": m.group(2).strip(),
                "source_quote": m.group(1),
                "confidence": 0.99,
            }

        # Carrier
        m = re.search(r"(\*\*Logistics Carrier:\*\*\s*([^\n\r]+))", text)
        if m:
            result["carrier"] = {
                "value": m.group(2).strip(),
                "source_quote": m.group(1),
                "confidence": 0.98,
            }

        # Recipient Name
        m = re.search(r"(\*\*Recipient Name:\*\*\s*([^\n\r]+))", text)
        if m:
            result["recipient_name"] = {
                "value": m.group(2).strip(),
                "source_quote": m.group(1),
                "confidence": 0.95,
            }

        # Address
        m = re.search(r"(\*\*Destination Address:\*\*\s*([^\n\r]+))", text)
        if m:
            result["delivery_address"] = {
                "value": m.group(2).strip(),
                "source_quote": m.group(1),
                "confidence": 0.95,
            }

        # Status
        m = re.search(r"(\*\*Status:\*\*\s*([^\n\r]+))", text)
        if m:
            result["delivery_status"] = {
                "value": m.group(2).strip(),
                "source_quote": m.group(1),
                "confidence": 0.99,
            }

        # Delivery Timestamp / Epoch
        m = re.search(r"(\*\*Delivery Timestamp:\*\*\s*([^\n\r(]+)\s*\(Epoch:\s*(\d+)\))", text)
        if m:
            result["delivery_date"] = {
                "value": m.group(2).strip(),
                "source_quote": m.group(1),
                "confidence": 0.98,
            }
            result["delivery_epoch"] = {
                "value": int(m.group(3)),
                "source_quote": m.group(1),
                "confidence": 0.98,
            }

        # Order ID
        m = re.search(r"(\*\*Merchant Order ID:\*\*\s*([^\n\r]+))", text)
        if m:
            result["order_id"] = {
                "value": m.group(2).strip(),
                "source_quote": m.group(1),
                "confidence": 0.99,
            }

        # OTP Verified
        m = re.search(r"(\*\*Verification Method:\*\*\s*OTP Verified[^\n\r]*)", text)
        if m:
            result["otp_verified"] = {
                "value": True,
                "source_quote": m.group(1),
                "confidence": 0.99,
            }

        return result

    def _extract_invoice(self, text: str) -> dict[str, Any]:
        """Extract invoice fields with verbatim quotes."""
        result: dict[str, Any] = {}

        # Invoice number
        m = re.search(r"(\*\*Invoice Number:\*\*\s*(\S+))", text)
        if m:
            result["invoice_number"] = {
                "value": m.group(2).strip(),
                "source_quote": m.group(1),
                "confidence": 0.99,
            }

        # Order ID
        m = re.search(r"(\*\*Order ID:\*\*\s*([^\n\r]+))", text)
        if m:
            result["order_id"] = {
                "value": m.group(2).strip(),
                "source_quote": m.group(1),
                "confidence": 0.99,
            }

        # Payment ID
        m = re.search(r"(\*\*Payment ID:\*\*\s*([^\n\r]+))", text)
        if m:
            result["payment_id"] = {
                "value": m.group(2).strip(),
                "source_quote": m.group(1),
                "confidence": 0.99,
            }

        # Customer Name
        m = re.search(r"(\*\*Customer Name:\*\*\s*([^\n\r]+))", text)
        if m:
            result["customer_name"] = {
                "value": m.group(2).strip(),
                "source_quote": m.group(1),
                "confidence": 0.95,
            }

        # Shipping Address
        m = re.search(r"(\*\*Shipping Address:\*\*\s*([^\n\r]+))", text)
        if m:
            result["shipping_address"] = {
                "value": m.group(2).strip(),
                "source_quote": m.group(1),
                "confidence": 0.95,
            }

        # Total Amount
        m = re.search(r"(\*\*Grand Total:\*\*\s*INR\s*([\d,]+\.?\d*))", text)
        if m:
            raw_rs = m.group(2).replace(",", "")
            amount_paise = round(float(raw_rs) * 100)
            result["total_amount_paise"] = {
                "value": amount_paise,
                "source_quote": m.group(1),
                "confidence": 0.99,
            }

        # Invoice Date
        m = re.search(r"(\*\*Invoice Date:\*\*\s*([^\n\r]+))", text)
        if m:
            result["invoice_date"] = {
                "value": m.group(2).strip(),
                "source_quote": m.group(1),
                "confidence": 0.95,
            }

        return result

    def _extract_chat_transcript(self, text: str) -> dict[str, Any]:
        """Extract chat transcript fields with verbatim quotes."""
        result: dict[str, Any] = {}

        m = re.search(r"(\*\*(?:Support Ticket|Ticket ID):\*\*\s*([^\n\r]+))", text)
        if m:
            result["ticket_id"] = {
                "value": m.group(2).strip(),
                "source_quote": m.group(1).strip(),
                "confidence": 0.95,
            }

        m = re.search(r"(\*\*(?:Customer Name|Customer):\*\*\s*([^\n\r]+))", text)
        if m:
            result["customer_name"] = {
                "value": m.group(2).strip(),
                "source_quote": m.group(1).strip(),
                "confidence": 0.95,
            }

        # Refund mentioned
        m = re.search(r"([^\n\r]*\b(?:refund|refunded|reimburse)\b[^\n\r]*)", text, re.IGNORECASE)
        if m:
            result["refund_mentioned"] = {
                "value": True,
                "source_quote": m.group(1).strip(),
                "confidence": 0.90,
            }
        else:
            result["refund_mentioned"] = {
                "value": False,
                "source_quote": "Customer Support Chat Transcript",
                "confidence": 0.85,
            }

        return result

    def _extract_cancellation_policy(self, text: str) -> dict[str, Any]:
        """Extract policy terms with verbatim quotes."""
        result: dict[str, Any] = {}

        m = re.search(r"([^\n\r]*\b(\d+)\s*days?\b[^\n\r]*)", text, re.IGNORECASE)
        if m:
            result["cancellation_window_days"] = {
                "value": int(m.group(2)),
                "source_quote": m.group(1).strip(),
                "confidence": 0.95,
            }

        result["refund_allowed"] = {
            "value": "non-refundable" not in text.lower(),
            "source_quote": "Cancellation Policy",
            "confidence": 0.90,
        }

        return result


def get_llm_client() -> LLMClient:
    """Return GeminiClient if LLM_API_KEY is configured, else FakeLLMClient."""
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if api_key and api_key.strip():
        logger.info("Initializing live GeminiClient with configured API key.")
        return GeminiClient(api_key=api_key.strip())

    logger.debug("LLM_API_KEY not set. Using offline FakeLLMClient.")
    return FakeLLMClient()
