"""B4: simple synthetic ED visits (chain Bayesian network over binned columns).

Each column is sampled conditionally on the previous one in a fixed order (a first-order chain), using
empirical conditional distributions with additive smoothing. Numeric columns are binned, then sampled
uniformly inside the bin. This is intentionally modest: it preserves marginals and adjacent pairs, loses
higher-order structure, and copies nothing row-for-row. Measure it with DCR / membership inference.
usage: python3 baselines/b4_synth_health.py --out results/b4_synth/health [--n 40000]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from _common import ROOT, io
from pets_eval.utility.health import derive

ORDER = ["age_band", "sex", "diagnosis_code", "triage", "arrival_mode", "disposition", "month", "dow", "hour",
         "municipality", "los_bin", "sbp_bin", "hr_bin", "temp_bin", "spo2_bin", "readmit_30d"]
BINS = {"los": [0, 60, 120, 180, 240, 360, 480, 720, 1440, 2880], "systolic_bp": [60, 90, 110, 130, 150, 170, 200, 260],
        "heart_rate": [30, 50, 60, 80, 100, 120, 150, 220], "temp_c": [34, 36, 36.8, 37.5, 38.3, 39.2, 42],
        "spo2": [70, 88, 92, 95, 97, 99, 101]}


def prepare(v: pd.DataFrame) -> pd.DataFrame:
    d = derive(v)
    x = pd.DataFrame(index=d.index)
    x["age_band"] = d.age_band
    x["sex"] = d.sex
    x["diagnosis_code"] = v.loc[d.index, "icd10_primary"].astype(str).str[:3]
    x["triage"], x["arrival_mode"], x["disposition"] = d.triage, d.arrival_mode, d.disposition
    x["month"] = d.arrival.dt.month
    x["dow"] = d.arrival.dt.dayofweek
    x["hour"] = d.hour
    x["municipality"] = d.municipality
    for c, b in BINS.items():
        x[f"{'los' if c == 'los' else {'systolic_bp': 'sbp', 'heart_rate': 'hr', 'temp_c': 'temp', 'spo2': 'spo2'}[c]}_bin"] = \
            pd.cut(d[c], b, labels=False, include_lowest=True)
    x["readmit_30d"] = v.loc[d.index, "readmit_30d"].astype(str) if "readmit_30d" in v else "0"
    return x.astype(str)


def fit_sample(x: pd.DataFrame, n: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = pd.DataFrame(index=range(n))
    first = x[ORDER[0]].value_counts(normalize=True)
    out[ORDER[0]] = rng.choice(first.index, size=n, p=first.values)
    for prev, cur in zip(ORDER, ORDER[1:]):
        tab = pd.crosstab(x[prev], x[cur]) + 0.1
        tab = tab.div(tab.sum(axis=1), axis=0)
        vals = np.empty(n, dtype=object)
        for pv, idx in out.groupby(prev).groups.items():
            row = tab.loc[pv] if pv in tab.index else x[cur].value_counts(normalize=True)
            vals[np.asarray(idx)] = rng.choice(row.index, size=len(idx), p=row.values / row.values.sum())
        out[cur] = vals
    return out


def decode(s: pd.DataFrame, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = len(s)
    lo_age = pd.to_numeric(s.age_band.str.extract(r"(\d+)")[0], errors="coerce").fillna(40)
    age = (lo_age + rng.integers(0, 10, n)).astype(int)
    day = []
    for m, dw in zip(s.month.astype(float).astype(int), s.dow.astype(float).astype(int)):
        days = pd.date_range(f"2025-{m:02d}-01", periods=pd.Period(f"2025-{m:02d}").days_in_month)
        cand = days[days.dayofweek == dw]
        day.append(cand[int(rng.integers(len(cand)))])
    hour = pd.to_numeric(s.hour, errors="coerce").fillna(12).astype(int)
    arrival = pd.Series(pd.to_datetime(day)) + pd.to_timedelta(hour.values, unit="h") + \
        pd.to_timedelta(rng.integers(0, 60, n), unit="m")

    def unbin(col, key):
        b = BINS[key]
        i = pd.to_numeric(s[col], errors="coerce")
        lo = i.map(lambda k: b[int(k)] if pd.notna(k) else np.nan)
        hi = i.map(lambda k: b[int(k) + 1] if pd.notna(k) else np.nan)
        return lo + (hi - lo) * rng.random(n)

    out = pd.DataFrame({
        "age": age, "sex": s.sex, "municipality": s.municipality, "arrival_ts": arrival.dt.strftime("%Y-%m-%d %H:%M"),
        "arrival_mode": s.arrival_mode, "triage": s.triage, "icd10_primary": s.diagnosis_code,
        "disposition": s.disposition, "los_minutes": unbin("los_bin", "los").round(),
        "systolic_bp": unbin("sbp_bin", "systolic_bp").round(), "heart_rate": unbin("hr_bin", "heart_rate").round(),
        "temp_c": unbin("temp_bin", "temp_c").round(1), "spo2": unbin("spo2_bin", "spo2").round(),
        "readmit_30d": s.readmit_30d})
    return out.replace({"nan": np.nan})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=40000)
    a = ap.parse_args()
    v = io.read_table(ROOT / "data" / "health" / "ed_visits.csv")
    syn = decode(fit_sample(prepare(v), a.n))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    syn.to_csv(out / "ed_visits.csv", index=False)
    print(f"wrote {len(syn)} synthetic visits -> {out}")
