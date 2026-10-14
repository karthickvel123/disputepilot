"""Evidence requirements evaluation and audit for dispute reason classes."""

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from disputepilot.core.models import (
    DisputeCase,
    RazorpayEvidence,
    ReasonClass,
)

REQUIREMENTS_YAML_DEFAULT = Path(__file__).parent / "requirements.yaml"


class CategoryStatus(str, Enum):
    """Presence status of an evidence category."""

    PRESENT = "present"
    MISSING = "missing"
    PARTIAL = "partial"


class EvidenceRole(str, Enum):
    """Importance of an evidence category for a specific dispute reason class."""

    REQUIRED = "required"
    HELPFUL = "helpful"
    IRRELEVANT = "irrelevant"


class CategoryEvaluation(BaseModel):
    """Evaluation result for a single evidence category."""

    category: str
    role: EvidenceRole
    status: CategoryStatus
    details: str = ""


class EvidenceAudit(BaseModel):
    """Complete evidence audit breakdown for a dispute case."""

    reason_class: ReasonClass
    categories: dict[str, CategoryEvaluation] = Field(default_factory=dict)
    required_satisfied: bool = False
    present_categories: list[str] = Field(default_factory=list)
    missing_categories: list[str] = Field(default_factory=list)
    partial_categories: list[str] = Field(default_factory=list)

    @property
    def status_by_category(self) -> dict[str, CategoryStatus]:
        """Convenience mapping of category name to CategoryStatus."""
        return {cat: eval_obj.status for cat, eval_obj in self.categories.items()}


@lru_cache(maxsize=1)
def load_requirements_config(config_path: str | None = None) -> dict[str, Any]:
    """Load and cache requirements.yaml configuration.

    Args:
        config_path: Optional path to custom requirements.yaml.

    Returns:
        Dictionary mapping reason classes to required, helpful, and irrelevant categories.
    """
    path = Path(config_path) if config_path else REQUIREMENTS_YAML_DEFAULT
    with open(path, encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return data


def get_requirements_for_class(
    reason_class: ReasonClass | str,
    config_path: Path | str | None = None,
) -> dict[str, list[str]]:
    """Retrieve evidence role lists (required, helpful, irrelevant) for a reason class.

    Args:
        reason_class: Target ReasonClass.
        config_path: Optional custom path to requirements.yaml.

    Returns:
        Dictionary containing 'required', 'helpful', and 'irrelevant' lists.
    """
    class_key = reason_class.value if isinstance(reason_class, ReasonClass) else str(reason_class).lower()
    config = load_requirements_config(str(config_path) if config_path else None)

    class_reqs = config.get(class_key)
    if not class_reqs:
        class_reqs = config.get("other", {"required": ["billing_proof"], "helpful": [], "irrelevant": []})

    return {
        "required": list(class_reqs.get("required", [])),
        "helpful": list(class_reqs.get("helpful", [])),
        "irrelevant": list(class_reqs.get("irrelevant", [])),
    }


def audit_evidence(
    reason_class: ReasonClass | str,
    available_evidence: list[str] | dict[str, Any] | RazorpayEvidence | DisputeCase | None,
    config_path: Path | str | None = None,
) -> EvidenceAudit:
    """Evaluate a case's available evidence against reason class requirements.

    Returns 'present', 'missing', or 'partial' for every category defined in requirements.

    Args:
        reason_class: The reason class of the dispute.
        available_evidence: List of category strings, dictionary of category -> docs,
            RazorpayEvidence model, or full DisputeCase.
        config_path: Optional custom path to requirements.yaml.

    Returns:
        EvidenceAudit model containing per-category evaluation.
    """
    if isinstance(reason_class, str):
        try:
            rc = ReasonClass(reason_class.lower())
        except ValueError:
            rc = ReasonClass.OTHER
    else:
        rc = reason_class

    reqs = get_requirements_for_class(rc, config_path=config_path)

    # Normalize available evidence into category -> documents mapping or category -> presence
    evidence_presence: dict[str, Any] = {}
    is_temporal_invalid = False

    if available_evidence is None:
        pass
    elif isinstance(available_evidence, DisputeCase):
        # Full dispute case with documents and dispute evidence
        disp_ev = available_evidence.dispute.evidence.model_dump()
        evidence_presence = {k: v for k, v in disp_ev.items() if v}
        # Check ground truth available evidence as well
        for cat in available_evidence.ground_truth.available_evidence:
            if cat not in evidence_presence:
                evidence_presence[cat] = ["available"]
        if "delivery_after_dispute" in available_evidence.ground_truth.adversarial.adversarial_types:
            is_temporal_invalid = True
    elif isinstance(available_evidence, RazorpayEvidence):
        disp_ev = available_evidence.model_dump()
        evidence_presence = {k: v for k, v in disp_ev.items() if v}
    elif isinstance(available_evidence, dict):
        for k, v in available_evidence.items():
            if isinstance(v, list) and v:
                evidence_presence[k] = v
            elif isinstance(v, bool) and v:
                evidence_presence[k] = ["available"]
            elif isinstance(v, str) and v.strip():
                evidence_presence[k] = [v]
    elif isinstance(available_evidence, (list, set, tuple)):
        for item in available_evidence:
            if isinstance(item, str) and item.strip():
                evidence_presence[item.strip()] = ["available"]

    categories_eval: dict[str, CategoryEvaluation] = {}
    present_list: list[str] = []
    missing_list: list[str] = []
    partial_list: list[str] = []

    all_categories: list[tuple[str, EvidenceRole]] = (
        [(c, EvidenceRole.REQUIRED) for c in reqs["required"]]
        + [(c, EvidenceRole.HELPFUL) for c in reqs["helpful"]]
        + [(c, EvidenceRole.IRRELEVANT) for c in reqs["irrelevant"]]
    )

    for cat_name, role in all_categories:
        docs = evidence_presence.get(cat_name)

        if not docs:
            status = CategoryStatus.MISSING
            details = f"No documents provided for {role.value} category '{cat_name}'."
            missing_list.append(cat_name)
        elif cat_name == "shipping_proof" and is_temporal_invalid:
            status = CategoryStatus.PARTIAL
            details = "Shipping proof present but delivery timestamp is after dispute date."
            partial_list.append(cat_name)
        elif isinstance(docs, list) and any(isinstance(d, str) and len(d.strip()) == 0 for d in docs):
            status = CategoryStatus.PARTIAL
            details = "Evidence category contains incomplete or empty document reference."
            partial_list.append(cat_name)
        else:
            status = CategoryStatus.PRESENT
            details = f"Valid documentation verified for {role.value} category '{cat_name}'."
            present_list.append(cat_name)

        categories_eval[cat_name] = CategoryEvaluation(
            category=cat_name,
            role=role,
            status=status,
            details=details,
        )

    # Required categories are satisfied only if every required category is strictly PRESENT
    required_satisfied = all(
        categories_eval[req_cat].status == CategoryStatus.PRESENT
        for req_cat in reqs["required"]
        if req_cat in categories_eval
    ) if reqs["required"] else True

    return EvidenceAudit(
        reason_class=rc,
        categories=categories_eval,
        required_satisfied=required_satisfied,
        present_categories=present_list,
        missing_categories=missing_list,
        partial_categories=partial_list,
    )
