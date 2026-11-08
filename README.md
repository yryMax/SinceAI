# TrustED PETs Transformer: our solution

**One line:** the tool reads only the input tables. It works out what each column is, picks a protection (PET) for each column from one general policy, and transforms the data. The same code runs on any dataset and any scenario; scenarios differ only in the recipient's trust level. Only the evaluation step reads the organisers' answers (`metadata/`, annotated PII, attackers).

The demo walkthrough, with the full per-scenario table and a worked example, is in [`script.md`](script.md).

## Quick start

```bash
pip install -e ./toolkit
python3 solution/pipeline.py data/health --trust controlled_research   # protect any folder of CSV files
python3 solution/pipeline.py data/unseen --trust contractual           # also works on the obfuscated dataset
# pipeline.py ends by printing the matching scorecard command, e.g.
pets-eval scorecard --original data/health --protected out/release/health/release --scenario HEALTH-S1 \
  --rowmap out/release/health/private/rowmap_ed_visits.csv --rowmap ...  --out out/release/health/private/scorecard
python3 solution/evaluate.py detection     # detector vs the organisers' field labels
python3 solution/evaluate.py text          # free-text redaction vs the annotated PII
python3 solution/evaluate.py scenarios     # all 27 scenarios vs the baselines (--only HEALTH-S1,... for a subset)
python3 -m pytest -q tests/                # 37 tests, including a "no access to answers" test
```

`pipeline.py` writes to `out/release/<folder>/`:

- `release/`: the protected tables, the only thing to share;
- `private/`: `field_labels.csv` (detected types), `pet_plan.csv` (the PET and reason for every column), `stats.json` (k-anonymity suppression), `rowmap_*.csv` (released row → original record id, for scoring only, never share).

Rows are shuffled, so the scorecard needs the row maps (`--rowmap`). Without them it treats the release as synthetic data. Keep `--out` pointing into `private/` so that `release/` holds only the tables.

`evaluate.py` writes to `out/evaluation/`.

| File | Role |
|---|---|
| `solution/subtype_detector.py` | about 50 judgers, one per data type |
| `solution/detector.py` | type + table context → privacy role |
| `solution/text_detector.py` | finds names, IDs, phones, addresses in free text |
| `solution/pipeline.py` | PET policy (`select`), transforms, k-anonymity, shuffle |
| `solution/evaluate.py` | the only code that reads `metadata/`, gold spans and attackers |
| `solution/baseline_scores.json` | B0 / B2 / B2-k / B4 composites per scenario, from the stock scorer |
| `archive/oracle_pipeline/` | an earlier pipeline that used the answers; kept for reference, not part of the solution |

## 1. Detector

One small judger per data type scores each column from 0 to 1; the highest score wins.

- **Values first:** checksums for HETU, IBAN and payment cards (Luhn); fixed formats for IP, MAC, ICD-10, timestamps and coordinates; word lists of first names, the region's 27 municipalities and street-name endings.
- **Then name and context:** words in the column name, whether the column is the table's key or a link to another table, whether the table is a timestamped log.
- **Type → privacy role:** the detected type plus the table context gives the role (direct identifier, quasi-identifier, sensitive attribute, …).
- **Free text:** the text detector's dictionary comes from the structured columns of the same dataset; it reads no annotations at run time.

## 2. PET policy (`pipeline.select`)

The protection depends only on **what the column is** and **who receives the data**. No column name appears in the rules.

| Data type | Example | PET | Why |
|---|---|---|---|
| Identifies a person and links tables | ID number, card, IBAN, email, account, plate | Keyed HMAC code; dropped for public releases | Tables still join; the value means nothing outside |
| Identifies a person | name, phone, address | Remove | No analysis needs it |
| System key or network address | visit ID, staff ID, IP | HMAC code; prefix-preserving code for IPs | Keeps links and subnet structure |
| Identifies in combination | birth date, time, postcode, place, job | Birth year, hour, month, 3-digit postcode, ~1 km, 2 significant digits, rare values → `other` | Just coarse enough |
| Diagnosis code | ICD-10 | 3-character category | A rare exact code can name a person |
| Other sensitive facts | triage, lab value, income, grade | Keep | What is analysed; the link to the person is cut |
| Free text | notes, chats, complaints | Names, numbers, addresses → `[PERSON]`, `[PHONE]` … | The meaning of the text stays |

