"""Rules-only classifier metrics per dev/validation/held-out split (group-aware, seeded).

Usage: uv run python scripts/eval_rules_splits.py [--splits dev,validation,heldout] [--seed 42]
Tune rules on `dev`, check `validation`, and look at `heldout` only for the final report.
"""

import argparse
import json

from disputepilot.evals.runner import _load_cases_from_dir, evaluate_reason_classifier
from disputepilot.evals.splits import three_way_split

p = argparse.ArgumentParser()
p.add_argument("--splits", default="dev,validation,heldout")
p.add_argument("--seed", type=int, default=42)
p.add_argument("--dir", default="data/cases_messy")
a = p.parse_args()
sp = three_way_split(_load_cases_from_dir(a.dir), a.seed)
out = {}
for name in a.splits.split(","):
    m = evaluate_reason_classifier(sp[name])
    wrong = sum(v for g, row in m["confusion_matrix"].items() for pr, v in row.items()
                if pr not in (g, "unclassified"))
    out[name] = {"n": len(sp[name]), "accuracy": m["accuracy"], "macro_f1": m["macro_f1"],
                 "coverage": m["coverage"], "accuracy_on_answered": m["accuracy_on_answered"],
                 "confidently_wrong": wrong}
print(json.dumps(out, indent=1))
