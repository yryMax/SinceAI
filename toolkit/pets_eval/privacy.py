"""Privacy-risk metrics for protected microdata, aggregate tables, synthetic data and trajectories.

All functions take pandas DataFrames and column names. Missing values in quasi-identifiers are
treated as their own value ("" after string conversion), which is how a linker would see them.
"""
from __future__ import annotations

from math import lgamma, log
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from . import parse


# ------------------------------------------------------------------ equivalence classes
def _keys(df: pd.DataFrame, qis: list) -> pd.Series:
    if not qis:
        return pd.Series(np.zeros(len(df), dtype=np.int64), index=df.index)
    sub = df[qis].astype(str)
    return pd.util.hash_pandas_object(sub, index=False)


def class_sizes(df: pd.DataFrame, qis: list) -> pd.Series:
    """Equivalence-class size for every record (aligned with df.index)."""
    k = _keys(df, qis)
    return k.map(k.value_counts()).astype(int)


def k_anonymity(df: pd.DataFrame, qis: list, thresholds: Iterable[int] = (2, 5, 10)) -> dict:
    qis = [q for q in qis if q in df.columns]
    if len(df) == 0:
        return {"qis": qis, "n": 0}
    ks = class_sizes(df, qis)
    return {
        "qis": qis, "n": int(len(df)), "n_classes": int(_keys(df, qis).nunique()),
        "min_k": int(ks.min()), "median_k": float(ks.median()),
        "share_below": {f"k<{t}": round(float((ks < t).mean()), 4) for t in thresholds},
        "sample_uniqueness": round(float((ks == 1).mean()), 4),
    }


def sample_uniqueness(df: pd.DataFrame, qis: list) -> float:
    return float((class_sizes(df, [q for q in qis if q in df.columns]) == 1).mean()) if len(df) else 0.0


def l_diversity(df: pd.DataFrame, qis: list, sensitive: str) -> dict:
    """Distinct and entropy l-diversity of `sensitive` within each equivalence class."""
    qis = [q for q in qis if q in df.columns]
    if sensitive not in df.columns or len(df) == 0:
        return {"evaluated": False, "reason": f"column {sensitive} not present"}
    k = _keys(df, qis)
    s = df[sensitive].astype(str)
    g = pd.DataFrame({"k": k.values, "s": s.values}).groupby("k")["s"]
    distinct = g.nunique()

    cnt = pd.DataFrame({"k": k.values, "s": s.values}).groupby(["k", "s"]).size()
    tot = cnt.groupby(level=0).transform("sum")
    p = cnt / tot
    entropy_l = np.exp(-(p * np.log(p)).groupby(level=0).sum())
    sizes = g.size()
    rec_distinct = k.map(distinct)
    return {
        "evaluated": True, "sensitive": sensitive, "qis": qis,
        "min_distinct_l": int(distinct.min()), "min_entropy_l": round(float(entropy_l.min()), 3),
        "share_records_l1": round(float((rec_distinct == 1).mean()), 4),
        "share_classes_l1": round(float((distinct == 1).mean()), 4),
        "n_classes": int(len(sizes)),
    }


def t_closeness(df: pd.DataFrame, qis: list, sensitive: str, numeric: Optional[bool] = None) -> dict:
    """Max / record-weighted mean distance between each class's sensitive distribution and the global one.
    Numeric: normalised 1-D EMD (ordered); categorical: total variation distance."""
    qis = [q for q in qis if q in df.columns]
    if sensitive not in df.columns or len(df) == 0:
        return {"evaluated": False, "reason": f"column {sensitive} not present"}
    col = df[sensitive]
    if numeric is None:
        numeric = pd.api.types.is_numeric_dtype(col)
    k = _keys(df, qis)
    if numeric:
        x = pd.to_numeric(col, errors="coerce")
        bins = np.unique(np.nanquantile(x.dropna(), np.linspace(0, 1, 21))) if x.notna().any() else np.array([0, 1])
        cat = pd.cut(x, bins=bins, include_lowest=True, labels=False).fillna(-1).astype(int)
    else:
        cat = col.astype(str)
    glob = cat.value_counts(normalize=True)
    order = sorted(glob.index)
    gvec = glob.reindex(order, fill_value=0).values
    dists = {}
    for key, idx in pd.Series(cat.values).groupby(k.values).groups.items():
        loc = pd.Series(cat.values[list(idx)]).value_counts(normalize=True).reindex(order, fill_value=0).values
        if numeric:
            d = float(np.abs(np.cumsum(loc - gvec)).sum() / max(len(order) - 1, 1))
        else:
            d = float(0.5 * np.abs(loc - gvec).sum())
        dists[key] = d
    rec = k.map(dists)
    return {"evaluated": True, "sensitive": sensitive, "numeric": bool(numeric), "max_t": round(float(rec.max()), 4),
            "mean_t": round(float(rec.mean()), 4), "share_records_t_gt_0.2": round(float((rec > 0.2).mean()), 4)}


