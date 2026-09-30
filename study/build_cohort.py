#!/usr/bin/env python3
"""CLI for acquiring, building, and auditing the frozen Combine cohort."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from study.cohort import build, undrafted_review_sample, write_csv
from study.nba_client import NBAClient


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "study/data/raw/nba")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "study/output")
    parser.add_argument("--birth-years", type=Path, default=ROOT / "study/data/birth_year_overrides.csv")
    parser.add_argument("--crosswalk", type=Path, default=ROOT / "study/data/identity_crosswalk.csv")
    parser.add_argument("--name-forms", type=Path, default=ROOT / "study/data/name_form_overrides.csv")
    parser.add_argument("--undrafted-review", type=Path, default=ROOT / "study/data/undrafted_review.csv")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--fetch-profiles", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--delay", type=float, default=0.6)
    parser.add_argument("--retries", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.end_year < args.start_year:
        print("end year must not precede start year", file=sys.stderr)
        return 2
    client = NBAClient(
        args.cache_dir, offline=args.offline, refresh=args.refresh,
        timeout=args.timeout, delay_seconds=args.delay, retries=args.retries,
    )
    try:
        rows, audit, unresolved = build(
            client, range(args.start_year, args.end_year + 1),
            args.birth_years, args.crosswalk, args.name_forms,
            args.undrafted_review, args.fetch_profiles,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "combine_cohort.csv", rows)
    write_csv(args.output_dir / "unresolved_birth_years.csv", unresolved)
    write_csv(args.output_dir / "undrafted_review_sample.csv", undrafted_review_sample(rows))
    (args.output_dir / "cohort_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "participants": audit["participant_count"],
        "usable_years": audit["usable_years"],
        "birth_year_coverage": audit["birth_year_coverage"],
        "generation_feature_coverage": audit["generation_feature_coverage"],
        "exact_birth_feature_coverage": audit["exact_birth_feature_coverage"],
        "given_name_primary_eligible": audit["given_name_primary_eligible"],
        "undrafted_review_completed": audit["undrafted_review_sample"]["completed"],
        "cohort_analysis_ready": audit["cohort_analysis_ready"],
        "output_dir": str(args.output_dir),
    }, indent=2))
    return 0 if audit["cohort_analysis_ready"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
