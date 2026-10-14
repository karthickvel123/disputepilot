"""Heuristic contest-or-accept recommendation engine for dispute resolution.

This is a rules-based baseline calibrated on synthetic data (no trained ML model).
Evaluates reason class prior, evidence completeness, cross-check discrepancies,
and expected value to output Contest / Accept / NeedsEvidence recommendations.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from disputepilot.agent.models import EvidenceReport

from disputepilot.core.evidence import CategoryStatus, EvidenceRole, audit_evidence
from disputepilot.core.models import DisputeCase
from disputepilot.core.reasons import ReasonClass, classify_reason

RECOMMEND_YAML_DEFAULT = Path(__file__).parent / "recommend.yaml"
HEURISTIC_DISCLAIMER = "Heuristic baseline calibrated on synthetic data."


class ContestDecision(str, Enum):
    """Recommended merchant dispute contest decision."""

    CONTEST = "contest"
    ACCEPT = "accept"
    NEEDS_EVIDENCE = "needs_evidence"
    UNCERTAIN = "uncertain"


class Recommendation(BaseModel):
    """Comprehensive recommendation result for a dispute case."""

    case_id: str
    decision: ContestDecision
    p_win: float | str
    p_win_low: float | str
    p_win_high: float | str
    expected_value_paise: int | str
    is_uncertain: bool
    preselect_action: str | None
    reasons: list[str] = Field(default_factory=list)
    disclaimer: str = HEURISTIC_DISCLAIMER


@lru_cache(maxsize=1)
def load_recommend_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load and cache the recommendation heuristic weights configuration."""
    path = Path(config_path) if config_path else RECOMMEND_YAML_DEFAULT
    with open(path, encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return data


def compute_p_win(
    reason_class: ReasonClass,
    category_statuses: dict[str, CategoryStatus],
    category_roles: dict[str, EvidenceRole],
    cross_check_flags: list[Any],
    config: dict[str, Any],
    has_strong_delivery_proof: bool = False,
) -> tuple[float, float, float, list[str]]:
    """Compute transparent weighted win probability and range from component weights.

    Args:
        reason_class: Grounded reason class for the dispute.
        category_statuses: Present, partial, or missing status per category.
        category_roles: Required, helpful, or irrelevant role per category.
        cross_check_flags: Discrepancy flags detected.
        config: Configuration dict with heuristic weights.
        has_strong_delivery_proof: True if delivery proof is verified without flags.

    Returns:
        Tuple of (p_win, p_win_low, p_win_high, reasons).
    """
    reasons: list[str] = []

    # 1. Base Prior from Reason Class
    priors = config.get("reason_priors", {})
    prior = priors.get(reason_class.value, 0.40)
    score = prior
    reasons.append(f"Baseline win prior for reason '{reason_class.value}': {prior:.2f}")

    # 2. Evidence Completeness
    ev_weights = config.get("evidence_weights", {})
    required_cats = [cat for cat, role in category_roles.items() if role == EvidenceRole.REQUIRED]
    helpful_cats = [cat for cat, role in category_roles.items() if role == EvidenceRole.HELPFUL]

    missing_required = [
        cat for cat in required_cats if category_statuses.get(cat, CategoryStatus.MISSING) == CategoryStatus.MISSING
    ]
    partial_required = [
        cat for cat in required_cats if category_statuses.get(cat) == CategoryStatus.PARTIAL
    ]
    present_helpful = [
        cat for cat in helpful_cats if category_statuses.get(cat) == CategoryStatus.PRESENT
    ]

    if required_cats and not missing_required and not partial_required:
        bonus = ev_weights.get("all_required_present_bonus", 0.20)
        score += bonus
        reasons.append(f"All required evidence categories present (+{bonus:.2f})")
    elif missing_required:
        penalty = ev_weights.get("any_required_missing_penalty", -0.35)
        score += penalty
        reasons.append(f"Missing required evidence: {', '.join(missing_required)} ({penalty:.2f})")
    elif partial_required:
        penalty = ev_weights.get("required_partial_penalty", -0.15)
        score += penalty
        reasons.append(f"Incomplete/degraded required evidence: {', '.join(partial_required)} ({penalty:.2f})")

    if present_helpful:
        bonus = len(present_helpful) * ev_weights.get("helpful_present_bonus", 0.08)
        score += bonus
        reasons.append(f"Helpful supporting evidence present: {', '.join(present_helpful)} (+{bonus:.2f})")

    # 3. Cross-Check Penalties
    penalties = config.get("cross_check_penalties", {})
    for flag in cross_check_flags:
        code = getattr(flag, "flag_code", str(flag))
        if code in penalties:
            pen = penalties[code]
            score += pen
            reasons.append(f"Cross-check discrepancy penalty '{code}': {pen:.2f}")

    # 4. Delivery Proof Boost
    if has_strong_delivery_proof:
        boost = config.get("delivery_proof_boost", 0.15)
        score += boost
        reasons.append(f"Verified delivery proof confirmation (+{boost:.2f})")

    # Clamp score to realistic probability range [0.05, 0.95]
    p_win = round(max(0.05, min(0.95, score)), 2)

    # Calculate low/high bounds (uncertainty interval)
    uncertainty_margin = 0.15
    if missing_required or cross_check_flags:
        uncertainty_margin = 0.20

    p_win_low = round(max(0.0, p_win - uncertainty_margin), 2)
    p_win_high = round(min(1.0, p_win + uncertainty_margin), 2)

    return p_win, p_win_low, p_win_high, reasons


def recommend_action(
    case: DisputeCase,
    evidence_report: EvidenceReport | None = None,
    config_path: str | Path | None = None,
    effort_cost_paise: int | None = None,
) -> Recommendation:
    """Evaluate dispute case and output transparent Contest / Accept / NeedsEvidence recommendation.

    Args:
        case: DisputeCase with dispute and order details.
        evidence_report: Optional precomputed EvidenceReport from evidence agent.
        config_path: Optional custom path to recommend.yaml.
        effort_cost_paise: Optional custom effort cost in paise.

    Returns:
        Recommendation object with decision, p_win range, expected value, and reasons.
    """
    config = load_recommend_config(config_path)

    # 1. Determine Reason Class
    if evidence_report:
        rc_val = evidence_report.reason_class
        try:
            reason_class = ReasonClass(rc_val)
        except ValueError:
            reason_class = ReasonClass.UNCLASSIFIED
    else:
        match = classify_reason(case.dispute.reason_code)
        reason_class = match.reason_class

    # When reason is unclassified, return Uncertain state immediately
    # Preselect nothing, and never use the "other" prior
    if reason_class == ReasonClass.UNCLASSIFIED or (
        isinstance(reason_class, str) and reason_class.lower() == "unclassified"
    ):
        return Recommendation(
            case_id=case.case_id,
            decision=ContestDecision.UNCERTAIN,
            p_win="n/a",
            p_win_low="n/a",
            p_win_high="n/a",
            expected_value_paise="n/a",
            is_uncertain=True,
            preselect_action=None,
            reasons=["reason could not be classified"],
            disclaimer=HEURISTIC_DISCLAIMER,
        )

    # 2. Determine Category Statuses & Roles
    if evidence_report:
        statuses = {
            cat: CategoryStatus(status_str)
            for cat, status_str in evidence_report.category_status.items()
        }
        flags = evidence_report.cross_check_flags
    else:
        available_evidence = {
            cat: getattr(case.dispute.evidence, cat, [])
            for cat in [
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
        }
        audit = audit_evidence(reason_class=reason_class, available_evidence=available_evidence)
        statuses = {cat: eval_obj.status for cat, eval_obj in audit.categories.items()}
        flags = []

    # Get roles from core requirements audit
    audit_base = audit_evidence(reason_class=reason_class, available_evidence={})
    roles = {cat: eval_obj.role for cat, eval_obj in audit_base.categories.items()}

    has_strong_delivery = (
        statuses.get("shipping_proof") == CategoryStatus.PRESENT
        and not any(getattr(f, "flag_code", "") == "DELIVERY_AFTER_DISPUTE" for f in flags)
    )

    # 3. Compute p_win
    p_win, p_win_low, p_win_high, reasons = compute_p_win(
        reason_class=reason_class,
        category_statuses=statuses,
        category_roles=roles,
        cross_check_flags=flags,
        config=config,
        has_strong_delivery_proof=has_strong_delivery,
    )

    # 4. Expected Value: EV = p_win * amount - effort_cost
    if effort_cost_paise is None:
        effort_cost_paise = config.get("effort_cost_paise", 0)

    disputed_amount = case.dispute.amount
    expected_value_paise = round(p_win * disputed_amount - effort_cost_paise)

    # 5. Check missing required evidence
    missing_required = [
        cat
        for cat, role in roles.items()
        if role == EvidenceRole.REQUIRED and statuses.get(cat) == CategoryStatus.MISSING
    ]

    thresholds = config.get("thresholds", {})
    band_min = thresholds.get("uncertain_band_min", 0.35)
    band_max = thresholds.get("uncertain_band_max", 0.55)
    max_range = thresholds.get("uncertain_range_width", 0.30)

    range_width = round(p_win_high - p_win_low, 2)
    is_uncertain = (band_min <= p_win <= band_max) or (range_width >= max_range)

    # 6. Decision logic
    if missing_required:
        decision = ContestDecision.NEEDS_EVIDENCE
        preselect_action = None
        reasons.insert(
            0,
            f"Needs evidence: Mandatory evidence category '{missing_required[0]}' is currently missing.",
        )
    elif p_win < band_min or expected_value_paise <= 0:
        decision = ContestDecision.ACCEPT
        preselect_action = None if is_uncertain else "accept"
        reasons.insert(
            0,
            f"Accept recommended: Win probability ({p_win:.0%}) is low or expected value is negative (₹{expected_value_paise / 100:.2f}).",
        )
    elif p_win > band_max and expected_value_paise > 0:
        decision = ContestDecision.CONTEST
        preselect_action = None if is_uncertain else "contest"
        reasons.insert(
            0,
            f"Contest recommended: Win probability ({p_win:.0%}) with positive expected value ₹{expected_value_paise / 100:.2f}.",
        )
    else:
        # Falls squarely within uncertain band
        decision = ContestDecision.CONTEST if expected_value_paise > 0 else ContestDecision.ACCEPT
        preselect_action = None
        reasons.insert(
            0,
            f"Uncertain recommendation (win probability {p_win:.0%} in ambiguous band {band_min:.0%}-{band_max:.0%}). Merchant review required; preselected nothing.",
        )

    return Recommendation(
        case_id=case.case_id,
        decision=decision,
        p_win=p_win,
        p_win_low=p_win_low,
        p_win_high=p_win_high,
        expected_value_paise=expected_value_paise,
        is_uncertain=is_uncertain,
        preselect_action=preselect_action,
        reasons=reasons,
        disclaimer=HEURISTIC_DISCLAIMER,
    )
