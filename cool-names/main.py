#!/usr/bin/env python3
"""Rate a given name's U.S. birth-cohort distinctiveness using SSA data.

Examples:
    python3 main.py LeBron --birth-year 1984 --sex M
    python3 main.py --interactive

The script downloads and caches the official SSA national baby-name archive on
first use. SSA excludes sex/name/year cells with fewer than five births, so an
unobserved name is reported as suppressed or outside the reference population,
not as having zero real-world use.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
import unicodedata
import zipfile
from collections import defaultdict
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path


SSA_NAMES_URL = "https://www.ssa.gov/oact/babynames/names.zip"
SSA_MIRROR_COMMIT = "0b1a1316457d55447d1a1f7bfe57ee15e53cc2f0"
SSA_MIRROR_URL = (
    "https://raw.githubusercontent.com/hackerb9/ssa-baby-names/"
    f"{SSA_MIRROR_COMMIT}/alldata.txt"
)
DEFAULT_DATA_PATH = Path(__file__).resolve().parent / "data" / "ssa_names.zip"
CENSUS_SURNAMES_URL = (
    "https://www2.census.gov/topics/genealogy/2010surnames/names.zip"
)
DEFAULT_CENSUS_DATA_PATH = (
    Path(__file__).resolve().parent / "data" / "census_surnames_2010.zip"
)
CENSUS_CSV_NAME = "Names_2010Census.csv"
USER_AGENT = "Mozilla/5.0 name-distinctiveness-research/0.1"


@dataclass(frozen=True)
class Rating:
    name: str
    reference_sex: str
    requested_birth_year: int
    cohort_start: int
    cohort_end: int
    window_years: int
    observed_in_ssa_data: bool
    published_birth_count: int
    reference_birth_count: int
    published_rate_per_million: float
    surprisal_bits: float | None
    birth_weighted_rarity_percentile: float
    distinctiveness_score: float
    interpretation: str
    caveat: str


@dataclass(frozen=True)
class SurnameRating:
    surname: str
    census_lookup_form: str
    matched_after_normalization: bool
    census_year: int
    observed_in_census_data: bool
    published_count: int
    published_rank: int | None
    published_rate_per_million: float
    surprisal_bits: float | None
    distinctiveness_score: float
    interpretation: str
    caveat: str


def download_ssa_data(destination: Path, force: bool = False) -> Path:
    """Download the official SSA national archive and cache it locally."""
    if destination.exists() and not force:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        _download_official_archive(temporary)
    except (OSError, urllib.error.URLError, zipfile.BadZipFile, ValueError):
        temporary.unlink(missing_ok=True)
        try:
            _download_pinned_mirror(temporary)
        except (OSError, urllib.error.URLError, zipfile.BadZipFile, ValueError) as error:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(
                "Could not download SSA data from either the official archive or "
                f"the pinned mirror: {error}"
            ) from error

    try:
        _validate_archive(temporary)
        os.replace(temporary, destination)
    except (OSError, zipfile.BadZipFile, ValueError) as error:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Could not download valid SSA data: {error}") from error

    return destination


def download_census_data(destination: Path, force: bool = False) -> Path:
    """Download and validate the official 2010 Census surname archive."""
    if destination.exists() and not force:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    request = urllib.request.Request(
        CENSUS_SURNAMES_URL, headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            temporary.write_bytes(response.read())
        with zipfile.ZipFile(temporary) as archive:
            if CENSUS_CSV_NAME not in archive.namelist():
                raise ValueError(
                    f"Census archive does not contain {CENSUS_CSV_NAME}."
                )
        os.replace(temporary, destination)
    except (OSError, urllib.error.URLError, zipfile.BadZipFile, ValueError) as error:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Could not download valid Census surname data: {error}") from error
    return destination


def _download_official_archive(destination: Path) -> None:
    request = urllib.request.Request(SSA_NAMES_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        destination.write_bytes(response.read())
    _validate_archive(destination)


def _download_pinned_mirror(destination: Path) -> None:
    """Package a pinned plain-text mirror into the cache archive."""
    request = urllib.request.Request(SSA_MIRROR_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        mirror_data = response.read()
    if not mirror_data.startswith(b"Mary,F,"):
        raise ValueError("Pinned SSA mirror has an unexpected format.")
    provenance = (
        "Authoritative dataset: SSA Baby Names from Social Security Card Applications\n"
        f"Official URL: {SSA_NAMES_URL}\n"
        f"Fallback mirror: {SSA_MIRROR_URL}\n"
        f"Pinned mirror commit: {SSA_MIRROR_COMMIT}\n"
    )
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("alldata.txt", mirror_data)
        archive.writestr("SOURCE.txt", provenance)


def _validate_archive(data_path: Path) -> None:
    with zipfile.ZipFile(data_path) as archive:
        members = archive.namelist()
        has_year_files = any(_year_from_member(name) is not None for name in members)
        has_combined_file = any(Path(name).name == "alldata.txt" for name in members)
        if not (has_year_files or has_combined_file):
            raise ValueError("The archive contains no recognized SSA name files.")


def _year_from_member(member_name: str) -> int | None:
    """Return the year encoded by an SSA archive member such as yob1984.txt."""
    filename = Path(member_name).name
    if not (filename.startswith("yob") and filename.endswith(".txt")):
        return None
    year_text = filename[3:-4]
    return int(year_text) if year_text.isdigit() else None


@lru_cache(maxsize=None)
def available_years(data_path: Path) -> tuple[int, ...]:
    with zipfile.ZipFile(data_path) as archive:
        years = sorted(
            year
            for member in archive.namelist()
            if (year := _year_from_member(member)) is not None
        )
        if not years:
            combined_member = next(
                (
                    member
                    for member in archive.namelist()
                    if Path(member).name == "alldata.txt"
                ),
                None,
            )
            if combined_member is not None:
                with archive.open(combined_member) as raw_file:
                    years = sorted(
                        {
                            int(raw_line.rsplit(b",", 1)[1])
                            for raw_line in raw_file
                            if raw_line.strip()
                        }
                    )
    if not years:
        raise ValueError(f"No yearly SSA files found in {data_path}")
    return tuple(years)


@lru_cache(maxsize=None)
def load_cohort_counts(
    data_path: Path,
    start_year: int,
    end_year: int,
    sex: str,
) -> tuple[dict[str, int], int]:
    """Aggregate published name counts over the selected cohort window."""
    counts: dict[str, int] = defaultdict(int)
    total_births = 0
    wanted_sexes = {"M", "F"} if sex == "ALL" else {sex}

    with zipfile.ZipFile(data_path) as archive:
        members_by_year = {
            year: member
            for member in archive.namelist()
            if (year := _year_from_member(member)) is not None
        }
        if not members_by_year:
            combined_member = next(
                (
                    member
                    for member in archive.namelist()
                    if Path(member).name == "alldata.txt"
                ),
                None,
            )
            if combined_member is None:
                raise ValueError("The archive contains no recognized SSA name files.")
            with archive.open(combined_member) as raw_file:
                for raw_line in raw_file:
                    line = raw_line.decode("utf-8-sig").strip()
                    if not line:
                        continue
                    name, recorded_sex, births_text, year_text = line.split(",")
                    year = int(year_text)
                    if not (start_year <= year <= end_year):
                        continue
                    if recorded_sex not in wanted_sexes:
                        continue
                    births = int(births_text)
                    counts[name.casefold()] += births
                    total_births += births
            if total_births == 0:
                raise ValueError("The selected cohort contains no matching SSA records.")
            return dict(counts), total_births

        for year in range(start_year, end_year + 1):
            member = members_by_year.get(year)
            if member is None:
                continue
            with archive.open(member) as raw_file:
                for raw_line in raw_file:
                    line = raw_line.decode("utf-8-sig").strip()
                    if not line:
                        continue
                    name, recorded_sex, births_text = line.split(",")
                    if recorded_sex not in wanted_sexes:
                        continue
                    births = int(births_text)
                    counts[name.casefold()] += births
                    total_births += births

    if total_births == 0:
        raise ValueError("The selected cohort contains no matching SSA records.")
    return dict(counts), total_births


def rate_name(
    name: str,
    birth_year: int,
    sex: str = "M",
    window: int = 3,
    data_path: Path = DEFAULT_DATA_PATH,
) -> Rating:
    """Calculate a birth-weighted rarity percentile and name surprisal."""
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Name cannot be empty.")
    if looks_like_initials(clean_name):
        raise ValueError(
            "Initials cannot be compared with SSA given names. The research pipeline "
            "keeps the public initials, records an initials indicator, and leaves the "
            "continuous SSA feature missing."
        )
    if any(character.isspace() for character in clean_name):
        raise ValueError("Enter a given name only, not a full name.")
    if window < 0:
        raise ValueError("Window must be zero or greater.")

    sex = sex.upper()
    if sex not in {"M", "F", "ALL"}:
        raise ValueError("Sex must be M, F, or ALL.")

    years = available_years(data_path)
    if birth_year < years[0] or birth_year > years[-1]:
        raise ValueError(
            f"Birth year must be between {years[0]} and {years[-1]} for this archive."
        )

    cohort_start = max(years[0], birth_year - window)
    cohort_end = min(years[-1], birth_year + window)
    counts, total_births = load_cohort_counts(
        data_path, cohort_start, cohort_end, sex
    )

    query_count = counts.get(clean_name.casefold(), 0)
    observed = query_count > 0

    if observed:
        # Birth-weighted midrank: the probability mass assigned to names more
        # common than this one, plus half the mass tied at the same frequency.
        more_common_births = sum(
            count for count in counts.values() if count > query_count
        )
        tied_births = sum(count for count in counts.values() if count == query_count)
        rarity_percentile = (
            100.0 * (more_common_births + 0.5 * tied_births) / total_births
        )
        probability = query_count / total_births
        surprisal = -math.log2(probability)
        rate_per_million = probability * 1_000_000
        score = log_frequency_score(rate_per_million)
    else:
        score = 100.0
        rarity_percentile = 100.0
        surprisal = None
        rate_per_million = 0.0

    interpretation = interpret_score(score, observed)
    caveat = (
        "SSA suppresses sex/name/year cells with fewer than five births. Counts and "
        "rates use published U.S. records only. The score measures U.S.-relative "
        "given-name rarity, not cultural or personal interestingness."
    )

    return Rating(
        name=clean_name,
        reference_sex=sex,
        requested_birth_year=birth_year,
        cohort_start=cohort_start,
        cohort_end=cohort_end,
        window_years=window,
        observed_in_ssa_data=observed,
        published_birth_count=query_count,
        reference_birth_count=total_births,
        published_rate_per_million=round(rate_per_million, 3),
        surprisal_bits=round(surprisal, 3) if surprisal is not None else None,
        birth_weighted_rarity_percentile=round(rarity_percentile, 2),
        distinctiveness_score=round(score, 2),
        interpretation=interpretation,
        caveat=caveat,
    )


@lru_cache(maxsize=None)
def load_census_surnames(data_path: Path) -> dict[str, tuple[int, int, float]]:
    """Load surname -> (count, rank, prevalence per 100,000)."""
    records: dict[str, tuple[int, int, float]] = {}
    with zipfile.ZipFile(data_path) as archive:
        try:
            raw_file = archive.open(CENSUS_CSV_NAME)
        except KeyError as error:
            raise ValueError(
                f"Census archive does not contain {CENSUS_CSV_NAME}."
            ) from error
        with raw_file:
            header = raw_file.readline().decode("utf-8-sig").strip().split(",")
            columns = {name: index for index, name in enumerate(header)}
            required = {"name", "rank", "count", "prop100k"}
            if not required.issubset(columns):
                raise ValueError("Census surname CSV has an unexpected schema.")
            for raw_line in raw_file:
                values = raw_line.decode("utf-8-sig").strip().split(",")
                if len(values) < len(header):
                    continue
                surname = normalize_census_surname(values[columns["name"]])
                records[surname] = (
                    int(values[columns["count"]]),
                    int(values[columns["rank"]]),
                    float(values[columns["prop100k"]]),
                )
    if not records:
        raise ValueError("Census surname file contains no records.")
    return records


def rate_surname(
    surname: str,
    data_path: Path = DEFAULT_CENSUS_DATA_PATH,
) -> SurnameRating:
    """Rate surname rarity in the 2010 U.S. Census surname tabulation."""
    clean_surname = surname.strip()
    if not clean_surname:
        raise ValueError("Surname cannot be empty.")

    records = load_census_surnames(data_path)
    lookup_form = normalize_census_surname(clean_surname)
    if not lookup_form:
        raise ValueError("Surname contains no characters usable by the Census lookup.")
    record = records.get(lookup_form)
    if record is None:
        observed = False
        count = 0
        rank = None
        rate_per_million = 0.0
        surprisal = None
        score = 100.0
    else:
        observed = True
        count, rank, prevalence_per_100k = record
        rate_per_million = prevalence_per_100k * 10
        probability = prevalence_per_100k / 100_000
        surprisal = -math.log2(probability)
        score = log_frequency_score(rate_per_million)

    caveat = (
        "The 2010 Census publishes only surnames occurring at least 100 times. "
        "This is a U.S. population cross-section, not a birth-cohort measure. An "
        "unobserved surname is censored or unmatched, not known to have zero users."
    )
    return SurnameRating(
        surname=clean_surname,
        census_lookup_form=lookup_form.upper(),
        matched_after_normalization=(
            observed and clean_surname.casefold() != lookup_form
        ),
        census_year=2010,
        observed_in_census_data=observed,
        published_count=count,
        published_rank=rank,
        published_rate_per_million=round(rate_per_million, 3),
        surprisal_bits=round(surprisal, 3) if surprisal is not None else None,
        distinctiveness_score=round(score, 2),
        interpretation=interpret_score(score, observed),
        caveat=caveat,
    )


def normalize_census_surname(surname: str) -> str:
    """Approximate the Census file's punctuation-free uppercase representation."""
    decomposed = unicodedata.normalize("NFKD", surname).casefold()
    return "".join(
        character
        for character in decomposed
        if character.isalnum() and not unicodedata.combining(character)
    )


