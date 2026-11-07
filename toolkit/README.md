# pets-eval

Self-assessment toolkit for the TrustED PETs Transformer challenge (Since AI Hackathon 2026).
It measures what your privacy transformation removes (risk) and what it keeps (utility).
Scores are a self-assessment aid, not the official judging score.

```bash
pip install -e ./toolkit        # or: export PYTHONPATH=$PWD/toolkit
pets-eval scenarios                                   # list sharing scenarios
pets-eval tasks --dataset health                      # list utility tasks
pets-eval check my_out/                               # residual direct identifiers (HETU, IBAN, cards, e-mail, phones, IPs, MACs, plates)
pets-eval detect --pred my_field_labels.csv           # score your Detect step against metadata/field_catalog.csv
pets-eval text --gold metadata/pii_spans/customer_service__turns__text.jsonl --pred my_spans.jsonl
pets-eval scorecard --original data/health --protected my_out/health --scenario HEALTH-S1
```

Protected-folder conventions for `scorecard`:
- same table file names as the original; tables you do not release are reported as withheld;
- keep original column names for the columns you keep; generalised values (age bands `30-39`, `90+`,
  truncated postcodes `201**`, rounded times, `2025-03`, `2025-W12`, rounded coordinates) are understood;
- for each released microdata table, a row map `rowmap_<table>.csv` (`protected_row`, `original_record_id`)
  used only for scoring — never publish it;
- a table without row map and without original record ids is evaluated as synthetic data
  (distance to closest record and membership inference against `holdout/`).

Python API: `pets_eval.privacy` (k-anonymity, l-diversity, t-closeness, uniqueness, small cells,
differencing, DCR/NNDR, membership inference, trajectory unicity), `pets_eval.attacks` (linkage attack,
attribute inference, hash dictionary attack, HETU enumeration), `pets_eval.text`, `pets_eval.detect`,
`pets_eval.parse`, `pets_eval.utility`.

MIT licence, © Since AI ry.
