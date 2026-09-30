# Source Manifest

| Source | Use | Public URL | Redistribution status |
|---|---|---|---|
| NBA Draft Combine Anthropometric | Cohort and physical measurements | [Combine anthropometrics](https://www.nba.com/stats/draft/combine-anthro); endpoint `https://stats.nba.com/stats/draftcombineplayeranthro` | Official public source linked; raw extracts kept local pending redistribution permission |
| NBA Draft Combine Strength and Agility | Cohort and athletic measurements | [Combine strength and agility](https://www.nba.com/stats/draft/combine-strength-agility); endpoint `https://stats.nba.com/stats/draftcombinedrillresults` | Official public source linked; raw extracts kept local pending redistribution permission |
| NBA Draft History | Draft outcome, round, and pick | [Draft history](https://www.nba.com/stats/draft/history); endpoint `https://stats.nba.com/stats/drafthistory` | Official public source linked; raw extracts kept local pending redistribution permission |
| NBA Common Player Info | Birth year where an NBA person ID resolves | [Player bios](https://www.nba.com/stats/players/bio); endpoint `https://stats.nba.com/stats/commonplayerinfo` | Official public source linked; raw responses kept local pending redistribution permission |
| Wikipedia yearly NBA draft selection tables | Independent check of sampled undrafted outcomes | [Immutable revisions used](UNDRAFTED_AUDIT_SOURCES.md) | CC BY-SA; only factual selection absence is recorded |
| SSA Baby Names | Male birth-cohort given-name frequencies | [Documentation](https://www.ssa.gov/oact/babynames/limits.html); [official archive](https://www.ssa.gov/oact/babynames/names.zip) | U.S. government public data; official source |
| 2010 U.S. Census Surnames | Surname frequencies | [Documentation](https://www.census.gov/topics/population/genealogy/data/2010_surnames.html); [official archive](https://www2.census.gov/topics/genealogy/2010surnames/names.zip) | U.S. government public data; official source |

Every manual identity, birth-year, nickname, or legal-name resolution must record its own source URL in the corresponding tracked override table. Search snippets and unsourced aggregators are not acceptable evidence.

## NBA endpoint parameters

`study/nba_client.py` is the executable source record. For each Combine year
`Y`, it requests the two Combine endpoints with `LeagueID=00` and
`SeasonYear=Y-(Y+1)`, and requests `drafthistory` with `Season=Y`,
`LeagueID=00`, `TeamID=0`, and the remaining filters blank. Player profiles are
requested from `commonplayerinfo` with the public NBA person ID. Requests span
2000–2025; the response shapes and parsing rules are tested.

The repository uses the source-link interpretation for publicly accessible
third-party data: it publishes official source URLs, acquisition and
transformation code, provenance, frozen hashes, and aggregate results. It does
not represent that public accessibility grants a right to mirror NBA files.
See `DATA_AVAILABILITY.md`.