def looks_like_initials(name: str) -> bool:
    """Identify explicit forms such as T.J., T. J., or T J."""
    letter_groups = re.findall(r"[^\W\d_]+", name, flags=re.UNICODE)
    if len(letter_groups) >= 2 and all(len(group) == 1 for group in letter_groups):
        return True
    return bool("." in name and letter_groups and all(len(group) == 1 for group in letter_groups))


def log_frequency_score(rate_per_million: float) -> float:
    """Map exact-name frequency to an interpretable 0-100 log scale.

    Anchors:
        10,000 per million (1 in 100)      -> 0
         1,000 per million (1 in 1,000)    -> 25
           100 per million (1 in 10,000)   -> 50
            10 per million (1 in 100,000)  -> 75
             1 per million                 -> 100
    """
    if rate_per_million <= 0:
        return 100.0
    return min(100.0, max(0.0, 25.0 * (4.0 - math.log10(rate_per_million))))


def interpret_score(score: float, observed: bool) -> str:
    if not observed:
        return "Extremely distinctive in the published SSA reference data"
    if score >= 90:
        return "Extremely distinctive"
    if score >= 75:
        return "Highly distinctive"
    if score >= 50:
        return "Distinctive"
    if score >= 25:
        return "Moderately distinctive"
    if score >= 10:
        return "Common"
    return "Very common"


