from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from study.modeling import (
    FrozenPreprocessor,
    _drop_aliased_columns,
    association_analysis,
    model_columns,
    prediction_metrics,
    preflight,
    sensitivity_variants,
    tune_models,
)
from study.run_models import create_final_marker


ROOT = Path(__file__).resolve().parents[1]


class PreprocessorTests(unittest.TestCase):
    def test_fit_values_come_only_from_fitting_rows(self):
        train = pd.DataFrame({"x": [1.0, None, 3.0], "cat": ["A", "A", None]})
        future = pd.DataFrame({"x": [1000.0], "cat": ["NEW"]})
        processor = FrozenPreprocessor(["x"], ["cat"]).fit(train)
        transformed = processor.transform(future)
        self.assertEqual(processor.medians["x"], 2.0)
        self.assertNotIn("NEW", processor.categories["cat"])
        category_columns = len(processor.categories["cat"])
        self.assertTrue(np.all(transformed[0, -category_columns:] == 0))

    def test_missing_indicator_and_zero_variance_are_reported(self):
        frame = pd.DataFrame({"x": [1.0, None, 1.0], "constant": [4, 4, 4]})
        processor = FrozenPreprocessor(["x", "constant"], []).fit(frame)
        self.assertIn("x__missing", processor.feature_names)
        self.assertIn("constant", processor.zero_variance)

    def test_alias_removal_preserves_explicit_frozen_predictor(self):
        matrix = np.array([
            [1, 0, 0],
            [1, 1, 1],
            [1, 0, 0],
        ], dtype=float)
        reduced, names, dropped = _drop_aliased_columns(
            matrix, ["intercept", "initials", "score__missing"], ["initials"]
        )
        self.assertEqual(names, ["intercept", "initials"])
        self.assertEqual(dropped, ["score__missing"])
        self.assertEqual(np.linalg.matrix_rank(reduced), 2)

    def test_final_marker_is_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "started.json"
            create_final_marker(path, {"status": "started"})
            with self.assertRaises(FileExistsError):
                create_final_marker(path, {"status": "started-again"})


class FrozenModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((ROOT / "study/modeling_spec.json").read_text())

    def test_model_column_sets_match_contract(self):
        baseline, categories = model_columns(self.spec, "baseline")
        expanded, expanded_categories = model_columns(self.spec, "baseline_plus_name")
        name_only, name_categories = model_columns(self.spec, "name_only")
        self.assertEqual(categories, ["POSITION"])
        self.assertEqual(expanded_categories, ["POSITION"])
        self.assertEqual(name_categories, [])
        self.assertEqual(set(expanded) - set(baseline), set(self.spec["name_features"]))
        self.assertEqual(name_only[0], "combine_year")

    def test_metrics_use_requested_definitions(self):
        result = prediction_metrics(np.array([0, 0, 1, 1]), np.array([0.1, 0.3, 0.7, 0.9]))
        self.assertGreater(result["roc_auc"], 0.99)
        self.assertIsNotNone(result["average_precision"])
        self.assertIsNotNone(result["calibration_intercept"])
        self.assertIsNotNone(result["calibration_slope"])

    def test_preflight_checks_real_frozen_cohort_when_present(self):
        cohort = ROOT / "study/output/combine_cohort.csv"
        audit = ROOT / "study/output/cohort_audit.json"
        if not cohort.exists() or not audit.exists():
            self.skipTest("derived cohort is not present")
        frame, _, report = preflight(cohort, ROOT / "study/modeling_spec.json", audit)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(len(frame), 1795)
        self.assertEqual(report["split_row_counts"], {
            "train": 1204, "validation": 265, "test": 326,
        })

    def test_tuning_does_not_require_test_rows(self):
        # A compact contract variant verifies that tuning addresses only the
        # designated training and validation years.
        spec = {
            "outcome": "drafted",
            "splits": {"train": [2000, 2001], "validation": [2002, 2002], "test": [2003, 2003]},
            "name_features": ["name"],
            "prediction_baseline_numeric": ["combine_year", "measurement"],
            "prediction_baseline_categorical": ["POSITION"],
            "models": {"baseline": "x", "name_only": "x", "baseline_plus_name": "x"},
            "penalty_C_grid": [0.1, 1.0],
        }
        rows = []
        for year in range(2000, 2003):
            for index in range(12):
                rows.append({
                    "combine_year": year,
                    "measurement": index,
                    "name": index / 2,
                    "POSITION": "G" if index % 2 else "F",
                    "drafted": index % 2,
                })
        result = tune_models(pd.DataFrame(rows), spec)
        self.assertEqual(set(result), set(spec["models"]))
        self.assertTrue(all(value["selected_C"] in {0.1, 1.0} for value in result.values()))

    def test_association_reports_raw_one_bit_effect_after_scaling(self):
        rng = np.random.default_rng(123)
        x = rng.normal(10, 4, 400)
        z = rng.normal(20, 2, 400)
        probability = 1 / (1 + np.exp(-(-1 + .08*x - .03*z)))
        frame = pd.DataFrame({
            "x": x, "z": z, "drafted": rng.binomial(1, probability),
            "PLAYER_ID": np.arange(400),
        })
        spec = {
            "outcome": "drafted",
            "name_features": ["x", "z"],
            "association_adjustment_numeric": [],
            "association_adjustment_categorical": [],
            "association": {
                "co_primary_exposures": ["x", "z"], "alpha": .05,
            },
        }
        result = association_analysis(frame, spec)
        for exposure in ("x", "z"):
            estimate = result["co_primary"][exposure]
            self.assertAlmostEqual(
                estimate["coefficient_per_bit"],
                estimate["coefficient_per_standard_deviation"]
                / estimate["standardization_scale_bits"],
            )

    def test_all_frozen_sensitivity_variants_are_constructible(self):
        cohort = ROOT / "study/output/combine_cohort.csv"
        if not cohort.exists():
            self.skipTest("derived cohort is not present")
        frame = pd.read_csv(cohort, low_memory=False)
        variants = sensitivity_variants(frame, self.spec)
        self.assertEqual(set(variants), set(self.spec["sensitivity_analyses"]))
        exact = variants["exact_birth_year_given_surprisal_verified_subset"][0]
        self.assertEqual(len(exact), 1337)
        self.assertTrue(exact["birth_year"].notna().all())


if __name__ == "__main__":
    unittest.main()
