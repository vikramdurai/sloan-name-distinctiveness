# Post-Analysis Audit Report

**Audit date:** 2026-09-30

## Scope

This audit was performed after the one-time locked analysis. It did not refit a
model, regenerate a prediction, change an analysis choice, or inspect
player-level results. It independently checks frozen file hashes, result
structure, arithmetic identities, multiplicity decisions, sensitivity
completeness, report-generation safety, and the repository test suite.

This is an internal code and artifact audit, not a substitute for review by an
independent human researcher.

## Findings

- All seven frozen cohort, specification, implementation, tuning, marker, and
  final-result hashes match `FINAL_RESULTS_MANIFEST.md`.
- The final artifact reports all three frozen prediction models, both
  co-primary association estimates, and all eight machine-contract sensitivity
  variants.
- All primary and sensitivity metric differences recompute exactly from their
  stored component metrics.
- Reported odds ratios equal the exponentiated per-bit coefficients, confidence
  intervals are ordered around their point estimates, and Holm decisions match
  the frozen alpha threshold.
- All 2,000 paired bootstrap replicates were retained for every primary metric.
- The aggregate reporting directory contains six tables and four figure files.
  No aggregate CSV contains player identifiers, names, birth years, or draft
  identity fields.
- The full repository test suite passes.

## Methodological review

The implementation matches the frozen temporal split, predictor blocks,
training-only prediction preprocessing, independent validation tuning,
one-bit association estimands, clustered association covariance, paired
player-within-year bootstrap, multiplicity correction, and prespecified
sensitivity definitions. Exact linear aliases among nuisance missingness fields
were removed and disclosed without removing either co-primary exposure.

No issue requiring a correction or second locked analysis was identified.

## Residual review needs

Before public submission, a researcher who did not write the implementation
should review the code, protocol, and interpretation. Data-sharing counsel or
the NBA data provider should resolve whether row-level official data may be
redistributed. Until then, only code, documentation, and aggregate results
should be released.
