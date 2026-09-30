#!/usr/bin/env python3
"""Generate release-safe aggregate tables and figures from locked results."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/research-paper-matplotlib")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty table: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fmt(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def interval(values: list[float]) -> str:
    return f"[{values[0]:.3f}, {values[1]:.3f}]"


def build_tables(result: dict[str, Any], output: Path) -> dict[str, list[dict[str, Any]]]:
    cohort = []
    for row in result["descriptive"]["year_level"]:
        cohort.append({
            "combine_year": row["combine_year"],
            "cohort_size": row["cohort_size"],
            "drafted": row["drafted"],
            "undrafted": row["cohort_size"] - row["drafted"],
            "draft_rate": row["draft_rate"],
        })

    missingness = []
    total = result["association"]["rows"]
    for predictor, values in sorted(result["descriptive"]["measurement_missingness"].items()):
        missingness.append({
            "predictor": predictor,
            "observed": total - values["missing"],
            "missing": values["missing"],
            "missing_fraction": values["missing_fraction"],
        })

    prediction = []
    model_labels = {
        "baseline": "Conventional baseline",
        "name_only": "Name only",
        "baseline_plus_name": "Baseline plus names",
    }
    for name in ("baseline", "name_only", "baseline_plus_name"):
        model = result["prediction"]["models"][name]
        prediction.append({
            "model": name,
            "label": model_labels[name],
            "selected_C": model["selected_C"],
            **model["metrics"],
        })
    differences = result["prediction"]["baseline_plus_name_minus_baseline"]
    bootstrap = result["prediction"]["paired_bootstrap_95"]
    prediction_differences = [
        {
            "metric": metric,
            "difference_baseline_plus_name_minus_baseline": difference,
            "lower_95": bootstrap[metric]["lower_95"],
            "upper_95": bootstrap[metric]["upper_95"],
            "retained_replicates": bootstrap[metric]["retained_replicates"],
        }
        for metric, difference in differences.items()
    ]

    association = []
    for exposure, estimate in result["association"]["co_primary"].items():
        association.append({
            "exposure": exposure,
            "coefficient_per_bit": estimate["coefficient_per_bit"],
            "odds_ratio_per_bit": estimate["odds_ratio"],
            "ci_95_lower": estimate["confidence_interval_95"][0],
            "ci_95_upper": estimate["confidence_interval_95"][1],
            "unadjusted_p": estimate["unadjusted_p"],
            "holm_adjusted_p": estimate["adjusted_p"],
            "holm_reject_0_05": estimate["reject"],
        })

    sensitivities = []
    for name, sensitivity in result["sensitivity_analyses"].items():
        estimates = sensitivity["association"]["co_primary"]
        given_name = next(key for key in estimates if "given" in key)
        surname_name = next(key for key in estimates if "surname" in key)
        given = estimates[given_name]
        surname = estimates[surname_name]
        sensitivity_prediction = sensitivity["prediction"]
        sensitivities.append({
            "sensitivity": name,
            "rows": sensitivity["rows"],
            "test_rows": sensitivity_prediction["test_rows"],
            "log_loss_difference": sensitivity_prediction["baseline_plus_name_minus_baseline"]["log_loss"],
            "given_exposure": given_name,
            "given_odds_ratio": given["odds_ratio"],
            "given_ci_95_lower": given["confidence_interval_95"][0],
            "given_ci_95_upper": given["confidence_interval_95"][1],
            "given_holm_adjusted_p": given["adjusted_p"],
            "surname_exposure": surname_name,
            "surname_odds_ratio": surname["odds_ratio"],
            "surname_ci_95_lower": surname["confidence_interval_95"][0],
            "surname_ci_95_upper": surname["confidence_interval_95"][1],
            "surname_holm_adjusted_p": surname["adjusted_p"],
        })

    tables = {
        "table_1_cohort_by_year.csv": cohort,
        "table_2_predictor_missingness.csv": missingness,
        "table_3_prediction_models.csv": prediction,
        "table_4_prediction_differences.csv": prediction_differences,
        "table_5_association.csv": association,
        "table_6_sensitivity_analyses.csv": sensitivities,
    }
    for filename, rows in tables.items():
        write_csv(output / "tables" / filename, rows)
    return tables


def association_figure(result: dict[str, Any], output: Path) -> None:
    estimates = result["association"]["co_primary"]
    keys = ["given_generation_surprisal", "surname_conservative_surprisal_bits"]
    labels = ["Given-name surprisal", "Surname surprisal"]
    odds = np.array([estimates[key]["odds_ratio"] for key in keys])
    lower = np.array([estimates[key]["confidence_interval_95"][0] for key in keys])
    upper = np.array([estimates[key]["confidence_interval_95"][1] for key in keys])
    y = np.arange(len(keys))[::-1]
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    ax.errorbar(
        odds, y, xerr=np.vstack([odds-lower, upper-odds]), fmt="o",
        color="#174A7E", ecolor="#174A7E", capsize=4, markersize=7,
    )
    ax.axvline(1, color="#666666", linestyle="--", linewidth=1)
    ax.set_yticks(y, labels)
    ax.set_xlabel("Adjusted odds ratio per one-bit increase (95% CI)")
    ax.set_title("Name surprisal and same-year NBA draft selection")
    ax.grid(axis="x", color="#DDDDDD", linewidth=.7)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    fig.tight_layout()
    for extension in ("png", "svg"):
        fig.savefig(output / "figures" / f"figure_1_association_forest.{extension}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def coverage_figure(result: dict[str, Any], output: Path) -> None:
    coverage = result["sensitivity_analyses"][
        "exact_birth_year_given_surprisal_verified_subset"
    ]["coverage"]
    labels = ["Undrafted", "Drafted", "Overall"]
    values = [
        coverage["by_draft_status"]["0"]["fraction"],
        coverage["by_draft_status"]["1"]["fraction"],
        coverage["overall"]["fraction"],
    ]
    colors = ["#B85C38", "#174A7E", "#6B7280"]
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    bars = ax.bar(labels, values, color=colors, width=.62)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Fraction with verified birth year")
    ax.set_title("Exact-birth-year coverage differs by draft outcome")
    ax.set_yticks(np.linspace(0, 1, 6), [f"{value:.0%}" for value in np.linspace(0, 1, 6)])
    ax.grid(axis="y", color="#DDDDDD", linewidth=.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x()+bar.get_width()/2, value+.025, f"{value:.1%}", ha="center", va="bottom")
    fig.tight_layout()
    for extension in ("png", "svg"):
        fig.savefig(output / "figures" / f"figure_2_birth_year_coverage.{extension}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def markdown_summary(result: dict[str, Any], output: Path) -> None:
    difference = result["prediction"]["baseline_plus_name_minus_baseline"]
    bootstrap = result["prediction"]["paired_bootstrap_95"]
    association = result["association"]["co_primary"]
    lines = [
        "# Locked Aggregate Results", "",
        "All values below are generated from the immutable locked result. Negative log-loss and Brier-score differences favor adding name features.", "",
        "## Primary prediction", "",
        "| Metric | Difference | Bootstrap 95% CI |", "|---|---:|---:|",
    ]
    for metric in ("log_loss", "brier_score", "roc_auc", "average_precision"):
        bounds = [bootstrap[metric]["lower_95"], bootstrap[metric]["upper_95"]]
        lines.append(f"| {metric.replace('_', ' ').title()} | {difference[metric]:.4f} | {interval(bounds)} |")
    lines.extend(["", "## Adjusted associations", "", "| Exposure | OR per bit | 95% CI | Unadjusted p | Holm-adjusted p |", "|---|---:|---:|---:|---:|"])
    for exposure in ("given_generation_surprisal", "surname_conservative_surprisal_bits"):
        value = association[exposure]
        lines.append(
            f"| {exposure} | {value['odds_ratio']:.3f} | {interval(value['confidence_interval_95'])} | "
            f"{value['unadjusted_p']:.3f} | {value['adjusted_p']:.3f} |"
        )
    lines.extend(["", "See the CSV files for full-precision values and all sensitivity analyses.", ""])
    (output / "TABLES.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=ROOT / "study/model_output/final_results.json")
    parser.add_argument("--output", type=Path, default=ROOT / "study/report")
    args = parser.parse_args()
    result = json.loads(args.results.read_text(encoding="utf-8"))
    if result.get("status") != "final_locked_test_consumed":
        raise SystemExit("final locked result is required")
    (args.output / "figures").mkdir(parents=True, exist_ok=True)
    build_tables(result, args.output)
    association_figure(result, args.output)
    coverage_figure(result, args.output)
    markdown_summary(result, args.output)
    print(f"Wrote aggregate report package to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
