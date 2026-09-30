from __future__ import annotations

import csv
import tempfile
import unittest
import zipfile
from pathlib import Path

from study.cohort import (
    attach_name_features,
    attach_draft_outcomes,
    audit_cohort,
    merge_participant_tables,
    normalize_name,
)
from study.name_features import (
    name_form_flags,
    rate_public_given_name,
    rate_public_given_name_generation,
    rate_public_surname,
)
from study.nba_client import combine_season, fetch_player_profile, result_rows


class NameFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.ssa = root / "ssa.zip"
        with zipfile.ZipFile(self.ssa, "w") as archive:
            for year in range(1995, 2004):
                archive.writestr(
                    f"yob{year}.txt", "Jack,M,10\nCommon,M,100\nJane,F,50\n"
                )
        self.census = root / "census.zip"
        with zipfile.ZipFile(self.census, "w") as archive:
            header = "name,rank,count,prop100k,cum_prop100k,pctwhite,pctblack,pctapi,pctaian,pct2prace,pcthispanic\n"
            rows = [
                "SMITH,1,1000,10.00,10.00,0,0,0,0,0,0\n",
                "ONEAL,2,100,1.00,11.00,0,0,0,0,0,0\n",
            ]
            archive.writestr("Names_2010Census.csv", header + "".join(rows))

    def tearDown(self):
        self.temp.cleanup()

    def test_suppression_upper_bound_is_applied_per_unpublished_year(self):
        feature = rate_public_given_name("Unique", 2000, self.ssa)
        self.assertEqual(feature.unpublished_years, 7)
        self.assertEqual(feature.conservative_birth_count, 28)
        self.assertFalse(feature.ssa_ever_observed)
        self.assertIsNone(feature.sensitivity_surprisal_zero)

    def test_observed_given_name_uses_published_counts(self):
        feature = rate_public_given_name("Jack", 2000, self.ssa)
        self.assertEqual(feature.published_birth_count, 70)
        self.assertEqual(feature.unpublished_years, 0)

    def test_2019_generation_window_is_1995_through_2001(self):
        feature = rate_public_given_name_generation("Jack", 2019, self.ssa)
        self.assertEqual((feature.cohort_start, feature.cohort_end), (1995, 2001))
        self.assertEqual(feature.published_birth_count, 70)

    def test_generation_scoring_handles_suppressed_and_accented_names(self):
        suppressed = rate_public_given_name_generation("Unique", 2019, self.ssa)
        accented = rate_public_given_name_generation("José", 2019, self.ssa)
        self.assertEqual(suppressed.conservative_birth_count, 28)
        self.assertEqual(accented.conservative_birth_count, 28)

    def test_generation_scoring_rejects_initials(self):
        with self.assertRaises(ValueError):
            rate_public_given_name_generation("T. J.", 2019, self.ssa)

    def test_primary_score_does_not_depend_on_birth_year(self):
        rows = [
            {"combine_year": 2019, "combine_key": "nba:1", "FIRST_NAME": "Jack", "LAST_NAME": "Smith", "birth_year": 1997},
            {"combine_year": 2019, "combine_key": "nba:2", "FIRST_NAME": "Jack", "LAST_NAME": "Smith", "birth_year": ""},
        ]
        attach_name_features(rows, ssa_path=self.ssa, census_path=self.census)
        self.assertEqual(rows[0]["given_generation_surprisal"], rows[1]["given_generation_surprisal"])
        self.assertFalse(rows[0]["given_exact_birth_missing"])
        self.assertTrue(rows[1]["given_exact_birth_missing"])

    def test_census_normalization_and_unpublished_bound(self):
        observed = rate_public_surname("O'Neal", self.census)
        absent = rate_public_surname("Bamba", self.census)
        self.assertEqual(observed.census_lookup_form, "ONEAL")
        self.assertTrue(observed.normalized_for_lookup)
        self.assertEqual(absent.conservative_count, 99)
        self.assertFalse(absent.observed)

    def test_initial_and_diacritic_flags(self):
        self.assertTrue(name_form_flags("T. J.", "Ford")["initials"])
        self.assertTrue(name_form_flags("Luka", "Dončić")["has_diacritic"])


