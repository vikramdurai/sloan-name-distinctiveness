#!/usr/bin/env python3
"""Post-analysis integrity audit that never refits or reads row-level outcomes."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HASHES = {
    "study/output/combine_cohort.csv": "c89fea37b806994ac521accfe1ebe5ebff6d5edd01b0c96edf9b0dbc66e9347f",
    "study/modeling_spec.json": "47901ebddcb8978d842748a94961410238cb0332689713737d491492d0cef9c1",
    "study/modeling.py": "7931543346517feb352cd509a85425f5628d9701433d28f5418ada6d7135c663",
    "study/run_models.py": "77cc077478a78955587c1502fb2058682a2d3076767ffa4763f9e59d5a5ee109",
    "study/model_output/validation_tuning.json": "00c63c1a61bff9f2df0d2d4cbc75724d0f480b7ca19179d955449904a47dc4ce",
    "study/model_output/final_run_started.json": "ffe1276d72b4e49dcda731b482a6c6870e6c1d242ca4d934b6d731ac7f697cf7",
    "study/model_output/final_results.json": "51adcee1f2d1944ac893ef4412b6f9816dae4aff28ab0cbe8ddc7e1141919519",
}
FORBIDDEN_AGGREGATE_FIELDS = {
    "PLAYER_ID", "combine_key", "FIRST_NAME", "LAST_NAME", "PLAYER_NAME",
    "display_name", "draft_person_id", "birth_year",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(left: float, right: float, tolerance: float = 1e-12) -> bool:
    return math.isclose(left, right, rel_tol=tolerance, abs_tol=tolerance)


def audit() -> dict:
    result = json.loads((ROOT / "study/model_output/final_results.json").read_text())
    spec = json.loads((ROOT / "study/modeling_spec.json").read_text())
    checks: dict[str, bool] = {}

    for relative, expected in EXPECTED_HASHES.items():
        checks[f"hash:{relative}"] = sha256(ROOT / relative) == expected

    checks["final_status"] = result.get("status") == "final_locked_test_consumed"
    checks["cohort_hash_embedded"] = result.get("cohort_sha256") == EXPECTED_HASHES["study/output/combine_cohort.csv"]
    checks["spec_hash_embedded"] = result.get("spec_sha256") == EXPECTED_HASHES["study/modeling_spec.json"]
    checks["all_models_reported"] = set(result["prediction"]["models"]) == set(spec["models"])
    checks["all_sensitivities_reported"] = set(result["sensitivity_analyses"]) == set(spec["sensitivity_analyses"])
    checks["all_bootstrap_replicates_retained"] = all(
        value["retained_replicates"] == spec["bootstrap"]["replicates"]
        for value in result["prediction"]["paired_bootstrap_95"].values()
    )

    baseline = result["prediction"]["models"]["baseline"]["metrics"]
    expanded = result["prediction"]["models"]["baseline_plus_name"]["metrics"]
    differences = result["prediction"]["baseline_plus_name_minus_baseline"]
    checks["primary_metric_differences_recompute"] = all(
        close(differences[metric], expanded[metric] - baseline[metric])
        for metric in differences
    )

    association = result["association"]["co_primary"]
    checks["association_exposures_match_contract"] = set(association) == set(
        spec["association"]["co_primary_exposures"]
    )
    checks["odds_ratios_match_coefficients"] = all(
        close(value["odds_ratio"], math.exp(value["coefficient_per_bit"]))
        for value in association.values()
    )
    checks["association_intervals_ordered"] = all(
        value["confidence_interval_95"][0] <= value["odds_ratio"] <= value["confidence_interval_95"][1]
        for value in association.values()
    )
    checks["holm_decisions_match_alpha"] = all(
        value["reject"] == (value["adjusted_p"] <= spec["association"]["alpha"])
        for value in association.values()
    )

    sensitivity_arithmetic = []
    for value in result["sensitivity_analyses"].values():
        metrics = value["prediction"]["models"]
        reported = value["prediction"]["baseline_plus_name_minus_baseline"]
        sensitivity_arithmetic.append(all(
            close(
                reported[metric],
                metrics["baseline_plus_name"]["metrics"][metric]
                - metrics["baseline"]["metrics"][metric],
            )
            for metric in reported
        ))
    checks["sensitivity_metric_differences_recompute"] = all(sensitivity_arithmetic)

    table_files = sorted((ROOT / "study/report/tables").glob("*.csv"))
    checks["six_aggregate_tables_present"] = len(table_files) == 6
    aggregate_safe = True
    for path in table_files:
        with path.open(newline="", encoding="utf-8") as source:
            fields = set(csv.DictReader(source).fieldnames or [])
        aggregate_safe &= not bool(fields & FORBIDDEN_AGGREGATE_FIELDS)
    checks["aggregate_tables_exclude_row_identifiers"] = aggregate_safe
    checks["four_figure_files_present"] = len(list((ROOT / "study/report/figures").glob("figure_*.*"))) == 4

    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "checks": checks,
        "scope_note": "Integrity and reproducibility audit only; locked models were not refitted.",
    }


def main() -> int:
    result = audit()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
