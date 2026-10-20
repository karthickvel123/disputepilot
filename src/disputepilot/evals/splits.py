"""Seeded, stratified dev/validation/held-out split with a leakage check."""

from __future__ import annotations

import random
import re
from collections import defaultdict

from disputepilot.core.models import DisputeCase

SPLITS = ("dev", "validation", "heldout")


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", (text or "").lower()).strip()


def three_way_split(
    cases: list[DisputeCase],
    seed: int = 42,
    fractions: tuple[float, float, float] = (0.5, 0.2, 0.3),
    group_aware: bool = True,
) -> dict[str, list[DisputeCase]]:
    """Stratify by ground-truth class; deterministic for a given seed and input order.

    With ``group_aware`` (default) all cases sharing the same normalised reason text are
    kept in ONE split, so templated duplicates cannot leak across dev/validation/held-out.
    """
    if abs(sum(fractions) - 1.0) > 1e-9:
        raise ValueError("fractions must sum to 1")
    by_class: dict[str, list[DisputeCase]] = defaultdict(list)
    for c in sorted(cases, key=lambda c: c.case_id):
        by_class[str(getattr(c.ground_truth.reason_class, "value", c.ground_truth.reason_class))].append(c)
    rng = random.Random(seed)
    out: dict[str, list[DisputeCase]] = {k: [] for k in SPLITS}
    # A text group spanning several classes is pinned to the first split it lands in.
    text_home: dict[str, str] = {}
    for key in sorted(by_class):
        items = by_class[key]
        if group_aware:
            groups: dict[str, list[DisputeCase]] = defaultdict(list)
            for c in items:
                groups[_norm(c.dispute.reason_code)].append(c)
            units = [groups[t] for t in sorted(groups)]
        else:
            units = [[c] for c in items]
        rng.shuffle(units)
        n = len(items)
        targets = {"dev": n * fractions[0], "validation": n * fractions[1], "heldout": n * fractions[2]}
        filled = {k: 0 for k in SPLITS}
        for unit in units:
            t = _norm(unit[0].dispute.reason_code)
            if group_aware and t in text_home:
                dest = text_home[t]
            else:
                dest = max(SPLITS, key=lambda k: targets[k] - filled[k])
                if group_aware:
                    text_home[t] = dest
            out[dest] += unit
            filled[dest] += len(unit)
    return out


def leakage_report(splits: dict[str, list[DisputeCase]]) -> dict[str, object]:
    """Report case-id overlap and identical normalised reason text shared across splits."""
    ids: dict[str, str] = {}
    id_overlap: list[str] = []
    text_owner: dict[str, set[str]] = defaultdict(set)
    for name, cs in splits.items():
        for c in cs:
            if c.case_id in ids:
                id_overlap.append(c.case_id)
            ids[c.case_id] = name
            text_owner[_norm(c.dispute.reason_code)].add(name)
    shared = {t: sorted(o) for t, o in text_owner.items() if len(o) > 1}
    total = sum(len(v) for v in splits.values())
    return {
        "sizes": {k: len(v) for k, v in splits.items()},
        "total": total,
        "case_id_overlap": id_overlap,
        "reason_text_shared_across_splits": len(shared),
        "distinct_reason_texts": len(text_owner),
        "examples": dict(list(shared.items())[:5]),
    }
