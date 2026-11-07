# TrustED PETs Proving Ground 2026

Synthetic data and evaluation tools for the **TrustED PETs Transformer** challenge at Since AI Hackathon 2026 (Turku, 6–8 November 2026).

**Open `START_HERE.html` (or `START_HERE.md`) first.**

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
