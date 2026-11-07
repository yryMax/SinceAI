# TrustED PETs Proving Ground 2026: start here

**Challenge:** TrustED PETs Transformer — *Protect the data, keep its value.*
**What this package is:** realistic synthetic data to protect, plus tools that measure how well you protected it.

The package contains:

- nine sensitive synthetic datasets from the domains named in the challenge brief;
- one surprise dataset whose contents you must identify without labels;
- the attackers' background knowledge, so your privacy claims can be tested;
- utility tasks and a scorecard that produce the before/after comparison the final demo requires.

Everything is synthetic. No real person's data was used (see `NOTICE.md`).

## The 30-second version

1. Pick a dataset and a **sharing scenario** (`docs/SCENARIOS.md`): who receives the data and why.
2. Build a tool that **detects** what each column and text contains, **selects** a PET for each, and **transforms** the data.
3. Run `pets-eval scorecard` to **demonstrate** what you removed (re-identification risk) and what you kept (utility).

## One world, ten datasets

All datasets draw on one synthetic population: 100,000 residents of Southwest Finland at synthetic addresses in real postcode areas. The same people appear in several datasets. A patient in the emergency department may also ride the bus, bank at Saaristo Bank, work at Meridian Logistics and file a noise complaint, which makes cross-dataset linkage as real a risk as it is in practice.

| Dataset | Story (fictional controller) | Main tables (rows) | Typical PET problems |
|---|---|---|---|
| `health` | Aurajoki Regional Hospital ED, 2025 | ed_visits 46k, lab_results 130k, clinical_notes 30k, published_weekly_stats 30k | HETU encodes birth date and sex, rare diagnoses, clinical free text, unsuppressed small cells, DP dashboard |
| `mobility` | Aura Transit travel cards and city bikes, Oct 2025 | taps 943k, cards 23k, bike_trips 58k | Trajectory unicity (4 points single out about 98 % of cards), home locations, discount types revealing disability |
| `smart_city` | City-centre Wi-Fi sensors and ANPR car parks, Nov 2025 | wifi_probes 586k, anpr_parking 49k, footfall_15min 27k | Static MACs, probed network names containing surnames, plates, purpose limitation |
| `energy` | Lounaisvirta Verkko Oy smart meters, winter 2025–26 | meter_readings_hourly 1.6M, customers 757 | Occupancy and vacation inference, medical-device priority flag (Art. 9) |
| `finance` | Saaristo Bank cards and transfers, H2 2025 | card_transactions 398k, transfers 87k, customers 6.3k | Tokenisation, receipts that re-link, Art. 9 inference from merchants, fraud-model utility |
| `cyber` | Meridian Logistics Oy SOC logs, Mar 2026 | proxy_logs 137k, dns_logs 76k, signin_logs 41k, email_gateway 30k | Joins across logs, prefix-preserving IPs, names in hostnames, secrets in URLs, labelled attack campaign |
| `education` | Upper-secondary and vocational schools, 2022–2025 | course_grades 152k, students 5.2k, counsellor_notes 3.8k | Small classes, religion and migrant-background proxies in course codes, counsellor notes |
| `public_admin` | Southwest Joint Service Centre feedback and permits, 2024–25 | service_requests 32k, building_permits 2.7k | Open-data release of free text, neighbours named in complaints, repeat reporters |
| `customer_service` | Aallokko Telecom contact centre, 2025 | turns 140k, conversations 12k | The redaction benchmark: spoken numbers, spelled emails, passwords in chat, a hidden eval split |
| `unseen` | An HR/payroll export from a care company | export_2025_q4 2.8k | Obfuscated headers `c01..c26`: detect everything without labels |

Across the package there are 4.7 million rows, 475 catalogued columns, 354,000 labelled PII spans in free text, and 13 attacker-knowledge files. Each dataset folder has its own `README.md`.

## Choose your path

These are suggestions; teams can combine them.