# ------------------------------------------------------------------ population uniqueness
def _expected_inverse_F(f: int, pi: float, kmax: int = 20000) -> float:
    """E[1/F | sample frequency f] under the negative-binomial superpopulation model
    (Benedetti–Franconi style record-level risk), F = population class size."""
    if pi >= 1:
        return 1.0 / f
    kmax = int(min(kmax, max(200, 30 * f / pi)))
    ks = np.arange(0, kmax)
    # log C(f+k-1, k) + f log pi + k log(1-pi)
    lc = np.array([lgamma(f + k) - lgamma(k + 1) - lgamma(f) for k in ks])
    lp = lc + f * log(pi) + ks * log(1 - pi)
    w = np.exp(lp - lp.max())
    w /= w.sum()
    return float((w / (f + ks)).sum())


def population_uniqueness(df: pd.DataFrame, qis: list, sampling_fraction: float) -> dict:
    """Estimate re-identification risk when the data is a sample (fraction pi) of a population.
    Returns expected number of correct re-identifications and record-level risk statistics."""
    qis = [q for q in qis if q in df.columns]
    f = class_sizes(df, qis)
    cache = {v: _expected_inverse_F(int(v), sampling_fraction) for v in f.unique()}
    r = f.map(cache)
    return {"qis": qis, "sampling_fraction": sampling_fraction,
            "expected_reidentifications": round(float(r.sum()), 1), "mean_record_risk": round(float(r.mean()), 4),
            "share_records_risk_gt_0.2": round(float((r > 0.2).mean()), 4),
            "estimated_population_uniques": round(float(((f == 1) * sampling_fraction).sum()), 1)}


# ------------------------------------------------------------------ aggregates
def small_cells(agg: pd.DataFrame, count_col: str, threshold: int = 5) -> dict:
    c = parse.parse_numeric(agg[count_col]) if count_col in agg else pd.Series(dtype=float)
    small = (c > 0) & (c < threshold)
    return {"count_col": count_col, "threshold": threshold, "n_cells": int(len(c)), "n_small": int(small.sum()),
            "share_small": round(float(small.mean()), 4) if len(c) else 0.0,
            "n_ones": int((c == 1).sum()), "examples": agg[small].head(5).to_dict("records")}


def differencing_check(table_a: pd.DataFrame, table_b: pd.DataFrame, keys: list, count_col: str,
                       threshold: int = 5) -> dict:
    """Two published tables over the same keys where B counts a subset of A (e.g. 'all visits' vs
    'visits excluding X'). Cells where 0 < A-B < threshold disclose a small group by subtraction even
    if both tables individually pass a small-cell rule."""
    a = table_a.groupby(keys)[count_col].sum().astype(float)
    b = table_b.groupby(keys)[count_col].sum().astype(float)
    a, b = a.align(b, fill_value=0)
    d = a - b
    risky = (d > 0) & (d < threshold)
    return {"n_cells": int(len(d)), "n_disclosive": int(risky.sum()), "share_disclosive": round(float(risky.mean()), 4),
            "examples": [dict(zip(keys, k if isinstance(k, tuple) else (k,)), difference=float(v))
                         for k, v in d[risky].head(5).items()]}


