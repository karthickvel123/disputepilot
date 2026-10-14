"""Deterministic deadline calculation and urgency evaluation for chargeback disputes."""

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from disputepilot.core.models import RazorpayDispute


class UrgencyLevel(str, Enum):
    """Urgency level classification based on hours remaining until deadline."""

    OK = "ok"
    SOON = "soon"
    CRITICAL = "critical"
    OVERDUE = "overdue"
    UNKNOWN = "unknown"


class DeadlineInfo(BaseModel):
    """Deadline and reminder information for a dispute."""

    dispute_id: str
    respond_by: int | None
    now: int
    hours_remaining: float | None
    urgency: UrgencyLevel
    reminders: dict[str, int | None] = Field(default_factory=dict)
    is_overdue: bool = False


def calculate_deadline(
    dispute: RazorpayDispute | dict[str, Any],
    now: int | None = None,
) -> DeadlineInfo:
    """Calculate hours remaining, urgency, and reminder timestamps for a dispute.

    Thresholds:
    - Overdue: hours_remaining <= 0
    - Critical: 0 < hours_remaining <= 24.0
    - Soon: 24.0 < hours_remaining <= 48.0
    - Ok: hours_remaining > 48.0
    - Unknown: missing or zero respond_by

    Args:
        dispute: RazorpayDispute object or dictionary representation.
        now: Current unix timestamp in seconds. Injected for determinism;
            defaults to current time if None.

    Returns:
        DeadlineInfo model instance.
    """
    if isinstance(dispute, RazorpayDispute):
        disp_id = dispute.id
        respond_by = dispute.respond_by
    else:
        disp_id = str(dispute.get("id", "unknown_dispute"))
        respond_by = dispute.get("respond_by")

    current_time = int(time.time()) if now is None else int(now)

    # Edge case: missing or zero respond_by
    if respond_by is None or respond_by <= 0:
        return DeadlineInfo(
            dispute_id=disp_id,
            respond_by=None,
            now=current_time,
            hours_remaining=None,
            urgency=UrgencyLevel.UNKNOWN,
            reminders={"t_minus_48h": None, "t_minus_24h": None, "t_minus_12h": None},
            is_overdue=False,
        )

    seconds_remaining = respond_by - current_time
    hours_remaining = round(seconds_remaining / 3600.0, 2)

    reminders = {
        "t_minus_48h": respond_by - (48 * 3600),
        "t_minus_24h": respond_by - (24 * 3600),
        "t_minus_12h": respond_by - (12 * 3600),
    }

    if seconds_remaining <= 0:
        urgency = UrgencyLevel.OVERDUE
        is_overdue = True
    elif hours_remaining <= 24.0:
        urgency = UrgencyLevel.CRITICAL
        is_overdue = False
    elif hours_remaining <= 48.0:
        urgency = UrgencyLevel.SOON
        is_overdue = False
    else:
        urgency = UrgencyLevel.OK
        is_overdue = False

    return DeadlineInfo(
        dispute_id=disp_id,
        respond_by=respond_by,
        now=current_time,
        hours_remaining=hours_remaining,
        urgency=urgency,
        reminders=reminders,
        is_overdue=is_overdue,
    )
