# Results

## Cohort and measurement coverage

The final cohort contained 1,795 player–Combine-year observations from 2000
through 2025. Of these, 1,067 (59.4%) were selected in the same year's NBA
draft and 728 were not. Annual cohort size ranged from 45 to 83, while the
annual draft rate ranged from 36.9% in 2000 to 87.0% in 2009 (Table 1).

Generation-window given-name surprisal was available for 1,774 observations
(98.8%); all 21 missing values were explicit initial forms. Surname surprisal
was available for 1,794 observations (99.9%). Conventional measurement
missingness varied substantially: modified lane agility time was missing for
63.3% of observations, hand length and width for 44.2%, and bench press for
39.0%. Height without shoes and wingspan were each missing for 3.2%. The
prespecified median-imputation and missing-indicator procedure retained all
1,795 observations in the primary models (Table 2).

The unadjusted name-surprisal distributions overlapped strongly by draft
status. Median given-name surprisal was 11.86 bits (interquartile range [IQR],
8.94–15.96) among undrafted participants and 11.59 bits (IQR, 9.11–15.26)
among drafted participants. Median surname surprisal was 13.55 bits (IQR,
10.71–18.49) among undrafted participants and 13.18 bits (IQR, 10.40–17.40)
among drafted participants.

## Locked temporal prediction

All three penalized logistic models selected `C = 0.001` using the 2018–2021
validation period. After refitting on 2000–2021, the conventional baseline had
a log loss of 0.63449 in the locked 2022–2025 test period. Adding the complete
name block reduced log loss to 0.63368, a difference of −0.00081 (paired
bootstrap 95% interval, −0.00328 to 0.00161). The interval included zero.

The baseline-plus-name model also had a slightly lower Brier score than the
baseline (difference, −0.00036; 95% interval, −0.00151 to 0.00076), a higher
ROC AUC (difference, 0.01033; 95% interval, −0.01124 to 0.03190), and higher
average precision (difference, 0.00903; 95% interval, −0.00738 to 0.02609).
Every interval included zero, and all 2,000 bootstrap replicates were retained.
The name-only model had log loss 0.64197, ROC AUC 0.55357, and average precision
0.68825, performing worse than either model containing conventional Combine
measurements (Tables 3 and 4).

Calibration was imperfect in both principal prediction models. The baseline
calibration intercept and slope were −0.565 and 2.146, respectively; the
baseline-plus-name values were −0.566 and 2.198. Adding name information did
not materially correct this pattern.

## Adjusted association analysis

The full-cohort association model converged without requiring the prespecified
Firth fallback. It included 1,734 player clusters and all frozen adjustment
variables. Three generated missingness columns that were exact linear aliases
of other frozen indicators were dropped and recorded.

For given-name surprisal, the adjusted odds ratio for draft selection was 0.996
per one-bit increase (95% confidence interval [CI], 0.963–1.030; unadjusted and
Holm-adjusted *p* = 0.803). For surname surprisal, the adjusted odds ratio was
0.966 per bit (95% CI, 0.935–0.999; unadjusted *p* = 0.041). After the
prespecified Holm correction across the two co-primary tests, the surname
result did not meet the 0.05 threshold (adjusted *p* = 0.082). Thus, neither
co-primary association was statistically distinguishable from no association
under the frozen multiplicity rule (Table 5 and Figure 1).

## Sensitivity analyses

Results were stable across the SSA suppression assumptions, Census surname
counts, exclusion of initial forms, exclusion of the 2020 Combine, and use of
only each player's final Combine appearance. Across these seven complete- or
near-complete-cohort variants, the test log-loss difference ranged from
−0.00101 to −0.00017, remaining small and in the same direction as the primary
point estimate. Given-name adjusted odds ratios remained between 0.994 and
0.996 per bit. None of the co-primary tests met its Holm-adjusted threshold.

The exact-birth-year sensitivity differed. Verified birth years were available
for 1,337 participants (74.5%), but coverage was 94.5% among drafted players
and only 45.2% among undrafted players (Figure 2). Within this selected subset,
adding the name block worsened test log loss by 0.00367. Exact-birth-year
given-name surprisal had an adjusted odds ratio of 0.986 per bit (95% CI,
0.942–1.033; Holm-adjusted *p* = 1.000). The surname estimate also changed
direction (odds ratio, 1.015; 95% CI, 0.972–1.059; Holm-adjusted *p* = 1.000).
These results show why exact-birth-year availability could not support an
unselected primary analysis (Table 6).

## Linked outputs

- [Aggregate tables](../study/report/TABLES.md)
- [Association forest plot](../study/report/figures/figure_1_association_forest.svg)
- [Birth-year coverage figure](../study/report/figures/figure_2_birth_year_coverage.svg)