def published_table_risk(agg: pd.DataFrame, keys: list, count_col: str, threshold: int = 5) -> dict:
    """Small cells + implicit differencing via margins: for every key, a margin (sum over the other keys)
    minus a non-suppressed sibling set can reveal a suppressed cell."""
    out = {"small_cells": small_cells(agg, count_col, threshold)}
    c = parse.parse_numeric(agg[count_col])
    suppressed = c.isna() & agg[count_col].notna()
    out["n_suppressed"] = int(suppressed.sum())
    return out


# ------------------------------------------------------------------ synthetic data
def _encode(frames: list, cols: list, max_categories: int = 50):
    """Mixed-type encoding: numeric columns robust-scaled on frames[0]; categoricals one-hot (top categories)."""
    ref = frames[0]
    blocks = [[] for _ in frames]
    for c in cols:
        x0 = ref[c]
        num = pd.to_numeric(x0, errors="coerce")
        if num.notna().mean() > 0.95 and x0.nunique() > 10:
            med = float(num.median())
            iqr = float(num.quantile(.75) - num.quantile(.25)) or float(num.std() or 1.0)
            for i, f in enumerate(frames):
                v = pd.to_numeric(f[c], errors="coerce").fillna(med).values
                blocks[i].append(((v - med) / iqr).reshape(-1, 1))
        else:
            top = x0.astype(str).value_counts().index[:max_categories]
            for i, f in enumerate(frames):
                s = f[c].astype(str)
                m = np.stack([(s == t).values for t in top], axis=1).astype(float) if len(top) else np.zeros((len(f), 0))
                blocks[i].append(m * (1 / np.sqrt(2)))
    return [np.hstack(b) if b else np.zeros((len(f), 0)) for b, f in zip(blocks, frames)]


def _nn(query: np.ndarray, ref: np.ndarray, k: int = 2):
    from sklearn.neighbors import NearestNeighbors
    nn = NearestNeighbors(n_neighbors=min(k, len(ref))).fit(ref)
    d, _ = nn.kneighbors(query)
    return d


def dcr_report(synthetic: pd.DataFrame, train: pd.DataFrame, holdout: Optional[pd.DataFrame], cols: list,
               max_rows: int = 20000, seed: int = 0) -> dict:
    """Distance to closest record. Synthetic rows that sit much closer to training (original) rows than
    to holdout rows indicate memorisation. 'share_closer_to_train' ≈ 0.5 is ideal when train/holdout
    sizes match; exact copies are reported separately."""
    cols = [c for c in cols if c in synthetic.columns and c in train.columns]
    if not cols:
        return {"evaluated": False, "reason": "no shared columns"}
    rng = np.random.default_rng(seed)

    def samp(df, n):
        return df.iloc[rng.choice(len(df), size=min(n, len(df)), replace=False)] if len(df) > n else df

    s = samp(synthetic, max_rows)
    if holdout is not None and len(holdout):
        holdout = samp(holdout, max_rows)
        t = samp(train, len(holdout))  # equal sizes -> share_closer_to_train ideal 0.5
    else:
        holdout = None
        t = samp(train, max_rows)
    frames = [t, s] + ([holdout] if holdout is not None else [])
    enc = _encode(frames, cols)
    d_tr = _nn(enc[1], enc[0], 2)
    out = {"evaluated": True, "columns": cols, "n_synthetic": int(len(s)),
           "median_dcr_train": round(float(np.median(d_tr[:, 0])), 4),
           "share_exact_copies": round(float((d_tr[:, 0] < 1e-9).mean()), 4),
           "median_nndr": round(float(np.median(d_tr[:, 0] / np.maximum(d_tr[:, -1], 1e-12))), 4)}
    if holdout is not None and len(holdout):
        d_ho = _nn(enc[1], enc[2], 1)
        out["median_dcr_holdout"] = round(float(np.median(d_ho[:, 0])), 4)
        out["share_closer_to_train"] = round(float((d_tr[:, 0] < d_ho[:, 0]).mean()), 4)
        out["train_holdout_size_ratio"] = round(len(t) / len(holdout), 3)
    return out


