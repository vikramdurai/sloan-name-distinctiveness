# Study cohort pipeline

This directory implements the frozen protocol in `STUDY_PROTOCOL.md`. It uses only the Python standard library.

## Build

Fetch and cache the 2000–2025 official NBA responses, then construct the cohort:

```bash
python3 study/build_cohort.py --fetch-profiles
```

Raw endpoint responses are cached under `study/data/raw/nba/`. Row-level outputs and audits are written under `study/output/`. Both locations are ignored because NBA redistribution permission remains unresolved.

For reproducible reruns without network access:

```bash
python3 study/build_cohort.py --offline --fetch-profiles
```

`--fetch-profiles` also applies when offline: it reads the cached official player profiles so the exact-birth-year sensitivity columns are reproduced without network access.

The command returns exit status `0` only when every frozen quality gate passes, including complete 2000–2025 generation-window scoring; `3` means it built successfully but is not analysis-ready, and `1` means acquisition or validation failed.

The NBA Stats service sometimes times out or blocks automated clients. Requests use browser-like NBA headers, bounded retries, local caching, and a configurable delay. A failed year aborts the build rather than producing a silently incomplete cohort. Example diagnostic run:

```bash
python3 study/build_cohort.py --start-year 2019 --end-year 2019 --timeout 10 --retries 1
```

## Manual resolution

The first run creates `unresolved_birth_years.csv` and a deterministic 50-player `undrafted_review_sample.csv` in the output directory.

Add sourced birth-year resolutions to `data/birth_year_overrides.csv` for the exact-birth-year sensitivity analysis; do not impute unresolved dates. Add only manually verified draft identity exceptions to `data/identity_crosswalk.csv`. Record verified nicknames, initials, and legal-name sensitivity forms in `data/name_form_overrides.csv`. The persistent 50-player audit is in `data/undrafted_review.csv`; the builder validates its targets, result, separate source URLs, and review date before copying it into the generated output. Rerun the builder; do not edit the derived cohort directly.

The audit reports year-level participation, outcomes, generation and exact-birth feature coverage, birth-year limitations, generation-versus-exact score agreement overall and by draft status, measurement missingness, match methods, undrafted-review completion, and every analysis-readiness gate.

## Frozen modeling pipeline

The human-readable contract is in `MODELING_SPEC.md` and its checksummed
machine contract is `modeling_spec.json`. First run the outcome-safe preflight
and training/validation penalty selection:

```bash
python3 -m study.run_models
```

This writes `study/model_output/preflight.json` and
`study/model_output/validation_tuning.json`. It does not calculate predictions
or outcome summaries for the locked 2022–2025 test period. The validation
artifact contains independently selected penalties for the three primary models
and every prespecified sensitivity analysis. After reviewing that artifact and
confirming that the implementation is final, consume the test set once with:

```bash
python3 -m study.run_models --run-final
```

The final command verifies that the cohort and specification hashes have not
changed, checks that the implementation hashes and numerical-library versions
still match the tuning run, refuses to run without a completed validation
artifact, and refuses to overwrite an existing `final_results.json`. It then
performs the locked test, paired bootstrap, and full-cohort association analysis
specified in the frozen protocol, followed by all prespecified sensitivities.
Immediately before reading test outcomes it exclusively creates
`final_run_started.json`; if the process subsequently fails, it will refuse a
silent rerun and require a documented recovery decision. The modeling code
requires NumPy, pandas, SciPy, and scikit-learn.
