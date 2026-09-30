from __future__ import annotations

import csv
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ModelingSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(
            (ROOT / "study/modeling_spec.json").read_text(encoding="utf-8")
        )
        cohort_path = ROOT / "study/output/combine_cohort.csv"
        cls.cohort_fields = None
        if cohort_path.exists():
            with cohort_path.open(newline="", encoding="utf-8") as source:
                reader = csv.DictReader(source)
                cls.cohort_fields = set(reader.fieldnames or [])

    def test_frozen_features_exist_in_cohort(self):
        if self.cohort_fields is None:
            self.skipTest("derived cohort is not present")
        feature_groups = (
            "name_features",
            "prediction_baseline_numeric",
            "prediction_baseline_categorical",
            "association_adjustment_numeric",
            "association_adjustment_categorical",
        )
        requested = {
            field for group in feature_groups for field in self.spec[group]
        }
        self.assertEqual(requested - self.cohort_fields, set())
        self.assertIn(self.spec["outcome"], self.cohort_fields)

    def test_temporal_split_is_complete_disjoint_and_ordered(self):
        expanded = {
            name: set(range(bounds[0], bounds[1] + 1))
            for name, bounds in self.spec["splits"].items()
        }
        self.assertFalse(expanded["train"] & expanded["validation"])
        self.assertFalse(expanded["train"] & expanded["test"])
        self.assertFalse(expanded["validation"] & expanded["test"])
        self.assertEqual(
            set().union(*expanded.values()),
            set(range(self.spec["year_range"][0], self.spec["year_range"][1] + 1)),
        )
        self.assertLess(max(expanded["train"]), min(expanded["validation"]))
        self.assertLess(max(expanded["validation"]), min(expanded["test"]))

    def test_primary_predictors_are_not_outcome_fields(self):
        predictors = set(self.spec["name_features"])
        predictors.update(self.spec["prediction_baseline_numeric"])
        predictors.update(self.spec["prediction_baseline_categorical"])
        forbidden = {"drafted", "draft_round", "overall_pick", "draft_person_id"}
        self.assertFalse(predictors & forbidden)

    def test_regularization_grid_and_bootstrap_are_frozen(self):
        grid = self.spec["penalty_C_grid"]
        self.assertEqual(grid, sorted(grid))
        self.assertTrue(all(value > 0 for value in grid))
        self.assertEqual(self.spec["bootstrap"]["replicates"], 2000)
        self.assertEqual(self.spec["bootstrap"]["seed"], 20260930)

    def test_frozen_contract_checksum(self):
        spec_path = ROOT / "study/modeling_spec.json"
        expected = (ROOT / "study/modeling_spec.sha256").read_text(
            encoding="utf-8"
        ).split()[0]
        actual = hashlib.sha256(spec_path.read_bytes()).hexdigest()
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
