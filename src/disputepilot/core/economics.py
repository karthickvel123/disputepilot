"""Single source of truth for dispute economics (all amounts SIMULATED unless stated).

Outcome definition (applies to every policy, so comparisons are like-for-like):

* Value is measured **relative to accepting the dispute**. Accepting forfeits the
  disputed amount, which is the zero point. This is NOT recovered revenue.
* Contest + win  -> ``+amount - contest_effort`` (and the fee if ``fee_trigger == "contest"``).
* Contest + lose -> ``-contest_effort - fee``.
* Accept         -> ``-accept_effort``.
* Escalate       -> ``-review_cost`` plus the outcome of the assumed human resolution.

With every cost at zero, contesting an unwinnable case is free, so contest-all is
weakly dominant and no policy can beat it. Uplift is only meaningful under non-zero
costs, which must come from the merchant's real fee schedule and labour cost.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any, Literal

FeeTrigger = Literal["loss", "contest"]
Bucket = Literal["contest", "accept", "escalate"]


@dataclass(frozen=True)
class CostModel:
    """Cost assumptions in INR. Defaults are zero (the legacy, degenerate setting)."""

    name: str = "zero_cost_legacy"
    fee_inr: float = 0.0
    fee_trigger: FeeTrigger = "loss"
    contest_effort_inr: float = 0.0
    accept_effort_inr: float = 0.0
    review_cost_inr: float = 0.0

    def __post_init__(self) -> None:
        for field in ("fee_inr", "contest_effort_inr", "accept_effort_inr", "review_cost_inr"):
            if getattr(self, field) < 0:
                raise ValueError(f"{field} must be non-negative")
        if self.fee_trigger not in ("loss", "contest"):
            raise ValueError("fee_trigger must be 'loss' or 'contest'")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def scaled(self, factor: float) -> CostModel:
        """Same model in other units (e.g. factor=100 converts INR -> paise)."""
        return CostModel(
            name=self.name,
            fee_inr=self.fee_inr * factor,
            fee_trigger=self.fee_trigger,
            contest_effort_inr=self.contest_effort_inr * factor,
            accept_effort_inr=self.accept_effort_inr * factor,
            review_cost_inr=self.review_cost_inr * factor,
        )

    @classmethod
    def from_config(cls, config: dict[str, Any], name: str = "config") -> CostModel:
        """Build from recommend.yaml (paise keys)."""
        return cls(
            name=name,
            fee_inr=float(config.get("fee_per_dispute_paise", 0) or 0) / 100.0,
            fee_trigger=config.get("fee_trigger", "loss"),
            contest_effort_inr=float(config.get("effort_cost_paise", 0) or 0) / 100.0,
            accept_effort_inr=float(config.get("accept_effort_paise", 0) or 0) / 100.0,
            review_cost_inr=float(config.get("review_cost_paise", 0) or 0) / 100.0,
        )


def contest_value(amount: float, won: bool, cm: CostModel) -> tuple[float, float, float]:
    """Return (net, fees, operational_cost) for a contested dispute."""
    fee = cm.fee_inr if (not won or cm.fee_trigger == "contest") else 0.0
    net = (amount if won else 0.0) - cm.contest_effort_inr - fee
    return net, fee, cm.contest_effort_inr


def accept_value(cm: CostModel) -> tuple[float, float, float]:
    return -cm.accept_effort_inr, 0.0, cm.accept_effort_inr


def expected_net_advantage_of_contest(p_win: float, amount: float, cm: CostModel) -> float:
    """Expected value of contesting minus expected value of accepting (INR).

    ``p_win`` is only as good as its source; the heuristic in ``recommend.py`` is
    uncalibrated, so this number is a simulated estimate, not a forecast.
    """
    if not 0.0 <= p_win <= 1.0:
        raise ValueError("p_win must be within [0, 1]")
    if amount < 0 or math.isnan(amount):
        raise ValueError("amount must be a non-negative number")
    fee_if_win = cm.fee_inr if cm.fee_trigger == "contest" else 0.0
    ev_contest = (
        p_win * (amount - cm.contest_effort_inr - fee_if_win)
        + (1.0 - p_win) * (-cm.contest_effort_inr - cm.fee_inr)
    )
    return ev_contest - (-cm.accept_effort_inr)


def break_even_p_win(amount: float, cm: CostModel) -> float | None:
    """p_win at which contesting and accepting have equal expected value."""
    if amount <= 0:
        return None
    fee_if_win = cm.fee_inr if cm.fee_trigger == "contest" else 0.0
    # p*(A - eff - fw) + (1-p)*(-eff - f) + acc_eff = 0
    denom = amount - fee_if_win + cm.fee_inr
    if denom <= 0:
        return None
    p = (cm.contest_effort_inr + cm.fee_inr - cm.accept_effort_inr) / denom
    return max(0.0, p)


# --------------------------------------------------------------------------- policies


@dataclass(frozen=True)
class CaseRecord:
    case_id: str
    amount_inr: float
    winnable: bool  # SIMULATED outcome label; not an observed bank result


def _case_value(rec: CaseRecord, bucket: Bucket, cm: CostModel, resolution: str) -> tuple[float, float, float]:
    if bucket == "escalate":
        bucket_after = resolution  # assumed human decision: "accept" or "contest"
        net, fee, ops = (contest_value(rec.amount_inr, rec.winnable, cm)
                         if bucket_after == "contest" else accept_value(cm))
        return net - cm.review_cost_inr, fee, ops + cm.review_cost_inr
    if bucket == "contest":
        return contest_value(rec.amount_inr, rec.winnable, cm)
    return accept_value(cm)


def _bootstrap_ci(diffs: list[float], seed: int, n_boot: int = 2000) -> tuple[float, float] | None:
    n = len(diffs)
    if n < 2:
        return None
    rng = random.Random(seed)
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]


def evaluate_policy(
    records: list[CaseRecord],
    buckets: dict[str, Bucket],
    cm: CostModel,
    resolution: str = "accept",
) -> dict[str, Any]:
    """Aggregate one policy on a fixed set of cases."""
    nets, fees, ops = [], 0.0, 0.0
    counts = {"contest": 0, "accept": 0, "escalate": 0}
    gross = {"contest": 0.0, "accept": 0.0, "escalate": 0.0}
    missed = incorrect = 0
    missed_amt = 0.0
    for r in records:
        b = buckets[r.case_id]
        counts[b] += 1
        gross[b] += r.amount_inr
        net, fee, op = _case_value(r, b, cm, resolution)
        nets.append(net)
        fees += fee
        ops += op
        eff_b = resolution if b == "escalate" else b
        if eff_b != "contest" and r.winnable:
            missed += 1
            missed_amt += r.amount_inr
        if eff_b == "contest" and not r.winnable:
            incorrect += 1
    n = len(records)
    return {
        "n_evaluated": n,
        "n_contested": counts["contest"],
        "n_accepted": counts["accept"],
        "n_escalated": counts["escalate"],
        "gross_inr_contested": round(gross["contest"], 2),
        "gross_inr_accepted": round(gross["accept"], 2),
        "gross_inr_escalated": round(gross["escalate"], 2),
        "net_value_inr_simulated": round(sum(nets), 2),
        "fees_inr": round(fees, 2),
        "operational_costs_inr": round(ops, 2),
        "avg_value_per_dispute_inr": round(sum(nets) / n, 2) if n else 0.0,
        "missed_opportunities": missed,
        "missed_opportunity_amount_inr": round(missed_amt, 2),
        "incorrect_contests": incorrect,
        "_per_case": nets,
    }


def compare_policies(
    records: list[CaseRecord],
    policy_buckets: dict[str, dict[str, Bucket]],
    cm: CostModel,
    resolution: str = "accept",
    seed: int = 42,
) -> dict[str, Any]:
    """Evaluate several policies on IDENTICAL cases and report uplift with 95% bootstrap CIs.

    Adds contest_all, accept_all and an oracle (contest iff simulated label says winnable;
    an upper bound that is not deployable).
    """
    ids = [r.case_id for r in records]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate case_id in records")
    for name, b in policy_buckets.items():
        if set(b) != set(ids):
            raise ValueError(f"policy '{name}' does not cover exactly the evaluated cases")

    all_policies: dict[str, dict[str, Bucket]] = {
        "contest_all": {i: "contest" for i in ids},
        "accept_all": {i: "accept" for i in ids},
        **policy_buckets,
        "oracle_upper_bound": {r.case_id: ("contest" if r.winnable else "accept") for r in records},
    }
    results = {k: evaluate_policy(records, v, cm, resolution) for k, v in all_policies.items()}
    for name, res in results.items():
        for base in ("contest_all", "accept_all"):
            diffs = [a - b for a, b in zip(res["_per_case"], results[base]["_per_case"])]
            ci = _bootstrap_ci(diffs, seed)
            res[f"uplift_vs_{base}_inr"] = round(sum(diffs), 2)
            res[f"uplift_vs_{base}_ci95_per_case_inr"] = (
                [round(ci[0], 2), round(ci[1], 2)] if ci else None
            )
    for res in results.values():
        res.pop("_per_case")
    return {"cost_model": cm.to_dict(), "escalation_resolution": resolution, "policies": results}


def break_even_contest_effort(
    records: list[CaseRecord],
    policy_buckets: dict[str, Bucket],
    cm: CostModel,
    resolution: str = "accept",
    hi: float = 100_000.0,
) -> float | None:
    """Per-contest effort (INR) at which the policy equals contest-all; None if no crossing in [0, hi].

    Net value is linear in contest effort, so two evaluations determine the root.
    """
    def uplift(effort: float) -> float:
        c = CostModel(**{**cm.to_dict(), "contest_effort_inr": effort})
        out = compare_policies(records, {"p": policy_buckets}, c, resolution)
        return out["policies"]["p"]["uplift_vs_contest_all_inr"]

    u0, u1 = uplift(0.0), uplift(hi)
    if u0 >= 0:
        return 0.0
    if u1 < 0:
        return None
    return round(-u0 * hi / (u1 - u0), 2)


# ---------------------------------------------------------------- probability metrics


def brier_score(pairs: Iterable[tuple[float, bool]]) -> float | None:
    pairs = list(pairs)
    if not pairs:
        return None
    return round(sum((p - float(y)) ** 2 for p, y in pairs) / len(pairs), 4)


def log_loss(pairs: Iterable[tuple[float, bool]], eps: float = 1e-6) -> float | None:
    pairs = list(pairs)
    if not pairs:
        return None
    total = 0.0
    for p, y in pairs:
        p = min(1 - eps, max(eps, p))
        total += -(math.log(p) if y else math.log(1 - p))
    return round(total / len(pairs), 4)


def base_rate_brier(pairs: Iterable[tuple[float, bool]]) -> float | None:
    """Brier score of always predicting the sample base rate (the defensible baseline)."""
    ys = [float(y) for _, y in pairs]
    if not ys:
        return None
    m = sum(ys) / len(ys)
    return round(sum((m - y) ** 2 for y in ys) / len(ys), 4)
