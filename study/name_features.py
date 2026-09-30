"""Frozen, outcome-blind name features used by the Combine study."""

from __future__ import annotations

import importlib.util
import math
import re
import sys
import unicodedata
import zipfile
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCORER_PATH = ROOT / "cool-names" / "main.py"
DEFAULT_SSA_PATH = ROOT / "cool-names" / "data" / "ssa_names.zip"
DEFAULT_CENSUS_PATH = ROOT / "cool-names" / "data" / "census_surnames_2010.zip"


def _load_scorer():
    spec = importlib.util.spec_from_file_location("cool_names_scorer", SCORER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import scorer from {SCORER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCORER = _load_scorer()


@dataclass(frozen=True)
class GivenNameFeature:
    display_given_name: str
    birth_year: int
    cohort_start: int
    cohort_end: int
    published_birth_count: int
    unpublished_years: int
    conservative_birth_count: float
    reference_birth_count: int
    conservative_rate_per_million: float
    conservative_surprisal_bits: float
    sensitivity_surprisal_zero: float | None
    sensitivity_surprisal_midpoint: float
    ssa_ever_observed: bool


@dataclass(frozen=True)
class GenerationGivenNameFeature:
    display_given_name: str
    combine_year: int
    cohort_start: int
    cohort_end: int
    published_birth_count: int
    unpublished_years: int
    conservative_birth_count: float
    reference_birth_count: int
    conservative_rate_per_million: float
    conservative_surprisal_bits: float
    sensitivity_surprisal_zero: float | None
    sensitivity_surprisal_midpoint: float
    ssa_ever_observed: bool


@dataclass(frozen=True)
class SurnameFeature:
    display_surname: str
    census_lookup_form: str
    observed: bool
    published_count: int
    conservative_count: int
    reference_population: int
    conservative_rate_per_million: float
    conservative_surprisal_bits: float
    sensitivity_surprisal_one: float
    sensitivity_surprisal_midpoint: float
    normalized_for_lookup: bool


def _surprisal(count: float, denominator: int) -> float | None:
    if count <= 0 or denominator <= 0:
        return None
    return -math.log2(count / denominator)


@lru_cache(maxsize=None)
def _yearly_published_counts(
    data_path: Path, start_year: int, end_year: int, sex: str
) -> tuple[dict[int, dict[str, int]], dict[int, int]]:
    wanted = {sex.upper()}
    yearly: dict[int, dict[str, int]] = {
        year: {} for year in range(start_year, end_year + 1)
    }
    totals = {year: 0 for year in yearly}
    with zipfile.ZipFile(data_path) as archive:
        members = {
            year: member
            for member in archive.namelist()
            if (year := SCORER._year_from_member(member)) is not None
        }
        if members:
            for year in yearly:
                member = members.get(year)
                if member is None:
                    continue
                with archive.open(member) as source:
                    for raw in source:
                        name, recorded_sex, count = raw.decode("utf-8-sig").strip().split(",")
                        if recorded_sex in wanted:
                            yearly[year][name.casefold()] = int(count)
                            totals[year] += int(count)
        else:
            member = next(
                (name for name in archive.namelist() if Path(name).name == "alldata.txt"),
                None,
            )
            if member is None:
                raise ValueError("SSA archive has no supported files")
            with archive.open(member) as source:
                for raw in source:
                    name, recorded_sex, count, year = raw.decode("utf-8-sig").strip().split(",")
                    year_number = int(year)
                    if year_number in yearly and recorded_sex in wanted:
                        yearly[year_number][name.casefold()] = int(count)
                        totals[year_number] += int(count)
    if not all(totals.values()):
        missing = [str(year) for year, total in totals.items() if total == 0]
        raise ValueError(f"SSA reference data missing cohort years: {', '.join(missing)}")
    return yearly, totals


def rate_public_given_name(
    name: str,
    birth_year: int,
    data_path: Path = DEFAULT_SSA_PATH,
    window: int = 3,
) -> GivenNameFeature:
    """Rate a public male given name using the frozen conservative censoring rule."""
    clean = name.strip()
    if not clean:
        raise ValueError("Given name cannot be empty")
    if SCORER.looks_like_initials(clean):
        raise ValueError("Initial forms do not receive a continuous SSA feature")
    years = SCORER.available_years(data_path)
    if birth_year < years[0] or birth_year > years[-1]:
        raise ValueError(f"Birth year {birth_year} is outside SSA coverage")
    start = max(years[0], birth_year - window)
    end = min(years[-1], birth_year + window)
    yearly, totals = _yearly_published_counts(data_path, start, end, "M")
    key = clean.casefold()
    counts = [yearly[year].get(key) for year in range(start, end + 1)]
    published = sum(count for count in counts if count is not None)
    unpublished = sum(count is None for count in counts)
    denominator = sum(totals.values())
    conservative = published + 4 * unpublished
    midpoint = published + 2.5 * unpublished
    return GivenNameFeature(
        display_given_name=clean,
        birth_year=birth_year,
        cohort_start=start,
        cohort_end=end,
        published_birth_count=published,
        unpublished_years=unpublished,
        conservative_birth_count=conservative,
        reference_birth_count=denominator,
        conservative_rate_per_million=conservative / denominator * 1_000_000,
        conservative_surprisal_bits=float(_surprisal(conservative, denominator)),
        sensitivity_surprisal_zero=_surprisal(published, denominator),
        sensitivity_surprisal_midpoint=float(_surprisal(midpoint, denominator)),
        ssa_ever_observed=published > 0,
    )


def rate_public_given_name_generation(
    name: str,
    combine_year: int,
    data_path: Path = DEFAULT_SSA_PATH,
) -> GenerationGivenNameFeature:
    """Rate a public male given name over the fixed Combine-age window (18--24)."""
    clean = name.strip()
    if not clean:
        raise ValueError("Given name cannot be empty")
    if SCORER.looks_like_initials(clean):
        raise ValueError("Initial forms do not receive a continuous SSA feature")
    start, end = combine_year - 24, combine_year - 18
    available = SCORER.available_years(data_path)
    if start < available[0] or end > available[-1]:
        raise ValueError(
            f"Generation window {start}-{end} is outside SSA coverage "
            f"{available[0]}-{available[-1]}"
        )
    yearly, totals = _yearly_published_counts(data_path, start, end, "M")
    key = clean.casefold()
    counts = [yearly[year].get(key) for year in range(start, end + 1)]
    published = sum(count for count in counts if count is not None)
    unpublished = sum(count is None for count in counts)
    denominator = sum(totals.values())
    conservative = published + 4 * unpublished
    midpoint = published + 2.5 * unpublished
    return GenerationGivenNameFeature(
        display_given_name=clean,
        combine_year=combine_year,
        cohort_start=start,
        cohort_end=end,
        published_birth_count=published,
        unpublished_years=unpublished,
        conservative_birth_count=conservative,
        reference_birth_count=denominator,
        conservative_rate_per_million=conservative / denominator * 1_000_000,
        conservative_surprisal_bits=float(_surprisal(conservative, denominator)),
        sensitivity_surprisal_zero=_surprisal(published, denominator),
        sensitivity_surprisal_midpoint=float(_surprisal(midpoint, denominator)),
        ssa_ever_observed=published > 0,
    )


@lru_cache(maxsize=None)
def _census_reference_population(data_path: Path) -> int:
    """Infer the Census denominator from published count and prop100k columns."""
    estimates: list[float] = []
    with zipfile.ZipFile(data_path) as archive:
        with archive.open(SCORER.CENSUS_CSV_NAME) as source:
            header = source.readline().decode("utf-8-sig").strip().split(",")
            columns = {name: index for index, name in enumerate(header)}
            for raw in source:
                values = raw.decode("utf-8-sig").strip().split(",")
                prop = values[columns["prop100k"]]
                if prop == "(S)" or not prop:
                    continue
                estimates.append(int(values[columns["count"]]) / (float(prop) / 100_000))
                if len(estimates) == 100:
                    break
    if not estimates:
        raise ValueError("Could not infer Census reference population")
    estimates.sort()
    return round(estimates[len(estimates) // 2])


def rate_public_surname(
    surname: str, data_path: Path = DEFAULT_CENSUS_PATH
) -> SurnameFeature:
    """Rate a displayed surname using the frozen Census censoring rule."""
    clean = surname.strip()
    if not clean:
        raise ValueError("Surname cannot be empty")
    rating = SCORER.rate_surname(clean, data_path=data_path)
    denominator = _census_reference_population(data_path)
    conservative = rating.published_count if rating.observed_in_census_data else 99
    midpoint = rating.published_count if rating.observed_in_census_data else 50
    one = rating.published_count if rating.observed_in_census_data else 1
    return SurnameFeature(
        display_surname=clean,
        census_lookup_form=rating.census_lookup_form,
        observed=rating.observed_in_census_data,
        published_count=rating.published_count,
        conservative_count=conservative,
        reference_population=denominator,
        conservative_rate_per_million=conservative / denominator * 1_000_000,
        conservative_surprisal_bits=float(_surprisal(conservative, denominator)),
        sensitivity_surprisal_one=float(_surprisal(one, denominator)),
        sensitivity_surprisal_midpoint=float(_surprisal(midpoint, denominator)),
        normalized_for_lookup=rating.matched_after_normalization,
    )


def name_form_flags(given_name: str, surname: str) -> dict[str, bool]:
    full = f"{given_name} {surname}".strip()
    folded = unicodedata.normalize("NFKD", full)
    return {
        "initials": SCORER.looks_like_initials(given_name),
        "has_punctuation": bool(re.search(r"[^\w\s]", full, flags=re.UNICODE)),
        "has_compound_given_name": bool(re.search(r"[\s-]", given_name.strip())),
        "has_diacritic": any(unicodedata.combining(char) for char in folded),
    }


def as_flat_dict(
    feature: GivenNameFeature | GenerationGivenNameFeature | SurnameFeature,
) -> dict[str, object]:
    return asdict(feature)
