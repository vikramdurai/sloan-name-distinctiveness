# Data Availability

## Public source links

The analysis was constructed from the following publicly accessible official
sources:

- [NBA Draft Combine anthropometric measurements](https://www.nba.com/stats/draft/combine-anthro)
- [NBA Draft Combine strength and agility results](https://www.nba.com/stats/draft/combine-strength-agility)
- [NBA draft history](https://www.nba.com/stats/draft/history)
- [NBA player biographies](https://www.nba.com/stats/players/bio)
- [Social Security Administration baby-name documentation](https://www.ssa.gov/oact/babynames/limits.html)
- [SSA national baby-name archive](https://www.ssa.gov/oact/babynames/names.zip)
- [2010 Census surname documentation](https://www.census.gov/topics/population/genealogy/data/2010_surnames.html)
- [2010 Census surname archive](https://www2.census.gov/topics/genealogy/2010surnames/names.zip)

The exact NBA endpoint names, query construction, headers, caching behavior,
and response parsing are implemented in `study/nba_client.py`. The complete
2000–2025 build is implemented in `study/build_cohort.py`; name-reference
downloads and scoring are implemented in `cool-names/main.py` and
`study/name_features.py`.

## Repository contents

This repository provides:

- Official source links and executable acquisition code;
- Cohort-construction and identity-resolution logic;
- Frozen source, cohort, specification, implementation, and result hashes;
- The complete modeling and aggregate-reporting code;
- Automated tests;
- Locked aggregate model results, tables, and figures; and
- A permanent record of all prespecified sensitivity analyses.

## Temporary redistribution limitation

The NBA source pages were publicly accessible when acquired, but public access
does not by itself establish a right to mirror third-party files. Cached NBA
responses and the derived player-level NBA cohort are therefore excluded while
the authors seek written redistribution permission from the NBA. NBA.com is
prominently credited as the source of all Combine measurements, draft outcomes,
and player-profile fields.

If permission is granted, the authorized source or derived files will be added
with the required attribution and license terms. If permission is limited, this
statement will be updated to identify exactly which files and fields may be
released. No restricted file will be added retroactively without preserving the
already frozen result and its hashes.

Under the publicly-available-source interpretation of open-source replication,
the official links and acquisition code above allow an independent researcher
to retrieve the same source categories, subject to the source websites' current
terms, availability, and access controls. The frozen hashes permit comparison
with the files used for the reported analysis.
