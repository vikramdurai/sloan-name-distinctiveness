# Name Distinctiveness and NBA Draft Selection

This release contains the frozen protocol, analysis code, aggregate locked
results, paper-ready tables and figures, and integrity checks for a study of
1,795 NBA Draft Combine player–year observations from 2000–2025.

Vikram Durai is the sole author. The role of AI assistance is documented in
[`docs/AI_USE_DISCLOSURE.md`](docs/AI_USE_DISCLOSURE.md).

## Main finding

Adding public-name distinctiveness to a conventional Combine-measurement model
changed locked-period log loss by −0.00081 (paired-bootstrap 95% interval,
−0.00328 to 0.00161). Neither co-primary name association met the prespecified
Holm-adjusted 0.05 threshold. These results do not support using name
distinctiveness in draft evaluation.

## Contents

- `docs/`: protocol, frozen specification, results, discussion, source record,
  final manifest, and post-analysis audit.
- `study/` and `cool-names/`: cohort construction, name scoring, modeling,
  reporting, and audit source code.
- `tests/`: automated tests for cohort logic and modeling contracts.
- `study/model_output/` and `study/report/`: locked aggregate JSON artifacts,
  CSV tables, and PNG/SVG figures.
- `requirements-analysis.txt`: exact numerical-library versions used.
- `SHA256SUMS`: checksums for every release file except the checksum file itself.

## License

Original software and source code are licensed under the MIT License; see
[`LICENSE-CODE`](LICENSE-CODE). Original documentation, prose, aggregate
tables, and figures are licensed under the Creative Commons Attribution 4.0
International License; see [`LICENSE-CONTENT.md`](LICENSE-CONTENT.md).

Neither license applies to third-party data or materials. In particular, it
does not grant rights in NBA, NBA.com, SSA, Census, Wikipedia, or other
third-party content. See the license files and data-availability statement for
the precise boundaries.

## Data sources and availability

Official source links are collected in
[`docs/SOURCE_MANIFEST.md`](docs/SOURCE_MANIFEST.md), including the public NBA
Combine, draft-history, and player-bio pages and the direct SSA and Census
archives. Exact NBA endpoint construction is preserved in
`study/nba_client.py`.

The detailed availability statement is in
[`docs/DATA_AVAILABILITY.md`](docs/DATA_AVAILABILITY.md). Cached NBA responses
and the derived row-level NBA cohort are excluded while written redistribution
permission is being sought. The repository provides source links, acquisition
and transformation code, frozen hashes, tests, and aggregate results.

## Reproduction

The aggregate tables and figures can be regenerated from the included locked
result without player-level data:

```bash
python3 -m study.report_results
```

The included integrity audit report was generated in the original repository.
The audit program also checks the intentionally omitted row-level cohort hash,
so its complete 22-check run requires the restricted original workspace.

The included unit tests can be run with `python3 -m unittest discover -s tests`;
tests requiring the omitted derived cohort skip automatically. Reconstructing
the cohort and refitting models additionally requires the source
files documented in `docs/SOURCE_MANIFEST.md`. The official NBA row-level
responses and derived player-level cohort are intentionally omitted from this
release while reuse permission remains unresolved.

## Interpretation and data-use boundary

This is an observational association and prediction study within an already
selected Combine population. It does not establish that names cause draft
decisions, and U.S. name records do not measure cultural rarity universally.

Only code, documentation, and aggregate results are released. Do not infer that
the absence of row-level NBA data grants permission to redistribute those data
from another source.

## SSAC27 submission materials

- [`docs/SSAC27_ABSTRACT.md`](docs/SSAC27_ABSTRACT.md)
- [`docs/SSAC27_SUBMISSION_CHECKLIST.md`](docs/SSAC27_SUBMISSION_CHECKLIST.md)
