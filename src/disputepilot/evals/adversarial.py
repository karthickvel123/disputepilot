"""Adversarial evaluation: how the classifier and injection detector behave on hostile input.

Run:  uv run python -m disputepilot.evals.adversarial            (rules only, offline)
      uv run python -m disputepilot.evals.adversarial --llm      (also use the configured LLM)

Reported per category and NEVER averaged into one score, because the failure modes differ:
  coverage         share of cases the classifier answered (did not abstain)
  accuracy_answered correct / answered
  wrong_answer     answered with a class outside the case's acceptable set (a confident mistake -
                   the dangerous outcome, since it would steer evidence checks and the draft)
  abstain          returned 'unclassified' (routes to a human; always safe)
  ambiguous_answered  share of deliberately ambiguous cases answered instead of routed to a human
  crashes          exceptions raised (must be zero)
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

DEFAULT_CASES = Path("evals/adversarial/cases.jsonl")
DEFAULT_REGRESSION = Path("evals/adversarial/regression_cases.jsonl")
DEFAULT_OUT = Path("evals/adversarial")
ABSTAIN = "unclassified"

Classifier = Callable[[str | None], tuple[str, bool]]  # text -> (class_value, needs_review)
Detector = Callable[[str], list[str]]


def load_cases(path: Path = DEFAULT_CASES) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _rate(n: int, d: int) -> float | None:
    return None if d == 0 else round(n / d, 4)


def evaluate_reasons(cases: list[dict[str, Any]], classify: Classifier) -> dict[str, Any]:
    by_cat: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "answered": 0, "correct": 0, "wrong": 0, "abstain": 0, "crashes": 0, "wrong_cases": []})
    for c in (x for x in cases if x["suite"] == "reason"):
        s = by_cat[c["category"]]
        s["n"] += 1
        try:
            pred, needs_review = classify(c["text"])
        except Exception as exc:  # noqa: BLE001 - a crash is itself a measured failure
            s["crashes"] += 1
            s["wrong_cases"].append({"id": c["id"], "text": c["text"], "pred": f"CRASH:{type(exc).__name__}", "ideal": c["ideal"]})
            continue
        if pred == ABSTAIN or needs_review:
            s["abstain"] += 1
            continue
        s["answered"] += 1
        if pred in c["acceptable"]:
            if c["ideal"] != "abstain":
                s["correct"] += 1
        else:
            s["wrong"] += 1
            s["wrong_cases"].append({"id": c["id"], "text": (c["text"] or "")[:90], "pred": pred, "ideal": c["ideal"], "note": c.get("note", "")})
    out: dict[str, Any] = {}
    for cat, s in sorted(by_cat.items()):
        n = s["n"]
        ambiguous = cat == "ambiguous"
        out[cat] = {
            "n": n,
            "coverage": _rate(s["answered"], n),
            "accuracy_answered": None if ambiguous else _rate(s["correct"], s["answered"]),
            "wrong_answer": _rate(s["wrong"], n),
            "wrong_answer_count": s["wrong"],
            "abstain": _rate(s["abstain"], n),
            "ambiguous_answered": _rate(s["answered"], n) if ambiguous else None,
            "crashes": s["crashes"],
            "wrong_cases": s["wrong_cases"],
        }
    return out


def evaluate_regression(cases: list[dict[str, Any]], classify: Classifier) -> dict[str, Any]:
    """Per-fix pass/fail. must=answer -> must return `ideal`; abstain -> must go to a human;
    safe -> `ideal` or an abstention is fine, any other class is a failure."""
    by_fix: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "passed": 0, "answered": 0, "failures": []})
    for c in cases:
        s = by_fix[c["fix"]]
        s["n"] += 1
        pred, needs_review = classify(c["text"])
        abstained = pred == ABSTAIN or needs_review
        if not abstained:
            s["answered"] += 1
        if c["must"] == "answer":
            ok = (not abstained) and pred == c["ideal"]
        elif c["must"] == "abstain":
            ok = abstained
        else:
            ok = abstained or pred == c["ideal"]
        if ok:
            s["passed"] += 1
        else:
            s["failures"].append({"id": c["id"], "text": c["text"], "pred": ABSTAIN if abstained else pred, "must": c["must"]})
    return dict(sorted(by_fix.items()))


def evaluate_injection(cases: list[dict[str, Any]], detect: Detector) -> dict[str, Any]:
    by_cat: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "flagged": 0, "missed": [], "false_pos": []})
    for c in (x for x in cases if x["suite"] == "injection"):
        s = by_cat[c["category"]]
        s["n"] += 1
        flags = detect(c["text"])
        if flags:
            s["flagged"] += 1
        if c["expect_flag"] and not flags:
            s["missed"].append({"id": c["id"], "text": c["text"], "note": c.get("note", "")})
        if not c["expect_flag"] and flags:
            s["false_pos"].append({"id": c["id"], "text": c["text"], "flags": flags})
    return {
        cat: {
            "n": s["n"],
            "flag_rate": _rate(s["flagged"], s["n"]),
            "missed": s["missed"],
            "false_positives": s["false_pos"],
        }
        for cat, s in sorted(by_cat.items())
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def render_markdown(reasons: dict[str, Any], injection: dict[str, Any], mode: str, regression: dict[str, Any] | None = None) -> str:
    L = [
        "# Adversarial Evaluation Report",
        "",
        f"Mode: **{mode}**. Cases are hand-written (`build_dataset.py`), small, and synthetic: they probe known weak points and are",
        "not a sample of real disputes. Categories are reported separately and never averaged.",
        "",
        "## Reason classification",
        "",
        "| Category | n | Coverage | Accuracy when answered | Wrong answer | Abstain | Ambiguous answered | Crashes |",
        "| :-- | --: | --: | --: | --: | --: | --: | --: |",
    ]
    for cat, r in reasons.items():
        L.append(f"| {cat} | {r['n']} | {_pct(r['coverage'])} | {_pct(r['accuracy_answered'])} | {_pct(r['wrong_answer'])} ({r['wrong_answer_count']}) | {_pct(r['abstain'])} | {_pct(r['ambiguous_answered'])} | {r['crashes']} |")
    L += ["", "### Confident wrong answers", ""]
    any_wrong = False
    for cat, r in reasons.items():
        for w in r["wrong_cases"]:
            any_wrong = True
            L.append(f"- `{w['id']}` [{cat}] predicted **{w['pred']}**, ideal {w['ideal']}: \"{w['text']}\"" + (f" ({w['note']})" if w.get("note") else ""))
    if not any_wrong:
        L.append("- none")
    if regression:
        L += ["", "## Regression cases (one or more new cases per fix)", "",
              "Written with fresh wording after the fixes were designed. Passing shows the mechanisms work as intended; it is not",
              "independent evidence of real-world accuracy, and `safe`/`abstain` cases can pass by routing to a human.", "",
              "| Fix | n | Passed | Answered | Failures |", "| :-- | --: | --: | --: | --: |"]
        for fix, r in regression.items():
            L.append(f"| {fix} | {r['n']} | {r['passed']} | {r['answered']} | {len(r['failures'])} |")
        for fix, r in regression.items():
            for f in r["failures"]:
                L.append(f"- FAIL `{f['id']}` [{fix}/{f['must']}] predicted {f['pred']}: \"{f['text']}\"")
    L += ["", "## Injection detector (audit flags only; the real defence is architectural)", "",
          "| Category | n | Flag rate | Missed | False positives |", "| :-- | --: | --: | --: | --: |"]
    for cat, r in injection.items():
        L.append(f"| {cat} | {r['n']} | {_pct(r['flag_rate'])} | {len(r['missed'])} | {len(r['false_positives'])} |")
    for cat, r in injection.items():
        for m in r["missed"]:
            L.append(f"- missed [{cat}] `{m['id']}`: \"{m['text']}\"" + (f" ({m['note']})" if m["note"] else ""))
        for f in r["false_positives"]:
            L.append(f"- false positive [{cat}] `{f['id']}`: \"{f['text']}\" -> {', '.join(f['flags'])}")
    L += ["", "## What this does not show", "",
          "- Behaviour on real disputes, or on documents (conflicting dates/amounts, malformed PDFs/images): not covered by this pass.",
          "- The LLM fallback is only exercised with `--llm`; without it, every case the rules do not match is an abstention.",
          ""]
    return "\n".join(L)


def _real_classifier(use_llm: bool) -> Classifier:
    from disputepilot.core.reasons import classify_reason

    llm = None
    if use_llm:
        from disputepilot.extraction.llm import get_llm_client

        llm = get_llm_client()

    def run(text: str | None) -> tuple[str, bool]:
        m = classify_reason(text, llm_client=llm)
        return m.reason_class.value, m.needs_review

    return run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--llm", action="store_true", help="also use the configured LLM for unmatched text")
    args = ap.parse_args(argv)

    from disputepilot.safety.untrusted import detect_injection

    cases = load_cases(args.cases)
    reasons = evaluate_reasons(cases, _real_classifier(args.llm))
    injection = evaluate_injection(cases, detect_injection)
    classify = _real_classifier(args.llm)
    regression = evaluate_regression(load_cases(DEFAULT_REGRESSION), classify) if DEFAULT_REGRESSION.exists() else None
    mode = "rules + LLM" if args.llm else "rules only (no LLM)"
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.json").write_text(json.dumps({"mode": mode, "reasons": reasons, "regression": regression, "injection": injection}, indent=2, ensure_ascii=False), encoding="utf-8")
    (args.out / "report.md").write_text(render_markdown(reasons, injection, mode, regression), encoding="utf-8")
    print(f"wrote {args.out / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
