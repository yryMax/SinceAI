# Benchmark: reference baselines to beat

The baselines are deliberately simple. They show the floor and the typical failure modes, not a target. They read the field catalog instead of detecting fields, so they show what protection alone achieves. All numbers come from `python3 baselines/run_all.py` with `pets-eval` 1.0.0. The scorecards are in `results/`.

| Baseline | What it does |
|---|---|
| **B0** | Drops the catalogued direct identifiers and keeps everything else. |
| **B1** | Rule-based field detector that uses column names and value patterns. |
| **B2** | Classic SDC: keyed HMAC pseudonyms for identifiers (joins survive), prefix-preserving IPs, birth year instead of date, 10-year age bands, 3-digit postcodes, coordinates at 2 decimals, timestamps to the hour, regex redaction of free text. |
| **B2-k** | B2 plus local suppression until every row has k ≥ 5 on the catalogued quasi-identifiers. |
| **B3** | Person-level differential privacy (Laplace) on the health query workload. |
| **B4** | Simple synthetic ED visits from a chain Bayesian network. |

## B0 / B2 / B2-k by dataset (all utility tasks; self-assessment scores, 0–1)

The privacy score is `1 − (0.5 × worst risk + 0.5 × mean risk)`, so one open door costs a lot. The worst re-identification rate is the highest share of attacker targets singled out by any attack in `metadata/attack_specs.json`, or the attribute-inference advantage over guessing, whichever is higher.

| Dataset | Privacy B0 / B2 / B2-k | Utility B0 / B2 / B2-k | Worst re-identification B0 / B2 / B2-k |
|---|---|---|---|
| health | 0.28 / 0.36 / 0.52 | 1.00 / 0.87 / 0.44 | 0.10 / 0.10 / 0.00 |
| mobility | 0.34 / 0.36 / 0.51 | 1.00 / 0.98 / 0.52 | 0.01 / 0.00 / 0.00 |
| smart_city | 0.34 / 0.45 / 0.47 | 0.83 / 0.74 / 0.59 | 0.00 / 0.00 / 0.00 |
| energy | 0.35 / 0.40 / 0.78 | 1.00 / 0.95 / 0.84 | 0.04 / 0.00 / 0.00 |
| finance | 0.24 / 0.29 / 0.61 | 0.47 / 0.83 / 0.17 | 0.79 / 0.00 / 0.00 |
| cyber | 0.29 / 0.43 / 0.57 | 0.36 / 0.74 / 0.70 | 0.00 / 0.00 / 0.00 |
| education | 0.38 / 0.39 / 0.52 | 1.00 / 0.77 / 0.73 | 0.00 / 0.00 / 0.00 |
| public_admin | 0.25 / 0.27 / 0.57 | 1.00 / 0.93 / 0.44 | 0.00 / 0.00 / 0.00 |
| customer_service | 0.22 / 0.31 / 0.50 | 1.00 / 0.86 / 0.86 | 0.00 / 0.00 / 0.00 |

Utility per sharing scenario (mean of the scenario's required tasks):

| Scenario | B0 | B2 | B2-k |
|---|---|---|---|
| HEALTH-S1 | 1.00 | 0.79 | 0.40 |
| HEALTH-S2 | 1.00 | 0.95 | 0.00 |
| HEALTH-S3 | 1.00 | 1.00 | 1.00 |
| MOB-S1 | 1.00 | 0.95 | 0.40 |
| MOB-S2 | 1.00 | 0.96 | 0.35 |
| MOB-S3 | 1.00 | 1.00 | 0.75 |
| CITY-S1 | 1.00 | 1.00 | 1.00 |
| CITY-S2 | 0.83 | 0.74 | 0.59 |
| CITY-S3 | 1.00 | 0.75 | 0.00 |
| ENERGY-S1 | 1.00 | 1.00 | 0.73 |
| ENERGY-S2 | 1.00 | 0.92 | 0.92 |
| ENERGY-S3 | 1.00 | 1.00 | 1.00 |
| FIN-S1 | 0.41 | 1.00 | 0.06 |
| FIN-S2 | 0.27 | 0.67 | 0.14 |
| FIN-S3 | 0.67 | 0.67 | 0.19 |
| CYBER-S1 | 0.30 | 0.81 | 0.76 |
| CYBER-S2 | 0.67 | 0.68 | 0.68 |
| CYBER-S3 | 0.14 | 0.73 | 0.66 |
| EDU-S1 | 1.00 | 0.75 | 0.71 |
| EDU-S2 | 1.00 | 0.80 | 0.79 |
| EDU-S3 | 1.00 | 0.67 | 0.67 |
| PUB-S1 | 1.00 | 0.89 | 0.40 |
| PUB-S2 | 1.00 | 1.00 | 0.25 |
| PUB-S3 | 1.00 | 0.88 | 0.22 |
| CS-S1 | 1.00 | 0.75 | 0.75 |
| CS-S2 | 1.00 | 0.66 | 0.66 |
| CS-S3 | 1.00 | 1.00 | 1.00 |

## B1 field detection (public catalog)

Macro-F1 over privacy roles is **0.65**, and recall of sensitive columns is 0.73. Per role:

| Role | Precision | Recall | F1 |
|---|---|---|---|
| direct_identifier | 0.82 | 0.89 | 0.86 |
| quasi_identifier | 0.78 | 0.59 | 0.67 |
| sensitive_attribute | 0.44 | 0.10 | 0.16 |
| technical_identifier | 0.55 | 0.84 | 0.67 |
| free_text | 0.63 | 0.80 | 0.71 |
| record_key | 0.97 | 0.74 | 0.84 |
| non_sensitive | 0.55 | 0.71 | 0.62 |

## B3 differential privacy on the health workload (254 queries)

This is person-level DP. Each patient contributes at most 4 visits, Laplace noise is added, and ε is split over 5 query families. The utility score is 1 − mean relative error / 0.5.

| ε | Mean relative error | Utility score |
|---|---|---|
| 0.25 | 0.382 | 0.24 |
| 0.5 | 0.249 | 0.50 |
| 1.0 | 0.157 | 0.69 |
| 2.0 | 0.099 | 0.80 |
| 5.0 | 0.067 | 0.87 |

## B4 synthetic ED visits

Privacy 1.00, utility 0.38, composite 0.57. Risk components:

- ed_visits: direct identifiers retained: 0.000
- ed_visits: free-text identifier leakage: 0.000
- ed_visits: membership inference advantage: 0.000
- ed_visits: exact copies of original rows: 0.000

Utility tasks:

- H-U2: 0.05
- H-U3: 0.29
- H-U5: 0.79

## What the baselines teach

- **Dropping names is not anonymisation.** Under B0 the card numbers are gone, yet a shared receipt (date, time, amount) still singles out 79 % of the attacker's targets in the card transactions.
- **Generalising columns without checking k leaves most rows unique** (B2). Enforcing k ≥ 5 (B2-k) closes that, at a utility cost that differs by scenario.
- **Keyed pseudonyms keep joins.** Cyber detections and revisit analyses survive B2. Random tokens or dropped keys break them (B0 utility).
- **Regex redaction misses names, spoken numbers and spelled-out emails.** Free-text leakage is where most teams can win.
- **DP utility depends on ε and on contribution bounding.** State both.
