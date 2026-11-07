# Evaluation: what `pets-eval` measures

`pets-eval` measures two things about your protected release: the privacy risk you removed and the utility you kept. It is a **self-assessment tool**: the official judging follows the Since AI evaluation process. Judges will expect the before/after evidence that the TrustED brief requires, and the scorecard produces it.

## Output folder conventions

- Use the same table file names as the original (`ed_visits.csv`). A table you do not release is reported as withheld.
- Keep the original column names for the columns you keep. Generalised values are understood:

| Kind of value | Accepted forms |
|---|---|
| Ages | `30-39`, `90+` |
| Postcodes | `201**`, `201` |
| Times | rounded times, `2025-03`, `2025-W12` |
| Coordinates | rounded coordinates |
| ICD-10 codes | 3-character codes or diagnosis groups |

- For each released row-level table, add `rowmap_<table>.csv` with the columns `protected_row` (a 0-based row index) and `original_record_id`. It is used only for scoring. **Never publish it.**
- A table with neither a row map nor original record ids is evaluated as **synthetic data**, using distance to the closest record and membership inference against `holdout/`.
- To answer the health DP workload, add `dp_answers.csv` (`id,value`) and describe the mechanism: ε, δ, the unit of privacy and the contribution bound.

## Privacy risk components (0 = no risk, 1 = maximal)

| Component | Meaning |
|---|---|
| direct identifiers retained | Share of values of catalogued direct identifiers that still appear verbatim |
| hashed ids reversible | Share of hashed values recovered by hashing candidate values (unsalted MD5, SHA-1 or SHA-256) |
| records with k<5 | Share of rows in equivalence classes smaller than 5 on the catalogued quasi-identifiers that you kept |
| linkage re-identification | Worst re-identification or attribute-inference rate over the attacks in `metadata/attack_specs.json` |
| free-text identifier leakage | Share of gold PII spans whose value survives in your text |
| trajectory unicity | Share of subjects (cards, accounts, devices, vehicles) singled out by a few known (place, hour) points, for the tables listed under `trajectories` in `attack_specs.json` |
| synthetic: DCR / membership inference | Rows copied from the original, and the advantage of a membership attacker over a coin flip |

The scorecard's privacy score is `1 − (0.5 × worst risk + 0.5 × mean risk)`. The worst risk counts on purpose, because one open door is enough for an attacker.

## Utility

Each dataset has 6–11 utility tasks (`pets-eval tasks`). Each task asks the same question of the original and the protected data and scores agreement in [0, 1]. A task that cannot be answered (because you removed or coarsened what it needs) is "not answerable" and scores 0 when the chosen scenario requires it. The utility score is the mean over the scenario's tasks.

## Composite

The composite is the weighted harmonic mean of privacy (weight 30) and utility (weight 25). It is high only when both are high: releasing nothing or releasing everything both score low.

## Detection and redaction

- `pets-eval detect --pred my_labels.csv` scores `dataset,table,column,privacy_role,subtype` against `metadata/field_catalog.csv`. It reports per-role precision, recall and F1, macro-F1, subtype accuracy and a confusion matrix.
- In the span files, a record that is absent from a JSONL file, or present with an empty `spans` list, contains no labelled PII.
- `pets-eval text --gold <spans.jsonl> --pred <my_spans.jsonl>` reports span precision, recall and F2 per label. F2 weights recall higher, because a missed identifier is worse than an extra redaction.
- `pets-eval text --gold <spans.jsonl> --protected <redacted.csv>` checks which gold values survive in redacted text, whatever redaction style you used.

## Optional organiser checks (things you cannot overfit)

On request during the event, the organisers can run any of these:

1. **Hidden attackers.** Your released tables and row maps are tested against a stronger private attacker for each domain: a data broker, HR knowledge, colleagues, a merchant, municipal insiders.
2. **Unseen dataset.** Your field labels for `data/unseen/export_2025_q4.csv` are scored against private labels.
3. **Redaction on the eval split.** Your redacted `customer_service` eval turns are scored against private gold spans.

To request this, put the outputs in a folder `pets_submission/` in your repository with:

- `unseen_field_labels.csv`;
- `customer_service_eval_redacted.csv` (`turn_id,text`) or `customer_service_eval_spans.jsonl`;
- protected tables with their row maps, one subfolder per dataset.