class CohortTests(unittest.TestCase):
    def test_union_merge_and_draft_join(self):
        anthro = [{
            "PLAYER_ID": 1, "TEMP_PLAYER_ID": 10, "FIRST_NAME": "Ada",
            "LAST_NAME": "Smith", "PLAYER_NAME": "Ada Smith", "HEIGHT_WO_SHOES": 72,
        }]
        drills = [
            {"PLAYER_ID": 1, "TEMP_PLAYER_ID": 10, "FIRST_NAME": "Ada", "LAST_NAME": "Smith", "PLAYER_NAME": "Ada Smith", "MAX_VERTICAL_LEAP": 40},
            {"PLAYER_ID": 2, "TEMP_PLAYER_ID": 11, "FIRST_NAME": "Bea", "LAST_NAME": "Jones", "PLAYER_NAME": "Bea Jones", "MAX_VERTICAL_LEAP": 35},
        ]
        rows, conflicts = merge_participant_tables(2020, anthro, drills)
        self.assertEqual(len(rows), 2)
        self.assertFalse(conflicts)
        ada = next(row for row in rows if row["combine_key"] == "nba:1")
        self.assertTrue(ada["in_anthro"])
        self.assertTrue(ada["in_drills"])
        draft = [{"PERSON_ID": 1, "PLAYER_NAME": "Ada Smith", "ROUND_NUMBER": 1, "OVERALL_PICK": 4}]
        attach_draft_outcomes(rows, draft, {})
        self.assertEqual(ada["drafted"], 1)
        self.assertEqual(ada["draft_match_method"], "nba_player_id")
        self.assertEqual(sum(row["drafted"] for row in rows), 1)

    def test_unique_normalized_name_fallback(self):
        rows = [{"combine_year": 2020, "combine_key": "temp:2020:5", "PLAYER_NAME": "Luka Dončić"}]
        draft = [{"PERSON_ID": 9, "PLAYER_NAME": "Luka Doncic", "ROUND_NUMBER": 1, "OVERALL_PICK": 3}]
        attach_draft_outcomes(rows, draft, {})
        self.assertEqual(rows[0]["draft_match_method"], "unique_exact_normalized_name")

    def test_audit_uses_complete_generation_scoring_gate(self):
        rows = []
        for year in range(2000, 2026):
            rows.append({
                "combine_year": year, "combine_key": f"nba:{year}", "drafted": year % 2,
                "draft_match_method": "nba_player_id" if year % 2 else "none",
                "birth_year": 1980 if year == 2000 else "", "display_given_name": "Ada",
                "given_generation_surprisal": 12.0, "given_generation_missing": False,
                "given_exact_birth_surprisal": 11.5 if year == 2000 else "",
                "given_exact_birth_missing": year != 2000, "initials": False,
                "undrafted_review_result": "confirmed_undrafted",
                "undrafted_combine_source_url": "https://example.test/combine",
                "undrafted_draft_source_url": "https://example.test/draft",
                "undrafted_reviewed_on": "2026-09-30",
                "undrafted_review_notes": "verified",
                "surname_observed": True, "in_anthro": True, "in_drills": True,
            })
        audit = audit_cohort(rows, [], range(2000, 2026))
        self.assertTrue(audit["quality_gates"]["at_least_15_usable_years"])
        self.assertTrue(audit["quality_gates"]["full_2000_2025_cohort_scored"])
        self.assertTrue(audit["cohort_analysis_ready"])
        self.assertLess(audit["birth_year_coverage"], 0.95)

    def test_audit_accepts_explained_initial_missingness(self):
        rows = [{
            "combine_year": year, "combine_key": f"nba:{year}", "drafted": 0,
            "draft_match_method": "none", "birth_year": "", "display_given_name": "T. J.",
            "given_generation_surprisal": "", "given_generation_missing": True,
            "given_exact_birth_surprisal": "", "given_exact_birth_missing": True,
            "initials": True, "surname_observed": True, "in_anthro": True, "in_drills": True,
            "undrafted_review_result": "confirmed_undrafted",
            "undrafted_combine_source_url": "https://example.test/combine",
            "undrafted_draft_source_url": "https://example.test/draft",
            "undrafted_reviewed_on": "2026-09-30",
            "undrafted_review_notes": "verified",
        } for year in range(2000, 2026)]
        audit = audit_cohort(rows, [], range(2000, 2026))
        self.assertTrue(audit["quality_gates"]["all_generation_feature_missingness_explained"])
        self.assertEqual(audit["generation_feature_missing_reasons"]["initials"], 26)

    def test_audit_requires_review_evidence(self):
        rows = [{
            "combine_year": year, "combine_key": f"nba:{year}", "drafted": 0,
            "draft_match_method": "none", "birth_year": "", "display_given_name": "Ada",
            "given_generation_surprisal": 12.0, "given_generation_missing": False,
            "given_exact_birth_surprisal": "", "given_exact_birth_missing": True,
            "initials": False, "surname_observed": True, "in_anthro": True, "in_drills": True,
            "undrafted_review_result": "confirmed_undrafted",
            "undrafted_combine_source_url": "https://example.test/combine",
            "undrafted_draft_source_url": "",
            "undrafted_reviewed_on": "2026-09-30",
            "undrafted_review_notes": "verified",
        } for year in range(2000, 2026)]
        audit = audit_cohort(rows, [], range(2000, 2026))
        self.assertFalse(audit["quality_gates"]["undrafted_review_sample_complete"])
        self.assertFalse(audit["cohort_analysis_ready"])

    def test_full_span_gate_requires_rows_in_every_year(self):
        rows = [{
            "combine_year": year, "combine_key": f"nba:{year}", "drafted": 0,
            "draft_match_method": "none", "birth_year": "", "display_given_name": "Ada",
            "given_generation_surprisal": 12.0, "given_generation_missing": False,
            "given_exact_birth_surprisal": "", "given_exact_birth_missing": True,
            "initials": False, "surname_observed": True, "in_anthro": True, "in_drills": True,
            "undrafted_review_result": "confirmed_undrafted",
            "undrafted_combine_source_url": "https://example.test/combine",
            "undrafted_draft_source_url": "https://example.test/draft",
            "undrafted_reviewed_on": "2026-09-30", "undrafted_review_notes": "verified",
        } for year in range(2000, 2025)]
        audit = audit_cohort(rows, [], range(2000, 2026))
        self.assertFalse(audit["quality_gates"]["full_2000_2025_cohort_scored"])

    def test_review_sample_hashes_player_year_unit(self):
        from study.cohort import undrafted_review_sample

        rows = [
            {"combine_year": 2023, "combine_key": "nba:1", "drafted": 0},
            {"combine_year": 2024, "combine_key": "nba:1", "drafted": 0},
        ]
        expected = sorted(
            rows,
            key=lambda row: __import__("hashlib").sha256(
                f'{row["combine_year"]}:{row["combine_key"]}'.encode()
            ).hexdigest(),
        )
        actual = undrafted_review_sample(rows, size=2)
        self.assertEqual(
            [(row["combine_year"], row["combine_key"]) for row in actual],
            [(row["combine_year"], row["combine_key"]) for row in expected],
        )

    def test_result_set_parser(self):
        payload = {"resultSets": [{"name": "Results", "headers": ["A", "B"], "rowSet": [[1, 2]]}]}
        self.assertEqual(result_rows(payload, "Results"), [{"A": 1, "B": 2}])

    def test_combine_season_uses_browser_endpoint_format(self):
        self.assertEqual(combine_season(2019), "2019-20")
        self.assertEqual(combine_season(1999), "1999-00")

    def test_empty_official_player_profile_is_unresolved(self):
        class EmptyProfileClient:
            def get(self, endpoint, params, cache_key):
                return {}

        self.assertIsNone(fetch_player_profile(EmptyProfileClient(), 12019))

    def test_name_normalization(self):
        self.assertEqual(normalize_name("Luka Dončić"), normalize_name("Luka Doncic"))


if __name__ == "__main__":
    unittest.main()
