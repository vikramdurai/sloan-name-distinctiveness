# Frozen Modeling Specification

**Frozen:** 2026-09-30, after cohort construction and before fitting or inspecting any name–draft outcome model.

Changes after this date require a dated amendment stating the reason, whether any outcome-model result had been inspected, and which analyses are affected. The machine-readable companion is `study/modeling_spec.json`.

## Objective and analysis population

The unit is one player–Combine-year from the complete 2000–2025 cohort. The binary outcome is `drafted`, meaning selected in that same year's NBA draft. The analysis is associational and predictive, not causal.

All 1,795 rows remain in the primary analysis. Repeated participants remain separate player–year observations. Initial-based given names retain a missing continuous given-name value and an `initials` indicator.

## Frozen predictors

### Name block

- `given_generation_surprisal` (primary given-name exposure)
- `surname_conservative_surprisal_bits` (co-primary surname exposure)
- `initials`
- `given_generation_ssa_ever_observed`
- `surname_observed`

The two surprisal measures are separate continuous predictors; no composite is permitted. The censoring and initials indicators are nuisance terms. Presentation scores, legal names, exact-birth-year scores, punctuation, diacritics, nickname flags, and orthographic adjustments are excluded from the primary models.

### Conventional prediction baseline

- Numeric year trend: `combine_year`
- Categorical position exactly as reported in `POSITION`, including hybrid categories
- Anthropometrics: `HEIGHT_WO_SHOES`, `HEIGHT_W_SHOES`, `WEIGHT`, `WINGSPAN`, `STANDING_REACH`, `BODY_FAT_PCT`, `HAND_LENGTH`, `HAND_WIDTH`
- Athletic tests: `STANDING_VERTICAL_LEAP`, `MAX_VERTICAL_LEAP`, `LANE_AGILITY_TIME`, `MODIFIED_LANE_AGILITY_TIME`, `THREE_QUARTER_SPRINT`, `BENCH_PRESS`

Age, nationality, pathway, production, recruiting rank, and mock-draft rank are excluded because they are not available with consistent complete-cohort coverage. They cannot be added to the primary model after results are seen.

### Conventional association adjustment set

To reduce collinearity in the interpretable association model, use `POSITION`, Combine-year fixed effects, `HEIGHT_WO_SHOES`, `WEIGHT`, `WINGSPAN`, `STANDING_REACH`, `MAX_VERTICAL_LEAP`, `LANE_AGILITY_TIME`, `THREE_QUARTER_SPRINT`, and `BENCH_PRESS`. This adjustment set and the name block are entered simultaneously.

## Preprocessing

All preprocessing is outcome-blind.

- Coerce numeric fields strictly; nonnumeric values become missing and are reported.
- Median-impute every continuous predictor and add a missingness indicator whenever the field has any missing values in the applicable fitting data.
- For `given_generation_surprisal`, initials therefore receive the fitting-data median plus `initials = 1`; they are not assigned a rarity value.
- Standardize continuous predictors to mean zero and unit variance using fitting-data values after imputation. Zero-variance columns are dropped and reported.
- One-hot encode `POSITION`, treating missing as an explicit category. Unknown future categories map to all-zero indicator columns.
- Fit every imputation, scaling, and encoding operation on training data only for prediction. The association model uses the full cohort because it is not evaluated as a forecasting model.

## Descriptive analysis

Before model coefficients are reported, publish year-level cohort size, draft rate, predictor coverage, and measurement missingness. Report given- and surname-surprisal distributions by draft status using medians, interquartile ranges, and fixed cohort-wide quintiles. These summaries are descriptive and not causal tests.

## Association analysis

Fit one unpenalized logistic regression on the full cohort with the conventional association adjustment set and complete name block. Use player-clustered sandwich standard errors, where the cluster is NBA player ID and every non-ID row is its own cluster. Combine-year fixed effects address common year-specific shifts.

The co-primary estimands are adjusted odds ratios per one-bit increase in:

1. `given_generation_surprisal`
2. `surname_conservative_surprisal_bits`

Report coefficients, odds ratios, 95% confidence intervals, and two-sided p-values. Control the family-wise error rate across the two co-primary tests with Holm's procedure at `alpha = 0.05`. Report unadjusted p-values as well. Do not select covariates, interactions, transformations, or subgroups from observed p-values.

If the model fails because of separation or rank deficiency, use Firth logistic regression with the same formula and profile-likelihood confidence intervals; label this as the prespecified fallback.

## Prediction analysis

### Locked temporal split

- Training: Combine years 2000–2017
- Validation: 2018–2021
- Final test: 2022–2025

The test period remains untouched until preprocessing choices, software checks, and hyperparameters are finalized from training and validation data. After choosing the penalty, refit on 2000–2021 and evaluate once on 2022–2025.

### Models

Fit L2-penalized logistic regression with an unpenalized intercept:

1. `baseline`: conventional prediction baseline only
2. `name_only`: numeric year trend plus the name block
3. `baseline_plus_name`: conventional prediction baseline plus the name block

For each model independently, select inverse regularization strength `C` from `[0.0001, 0.001, 0.01, 0.1, 1, 10, 100, 1000, 10000]` by lowest validation log loss. Ties within `1e-12` select the smaller `C` (stronger regularization). No interaction terms, nonlinear splines, feature selection, class weighting, resampling, or post-hoc probability calibration are permitted in the primary analysis.

### Metrics and comparison

The primary predictive estimand is:

```text
test log loss(baseline_plus_name) - test log loss(baseline)
```

A negative value favors adding the name block. Secondary test metrics are Brier score, ROC AUC, average precision (stepwise area under the precision–recall curve), calibration intercept, and calibration slope. Estimate calibration intercept and slope jointly from `logit(drafted) = a + b * logit(predicted probability)`, clipping probabilities to `[1e-6, 1 - 1e-6]`. Also report the name-only model without treating it as the main comparison.

Use 2,000 paired bootstrap replicates, sampled by player identity within test year, with seed `20260930`, to obtain percentile 95% confidence intervals for metric differences. If a replicate makes a metric undefined, omit it for that metric and report the retained replicate count. Do not convert predictive metric comparisons into causal claims.

## Prespecified sensitivity analyses

1. Replace generation surprisal with `given_exact_birth_surprisal` among players with verified birth years; report coverage overall and by draft status.
2. Repeat given-name models with SSA suppression assumptions of zero and 2.5 births per unpublished year. Under zero suppression, median-impute undefined all-zero continuous scores and retain the SSA-observed indicator.
3. Repeat surname models with unpublished-surname counts of one and 50.
4. Exclude explicit initial forms rather than imputing their continuous given-name value.
5. Retain only each player's final Combine appearance to assess dependence from repeated participants.
6. Exclude the 2020 Combine year.

Sensitivities do not replace the primary analysis and are not used to tune the primary specification.

## Reporting and stopping rules

- Report all three prediction models and both co-primary association estimates regardless of direction or significance.
- Report missingness indicators and dropped zero-variance columns.
- Report the locked test result once; corrections for implementation errors must be versioned and explained.
- Do not interpret a null result as proof of no association.
- Do not publish raw NBA row-level data until reuse permission is resolved.
