"""Deterministic dispute triage and prioritized worklist ranking."""

import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from disputepilot.core.deadlines import calculate_deadline
from disputepilot.core.models import DisputeCase, ReasonClass
from disputepilot.core.reasons import classify_reason

# Configurable placeholder win probabilities by reason class
DEFAULT_P_WIN_MAP: dict[ReasonClass, float] = {
    ReasonClass.ITEM_NOT_RECEIVED: 0.65,
    ReasonClass.DUPLICATE_CHARGE: 0.70,
    ReasonClass.REFUND_NOT_RECEIVED: 0.60,
    ReasonClass.UNAUTHORISED: 0.55,
    ReasonClass.NOT_AS_DESCRIBED: 0.50,
    ReasonClass.SUBSCRIPTION_CANCELLED: 0.45,
    ReasonClass.OTHER: 0.40,
    ReasonClass.UNCLASSIFIED: 0.0,
}

# Configurable placeholder investigation/rebuttal effort units by reason class
DEFAULT_EFFORT_MAP: dict[ReasonClass, float] = {
    ReasonClass.ITEM_NOT_RECEIVED: 1.0,
    ReasonClass.DUPLICATE_CHARGE: 1.0,
    ReasonClass.REFUND_NOT_RECEIVED: 1.2,
    ReasonClass.UNAUTHORISED: 1.5,
    ReasonClass.SUBSCRIPTION_CANCELLED: 1.5,
    ReasonClass.NOT_AS_DESCRIBED: 2.0,
    ReasonClass.OTHER: 2.0,
    ReasonClass.UNCLASSIFIED: 1.0,
}


class TriageItem(BaseModel):
    """Ranked item in the merchant triage worklist."""

    rank: int = 0
    case_id: str
    amount_paise: int
    amount_inr: float
    reason_class: ReasonClass
    reason_code: str
    p_win: float
    effort: float
    priority_score: float
    respond_by: int | None
    hours_remaining: float | None
    urgency: str
    winnable_ground_truth: bool | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


def calculate_priority(
    amount_paise: int,
    p_win: float,
    effort: float,
) -> float:
    """Calculate deterministic triage priority.

    Formula: priority = amount * p_win / effort

    Args:
        amount_paise: Dispute amount in paise.
        p_win: Estimated probability of winning (0.0 to 1.0).
        effort: Estimated effort score (> 0).

    Returns:
        Priority score (higher is higher priority).
    """
    safe_effort = max(effort, 0.001)
    safe_p_win = max(min(p_win, 1.0), 0.0)
    return round((amount_paise * safe_p_win) / safe_effort, 2)


def triage_cases(
    cases: list[DisputeCase | dict[str, Any]],
    now: int | None = None,
    p_win_map: dict[ReasonClass, float] | None = None,
    effort_map: dict[ReasonClass, float] | None = None,
) -> list[TriageItem]:
    """Rank dispute cases by priority = (amount * p_win) / effort.

    Tie-breaking: cases with identical priority are sorted by closest deadline first.

    Args:
        cases: List of DisputeCase objects or dictionary representations.
        now: Current unix timestamp in seconds for deadline calculation.
        p_win_map: Custom mapping of ReasonClass to win probability.
        effort_map: Custom mapping of ReasonClass to effort units.

    Returns:
        List of TriageItem objects sorted in descending order of priority.
    """
    current_time = int(time.time()) if now is None else int(now)
    p_win_cfg = p_win_map or DEFAULT_P_WIN_MAP
    effort_cfg = effort_map or DEFAULT_EFFORT_MAP

    items: list[TriageItem] = []

    for raw_case in cases:
        if isinstance(raw_case, DisputeCase):
            case_id = raw_case.case_id
            amount_paise = raw_case.dispute.amount
            raw_reason = raw_case.dispute.reason_code
            respond_by = raw_case.dispute.respond_by
            gt_winnable = raw_case.ground_truth.winnable
            gt_reason_class = raw_case.ground_truth.reason_class
            dispute_dict = raw_case.dispute.model_dump()
        else:
            case_id = str(raw_case.get("case_id", raw_case.get("id", "unknown")))
            disp = raw_case.get("dispute", raw_case)
            amount_paise = int(disp.get("amount", 0))
            raw_reason = str(disp.get("reason_code", "other"))
            respond_by = disp.get("respond_by")
            gt = raw_case.get("ground_truth", {})
            gt_winnable = gt.get("winnable") if isinstance(gt, dict) else None
            gt_reason_class = None
            dispute_dict = disp

        # Classify reason if not already parsed
        if gt_reason_class:
            r_class = gt_reason_class
        else:
            match = classify_reason(raw_reason)
            r_class = match.reason_class

        p_win = p_win_cfg.get(r_class, 0.50)
        effort = effort_cfg.get(r_class, 1.0)
        score = calculate_priority(amount_paise, p_win, effort)

        dl = calculate_deadline(dispute_dict, now=current_time)

        items.append(
            TriageItem(
                rank=0,
                case_id=case_id,
                amount_paise=amount_paise,
                amount_inr=round(amount_paise / 100.0, 2),
                reason_class=r_class,
                reason_code=raw_reason,
                p_win=p_win,
                effort=effort,
                priority_score=score,
                respond_by=respond_by,
                hours_remaining=dl.hours_remaining,
                urgency=dl.urgency.value,
                winnable_ground_truth=gt_winnable,
            )
        )

    # Sort descending by priority_score, then ascending by respond_by (earliest deadline first)
    def sort_key(item: TriageItem) -> tuple[float, float]:
        dl_key = float(item.respond_by) if item.respond_by is not None else float("inf")
        return (-item.priority_score, dl_key)

    items.sort(key=sort_key)

    for rank_idx, item in enumerate(items, start=1):
        item.rank = rank_idx

    return items


def load_cases_from_directory(cases_dir: Path | str) -> list[DisputeCase]:
    """Load all dispute cases from JSON files in the specified directory.

    Args:
        cases_dir: Directory containing dispute case JSON files.

    Returns:
        List of parsed DisputeCase instances.
    """
    path = Path(cases_dir)
    cases: list[DisputeCase] = []

    # Read top-level *.json files
    json_files = sorted(path.glob("*.json"))
    for jf in json_files:
        try:
            with open(jf, encoding="utf-8") as f:
                data = json.load(f)
            cases.append(DisputeCase.model_validate(data))
        except (json.JSONDecodeError, OSError, ValueError):
            pass

    return cases


def format_worklist(worklist: list[TriageItem], top_n: int = 10) -> str:
    """Format the top N triage worklist items as a formatted table string.

    Args:
        worklist: Ranked list of TriageItem objects.
        top_n: Number of top items to include.

    Returns:
        Formatted ASCII table string.
    """
    top_items = worklist[:top_n]
    lines = [
        f"{'Rank':<4} | {'Case ID':<18} | {'Amount (INR)':<13} | {'Reason Class':<23} | {'p_win':<5} | {'Effort':<6} | {'Priority':<12} | {'Urgency':<8} | {'Due In':<10}",
        "-" * 115,
    ]

    for itm in top_items:
        hours_str = f"{itm.hours_remaining:.1f}h" if itm.hours_remaining is not None else "N/A"
        amt_str = f"INR {itm.amount_inr:,.2f}"
        lines.append(
            f"{itm.rank:<4} | {itm.case_id:<18} | {amt_str:<13} | {itm.reason_class.value:<23} | {itm.p_win:<5.2f} | {itm.effort:<6.1f} | {itm.priority_score:<12.1f} | {itm.urgency:<8} | {hours_str:<10}"
        )

    return "\n".join(lines)
