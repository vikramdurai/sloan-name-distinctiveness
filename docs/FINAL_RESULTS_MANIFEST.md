# Final Results Manifest

**Locked test consumed:** 2026-09-30 at 16:15:27 UTC, after the frozen
modeling specification and development-period tuning were complete.

The final analysis used the prespecified 2000–2017 training period, 2018–2021
validation period, and 2022–2025 locked test period. The result is immutable.
Corrections, if ever required, must preserve this artifact and be documented as
a dated correction rather than silently replacing it.

## Frozen artifact hashes

| Artifact | SHA-256 |
|---|---|
| `study/output/combine_cohort.csv` | `c89fea37b806994ac521accfe1ebe5ebff6d5edd01b0c96edf9b0dbc66e9347f` |
| `study/modeling_spec.json` | `47901ebddcb8978d842748a94961410238cb0332689713737d491492d0cef9c1` |
| `study/modeling.py` | `7931543346517feb352cd509a85425f5628d9701433d28f5418ada6d7135c663` |
| `study/run_models.py` | `77cc077478a78955587c1502fb2058682a2d3076767ffa4763f9e59d5a5ee109` |
| `study/model_output/validation_tuning.json` | `00c63c1a61bff9f2df0d2d4cbc75724d0f480b7ca19179d955449904a47dc4ce` |
| `study/model_output/final_run_started.json` | `ffe1276d72b4e49dcda731b482a6c6870e6c1d242ca4d934b6d731ac7f697cf7` |
| `study/model_output/final_results.json` | `51adcee1f2d1944ac893ef4412b6f9816dae4aff28ab0cbe8ddc7e1141919519` |

## Execution environment

- Python 3.11.4
- NumPy 1.26.4
- pandas 2.3.2
- SciPy 1.16.1
- scikit-learn 1.7.2
- Bootstrap seed: 20260930
- Bootstrap replicates: 2,000; all were retained for every primary metric

The raw and derived NBA row-level files remain non-releaseable until reuse
permission is resolved. Aggregate results generated from the locked artifact may
be released.
