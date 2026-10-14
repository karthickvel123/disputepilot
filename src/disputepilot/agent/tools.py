"""Allow-listed READ-ONLY tool registry for the Evidence Agent.

CRITICAL ARCHITECTURAL SAFETY INVARIANT:
No write tools exist anywhere in this module. All operations are strictly read-only:
get_dispute, get_order, get_refund, list_documents, get_extracted_doc.
Any attempt to call a non-allow-listed tool is rejected immediately with PermissionError.
"""

import json
from pathlib import Path
from typing import Any

from disputepilot.core.models import DisputeCase
from disputepilot.extraction.extractor import ExtractedDocument, extract_document
from disputepilot.extraction.llm import LLMClient

ALLOWLISTED_TOOLS = {
    "get_dispute",
    "get_order",
    "get_refund",
    "list_documents",
    "get_extracted_doc",
}


class ReadOnlyToolRegistry:
    """Provides bounded, read-only data access to dispute case entities and documents."""

    def __init__(
        self,
        case: DisputeCase | None = None,
        cases_dir: Path | str = "data/cases",
        llm_client: LLMClient | None = None,
    ) -> None:
        self._case = case
        self._cases_dir = Path(cases_dir)
        self._llm_client = llm_client
        self._extracted_cache: dict[str, ExtractedDocument] = {}

    def _resolve_case(self, case_id: str) -> DisputeCase:
        """Resolve DisputeCase from memory or disk."""
        if self._case and self._case.case_id == case_id:
            return self._case

        case_file = self._cases_dir / f"{case_id}.json"
        if case_file.exists():
            with open(case_file, encoding="utf-8") as f:
                data = json.load(f)
            return DisputeCase.model_validate(data)

        if self._case:
            return self._case

        raise KeyError(f"Case '{case_id}' not found.")

    def get_dispute(self, case_id: str) -> dict[str, Any]:
        """Fetch dispute metadata for the case."""
        case = self._resolve_case(case_id)
        return case.dispute.model_dump()

    def get_order(self, case_id: str) -> dict[str, Any] | None:
        """Fetch order record for the case."""
        case = self._resolve_case(case_id)
        return case.order.model_dump() if case.order else None

    def get_refund(self, case_id: str) -> dict[str, Any] | None:
        """Fetch refund record for the case if one exists."""
        case = self._resolve_case(case_id)
        return case.refund.model_dump() if case.refund else None

    def list_documents(self, case_id: str) -> list[dict[str, Any]]:
        """List all evidence documents associated with the case."""
        case = self._resolve_case(case_id)
        return [
            {
                "doc_id": doc.doc_id,
                "doc_type": doc.doc_type,
                "file_name": doc.file_name,
                "file_path": doc.file_path,
            }
            for doc in case.documents
        ]

    def get_extracted_doc(self, case_id: str, doc_id: str) -> dict[str, Any] | None:
        """Extract and return structured data from a specific evidence document."""
        cache_key = f"{case_id}_{doc_id}"
        if cache_key in self._extracted_cache:
            return self._extracted_cache[cache_key].model_dump()

        case = self._resolve_case(case_id)
        target_doc = next((d for d in case.documents if d.doc_id == doc_id), None)
        if not target_doc:
            return None

        extracted = extract_document(
            text_or_path=target_doc.content,
            case_id=case.case_id,
            doc_id=target_doc.doc_id,
            doc_type=target_doc.doc_type,
            known_names=[case.order.customer_name] if case.order else None,
            protected_ids={case.order.id, case.dispute.payment_id} if case.order else None,
            llm_client=self._llm_client,
        )
        self._extracted_cache[cache_key] = extracted
        return extracted.model_dump()

    def execute_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Execute an allow-listed tool with strict permission enforcement."""
        if tool_name not in ALLOWLISTED_TOOLS:
            raise PermissionError(
                f"Unauthorized tool execution attempted: '{tool_name}'. "
                f"Only read-only tools are allowed: {sorted(ALLOWLISTED_TOOLS)}. "
                "No write tools exist."
            )

        method = getattr(self, tool_name)
        return method(**kwargs)
