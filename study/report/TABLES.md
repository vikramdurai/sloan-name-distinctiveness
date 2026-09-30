# Locked Aggregate Results

All values below are generated from the immutable locked result. Negative log-loss and Brier-score differences favor adding name features.

## Primary prediction

| Metric | Difference | Bootstrap 95% CI |
|---|---:|---:|
| Log Loss | -0.0008 | [-0.003, 0.002] |
| Brier Score | -0.0004 | [-0.002, 0.001] |
| Roc Auc | 0.0103 | [-0.011, 0.032] |
| Average Precision | 0.0090 | [-0.007, 0.026] |

## Adjusted associations

| Exposure | OR per bit | 95% CI | Unadjusted p | Holm-adjusted p |
|---|---:|---:|---:|---:|
| given_generation_surprisal | 0.996 | [0.963, 1.030] | 0.803 | 0.803 |
| surname_conservative_surprisal_bits | 0.966 | [0.935, 0.999] | 0.041 | 0.082 |

See the CSV files for full-precision values and all sensitivity analyses.
