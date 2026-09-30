# Memorable, Not Predictive: Do Distinctive Names Matter in the NBA Draft?

## Introduction

Memorable professional athletes often appear to have distinctive names, but
this impression may reflect salience after success rather than information
available before selection. We test whether public-name distinctiveness is
associated with NBA draft selection and whether it improves out-of-sample
prediction beyond conventional Draft Combine measurements.

## Methods

We assembled 1,795 player–Combine-year observations from the official NBA
Draft Combine and draft-history records for 2000–2025. Given names were scored
by surprisal relative to male U.S. Social Security records from the plausible
birth-generation window for each Combine class (Combine year minus 24 through
minus 18); surnames were scored against the 2010 U.S. Census surname file.
Disclosure-threshold uncertainty was handled conservatively, and initial forms
retained missing continuous scores plus an indicator. We froze the protocol and
models before outcome analysis. Penalized logistic models were trained on
2000–2017, tuned on 2018–2021, and evaluated once on a locked 2022–2025 test
set. We compared a conventional anthropometric-and-athletic baseline with
name-only and baseline-plus-name models. A full-cohort logistic association
model used player-clustered standard errors and Holm correction across the two
name exposures. Uncertainty in predictive differences used 2,000 paired
player-within-year bootstrap samples.

## Results

Adding names changed locked-period log loss from 0.63449 to 0.63368, a
difference of −0.00081 (95% bootstrap interval, −0.00328 to 0.00161). Changes
in Brier score, ROC AUC, and average precision also favored names slightly in
point estimates, but every interval included zero. The adjusted odds ratio per
one-bit increase was 0.996 for given-name surprisal (95% CI, 0.963–1.030;
Holm-adjusted p=0.803) and 0.966 for surname surprisal (95% CI, 0.935–0.999;
adjusted p=0.082). Neither met the prespecified corrected threshold. Results
were similar across suppression assumptions and repeated-player exclusions.
Verified birth years covered 94.5% of drafted but only 45.2% of undrafted
participants; the selected exact-birth-year sensitivity reversed the small
predictive point estimate.

## Conclusion

Public-name distinctiveness added no reliable or practically meaningful draft
information beyond available Combine measurements. Teams should not use name
rarity in prospect evaluation. More broadly, the study shows how a memorable
sports hypothesis can survive intuition yet fail temporal validation, and how
outcome-related data availability can make individually precise measures less
credible than a common cohort reference.