def membership_inference_auc(synthetic: pd.DataFrame, members: pd.DataFrame, nonmembers: pd.DataFrame,
                             cols: list, max_rows: int = 5000, seed: int = 0) -> dict:
    """Distance-based membership inference: the attacker scores each candidate record by
    -distance to its nearest synthetic record. AUC 0.5 = no membership signal, 1.0 = full leakage."""
    from sklearn.metrics import roc_auc_score
    cols = [c for c in cols if c in synthetic.columns and c in members.columns and c in nonmembers.columns]
    if not cols or len(nonmembers) == 0:
        return {"evaluated": False, "reason": "no shared columns or no non-members"}
    rng = np.random.default_rng(seed)
    n = min(max_rows, len(members), len(nonmembers))
    m = members.iloc[rng.choice(len(members), n, replace=False)]
    nm = nonmembers.iloc[rng.choice(len(nonmembers), n, replace=False)]
    s = synthetic.iloc[rng.choice(len(synthetic), min(len(synthetic), 50000), replace=False)]
    enc = _encode([m, s, nm], cols)
    dm = _nn(enc[0], enc[1], 1)[:, 0]
    dn = _nn(enc[2], enc[1], 1)[:, 0]
    y = np.r_[np.ones(n), np.zeros(n)]
    auc = roc_auc_score(y, -np.r_[dm, dn])
    return {"evaluated": True, "columns": cols, "n_each": int(n), "auc": round(float(auc), 4),
            "advantage": round(float(max(0.0, 2 * auc - 1)), 4)}


# ------------------------------------------------------------------ trajectories
def trajectory_unicity(df: pd.DataFrame, user_col: str, time_col: str, lat_col: Optional[str] = None,
                       lon_col: Optional[str] = None, place_col: Optional[str] = None, p: int = 4,
                       spatial_m: int = 500, temporal: str = "1h", n_users: int = 1000, seed: int = 0) -> dict:
    """de Montjoye-style unicity: share of sampled users uniquely singled out by `p` random points
    (place cell, time bin) drawn from their own trace, at the given spatial and temporal resolution."""
    if user_col not in df.columns or time_col not in df.columns:
        return {"evaluated": False, "reason": "user or time column missing"}
    t = parse.to_datetime(df[time_col]).dt.floor(temporal)
    if place_col and place_col in df.columns:
        place = df[place_col].astype(str)
    elif lat_col in df.columns and lon_col in df.columns:
        place = parse.latlon_to_grid(df[lat_col], df[lon_col], spatial_m)
    else:
        return {"evaluated": False, "reason": "no location column"}
    ok = place.notna().values & t.notna().values & df[user_col].notna().values
    ok &= (place.astype(object).astype(str).str.strip().isin(["", "nan", "None", "<NA>"]) == False).values  # noqa: E712
    pts = pd.DataFrame({"u": df[user_col].astype(object).astype(str).values[ok],
                        "pt": place.astype(object).astype(str).values[ok] + "|" + t.astype(object).astype(str).values[ok]})
    pts = pts[pts.u.str.strip() != ""].drop_duplicates()
    if pts.empty:
        return {"evaluated": False, "reason": "no usable points"}
    inv = pts.groupby("pt")["u"].apply(lambda s: frozenset(s)).to_dict()
    by_user = pts.groupby("u")["pt"].apply(list)
    by_user = by_user[by_user.map(len) >= p]
    if by_user.empty:
        return {"evaluated": True, "unicity": 0.0, "n_users_tested": 0, "note": f"no user has ≥{p} points"}
    rng = np.random.default_rng(seed)
    users = by_user.index.values
    if len(users) > n_users:
        users = rng.choice(users, n_users, replace=False)
    uniq = 0
    for u in users:
        cand = by_user[u]
        sel = [cand[i] for i in rng.choice(len(cand), p, replace=False)]
        s = None
        for x in sel:
            s = inv[x] if s is None else s & inv[x]
            if len(s) == 1:
                break
        uniq += int(len(s) == 1)
    return {"evaluated": True, "p": p, "spatial_m": spatial_m, "temporal": temporal, "n_users_tested": int(len(users)),
            "unicity": round(uniq / len(users), 4)}
