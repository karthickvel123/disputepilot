"""Document extraction module executing safe ingestion, untrusted wrapping, LLM extraction, and quote verification."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from disputepilot.extraction.llm import LLMClient, get_llm_client
from disputepilot.extraction.schemas import ExtractedField, get_schema_for_doc_type
from disputepilot.safety.ingest import IngestResult, ingest_document
from disputepilot.safety.untrusted import wrap_untrusted


class DroppedField(BaseModel):
    """Details of a candidate field dropped due to lack of verbatim source quote."""

    field_name: str
    field_value: Any
    source_quote: str
    reason: str


class ExtractedDocument(BaseModel):
    """Result of safe extraction from an evidence document."""

    doc_id: str
    doc_type: str
    surviving_fields: dict[str, Any] = Field(default_factory=dict)
    dropped_fields: list[DroppedField] = Field(default_factory=list)
    clean_text: str
    injection_flags: list[str] = Field(default_factory=list)
    vault_id: str


SYSTEM_EXTRACTION_PROMPT = """You are an accurate, deterministic legal & financial document extractor for payment dispute defense.
Extract structured factual fields strictly from the provided text.
CRITICAL RULES:
1. Every extracted field must include 'value', 'source_quote', and 'confidence'.
2. The 'source_quote' MUST be an EXACT, VERBATIM substring directly copied from the text. Never paraphrase or fabricate.
3. If a field is not explicitly present in the document, set it to null.
4. Output strict JSON conforming exactly to the requested schema. Do not add any extra keys.
"""


def extract_document(
    text_or_path: str | Path,
    case_id: str,
    doc_id: str,
    doc_type: str,
    known_names: list[str] | None = None,
    protected_ids: set[str] | list[str] | None = None,
    llm_client: LLMClient | None = None,
) -> ExtractedDocument:
    """Safely ingest, wrap, extract, validate, and verify an evidence document.

    Pipeline:
    1. Ingest via safety module (card numbers redacted, PII tokenized, binary rejected).
    2. Wrap clean text inside untrusted data boundary.
    3. Query LLM for structured extraction according to strict document schema.
    4. Validate against Pydantic schema (extra keys forbidden).
    5. Verify source quotes: DROP any field whose source_quote is not verbatim in the cleaned text.

    Args:
        text_or_path: Raw text content or Path to document on disk.
        case_id: Dispute case identifier.
        doc_id: Document identifier.
        doc_type: Type of document (delivery_proof, invoice, chat_transcript, cancellation_policy).
        known_names: Optional customer names for PII tokenization.
        protected_ids: Optional order/AWB/payment IDs to preserve from redaction.
        llm_client: Optional LLMClient instance (defaults to get_llm_client()).

    Returns:
        ExtractedDocument containing surviving verified fields and dropped fields list.
    """
    # 1. Safety ingestion: sanitize cards, tokenize PII, detect injection
    ingest_res: IngestResult = ingest_document(
        text_or_path=text_or_path,
        case_id=case_id,
        known_names=known_names,
        protected_ids=protected_ids,
    )
    clean_text = ingest_res.clean_text

    # 2. Wrap untrusted data with non-instruction boundary notice
    wrapped_content = wrap_untrusted(clean_text, source_id=doc_id)

    # 3. Resolve strict schema and LLM client
    schema_cls = get_schema_for_doc_type(doc_type)
    client = llm_client or get_llm_client()

    # 4. Generate structured JSON
    raw_dict = client.generate_json(
        system=SYSTEM_EXTRACTION_PROMPT,
        user=wrapped_content,
        json_schema=schema_cls,
        case_id=case_id,
        stage="extraction",
        doc_id=doc_id,
    )

    # 5. Validate schema (Pydantic models have extra="forbid" so extra keys fail validation)
    validated_model = schema_cls.model_validate(raw_dict)

    # 6. Verify quotes verbatim in cleaned text
    surviving_fields: dict[str, Any] = {}
    dropped_fields: list[DroppedField] = []

    for field_name, field_obj in validated_model:
        if field_obj is None:
            continue

        if isinstance(field_obj, ExtractedField):
            quote = field_obj.source_quote
            if not quote or quote not in clean_text:
                dropped_fields.append(
                    DroppedField(
                        field_name=field_name,
                        field_value=field_obj.value,
                        source_quote=quote,
                        reason=f"Source quote {quote!r} is not verbatim in cleaned document text.",
                    )
                )
            else:
                surviving_fields[field_name] = field_obj

    return ExtractedDocument(
        doc_id=doc_id,
        doc_type=doc_type,
        surviving_fields=surviving_fields,
        dropped_fields=dropped_fields,
        clean_text=clean_text,
        injection_flags=ingest_res.injection_flags,
        vault_id=ingest_res.vault_id,
    )