| Trust level | k | Identifiers that link tables |
|---|---|---|
| `internal`, `contractual`, `controlled_research` | 5 | HMAC code |
| `public` | 10 | Removed |

**Final checks:** in groups of quasi-identifier values smaller than k, the most specific column is blanked, and rows that are still too rare are dropped. Rows are then shuffled with the secret key.

## 3. Results

**Detection** (475 labelled columns):

| | Data type correct | Privacy role correct | Sensitive recall |
|---|---|---|---|
| Ours, column names visible | 100 % * | 100 % * | 100 % * |
| Ours, names hidden (like `unseen`) | 73 % | 65 % | 66 % |
| Baseline B1 | 60 % | 67 % | 73 % |

\* In-sample: the rules were written with these columns in view. The hidden-names row is the honest estimate for new data.

**Free-text redaction** (10 text fields): identifiers that survive redaction are 0–4.9 % for us against 39–88 % for the B2 regular expressions. This is also in-sample.

**Scenarios** (organisers' `pets-eval` scorecard, self-assessment; compared with the best of B0, B2, B2-k, B4): **we beat the best baseline in 17 of 27 scenarios**, mean composite 0.60 vs 0.58. Per-scenario results are in `out/evaluation/scenarios.csv` and in `script.md` section 4.

| | Scenarios |
|---|---|
| Win (17) | HEALTH-S1, HEALTH-S3; MOB-S3; CITY-S1; ENERGY-S1/S2/S3; CYBER-S1/S2; EDU-S1/S2/S3; PUB-S1/S2; CS-S1/S2/S3 |
| Lose (10) | HEALTH-S2; MOB-S1/S2; CITY-S2/S3; FIN-S1/S2/S3; CYBER-S3; PUB-S3 |

The losses are event tables (taps, parking, transactions, logs) and public scenarios. Timestamps combined with places make almost every row unique, so k-anonymity blanks the whole time column, and tasks that need time fail. A purpose-aware tool would keep the hour of day or publish aggregates; we chose one general rule instead.

**Example, HEALTH-S3** (ED data for an AI vendor): re-identification by news clips 18.5 % → 0 %, by social posts 54.2 % → 0 %, admission-model AUC 0.785 → 0.82; composite 1.00 against 0.66 for B2-k. Details in `script.md` section 5.

## Limitations

- **Not purpose-aware:** columns a scenario does not need are still released (generalised), and event timestamps are often blanked entirely.
- **Public scenarios still get row-level data**, only with a larger k. A proper public release would use aggregates or differential privacy; that is not implemented.
- **k counts rows, not people:** several rows of the same person are not merged.
- **Detection and redaction make mistakes:** for example, in `unseen` a child's name was missed and a hash column was kept as non-sensitive. Review `private/pet_plan.csv` before any real release.
- **The scorecard is a self-assessment**, not the official score; the organisers' hidden attackers were not tested.

---

## About the challenge package

Synthetic data and evaluation tools for the **TrustED PETs Transformer** challenge at Since AI Hackathon 2026 (Turku, 6–8 November 2026). **Open `START_HERE.html` (or `START_HERE.md`) first.**

- 9 sensitive synthetic datasets (health, mobility, smart city, energy, finance, cybersecurity, education, public administration, customer service) and 1 unlabelled surprise dataset, all drawn from one synthetic population of 100,000 people in Southwest Finland
- `metadata/`: field-level privacy labels, 354,000 labelled PII spans in free text, 27 sharing scenarios, attack specifications, a DP query workload
- `adversary/` + `truth/`: attacker background knowledge with ground truth, so re-identification can be measured, not guessed
- `toolkit/`: the `pets-eval` package (detection scoring, k-anonymity / l-diversity / t-closeness, linkage and hash attacks, DCR and membership inference, trajectory unicity, utility tasks, HTML scorecard)
- `baselines/` + `results/` + `docs/BENCHMARK.md`: six reference solutions to beat (B0, B1, B2, B2-k, B3, B4)

Everything is synthetic; see `NOTICE.md`. Data CC BY 4.0, code MIT, © 2026 Since AI ry.

```bash
pip install -e ./toolkit && python3 examples/quickstart.py
python3 -m pytest -q tests/        # package integrity + toolkit tests
```
