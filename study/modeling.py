"""Implementation of the frozen modeling contract.

The public entry points deliberately separate validation tuning from the one-time
locked-test evaluation.  Nothing in :func:`tune_models` computes a test-period
outcome summary or prediction.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)


MISSING_CATEGORY = "__MISSING__"
PROBABILITY_EPSILON = 1e-6


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_spec(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_value(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.ndarray):
        return [_json_value(item) for item in value.tolist()]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_value(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def model_columns(spec: dict[str, Any], model_name: str) -> tuple[list[str], list[str]]:
    name = list(spec["name_features"])
    baseline_numeric = list(spec["prediction_baseline_numeric"])
    baseline_categorical = list(spec["prediction_baseline_categorical"])
    if model_name == "baseline":
        return baseline_numeric, baseline_categorical
    if model_name == "name_only":
        return ["combine_year", *name], []
    if model_name == "baseline_plus_name":
        return [*baseline_numeric, *name], baseline_categorical
    raise ValueError(f"unknown frozen model: {model_name}")


@dataclass
class FrozenPreprocessor:
    numeric: list[str]
    categorical: list[str]
    medians: dict[str, float] | None = None
    means: dict[str, float] | None = None
    scales: dict[str, float] | None = None
    missing_indicators: list[str] | None = None
    categories: dict[str, list[str]] | None = None
    feature_names: list[str] | None = None
    zero_variance: list[str] | None = None
    coercion_failures: dict[str, int] | None = None

    def fit(self, frame: pd.DataFrame) -> "FrozenPreprocessor":
        self.medians = {}
        self.means = {}
        self.scales = {}
        self.missing_indicators = []
        self.categories = {}
        self.zero_variance = []
        self.coercion_failures = {}
        names: list[str] = []

        for column in self.numeric:
            raw = frame[column]
            values = pd.to_numeric(raw, errors="coerce")
            self.coercion_failures[column] = int((raw.notna() & values.isna()).sum())
            if values.isna().any():
                self.missing_indicators.append(column)
            median = float(values.median()) if values.notna().any() else 0.0
            imputed = values.fillna(median).to_numpy(dtype=float)
            mean = float(np.mean(imputed))
            scale = float(np.std(imputed, ddof=0))
            self.medians[column] = median
            self.means[column] = mean
            if not np.isfinite(scale) or scale <= 0:
                self.zero_variance.append(column)
            else:
                self.scales[column] = scale
                names.append(column)
            if column in self.missing_indicators:
                indicator = f"{column}__missing"
                if values.isna().nunique() > 1:
                    names.append(indicator)
                else:
                    self.zero_variance.append(indicator)

        for column in self.categorical:
            values = frame[column].fillna(MISSING_CATEGORY).astype(str)
            levels = sorted(values.unique().tolist())
            self.categories[column] = levels
            names.extend(f"{column}={level}" for level in levels)

        self.feature_names = names
        return self

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        if self.feature_names is None:
            raise RuntimeError("preprocessor has not been fitted")
        columns: list[np.ndarray] = []
        for column in self.numeric:
            raw = pd.to_numeric(frame[column], errors="coerce")
            if column in self.scales:
                values = raw.fillna(self.medians[column]).to_numpy(dtype=float)
                columns.append((values - self.means[column]) / self.scales[column])
            indicator = f"{column}__missing"
            if indicator in self.feature_names:
                columns.append(raw.isna().to_numpy(dtype=float))
        for column in self.categorical:
            values = frame[column].fillna(MISSING_CATEGORY).astype(str).to_numpy()
            for level in self.categories[column]:
                columns.append((values == level).astype(float))
        return np.column_stack(columns) if columns else np.empty((len(frame), 0))

    def report(self) -> dict[str, Any]:
        return {
            "numeric_medians": self.medians,
            "numeric_means": self.means,
            "numeric_scales": self.scales,
            "missing_indicators": self.missing_indicators,
            "categorical_levels": self.categories,
            "zero_variance_dropped": self.zero_variance,
            "numeric_coercion_failures": self.coercion_failures,
            "output_feature_count": len(self.feature_names or []),
        }


def preflight(
    cohort_path: Path, spec_path: Path, audit_path: Path | None = None
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    spec = load_spec(spec_path)
    frame = pd.read_csv(cohort_path, low_memory=False)
    required = {spec["outcome"], "combine_year", "combine_key", "PLAYER_ID"}
    for name in spec["models"]:
        numeric, categorical = model_columns(spec, name)
        required.update(numeric)
        required.update(categorical)
    required.update(spec["association_adjustment_numeric"])
    required.update(spec["association_adjustment_categorical"])
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"cohort is missing frozen fields: {missing}")

    years = pd.to_numeric(frame["combine_year"], errors="coerce")
    outcome = pd.to_numeric(frame[spec["outcome"]], errors="coerce")
    if years.isna().any():
        raise ValueError("year must be fully numeric")
    # Before final unlock, validate outcomes only in the development period.
    # Merely loading the locked column is unavoidable, but no test-period
    # outcome validation, summary, fitting, or metric is performed here.
    development = years <= spec["splits"]["validation"][1]
    development_outcome = outcome[development]
    if development_outcome.isna().any() or set(development_outcome.unique()) - {0, 1}:
        raise ValueError("development-period outcome must be fully observed and binary")
    expected_years = set(range(spec["year_range"][0], spec["year_range"][1] + 1))
    if set(years.astype(int).unique()) != expected_years:
        raise ValueError("cohort does not contain every frozen analysis year")
    if frame["combine_key"].isna().any() or frame.duplicated(["combine_year", "combine_key"]).any():
        raise ValueError("player-Combine-year keys must be present and unique")

    audit_status = None
    if audit_path is not None:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit_status = bool(audit.get("cohort_analysis_ready"))
        if not audit_status:
            raise ValueError("cohort audit is not analysis-ready")

    split_counts = {}
    for split, bounds in spec["splits"].items():
        split_counts[split] = int(years.between(bounds[0], bounds[1]).sum())
        if not split_counts[split]:
            raise ValueError(f"empty frozen split: {split}")

    report = {
        "status": "passed",
        "cohort_sha256": file_sha256(cohort_path),
        "spec_sha256": file_sha256(spec_path),
        "rows": int(len(frame)),
        "years": [int(years.min()), int(years.max())],
        "split_row_counts": split_counts,
        "audit_analysis_ready": audit_status,
    }
    frame["combine_year"] = years.astype(int)
    frame[spec["outcome"]] = outcome
    return frame, spec, report


def validate_locked_outcomes(frame: pd.DataFrame, spec: dict[str, Any]) -> None:
    bounds = spec["splits"]["test"]
    values = pd.to_numeric(
        frame.loc[frame["combine_year"].between(*bounds), spec["outcome"]],
        errors="coerce",
    )
    if values.isna().any() or set(values.unique()) - {0, 1}:
        raise ValueError("locked-test outcome must be fully observed and binary")


def _fit_prediction_model(
    fit: pd.DataFrame,
    target: np.ndarray,
    numeric: list[str],
    categorical: list[str],
    c_value: float,
) -> tuple[FrozenPreprocessor, LogisticRegression]:
    processor = FrozenPreprocessor(numeric, categorical).fit(fit)
    matrix = processor.transform(fit)
    model = LogisticRegression(
        C=c_value,
        penalty="l2",
        solver="lbfgs",
        fit_intercept=True,
        max_iter=10_000,
        random_state=0,
    )
    model.fit(matrix, target)
    return processor, model


def tune_models(frame: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    train_bounds = spec["splits"]["train"]
    validation_bounds = spec["splits"]["validation"]
    train = frame[frame["combine_year"].between(*train_bounds)].copy()
    validation = frame[frame["combine_year"].between(*validation_bounds)].copy()
    outcome = spec["outcome"]
    results: dict[str, Any] = {}
    for model_name in spec["models"]:
        numeric, categorical = model_columns(spec, model_name)
        processor = FrozenPreprocessor(numeric, categorical).fit(train)
        x_train = processor.transform(train)
        x_validation = processor.transform(validation)
        candidates = []
        for c_value in spec["penalty_C_grid"]:
            model = LogisticRegression(
                C=float(c_value), penalty="l2", solver="lbfgs",
                fit_intercept=True, max_iter=10_000, random_state=0,
            )
            model.fit(x_train, train[outcome].to_numpy())
            probabilities = model.predict_proba(x_validation)[:, 1]
            candidates.append({
                "C": float(c_value),
                "validation_log_loss": float(log_loss(validation[outcome], probabilities)),
                "iterations": int(model.n_iter_[0]),
            })
        minimum = min(item["validation_log_loss"] for item in candidates)
        eligible = [
            item for item in candidates
            if item["validation_log_loss"] <= minimum + 1e-12
        ]
        selected = min(eligible, key=lambda item: item["C"])
        results[model_name] = {
            "selected_C": selected["C"],
            "selection_rule": "minimum_validation_log_loss_tie_smaller_C",
            "candidates": candidates,
            "preprocessing": processor.report(),
        }
    return results


def sensitivity_variants(
    frame: pd.DataFrame, spec: dict[str, Any]
) -> dict[str, tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]]:
    """Build all frozen sensitivity populations and feature substitutions."""
    variants: dict[str, tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]] = {}

    def add(
        name: str,
        data: pd.DataFrame,
        given: str = "given_generation_surprisal",
        surname: str = "surname_conservative_surprisal_bits",
        observed: str = "given_generation_ssa_ever_observed",
        detail: dict[str, Any] | None = None,
    ) -> None:
        variant = deepcopy(spec)
        replacements = {
            "given_generation_surprisal": given,
            "surname_conservative_surprisal_bits": surname,
            "given_generation_ssa_ever_observed": observed,
        }
        variant["name_features"] = [replacements.get(value, value) for value in spec["name_features"]]
        variant["association"]["co_primary_exposures"] = [given, surname]
        variants[name] = (data.copy(), variant, detail or {})

    verified_confidence = frame["birth_year_confidence"].astype("string").str.lower().isin({"high", "verified"})
    exact = frame[frame["birth_year"].notna() & verified_confidence].copy()
    add(
        "exact_birth_year_given_surprisal_verified_subset", exact,
        given="given_exact_birth_surprisal",
        observed="given_exact_birth_ssa_ever_observed",
        detail={"population": "verified_birth_year"},
    )
    add(
        "ssa_suppression_zero", frame,
        given="given_generation_sensitivity_surprisal_zero",
        detail={"undefined_scores": "median_imputed_with_observed_indicator_retained"},
    )
    add(
        "ssa_suppression_midpoint_2_5", frame,
        given="given_generation_sensitivity_surprisal_midpoint",
    )
    add(
        "surname_unpublished_count_1", frame,
        surname="surname_sensitivity_surprisal_one",
    )
    add(
        "surname_unpublished_count_50", frame,
        surname="surname_sensitivity_surprisal_midpoint",
    )
    add("exclude_initial_forms", frame[~frame["initials"].astype(bool)])

    identity = frame["PLAYER_ID"].astype("string")
    identity = identity.where(identity.notna() & identity.str.strip().ne(""), frame["combine_key"].astype(str))
    last_indices = (
        frame.assign(_identity=identity)
        .sort_values(["combine_year", "combine_key"])
        .groupby("_identity", sort=False)
        .tail(1)
        .index
    )
    add("final_combine_appearance_only", frame.loc[last_indices].sort_index())
    add("exclude_2020", frame[frame["combine_year"] != 2020])
    return variants


def tune_sensitivity_models(frame: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    results = {}
    for name, (data, variant, detail) in sensitivity_variants(frame, spec).items():
        results[name] = {
            "detail": detail,
            "split_row_counts": {
                split: int(data["combine_year"].between(*bounds).sum())
                for split, bounds in spec["splits"].items()
            },
            "models": tune_models(data, variant),
        }
    return results


def prediction_metrics(y: np.ndarray, probability: np.ndarray) -> dict[str, float | None]:
    probability = np.asarray(probability, dtype=float)
    y = np.asarray(y, dtype=int)
    clipped = np.clip(probability, PROBABILITY_EPSILON, 1 - PROBABILITY_EPSILON)
    result: dict[str, float | None] = {
        "log_loss": float(log_loss(y, probability)),
        "brier_score": float(brier_score_loss(y, probability)),
        "roc_auc": None,
        "average_precision": None,
        "calibration_intercept": None,
        "calibration_slope": None,
    }
    if len(np.unique(y)) == 2:
        result["roc_auc"] = float(roc_auc_score(y, probability))
        result["average_precision"] = float(average_precision_score(y, probability))
        logit_probability = np.log(clipped / (1 - clipped))
        design = np.column_stack([np.ones(len(y)), logit_probability])

        def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
            fitted = expit(design @ beta)
            loss = -np.sum(y * np.log(np.clip(fitted, 1e-15, 1)) + (1-y) * np.log(np.clip(1-fitted, 1e-15, 1)))
            gradient = design.T @ (fitted - y)
            return float(loss), gradient

        calibrated = minimize(
            lambda b: objective(b)[0], np.array([0.0, 1.0]),
            jac=lambda b: objective(b)[1], method="BFGS",
        )
        if calibrated.success or np.isfinite(calibrated.fun):
            result["calibration_intercept"] = float(calibrated.x[0])
            result["calibration_slope"] = float(calibrated.x[1])
    return result


def _test_cluster(frame: pd.DataFrame) -> pd.Series:
    ids = frame["PLAYER_ID"].astype("string")
    valid = ids.notna() & (ids.str.strip() != "")
    clusters = "row:" + frame.index.astype(str)
    clusters = pd.Series(clusters, index=frame.index, dtype="string")
    clusters.loc[valid] = "nba:" + ids.loc[valid].str.strip()
    return clusters


def paired_bootstrap(
    test: pd.DataFrame,
    predictions: dict[str, np.ndarray],
    spec: dict[str, Any],
) -> dict[str, Any]:
    rng = np.random.default_rng(spec["bootstrap"]["seed"])
    replicates = int(spec["bootstrap"]["replicates"])
    outcome = test[spec["outcome"]].to_numpy(dtype=int)
    clusters = _test_cluster(test)
    groups_by_year: list[list[np.ndarray]] = []
    for year in sorted(test["combine_year"].unique()):
        positions = np.flatnonzero(test["combine_year"].to_numpy() == year)
        labels = clusters.iloc[positions].to_numpy()
        groups_by_year.append([positions[labels == label] for label in pd.unique(labels)])

    metric_names = list(prediction_metrics(outcome, predictions["baseline"]).keys())
    differences: dict[str, list[float]] = {name: [] for name in metric_names}
    for _ in range(replicates):
        sampled_parts = []
        for groups in groups_by_year:
            chosen = rng.integers(0, len(groups), size=len(groups))
            sampled_parts.extend(groups[index] for index in chosen)
        sample = np.concatenate(sampled_parts)
        left = prediction_metrics(outcome[sample], predictions["baseline_plus_name"][sample])
        right = prediction_metrics(outcome[sample], predictions["baseline"][sample])
        for metric in metric_names:
            if left[metric] is not None and right[metric] is not None:
                difference = float(left[metric] - right[metric])
                if np.isfinite(difference):
                    differences[metric].append(difference)
    return {
        metric: {
            "lower_95": float(np.percentile(values, 2.5)) if values else None,
            "upper_95": float(np.percentile(values, 97.5)) if values else None,
            "retained_replicates": len(values),
        }
        for metric, values in differences.items()
    }


def evaluate_locked_test(
    frame: pd.DataFrame,
    spec: dict[str, Any],
    tuning: dict[str, Any],
    include_bootstrap: bool = True,
) -> dict[str, Any]:
    validation_end = spec["splits"]["validation"][1]
    test_bounds = spec["splits"]["test"]
    fit = frame[frame["combine_year"] <= validation_end].copy()
    test = frame[frame["combine_year"].between(*test_bounds)].copy()
    outcome = spec["outcome"]
    predictions: dict[str, np.ndarray] = {}
    models: dict[str, Any] = {}
    for model_name in spec["models"]:
        numeric, categorical = model_columns(spec, model_name)
        processor, model = _fit_prediction_model(
            fit, fit[outcome].to_numpy(), numeric, categorical,
            float(tuning[model_name]["selected_C"]),
        )
        predictions[model_name] = model.predict_proba(processor.transform(test))[:, 1]
        models[model_name] = {
            "selected_C": float(tuning[model_name]["selected_C"]),
            "metrics": prediction_metrics(test[outcome].to_numpy(), predictions[model_name]),
            "preprocessing": processor.report(),
            "iterations": int(model.n_iter_[0]),
        }
    differences = {
        metric: (
            models["baseline_plus_name"]["metrics"][metric]
            - models["baseline"]["metrics"][metric]
            if models["baseline_plus_name"]["metrics"][metric] is not None
            and models["baseline"]["metrics"][metric] is not None else None
        )
        for metric in models["baseline"]["metrics"]
    }
    result = {
        "test_years": test_bounds,
        "test_rows": int(len(test)),
        "models": models,
        "baseline_plus_name_minus_baseline": differences,
    }
    if include_bootstrap:
        result["paired_bootstrap_95"] = paired_bootstrap(test, predictions, spec)
    return result


def sensitivity_analysis(
    frame: pd.DataFrame,
    spec: dict[str, Any],
    tuning: dict[str, Any],
) -> dict[str, Any]:
    results = {}
    for name, (data, variant, detail) in sensitivity_variants(frame, spec).items():
        outcome = spec["outcome"]
        coverage = None
        if name == "exact_birth_year_given_surprisal_verified_subset":
            coverage = {
                "overall": {"eligible": int(len(data)), "cohort": int(len(frame)), "fraction": float(len(data) / len(frame))},
                "by_draft_status": {
                    str(status): {
                        "eligible": int((data[outcome] == status).sum()),
                        "cohort": int((frame[outcome] == status).sum()),
                        "fraction": float((data[outcome] == status).sum() / (frame[outcome] == status).sum()),
                    }
                    for status in (0, 1)
                },
            }
        results[name] = {
            "detail": detail,
            "rows": int(len(data)),
            "coverage": coverage,
            "prediction": evaluate_locked_test(
                data, variant, tuning[name]["models"], include_bootstrap=False
            ),
            "association": association_analysis(data, variant),
        }
    return results


def _holm_two(p_values: dict[str, float], alpha: float) -> dict[str, Any]:
    ordered = sorted(p_values, key=p_values.get)
    adjusted: dict[str, float] = {}
    running = 0.0
    count = len(ordered)
    for rank, name in enumerate(ordered):
        running = max(running, (count - rank) * p_values[name])
        adjusted[name] = min(1.0, running)
    return {
        name: {"adjusted_p": adjusted[name], "reject": adjusted[name] <= alpha}
        for name in p_values
    }


def descriptive_analysis(frame: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    """Create the prespecified descriptive summaries without row-level output."""
    outcome = spec["outcome"]
    coverage_fields = list(dict.fromkeys([
        *spec["prediction_baseline_numeric"], *spec["name_features"],
        *spec["prediction_baseline_categorical"],
    ]))
    by_year = []
    for year, rows in frame.groupby("combine_year", sort=True):
        by_year.append({
            "combine_year": int(year),
            "cohort_size": int(len(rows)),
            "drafted": int(rows[outcome].sum()),
            "draft_rate": float(rows[outcome].mean()),
            "predictor_nonmissing": {
                column: int(rows[column].notna().sum()) for column in coverage_fields
            },
        })

    measurement_missingness = {
        column: {
            "missing": int(frame[column].isna().sum()),
            "missing_fraction": float(frame[column].isna().mean()),
        }
        for column in coverage_fields
    }
    distributions: dict[str, Any] = {}
    for exposure in spec["association"]["co_primary_exposures"]:
        values = pd.to_numeric(frame[exposure], errors="coerce")
        valid = values.notna()
        # Fixed cohort-wide quintiles are computed once, then applied to both
        # outcome groups. Duplicate edges are retained in the report and
        # removed only for categorical assignment, as pandas requires.
        edges = values[valid].quantile([0, .2, .4, .6, .8, 1]).to_numpy(dtype=float)
        unique_edges = np.unique(edges)
        quintile_counts = None
        if len(unique_edges) >= 2:
            assignments = pd.cut(values, bins=unique_edges, include_lowest=True, labels=False)
            quintile_counts = {
                str(status): {
                    str(int(quintile) + 1): int(count)
                    for quintile, count in assignments[frame[outcome] == status].value_counts(sort=False).items()
                }
                for status in (0, 1)
            }
        by_status = {}
        for status in (0, 1):
            group = values[(frame[outcome] == status) & valid]
            by_status[str(status)] = {
                "count": int(group.size),
                "median": float(group.median()) if len(group) else None,
                "q1": float(group.quantile(.25)) if len(group) else None,
                "q3": float(group.quantile(.75)) if len(group) else None,
            }
        distributions[exposure] = {
            "cohort_quintile_edges": edges,
            "quintile_counts_by_draft_status": quintile_counts,
            "summary_by_draft_status": by_status,
        }
    return {
        "year_level": by_year,
        "measurement_missingness": measurement_missingness,
        "name_surprisal_distributions": distributions,
    }


def _drop_aliased_columns(
    x: np.ndarray, names: list[str], protected: Iterable[str]
) -> tuple[np.ndarray, list[str], list[str]]:
    """Drop exact linear aliases while retaining named estimands by priority."""
    protected = set(protected)
    priority = sorted(
        range(len(names)),
        key=lambda index: (
            0 if names[index] == "intercept" else
            1 if names[index] in protected else
            3 if names[index].endswith("__missing") else 2,
            index,
        ),
    )
    accepted: list[int] = []
    basis: list[np.ndarray] = []
    tolerance = max(x.shape) * np.finfo(float).eps * max(1.0, np.linalg.norm(x, ord=2))
    for index in priority:
        residual = x[:, index].astype(float, copy=True)
        # Two passes make modified Gram-Schmidt stable for nearly collinear
        # anthropometric columns without repeatedly computing a full SVD.
        for _ in range(2):
            for vector in basis:
                residual -= vector * np.dot(vector, residual)
        norm = float(np.linalg.norm(residual))
        if norm > tolerance:
            accepted.append(index)
            basis.append(residual / norm)
    accepted.sort()
    dropped = [name for index, name in enumerate(names) if index not in accepted]
    return x[:, accepted], [names[index] for index in accepted], dropped


def association_analysis(frame: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    numeric = [*spec["association_adjustment_numeric"], *spec["name_features"]]
    categorical = list(spec["association_adjustment_categorical"])
    processor = FrozenPreprocessor(numeric, categorical).fit(frame)
    matrix = processor.transform(frame)
    names = list(processor.feature_names)

    # Drop one level from every categorical block; prediction keeps the complete
    # one-hot encoding because its L2 penalty identifies those coefficients.
    drop = set()
    for column in categorical:
        levels = processor.categories[column]
        if levels:
            drop.add(f"{column}={levels[0]}")
    keep = [index for index, name in enumerate(names) if name not in drop]
    x = np.column_stack([np.ones(len(frame)), matrix[:, keep]])
    names = ["intercept", *(names[index] for index in keep)]
    x, names, aliased = _drop_aliased_columns(
        x, names, spec["association"]["co_primary_exposures"]
    )
    y = frame[spec["outcome"]].to_numpy(dtype=float)

    estimator = LogisticRegression(
        penalty=None, solver="newton-cholesky", fit_intercept=False,
        max_iter=1_000, tol=1e-8, random_state=0,
    )
    estimator.fit(x, y.astype(int))
    coefficients = estimator.coef_[0]
    probabilities = expit(x @ coefficients)
    weights = probabilities * (1 - probabilities)
    information = x.T @ (weights[:, None] * x)
    rank = int(np.linalg.matrix_rank(information))
    separation = bool(np.any(np.abs(coefficients) > 25) or np.min(weights) < 1e-12)
    if rank < x.shape[1] or separation:
        return _firth_association(x, y, names, processor, spec, reason=(
            "rank_deficiency" if rank < x.shape[1] else "separation"
        ))

    bread = np.linalg.pinv(information)
    row_scores = x * (y - probabilities)[:, None]
    clusters = _test_cluster(frame)
    summed = pd.DataFrame(row_scores).groupby(clusters.to_numpy(), sort=False).sum().to_numpy()
    meat = summed.T @ summed
    cluster_count = len(summed)
    correction = (cluster_count / (cluster_count - 1)) * ((len(y) - 1) / (len(y) - x.shape[1]))
    covariance = correction * bread @ meat @ bread
    standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0))
    primary = {}
    raw_p = {}
    for exposure in spec["association"]["co_primary_exposures"]:
        index = names.index(exposure)
        standardized_coefficient = float(coefficients[index])
        standardized_se = float(standard_errors[index])
        scale = float(processor.scales[exposure])
        coefficient = standardized_coefficient / scale
        se = standardized_se / scale
        p_value = float(2 * norm.sf(abs(standardized_coefficient / standardized_se)))
        raw_p[exposure] = p_value
        primary[exposure] = {
            "coefficient_per_bit": coefficient,
            "standard_error": se,
            "standardization_scale_bits": scale,
            "coefficient_per_standard_deviation": standardized_coefficient,
            "odds_ratio": math.exp(coefficient),
            "confidence_interval_95": [math.exp(coefficient - 1.96 * se), math.exp(coefficient + 1.96 * se)],
            "unadjusted_p": p_value,
        }
    holm = _holm_two(raw_p, float(spec["association"]["alpha"]))
    for exposure in primary:
        primary[exposure].update(holm[exposure])
    return {
        "estimator": "unpenalized_logistic",
        "converged": bool(estimator.n_iter_[0] < estimator.max_iter),
        "iterations": int(estimator.n_iter_[0]),
        "rows": int(len(frame)),
        "clusters": cluster_count,
        "design_rank": rank,
        "design_columns": x.shape[1],
        "cluster_covariance_finite_sample_correction": correction,
        "co_primary": primary,
        "preprocessing": processor.report(),
        "dropped_reference_levels": sorted(drop),
        "dropped_aliased_columns": aliased,
    }


def _firth_association(
    x: np.ndarray,
    y: np.ndarray,
    names: list[str],
    processor: FrozenPreprocessor,
    spec: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    """Firth fallback using Jeffreys-penalized likelihood.

    Profile-likelihood intervals are computed for the two prespecified exposure
    coefficients by constraining each coefficient and optimizing all others.
    """
    def penalized_log_likelihood(beta: np.ndarray) -> float:
        linear = x @ beta
        probability = expit(linear)
        log_likelihood = np.sum(y * -np.logaddexp(0, -linear) + (1-y) * -np.logaddexp(0, linear))
        information = x.T @ ((probability * (1-probability))[:, None] * x)
        sign, logdet = np.linalg.slogdet(information)
        return float(log_likelihood + 0.5 * logdet) if sign > 0 else -np.inf

    fitted = minimize(lambda b: -penalized_log_likelihood(b), np.zeros(x.shape[1]), method="BFGS")
    optimum = penalized_log_likelihood(fitted.x)
    cutoff = optimum - 0.5 * 3.841458820694124

    def profile(index: int, value: float, start: np.ndarray) -> tuple[float, np.ndarray]:
        free = [j for j in range(x.shape[1]) if j != index]
        result = minimize(
            lambda b: -penalized_log_likelihood(np.insert(b, index, value)),
            np.delete(start, index), method="BFGS",
        )
        beta = np.insert(result.x, index, value)
        return penalized_log_likelihood(beta), beta

    def endpoint(index: int, direction: int) -> float:
        center = float(fitted.x[index])
        inside = center
        outside = center + direction
        value, start = profile(index, outside, fitted.x)
        while value > cutoff and abs(outside-center) < 100:
            inside, outside = outside, center + 2 * (outside-center)
            value, start = profile(index, outside, start)
        for _ in range(45):
            middle = (inside + outside) / 2
            value, start = profile(index, middle, start)
            if value > cutoff:
                inside = middle
            else:
                outside = middle
        return float((inside + outside) / 2)

    primary = {}
    raw_p = {}
    for exposure in spec["association"]["co_primary_exposures"]:
        index = names.index(exposure)
        standardized_coefficient = float(fitted.x[index])
        standardized_lower, standardized_upper = endpoint(index, -1), endpoint(index, 1)
        scale = float(processor.scales[exposure])
        coefficient = standardized_coefficient / scale
        lower, upper = standardized_lower / scale, standardized_upper / scale
        null_value, _ = profile(index, 0.0, fitted.x)
        statistic = max(0.0, 2 * (optimum - null_value))
        p_value = float(2 * norm.sf(math.sqrt(statistic)))
        raw_p[exposure] = p_value
        primary[exposure] = {
            "coefficient_per_bit": coefficient,
            "standardization_scale_bits": scale,
            "coefficient_per_standard_deviation": standardized_coefficient,
            "odds_ratio": math.exp(coefficient),
            "confidence_interval_95": [math.exp(lower), math.exp(upper)],
            "unadjusted_p": p_value,
        }
    holm = _holm_two(raw_p, float(spec["association"]["alpha"]))
    for exposure in primary:
        primary[exposure].update(holm[exposure])
    return {
        "estimator": "firth_logistic_profile_likelihood",
        "fallback_reason": reason,
        "converged": bool(fitted.success or np.isfinite(optimum)),
        "rows": int(len(y)),
        "design_columns": int(x.shape[1]),
        "co_primary": primary,
        "preprocessing": processor.report(),
    }
