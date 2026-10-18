"""CLI for generating synthetic dispute cases."""

import argparse
import json
from pathlib import Path
from typing import Any

from disputepilot.sim.generator import generate_cases


def save_cases(cases: list[Any], out_dir: Path) -> None:
    """Save generated dispute cases and markdown documents to disk.

    Args:
        cases: List of DisputeCase objects.
        out_dir: Target root directory.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    for case in cases:
        # 1. Write the primary case JSON file in out_dir/<case_id>.json
        case_json_path = out_dir / f"{case.case_id}.json"
        case_data = case.model_dump(mode="json")
        with open(case_json_path, "w", encoding="utf-8") as f:
            json.dump(case_data, f, indent=2)

        # 2. Write individual evidence document files in out_dir/<case_id>/<doc_filename>
        case_folder = out_dir / case.case_id
        case_folder.mkdir(parents=True, exist_ok=True)

        for doc in case.documents:
            doc_path = case_folder / doc.file_name
            with open(doc_path, "w", encoding="utf-8") as f:
                f.write(doc.content)

        # 3. Also write case.json inside the case folder for folder-based access
        with open(case_folder / "case.json", "w", encoding="utf-8") as f:
            json.dump(case_data, f, indent=2)


def print_distribution_summary(cases: list[Any]) -> None:
    """Print label and adversarial distribution summary table to stdout."""
    total = len(cases)
    reason_counts: dict[str, int] = {}
    winnable_counts: dict[bool, int] = {True: 0, False: 0}
    adversarial_count = 0
    adv_types_count: dict[str, int] = {}
    doc_counts: list[int] = []

    for case in cases:
        rc = case.ground_truth.reason_class.value
        reason_counts[rc] = reason_counts.get(rc, 0) + 1

        winnable_counts[case.ground_truth.winnable] += 1

        if case.ground_truth.adversarial.is_adversarial:
            adversarial_count += 1
            for adv_type in case.ground_truth.adversarial.adversarial_types:
                adv_types_count[adv_type] = adv_types_count.get(adv_type, 0) + 1

        doc_counts.append(len(case.documents))

    print("\n" + "=" * 60)
    print(f"DISPUTE SIMULATOR GENERATION SUMMARY (Total Cases: {total})")
    print("=" * 60)

    print("\n[Reason Class Distribution]")
    for r_class, count in sorted(reason_counts.items()):
        pct = (count / total) * 100
        print(f"  - {r_class:<25}: {count:3d} ({pct:5.1f}%)")

    print("\n[Ground-Truth Winnability Distribution]")
    w_count = winnable_counts[True]
    l_count = winnable_counts[False]
    print(f"  - Winnable (Contestable) : {w_count:3d} ({(w_count / total) * 100:5.1f}%)")
    print(f"  - Unwinnable (Accept)    : {l_count:3d} ({(l_count / total) * 100:5.1f}%)")

    print("\n[Adversarial Cases Breakdown]")
    adv_pct = (adversarial_count / total) * 100
    print(f"  - Total Adversarial Cases: {adversarial_count:3d} ({adv_pct:5.1f}%)")
    for adv_type, count in sorted(adv_types_count.items()):
        print(f"    * {adv_type:<23}: {count:3d}")

    avg_docs = sum(doc_counts) / total if total > 0 else 0
    print(f"\n[Evidence Documents per Case]: Average {avg_docs:.1f} docs (Range: {min(doc_counts)}-{max(doc_counts)})")
    print("=" * 60 + "\n")


def main() -> None:
    """CLI entry point for dispute simulation generator."""
    parser = argparse.ArgumentParser(description="Generate synthetic Razorpay dispute cases.")
    parser.add_argument(
        "--n",
        "-n",
        type=int,
        default=150,
        help="Number of dispute cases to generate (default: 150)",
    )
    parser.add_argument(
        "--seed",
        "-s",
        type=int,
        default=42,
        help="Random seed for deterministic generation (default: 42)",
    )
    parser.add_argument(
        "--out",
        "-o",
        type=str,
        default="data/cases/",
        help="Output directory path (default: data/cases/)",
    )
    parser.add_argument(
        "--messy",
        action="store_true",
        help="Generate noisy, colloquial, non-standard dispute cases",
    )

    args = parser.parse_args()

    out_dir_str = args.out
    if args.messy and out_dir_str == "data/cases/":
        out_dir_str = "data/cases_messy/"

    out_path = Path(out_dir_str)
    if args.messy:
        from disputepilot.sim.messy import generate_messy_cases

        cases = generate_messy_cases(n=args.n, seed=args.seed)
    else:
        cases = generate_cases(n=args.n, seed=args.seed)

    save_cases(cases=cases, out_dir=out_path)
    print_distribution_summary(cases)
    print(f"Successfully wrote {len(cases)} cases and evidence documents to {out_path.resolve()}")


if __name__ == "__main__":
    main()
