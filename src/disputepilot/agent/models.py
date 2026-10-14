"""Models for Evidence Agent outputs and audit reports."""

from pydantic import BaseModel, Field

from disputepilot.extraction.cross_checks import CrossCheckFlag


class EvidenceReport(BaseModel):
    """Structured report produced by the bounded Evidence Agent.

    Contains:
    - Per category status (present/partial/missing)
    - Document IDs mapped to each category
    - Average extraction confidence per category
    - Discrepancy flags detected across records and evidence
    - Specific asks generated for each missing required or helpful item
    - Complete audit trail of read-only tool steps
    """

    case_id: str
    reason_class: str
    category_status: dict[str, str] = Field(default_factory=dict)
    category_documents: dict[str, list[str]] = Field(default_factory=dict)
    extraction_confidence: dict[str, float] = Field(default_factory=dict)
    cross_check_flags: list[CrossCheckFlag] = Field(default_factory=list)
    specific_asks: dict[str, str] = Field(default_factory=dict)
    steps_taken: int = 0
    tool_calls: list[str] = Field(default_factory=list)