def display_rating(rating: Rating) -> None:
    print(f"Name: {rating.name}")
    print(
        "Reference cohort: "
        f"{rating.cohort_start}-{rating.cohort_end}, sex={rating.reference_sex}"
    )
    print(f"Distinctiveness score: {rating.distinctiveness_score:.2f}/100")
    print(f"Interpretation: {rating.interpretation}")
    print(f"Published births with name: {rating.published_birth_count:,}")
    print(f"Published reference births: {rating.reference_birth_count:,}")
    print(f"Published rate: {rating.published_rate_per_million:,.3f} per million")
    print(
        "Birth-weighted rarity percentile: "
        f"{rating.birth_weighted_rarity_percentile:.2f}"
    )
    if rating.surprisal_bits is None:
        print("Surprisal: unavailable because the name is not in published cells")
    else:
        print(f"Surprisal: {rating.surprisal_bits:.3f} bits")
    print(f"Caveat: {rating.caveat}")


def display_surname_rating(rating: SurnameRating) -> None:
    print("\nSurname measure")
    print(f"Surname: {rating.surname}")
    print(f"Census lookup form: {rating.census_lookup_form}")
    print(f"Matched after normalization: {rating.matched_after_normalization}")
    print(f"Reference: {rating.census_year} U.S. Census")
    print(f"Distinctiveness score: {rating.distinctiveness_score:.2f}/100")
    print(f"Interpretation: {rating.interpretation}")
    print(f"Published count: {rating.published_count:,}")
    print(
        "Published rank: "
        f"{rating.published_rank:,}" if rating.published_rank is not None else "Published rank: unavailable"
    )
    print(f"Published rate: {rating.published_rate_per_million:,.3f} per million")
    if rating.surprisal_bits is None:
        print("Surprisal: unavailable because the surname is not published")
    else:
        print(f"Surprisal: {rating.surprisal_bits:.3f} bits")
    print(f"Caveat: {rating.caveat}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rate U.S.-relative given-name distinctiveness from official SSA data."
    )
    parser.add_argument("name", nargs="?", help="Given name to rate")
    parser.add_argument("--surname", help="Optional surname to rate separately")
    parser.add_argument("--birth-year", type=int, help="Person's birth year")
    parser.add_argument(
        "--sex",
        choices=("M", "F", "ALL", "m", "f", "all"),
        default="M",
        help="SSA reference category (default: M)",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=3,
        help="Years on either side of the birth year (default: 3)",
    )
    parser.add_argument(
        "--data-file",
        type=Path,
        default=DEFAULT_DATA_PATH,
        help=f"Cached SSA names.zip path (default: {DEFAULT_DATA_PATH})",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Redownload the official SSA archive before rating",
    )
    parser.add_argument(
        "--census-data-file",
        type=Path,
        default=DEFAULT_CENSUS_DATA_PATH,
        help=f"Cached Census surname ZIP path (default: {DEFAULT_CENSUS_DATA_PATH})",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for a name and birth year",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.interactive or args.name is None:
        args.name = input("Given name: ").strip()
    if args.interactive or args.birth_year is None:
        try:
            args.birth_year = int(input("Birth year: ").strip())
        except ValueError:
            print("Error: birth year must be an integer.", file=sys.stderr)
            return 2
    if args.interactive and args.surname is None:
        args.surname = input("Surname (optional): ").strip() or None

    try:
        download_ssa_data(args.data_file, force=args.refresh)
        rating = rate_name(
            name=args.name,
            birth_year=args.birth_year,
            sex=args.sex,
            window=args.window,
            data_path=args.data_file,
        )
        surname_rating = None
        if args.surname:
            download_census_data(args.census_data_file, force=args.refresh)
            surname_rating = rate_surname(args.surname, data_path=args.census_data_file)
    except (RuntimeError, ValueError, zipfile.BadZipFile) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if args.json:
        output = {"given_name": asdict(rating)}
        if surname_rating is not None:
            output["surname"] = asdict(surname_rating)
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        display_rating(rating)
        if surname_rating is not None:
            display_surname_rating(surname_rating)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
