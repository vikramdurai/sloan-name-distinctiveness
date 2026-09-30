#!/usr/bin/env python3
"""Run validation tuning or explicitly unlock the frozen final analysis."""

from __future__ import annotations

import argparse
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy
import pandas
import scipy
import sklearn

from study.modeling import (
    association_analysis,
    descriptive_analysis,
    evaluate_locked_test,
    file_sha256,
    preflight,
    sensitivity_analysis,
    tune_sensitivity_models,
    tune_models,
    validate_locked_outcomes,
    write_json,
)


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_FILES = [ROOT / "study/modeling.py", Path(__file__).resolve()]


def implementation_hashes() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): file_sha256(path)
        for path in IMPLEMENTATION_FILES
    }


def software_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "scipy": scipy.__version__,
        "scikit_learn": sklearn.__version__,
    }


def create_final_marker(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as destination:
        json.dump(payload, destination, indent=2, sort_keys=True)
        destination.write("\n")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--cohort", type=Path, default=ROOT / "study/output/combine_cohort.csv")
    result.add_argument("--audit", type=Path, default=ROOT / "study/output/cohort_audit.json")
    result.add_argument("--spec", type=Path, default=ROOT / "study/modeling_spec.json")
    result.add_argument("--output", type=Path, default=ROOT / "study/model_output")
    result.add_argument(
        "--run-final", action="store_true",
        help="consume the locked 2022-2025 test set and fit the full-cohort association model",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    frame, spec, check = preflight(args.cohort, args.spec, args.audit)
    write_json(args.output / "preflight.json", check)
    tuning_path = args.output / "validation_tuning.json"
    final_path = args.output / "final_results.json"
    started_path = args.output / "final_run_started.json"

    if not args.run_final:
        if started_path.exists() or final_path.exists():
            raise SystemExit("final analysis has started; refusing to replace validation tuning")
        tuning = tune_models(frame, spec)
        sensitivity_tuning = tune_sensitivity_models(frame, spec)
        artifact = {
            "status": "validation_complete_test_locked",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "cohort_sha256": check["cohort_sha256"],
            "spec_sha256": check["spec_sha256"],
            "implementation_sha256": implementation_hashes(),
            "software_versions": software_versions(),
            "splits_used": ["train", "validation"],
            "models": tuning,
            "sensitivity_models": sensitivity_tuning,
        }
        write_json(tuning_path, artifact)
        print(json.dumps({
            "status": artifact["status"],
            "selected_C": {name: value["selected_C"] for name, value in tuning.items()},
            "next": "review validation_tuning.json, then rerun with --run-final exactly once",
        }, indent=2))
        return 0

    if final_path.exists():
        raise SystemExit("locked final result already exists; refusing to overwrite it")
    if started_path.exists():
        raise SystemExit("locked final run has already started; manual recovery review is required")
    if not tuning_path.exists():
        raise SystemExit("validation tuning artifact is required before --run-final")
    artifact = json.loads(tuning_path.read_text(encoding="utf-8"))
    if artifact.get("status") != "validation_complete_test_locked":
        raise SystemExit("validation tuning artifact is not in the locked-ready state")
    if artifact.get("cohort_sha256") != file_sha256(args.cohort):
        raise SystemExit("cohort changed after validation tuning")
    if artifact.get("spec_sha256") != file_sha256(args.spec):
        raise SystemExit("frozen spec changed after validation tuning")
    if artifact.get("implementation_sha256") != implementation_hashes():
        raise SystemExit("modeling implementation changed after validation tuning")
    if artifact.get("software_versions") != software_versions():
        raise SystemExit("modeling software versions changed after validation tuning")
    if set(artifact.get("sensitivity_models", {})) != set(spec["sensitivity_analyses"]):
        raise SystemExit("validation tuning is missing frozen sensitivity analyses")

    started = {
        "status": "final_locked_test_started",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "cohort_sha256": artifact["cohort_sha256"],
        "spec_sha256": artifact["spec_sha256"],
        "implementation_sha256": artifact["implementation_sha256"],
        "software_versions": artifact["software_versions"],
    }
    # Exclusive creation is the crash-safe boundary. Any later failure requires
    # documented manual recovery instead of a silent second look at test data.
    create_final_marker(started_path, started)

    validate_locked_outcomes(frame, spec)

    result = {
        "status": "final_locked_test_consumed",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "cohort_sha256": artifact["cohort_sha256"],
        "spec_sha256": artifact["spec_sha256"],
        "descriptive": descriptive_analysis(frame, spec),
        "prediction": evaluate_locked_test(frame, spec, artifact["models"]),
        "association": association_analysis(frame, spec),
        "sensitivity_analyses": sensitivity_analysis(
            frame, spec, artifact["sensitivity_models"]
        ),
    }
    write_json(final_path, result)
    print(json.dumps({
        "status": result["status"],
        "result": str(final_path),
        "primary_log_loss_difference": result["prediction"]["baseline_plus_name_minus_baseline"]["log_loss"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
