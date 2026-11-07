# Baselines

Reference solutions to beat (results: `docs/BENCHMARK.md`, scorecards in `results/`).

| Id | Script | What it does |
|---|---|---|
| B0 | `protect.py --level b0` | Drops the catalogued direct identifiers and keeps everything else |
| B1 | `b1_detect_rules.py` | Rule-based field detector (column names + value patterns) |
| B2 | `protect.py --level b2` | Classic SDC: keyed pseudonyms, prefix-preserving IPs, generalised QIs, regex redaction |
| B2-k | `protect.py --level b2k` | B2 + local suppression to k ≥ 5 |
| B3 | `b3_dp_health.py --eps 1` | Person-level Laplace DP answers to the health query workload |
| B4 | `b4_synth_health.py` | Synthetic ED visits from a chain Bayesian network |

Use `run_all.py` to rerun all of them (about 25 minutes on a laptop).

The baselines read the field catalog (they "cheat" on detection) to show what protection alone achieves. Your tool should detect fields itself.
