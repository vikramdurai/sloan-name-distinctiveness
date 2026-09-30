"""Construct and audit the frozen NBA Draft Combine study cohort."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime
from math import sqrt
from pathlib import Path
from typing import Iterable

from study.name_features import (
    DEFAULT_CENSUS_PATH,
    DEFAULT_SSA_PATH,
    name_form_flags,
    rate_public_given_name,
    rate_public_given_name_generation,
    rate_public_surname,
)
from study.nba_client import NBAClient, fetch_combine_year, fetch_player_profile


ANTHRO_FIELDS = (
    "HEIGHT_WO_SHOES", "HEIGHT_W_SHOES", "WEIGHT", "WINGSPAN",
    "STANDING_REACH", "BODY_FAT_PCT", "HAND_LENGTH", "HAND_WIDTH",
)
DRILL_FIELDS = (
    "STANDING_VERTICAL_LEAP", "MAX_VERTICAL_LEAP", "LANE_AGILITY_TIME",
    "MODIFIED_LANE_AGILITY_TIME", "THREE_QUARTER_SPRINT", "BENCH_PRESS",
)


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    return "".join(
        char for char in decomposed if char.isalnum() and not unicodedata.combining(char)
    )


def _positive_id(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def participant_key(row: dict[str, object], year: int) -> str:
    player_id = _positive_id(row.get("PLAYER_ID"))
    if player_id:
        return f"nba:{player_id}"
    temp_id = _positive_id(row.get("TEMP_PLAYER_ID"))
    if temp_id:
        return f"temp:{year}:{temp_id}"
    name = str(row.get("PLAYER_NAME") or "").strip()
    if not name:
        raise ValueError(f"Combine row in {year} has neither ID nor name")
    return f"name:{year}:{normalize_name(name)}"


def merge_participant_tables(
    year: int, anthro: list[dict], drills: list[dict]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    merged: dict[str, dict[str, object]] = {}
    conflicts: list[dict[str, object]] = []
    for source_name, rows in (("anthro", anthro), ("drills", drills)):
        for source in rows:
            key = participant_key(source, year)
            target = merged.setdefault(
                key,
                {
                    "combine_year": year,
                    "combine_key": key,
                    "in_anthro": False,
                    "in_drills": False,
                },
            )
            target[f"in_{source_name}"] = True
            for field, value in source.items():
                if value in (None, ""):
                    continue
                old = target.get(field)
                if old not in (None, "") and str(old) != str(value):
                    conflicts.append(
                        {"combine_year": year, "combine_key": key, "field": field,
                         "first_value": old, "second_value": value}
                    )
                    continue
                target[field] = value
    return list(merged.values()), conflicts


def _read_indexed_csv(path: Path, key_fields: tuple[str, ...]) -> dict[tuple[str, ...], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    return {tuple(row[field].strip() for field in key_fields): row for row in rows}


def attach_draft_outcomes(
    participants: list[dict[str, object]],
    draft_rows: list[dict],
    crosswalk: dict[tuple[str, ...], dict[str, str]],
) -> None:
    by_id = {
        int(row["PERSON_ID"]): row
        for row in draft_rows
        if _positive_id(row.get("PERSON_ID"))
    }
    by_name: dict[str, list[dict]] = defaultdict(list)
    for row in draft_rows:
        by_name[normalize_name(str(row.get("PLAYER_NAME") or ""))].append(row)

    for row in participants:
        match = None
        method = "none"
        player_id = _positive_id(row.get("PLAYER_ID"))
        if player_id in by_id:
            match, method = by_id[player_id], "nba_player_id"
        override = crosswalk.get((str(row["combine_year"]), str(row["combine_key"])))
        if match is None and override and override.get("draft_person_id"):
            match = by_id.get(int(override["draft_person_id"]))
            if match is None:
                raise ValueError(f"Crosswalk target is absent from draft history: {override}")
            method = "frozen_crosswalk"
        if match is None:
            candidates = by_name.get(normalize_name(str(row.get("PLAYER_NAME") or "")), [])
            if len(candidates) == 1:
                match, method = candidates[0], "unique_exact_normalized_name"
        row["drafted"] = int(match is not None)
        row["draft_match_method"] = method
        row["draft_person_id"] = match.get("PERSON_ID") if match else ""
        row["draft_round"] = match.get("ROUND_NUMBER") if match else ""
        row["overall_pick"] = match.get("OVERALL_PICK") if match else ""


def _parse_birth_year(value: object) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    match = re.search(r"(?:19|20)\d{2}", text)
    return int(match.group()) if match else None


def attach_birth_years(
    participants: list[dict[str, object]],
    client: NBAClient,
    overrides: dict[tuple[str, ...], dict[str, str]],
    fetch_profiles: bool,
) -> list[dict[str, object]]:
    unresolved: list[dict[str, object]] = []
    profile_cache: dict[int, dict | None] = {}
    for row in participants:
        year = str(row["combine_year"])
        key = str(row["combine_key"])
        override = overrides.get((year, key))
        birth_year = None
        if override and override.get("birth_year"):
            birth_year = int(override["birth_year"])
            row["birth_year_source"] = override.get("source_url", "")
            row["birth_year_source_type"] = override.get("source_type", "manual override")
            row["birth_year_confidence"] = override.get("confidence", "")
        player_id = _positive_id(row.get("PLAYER_ID"))
        if birth_year is None and fetch_profiles and player_id:
            if player_id not in profile_cache:
                profile_cache[player_id] = fetch_player_profile(client, player_id)
            profile = profile_cache[player_id]
            birth_year = _parse_birth_year(profile.get("BIRTHDATE")) if profile else None
            if birth_year:
                row["birth_year_source"] = f"https://www.nba.com/player/{player_id}"
                row["birth_year_source_type"] = "official NBA profile"
                row["birth_year_confidence"] = "high"
        row["birth_year"] = birth_year or ""
        if birth_year is None:
            unresolved.append(
                {"combine_year": row["combine_year"], "combine_key": key,
                 "display_name": row.get("PLAYER_NAME", ""), "nba_player_id": player_id or "",
                 "birth_year": "", "source_url": "", "source_type": "", "confidence": "",
                 "notes": ""}
            )
    return unresolved


def attach_name_features(
    participants: list[dict[str, object]],
    name_form_overrides: dict[tuple[str, ...], dict[str, str]] | None = None,
    ssa_path: Path = DEFAULT_SSA_PATH,
    census_path: Path = DEFAULT_CENSUS_PATH,
) -> None:
    name_form_overrides = name_form_overrides or {}
    for row in participants:
        given = str(row.get("FIRST_NAME") or "").strip()
        surname = str(row.get("LAST_NAME") or "").strip()
        row["display_name"] = str(row.get("PLAYER_NAME") or f"{given} {surname}").strip()
        row["display_given_name"] = given
        row["display_surname"] = surname
        row.update(name_form_flags(given, surname))
        override = name_form_overrides.get(
            (str(row["combine_year"]), str(row["combine_key"]))
        )
        row["name_form"] = override.get("name_form", "unreviewed") if override else "unreviewed"
        row["nickname_verified"] = bool(override and override.get("name_form") == "nickname")
        row["legal_or_birth_given_name"] = (
            override.get("legal_or_birth_given_name", "") if override else ""
        )
        row["legal_or_birth_full_name"] = (
            override.get("legal_or_birth_full_name", "") if override else ""
        )
        row["name_form_source_url"] = override.get("source_url", "") if override else ""
        if surname:
            feature = rate_public_surname(surname, census_path)
            for key, value in asdict(feature).items():
                row[f"surname_{key}"] = value
        if given and not row["initials"]:
            feature = rate_public_given_name_generation(
                given, int(row["combine_year"]), ssa_path
            )
            for key, value in asdict(feature).items():
                row[f"given_generation_{key}"] = value if value is not None else ""
            row["given_generation_surprisal"] = feature.conservative_surprisal_bits
            row["given_generation_missing"] = False
            row["given_name_missing"] = False
        else:
            row["given_generation_surprisal"] = ""
            row["given_generation_missing"] = True
            row["given_name_missing"] = True
        birth_year = _parse_birth_year(row.get("birth_year"))
        if given and birth_year and not row["initials"]:
            exact = rate_public_given_name(given, birth_year, ssa_path)
            for key, value in asdict(exact).items():
                row[f"given_exact_birth_{key}"] = value if value is not None else ""
            row["given_exact_birth_surprisal"] = exact.conservative_surprisal_bits
            row["given_exact_birth_missing"] = False
        else:
            row["given_exact_birth_surprisal"] = ""
            row["given_exact_birth_missing"] = True


def attach_undrafted_reviews(
    participants: list[dict[str, object]],
    reviews: dict[tuple[str, ...], dict[str, str]],
) -> None:
    """Attach and validate the persistent deterministic undrafted audit sample."""
    by_key = {
        (str(row["combine_year"]), str(row["combine_key"])): row
        for row in participants
    }
    for row in participants:
        row["undrafted_review_result"] = ""
        row["undrafted_combine_source_url"] = ""
        row["undrafted_draft_source_url"] = ""
        row["undrafted_reviewed_on"] = ""
        row["undrafted_review_notes"] = ""
    for key, review in reviews.items():
        row = by_key.get(key)
        if row is None:
            raise ValueError(f"Undrafted review target is absent from cohort: {key}")
        if row.get("drafted") != 0:
            raise ValueError(f"Undrafted review target is coded drafted: {key}")
        reviewed_name = review.get("display_name", "")
        cohort_name = str(row.get("PLAYER_NAME") or row.get("display_name") or "")
        if normalize_name(reviewed_name) != normalize_name(cohort_name):
            raise ValueError(
                f"Undrafted review name does not match cohort for {key}: "
                f"{reviewed_name!r} != {cohort_name!r}"
            )
        row["undrafted_review_result"] = review.get("review_result", "")
        row["undrafted_combine_source_url"] = review.get("combine_source_url", "")
        row["undrafted_draft_source_url"] = review.get("draft_source_url", "")
        row["undrafted_reviewed_on"] = review.get("reviewed_on", "")
        row["undrafted_review_notes"] = review.get("notes", "")


def _comparison_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    pairs = [
        (float(row["given_generation_surprisal"]), float(row["given_exact_birth_surprisal"]))
        for row in rows
        if row.get("given_generation_surprisal") not in (None, "")
        and row.get("given_exact_birth_surprisal") not in (None, "")
    ]
    if not pairs:
        return {"count": 0, "pearson_correlation": None, "score_difference": None}
    generation = [pair[0] for pair in pairs]
    exact = [pair[1] for pair in pairs]
    differences = [left - right for left, right in pairs]
    mean_generation = sum(generation) / len(pairs)
    mean_exact = sum(exact) / len(pairs)
    numerator = sum(
        (left - mean_generation) * (right - mean_exact)
        for left, right in pairs
    )
    variance_generation = sum((value - mean_generation) ** 2 for value in generation)
    variance_exact = sum((value - mean_exact) ** 2 for value in exact)
    denominator = sqrt(variance_generation * variance_exact)
    ordered = sorted(differences)
    middle = len(ordered) // 2
    median = (
        ordered[middle] if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / 2
    )
    return {
        "count": len(pairs),
        "pearson_correlation": numerator / denominator if denominator else None,
        "score_difference": {
            "definition": "generation minus exact-birth surprisal bits",
            "mean": sum(differences) / len(differences),
            "median": median,
            "mean_absolute": sum(abs(value) for value in differences) / len(differences),
            "minimum": min(differences),
            "maximum": max(differences),
        },
    }


def audit_cohort(
    participants: list[dict[str, object]],
    conflicts: list[dict[str, object]],
    requested_years: Iterable[int],
) -> dict[str, object]:
    requested_years = list(requested_years)
    by_year: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in participants:
        by_year[int(row["combine_year"])].append(row)
    yearly = []
    for year in requested_years:
        rows = by_year.get(year, [])
        drafted = [row for row in rows if row.get("drafted") == 1]
        yearly.append({
            "year": year,
            "participants": len(rows),
            "anthro_rows": sum(bool(row.get("in_anthro")) for row in rows),
            "drill_rows": sum(bool(row.get("in_drills")) for row in rows),
            "drafted": len(drafted),
            "draft_rate": len(drafted) / len(rows) if rows else None,
            "birth_year_coverage": sum(bool(row.get("birth_year")) for row in rows) / len(rows) if rows else None,
            "generation_feature_coverage": sum(not row.get("given_generation_missing", True) for row in rows) / len(rows) if rows else None,
            "exact_birth_feature_coverage": sum(not row.get("given_exact_birth_missing", True) for row in rows) / len(rows) if rows else None,
            "census_observed_rate": sum(bool(row.get("surname_observed")) for row in rows) / len(rows) if rows else None,
            "measurement_missingness": {
                field.lower(): sum(row.get(field) in (None, "") for row in rows) / len(rows) if rows else None
                for field in ANTHRO_FIELDS + DRILL_FIELDS
            },
        })
    drafted_rows = [row for row in participants if row.get("drafted") == 1]
    undrafted_rows = [row for row in participants if row.get("drafted") == 0]
    coverage = lambda rows: sum(bool(row.get("birth_year")) for row in rows) / len(rows) if rows else 0.0
    drafted_coverage = coverage(drafted_rows)
    undrafted_coverage = coverage(undrafted_rows)
    usable_years = sum(item["participants"] > 0 for item in yearly)
    generation_scored = [
        row for row in participants
        if row.get("given_generation_surprisal") not in (None, "")
    ]
    generation_missing = [
        row for row in participants
        if row.get("given_generation_surprisal") in (None, "")
    ]
    explained_generation_missing = all(
        bool(row.get("initials")) or not str(row.get("display_given_name") or "").strip()
        for row in generation_missing
    )
    complete_span = requested_years == list(range(2000, 2026)) and all(
        by_year.get(year) for year in range(2000, 2026)
    )
    review_sample = undrafted_review_sample(participants)
    completed_review_rows = sum(
        str(row.get("review_result", "")).strip().casefold() == "confirmed_undrafted"
        and str(row.get("combine_source_url", "")).startswith("https://")
        and str(row.get("draft_source_url", "")).startswith("https://")
        and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row.get("reviewed_on", ""))))
        and bool(str(row.get("notes", "")).strip())
        for row in review_sample
    )
    review_complete = bool(review_sample) and completed_review_rows == len(review_sample)
    gates = {
        "at_least_15_usable_years": usable_years >= 15,
        "no_identity_conflicts": not conflicts,
        "all_drafted_matches_auditable": all(
            row.get("draft_match_method") in {
                "nba_player_id", "frozen_crosswalk", "unique_exact_normalized_name"
            } for row in drafted_rows
        ),
        "all_generation_feature_missingness_explained": explained_generation_missing,
        "full_2000_2025_cohort_scored": complete_span and explained_generation_missing,
        "undrafted_review_sample_complete": review_complete,
    }
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "participant_count": len(participants),
        "drafted_count": len(drafted_rows),
        "usable_years": usable_years,
        "birth_year_coverage": coverage(participants),
        "drafted_birth_year_coverage": drafted_coverage,
        "undrafted_birth_year_coverage": undrafted_coverage,
        "generation_feature_coverage": len(generation_scored) / len(participants) if participants else 0.0,
        "generation_feature_missing_reasons": {
            "initials": sum(bool(row.get("initials")) for row in generation_missing),
            "missing_or_malformed_source_given_name": sum(
                not bool(row.get("initials")) for row in generation_missing
            ),
        },
        "exact_birth_feature_coverage": sum(
            row.get("given_exact_birth_surprisal") not in (None, "") for row in participants
        ) / len(participants) if participants else 0.0,
        "generation_exact_birth_comparison": {
            "all": _comparison_summary(participants),
            "drafted": _comparison_summary(drafted_rows),
            "undrafted": _comparison_summary(undrafted_rows),
        },
        "undrafted_review_sample": {
            "sample_size": len(review_sample),
            "completed": completed_review_rows,
        },
        "identity_conflicts": conflicts,
        "draft_match_methods": dict(Counter(str(row.get("draft_match_method")) for row in participants)),
        "quality_gates": gates,
        "given_name_primary_eligible": gates["all_generation_feature_missingness_explained"] and gates["full_2000_2025_cohort_scored"],
        "cohort_analysis_ready": all(gates.values()),
        "yearly": yearly,
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def undrafted_review_sample(rows: list[dict[str, object]], size: int = 50) -> list[dict[str, object]]:
    undrafted = [row for row in rows if row.get("drafted") == 0]
    ranked = sorted(
        undrafted,
        key=lambda row: hashlib.sha256(
            f'{row["combine_year"]}:{row["combine_key"]}'.encode()
        ).hexdigest(),
    )[:size]
    return [
        {"combine_year": row["combine_year"], "combine_key": row["combine_key"],
         "display_name": row.get("display_name", row.get("PLAYER_NAME", "")),
         "review_result": row.get("undrafted_review_result", ""),
         "combine_source_url": row.get("undrafted_combine_source_url", ""),
         "draft_source_url": row.get("undrafted_draft_source_url", ""),
         "reviewed_on": row.get("undrafted_reviewed_on", ""),
         "notes": row.get("undrafted_review_notes", "")}
        for row in ranked
    ]


def load_overrides(
    birth_year_path: Path,
    crosswalk_path: Path,
    name_form_path: Path,
    undrafted_review_path: Path,
):
    return (
        _read_indexed_csv(birth_year_path, ("combine_year", "combine_key")),
        _read_indexed_csv(crosswalk_path, ("combine_year", "combine_key")),
        _read_indexed_csv(name_form_path, ("combine_year", "combine_key")),
        _read_indexed_csv(undrafted_review_path, ("combine_year", "combine_key")),
    )


def build(
    client: NBAClient,
    years: range,
    birth_year_path: Path,
    crosswalk_path: Path,
    name_form_path: Path,
    undrafted_review_path: Path,
    fetch_profiles: bool,
) -> tuple[list[dict[str, object]], dict[str, object], list[dict[str, object]]]:
    birth_overrides, crosswalk, name_form_overrides, undrafted_reviews = load_overrides(
        birth_year_path, crosswalk_path, name_form_path, undrafted_review_path
    )
    all_rows: list[dict[str, object]] = []
    conflicts: list[dict[str, object]] = []
    for year in years:
        anthro, drills, draft = fetch_combine_year(client, year)
        participants, year_conflicts = merge_participant_tables(year, anthro, drills)
        attach_draft_outcomes(participants, draft, crosswalk)
        all_rows.extend(participants)
        conflicts.extend(year_conflicts)
    unresolved = attach_birth_years(all_rows, client, birth_overrides, fetch_profiles)
    attach_name_features(all_rows, name_form_overrides)
    attach_undrafted_reviews(all_rows, undrafted_reviews)
    audit = audit_cohort(all_rows, conflicts, years)
    return all_rows, audit, unresolved
