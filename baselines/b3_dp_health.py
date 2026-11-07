"""B3: differentially private answers to the health query workload (person-level DP, Laplace mechanism).

Method (stated so it can be checked):
- unit of privacy = one patient (patient_hetu); each patient's contribution is bounded to C visits
  (excess visits are dropped at random before answering);
- count queries: each visit falls in at most one query of each count family (weekly ILI, month x age band,
  municipality x diagnosis group), so the L1 sensitivity of a family is C; Laplace(C / eps_family) noise;
- mean queries (LOS, admitted share): noisy sum / noisy count with values clipped to the published bounds;
  each person contributes to at most one triage/age query set per visit, sensitivity C*upper bound for sums;
- the total epsilon is split equally over 5 query families (sequential composition).
usage: python3 baselines/b3_dp_health.py --eps 1.0 --out results/b3_eps1/health
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from _common import ROOT, io
from pets_eval.utility.health import derive

C = 4  # max visits per patient


def answer(visits: pd.DataFrame, workload: dict, eps: float, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    v = visits.copy()
    v["_r"] = rng.random(len(v))
    # visits registered without an identity code (unknown patients) count as their own person
    v["patient_hetu"] = v.patient_hetu.where(v.patient_hetu.notna() & (v.patient_hetu.astype(str) != ""), "visit:" + v.visit_id.astype(str))
    v = v.sort_values(["patient_hetu", "_r"])
    v = v[v.groupby("patient_hetu").cumcount() < C]  # contribution bounding
    d = derive(v)
    fams = {"HQ-ILI": [], "HQ-M": [], "HQ-MG": [], "HQ-LOS": [], "HQ-ADM": []}
    for q in workload["queries"]:
        i = q["id"]
        fam = ("HQ-ILI" if i.startswith("HQ-ILI-") else "HQ-MG" if i.startswith("HQ-MG-") else
               "HQ-LOS" if i.startswith("HQ-LOS-") else "HQ-ADM" if i.startswith("HQ-ADM-") else "HQ-M")
        fams[fam].append(q)
    eps_f = eps / len(fams)
    out = []
    for fam, qs in fams.items():
        for q in qs:
            m = pd.Series(True, index=d.index)
            for k, val in q["filters"].items():
                m &= d[k].astype(str) == str(val)
            if q["type"] == "count":
                val = m.sum() + rng.laplace(0, C / eps_f)
                out.append((q["id"], max(0.0, float(val))))
            else:
                lo, hi = q["bounds"]
                x = d.loc[m, q["value"]].clip(lo, hi).dropna()
                # split the family budget between the sum and the count
                s = x.sum() + rng.laplace(0, 2 * C * hi / eps_f)
                n = len(x) + rng.laplace(0, 2 * C / eps_f)
                out.append((q["id"], float(np.clip(s / max(n, 1.0), lo, hi))))
    return pd.DataFrame(out, columns=["id", "value"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--eps", type=float, default=1.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    visits = io.read_table(ROOT / "data" / "health" / "ed_visits.csv")
    wl = json.loads((ROOT / "metadata" / "dp_query_workload_health.json").read_text())
    res = answer(visits, wl, a.eps)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "dp_answers.csv", index=False)
    (out / "dp_method.json").write_text(json.dumps({"mechanism": "Laplace", "epsilon_total": a.eps, "delta": 0,
                                                    "unit": "patient", "contribution_bound_visits": C,
                                                    "composition": "sequential over 5 query families"}, indent=2))
    print(f"wrote {len(res)} DP answers (eps={a.eps}) -> {out}")