- **Free-text redaction:** `customer_service` (with a hidden eval split), `health/clinical_notes`, `public_admin`.
- **Tabular de-identification under linkage attacks:** `health/ed_visits`, `finance/customers`, `education/students`.
- **Location and trajectory privacy:** `mobility`, `smart_city`.
- **Pseudonymisation that keeps joins:** `cyber`. Detection must still work after protection.
- **Differential privacy for published statistics:** `health/published_weekly_stats` with the DP query workload `metadata/dp_query_workload_health.json`, or `energy` neighbourhood load.
- **Synthetic data with a measured privacy risk:** any table; `holdout/` gives the non-members needed for membership-inference tests.
- **Automatic detection:** the `unseen` dataset, scored by the organisers.

## Ten-minute quickstart

```bash
pip install -e ./toolkit                 # pets-eval CLI; Python ≥ 3.10, numpy, pandas 2 or 3, scipy, scikit-learn
python3 examples/quickstart.py           # protects health/ed_visits for HEALTH-S1 and writes a scorecard
pets-eval scenarios                      # list the 27 sharing scenarios
pets-eval tasks --dataset finance        # utility tasks for a dataset
pets-eval check results/quickstart       # scan any output for residual identifiers
pets-eval scorecard --original data/health --protected my_out/health --scenario HEALTH-S1
```

Read every CSV with `dtype=str` first, because phone numbers, postcodes and identifiers break when they are parsed as numbers.

## What the final demo must show, and how this package helps

| Demo requirement (TrustED brief) | Use |
|---|---|
| 1. Data types identified | Your detector's output, scored with `pets-eval detect` against `metadata/field_catalog.csv` |
| 2. PETs selected per data type | `docs/PET_PLAYBOOK.md`; justify each choice against the scenario |
| 3. Transformed dataset or protected view | Your output folder |
| 4. Utility before vs after | `pets-eval scorecard`: utility tasks per scenario, as JSON and HTML |
| 5. The sharing scenario it is fit for | `docs/SCENARIOS.md`, plus the residual risks reported by the scorecard |

The best solutions do not merely hide values. They keep the patterns, distributions, trends and relationships the scenario needs, and they report honestly which risks remain.

## How you are measured

- **Self-assessment (yours):** `pets-eval scorecard` combines privacy, utility and a composite score. The scorecard is a tool for building and presenting your work. It is not the official judging score.
- **Judging:** judging follows the official Since AI evaluation process.
- **Optional organiser checks:** the organisers can run your outputs against things you have not seen: a stronger hidden attacker for every domain, the private labels of the `unseen` dataset, and the hidden eval spans of `customer_service`. See `docs/EVALUATION.md`.
- **Baselines to beat:** `docs/BENCHMARK.md`.

## Rules of the road

- Use only this synthetic data, public data, or data you are explicitly allowed to use.
- Never publish row maps (`rowmap_*.csv`). They exist only so that your protection can be scored.
- Say what your guarantee is. "Anonymised" and "differentially private" are claims that need a method and parameters (see the playbook).
- Licences: data CC BY 4.0, code MIT, © Since AI ry. Postcode centroids come from GeoNames (CC BY 4.0).

## Folder map

```
data/<dataset>/              tables + README per dataset
metadata/                    field_catalog.csv, scenarios.json, pii_spans/, taxonomy.md, attack_specs.json,
                             dp_query_workload_health.json, pii_span_guidelines.md
adversary/                   what attackers know (public part)
truth/                       who is who: record -> person, attacker row -> person (for self-assessment)
holdout/                     non-member records for membership-inference tests
toolkit/                     the pets-eval Python package and CLI
baselines/                   B0–B4 reference solutions; results/ holds their scorecards
examples/                    quickstart
docs/                        DATA_DICTIONARY, SCENARIOS, THREAT_MODEL, PET_PLAYBOOK, EVALUATION, BENCHMARK, GLOSSARY, LIMITATIONS
```

Inspired by the European project TrustED (Horizon Europe grant agreement No. 101168467), coordinated by Gradiant. Since AI ry produced this package for Since AI Hackathon 2026. It does not imply endorsement by the EU or the TrustED consortium. Questions go to the TrustED challenge channel on the Since AI Discord.
