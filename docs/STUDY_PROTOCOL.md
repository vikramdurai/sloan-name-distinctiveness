# Frozen Study Protocol

**Frozen:** 2026-09-29. **Amended:** 2026-09-30, before fitting any draft-outcome model.

**Modeling specification frozen:** 2026-09-30, before fitting or inspecting any name–draft outcome model. The exact predictors, preprocessing, estimands, temporal split, metrics, uncertainty procedure, and sensitivity analyses are in `MODELING_SPEC.md`; `study/modeling_spec.json` is the machine-readable contract.

## Protocol amendment: generation reference window (2026-09-30)

Verified birth dates were available for 1,337 of 1,795 participants and were much less complete among undrafted players. Before fitting or inspecting any name–draft outcome model, the primary given-name reference was therefore changed from an exact-birth-year window to the same fixed plausible birth-generation window for every member of a Combine class. This change was prompted by differential source coverage, not by observed name–draft associations. Individual birth dates are not imputed.

The primary window is Combine year minus 24 through Combine year minus 18, inclusive. It represents ages 18–24, which cover more than 99% of participants with resolved birth dates. The age limits are fixed in advance and will not be tuned against draft results. Exact-birth-year ±3 scoring is retained as a sensitivity analysis for participants with verified dates, including those whose observed age falls outside 18–24.

## Research question

> Among NBA Draft Combine participants from 2000–2025, is a player's public-name distinctiveness associated with selection in that year's NBA draft, and does it improve out-of-sample prediction beyond conventional anthropometric and athletic measurements?

This is an observational association and prediction study within an already elite prospect pool. It does not test whether a distinctive name causes selection, and it does not generalize to all basketball players.

The unit of analysis is one player–Combine-year. The primary outcome is selection in that year's NBA draft. A participant is a player appearing in either the official NBA anthropometric table or the official strength-and-agility table for that year.

## Frozen name construct

The exposure is the public name shown in the official Combine data. This intentionally measures distinctiveness relative to U.S. name records, including for international players; it is not a claim that a name is unusual in its culture of origin.

### Given name

- Use the official `FIRST_NAME` field without replacing nicknames with legal names.
- Compare it with male SSA records from Combine year minus 24 through Combine year minus 18 (seven years inclusive).
- The model variable is surprisal, `-log2(rate)`. The 0–100 score is presentation-only.
- For each cohort year without a published cell, add four births, the conservative SSA suppression upper bound. This creates a lower bound on distinctiveness.
- Retain `ssa_unobserved_years` and `ssa_ever_observed` indicators.
- Sensitivity analyses replace four with zero and 2.5 births per unpublished year.
- Initial forms receive no continuous SSA value and retain an `initials` indicator.
- The primary model field is `given_generation_surprisal`. The verified-date sensitivity field is `given_exact_birth_surprisal`, calculated over birth year ±3 with the same censoring rules.

### Surname

- Use the official `LAST_NAME` field.
- Compare it with the 2010 U.S. Census surname table.
- Census-required punctuation and diacritic normalization is recorded separately.
- For an unpublished surname, assign 99 occurrences, the conservative publication upper bound, and retain a `census_unobserved` indicator.
- Sensitivity analyses use one and 50 occurrences.

Given-name and surname surprisal remain separate predictors. There is no primary composite, phonetic adjustment, or orthographic-neighborhood adjustment. Verified nicknames, initials, punctuation, compound forms, and lookup normalization are flags rather than outcome-informed corrections. Legal or birth names may be used only in a labeled sensitivity analysis.

## Cohort and outcome construction

For each year from 2000 through 2025, preserve the raw official responses for:

- `draftcombineplayeranthro`
- `draftcombinedrillresults`
- `drafthistory`

Form the cohort from the union of the first two tables. Join draft outcomes by NBA person ID, then by a frozen manual crosswalk, and finally by an exact unique normalized name within year. Every non-ID match must be auditable. A player not found in that year's complete draft history is coded undrafted.

Birth year is resolved in this order: official NBA player profile, explicitly sourced manual/open-data override, then unresolved. Birth year is never estimated from draft year or apparent age. Unresolved birth years remain in the primary cohort because primary generation-window scoring does not require them. Verified birth-year coverage, including its drafted/undrafted gap, is reported as a limitation of the exact-birth-year sensitivity analysis.

Missing measurements remain missing and receive indicators during modeling. They are not coded as poor performance. Raw NBA data must not be published until reuse permission is resolved.

## Analysis-readiness gates

- At least 15 usable Combine years.
- All within-year identity collisions resolved.
- Every drafted match verified by ID, frozen crosswalk, or unique exact name.
- Generation-window feature coverage reported for the complete cohort, with every missing continuous value attributable to an initial or a malformed/missing source given name.
- All Combine years from 2000 through 2025 scored before outcome modeling.
- Exact-birth-year feature coverage and generation-versus-exact agreement reported overall and separately for drafted and undrafted players.
- The deterministic 50-player undrafted sample drawn by hashing the player–Combine-year key, with Combine identity checked against the official records and undrafted status checked against an independently published complete same-year draft list. Immutable source revisions and the review date are retained.
- Year-by-year counts, outcome rates, name coverage, and measurement missingness reported before modeling.
- Crosswalks and scoring rules frozen before any outcome model is fitted.

The acquisition and audit implementation is in `study/build_cohort.py`.

Outcome models must not be fitted until the frozen machine-readable modeling contract validates against the derived cohort schema.

## Final analysis execution record (2026-09-30)

After all readiness gates passed, the modeling specification was frozen, and
training/validation choices were complete, the 2022–2025 locked test period was
consumed once at 16:15:27 UTC. The primary analysis, 2,000-replicate paired
bootstrap, association model, and all prespecified sensitivity analyses
completed successfully. No post-result change was made to the cohort,
specification, model implementation, or tuning choices.

The immutable artifact hashes and execution environment are recorded in
`FINAL_RESULTS_MANIFEST.md`. Any future correction must be dated, explain the
error and its consequences, and retain the original locked result.
