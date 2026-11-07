"""Utility tasks for the energy dataset (hourly smart-meter data).

Tables: customers, meter_readings_hourly, weather_hourly (public context; always taken from the original).
Protected readings may be row-level (pseudonymised meter key) or aggregated. Aggregated releases can keep the
column names `ts`, `kwh` (mean kWh per meter in the cell), a location column (`postcode`) and optionally
`n_meters` (cell size, used as weight).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import parse
from . import UtilityTask, not_answerable, require, result

DS = "energy"
R, CU, W = "meter_readings_hourly", "customers", "weather_hourly"
JOIN_KEYS = ["metering_point_id", "customer_id"]
_CACHE: dict = {}


def _dt(s: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    out = pd.to_datetime(s, format="ISO8601", errors="coerce")
    if out.isna().sum() > s.isna().sum() + 0.01 * len(s):
        out = parse.to_datetime(s)
    return out


def _prep(tabs: dict) -> pd.DataFrame | None:
    """Readings with parsed ts/kwh, weight w, plus customer attributes (postcode3, heating_type, late_payment_count)."""
    r = tabs.get(R)
    if r is None or "ts" not in r.columns or "kwh" not in r.columns:
        return None
    key = (id(r), id(tabs.get(CU)))
    if key in _CACHE:
        return _CACHE[key][2]
    df = pd.DataFrame({"ts": _dt(r["ts"]), "kwh": parse.parse_numeric(r["kwh"])})
    df["w"] = parse.parse_numeric(r["n_meters"]).fillna(1.0) if "n_meters" in r.columns else 1.0
    cu = tabs.get(CU)
    jk = next((k for k in JOIN_KEYS if k in r.columns), None)
    df["meter"] = r[jk].astype(str).values if jk else None
    attrs = {}
    for col in ("postcode", "heating_type", "late_payment_count"):
        if col in r.columns:
            attrs[col] = r[col].values
        elif cu is not None and jk and jk in cu.columns and col in cu.columns:
            m = dict(zip(cu[jk].astype(str), cu[col]))
            attrs[col] = df["meter"].map(m).values
    for k, v in attrs.items():
        df[k] = v
    if "postcode" in df:
        df["pc3"] = parse.postcode_prefix(df["postcode"].astype(str), 3)
    df = df[df.ts.notna()]
    if len(_CACHE) > 6:
        _CACHE.clear()
    _CACHE[key] = (r, tabs.get(CU), df)
    return df


def _hourly(df) -> bool:
    return df is not None and df.ts.dt.hour.nunique() > 1


def _wmean(g, col="kwh"):
    return (g[col] * g["w"]).sum() / g["w"].sum()


def _weather(orig) -> pd.DataFrame:
    w = orig[W].copy()
    w["ts"] = _dt(w.ts)
    return w


# ---------------------------------------------------------------- U1
def u1_postcode_hour(orig, prot):
    o, p = _prep(orig), _prep(prot)
    if p is None or "pc3" not in p or not _hourly(p):
        return not_answerable(["ts (hourly)", "kwh", "postcode (via readings or customers)"])
    agg = lambda d: d.dropna(subset=["kwh", "pc3"]).assign(h=lambda x: x.ts.dt.hour, kw=lambda x: x.kwh * x.w) \
        .groupby(["pc3", "h"]).agg(kw=("kw", "sum"), w=("w", "sum")).eval("kw / w")
    mape = parse.table_mape(agg(o), agg(p))
    return result(parse.score_from_rel_error(mape, .5), "1 - MAPE/0.5 of mean kWh per postcode area x hour", mape=mape)


# ---------------------------------------------------------------- U2
def _system(d):
    d = d.dropna(subset=["kwh"])
    d = d[d.kwh < 100]  # exclude meter-swap artefacts
    return (d.kwh * d.w).groupby(d.ts).sum() / d.w.groupby(d.ts).sum()


def u2_peaks(orig, prot):
    o, p = _prep(orig), _prep(prot)
    if p is None or not _hourly(p):
        return not_answerable(["ts (hourly)", "kwh"])
    so, sp = _system(o), _system(p)
    top_o, top_p = set(so.nlargest(50).index), set(sp.nlargest(50).index)
    jac = len(top_o & top_p) / len(top_o | top_p)
    po = so.groupby(so.index.normalize()).idxmax().dt.hour
    pp = sp.groupby(sp.index.normalize()).idxmax().dt.hour
    agree = float((po.reindex(pp.index) - pp).abs().le(1).mean()) if len(pp) else 0.0
    return result(.5 * jac + .5 * agree, "0.5*Jaccard(top-50 peak hours) + 0.5*share of days with daily peak hour within ±1 h",
                  jaccard=jac, daily_peak_agreement=agree)


# ---------------------------------------------------------------- U3
def _slopes(d, w):
    d = d.dropna(subset=["kwh", "heating_type"])
    d = d[d.kwh < 100]
    d = d.assign(day=d.ts.dt.normalize())
    tday = w.groupby(w.ts.dt.normalize()).temperature_c.mean()
    g = d.assign(kw=d.kwh * d.w).groupby(["heating_type", "day"]).agg(kw=("kw", "sum"), w=("w", "sum"))
    daily = (g.kw / g.w * 24).rename("kwh_day").reset_index()
    daily["t"] = daily.day.map(tday)
    out = {}
    for h, x in daily.dropna().groupby("heating_type"):
        if len(x) > 10:
            out[h] = float(np.polyfit(x.t, x.kwh_day, 1)[0])
    return out


def u3_temperature(orig, prot):
    o, p = _prep(orig), _prep(prot)
    if p is None or "heating_type" not in p:
        return not_answerable(["ts (daily or finer)", "kwh", "heating_type"])
    w = _weather(orig)
    so, sp = _slopes(o, w), _slopes(p, w)
    # relative error with a floor of 0.5 kWh/day/°C so near-zero slopes (district heating) are not over-penalised
    scores = {h: parse.score_from_rel_error(abs(v - sp[h]) / max(abs(v), .5), .5) if h in sp else 0.0 for h, v in so.items()}
    return result(float(np.mean(list(scores.values()))), "mean over heating types of 1 - rel.error/0.5 of kWh-per-°C slope",
                  slopes_orig=so, slopes_prot=sp)


# ---------------------------------------------------------------- U4
def _meter_features(d, w):
    d = d.dropna(subset=["kwh", "meter"])
    d = d[d.kwh < 100]
    tday = w.groupby(w.ts.dt.normalize()).temperature_c.mean()
    d = d.assign(h=d.ts.dt.hour, dow=d.ts.dt.dayofweek, day=d.ts.dt.normalize())
    g = d.groupby("meter")
    f = pd.DataFrame({"mean": g.kwh.mean(), "cv": g.kwh.std() / (g.kwh.mean() + 1e-6)})
    night = d[(d.h >= 22) | (d.h < 7)].groupby("meter").kwh.mean()
    f["night_ratio"] = night / (f["mean"] + 1e-6)
    sat = d[(d.dow == 5) & d.h.between(16, 20)].groupby("meter").kwh.mean()
    f["sat_eve_ratio"] = sat / (f["mean"] + 1e-6)
    daily = d.groupby(["meter", "day"]).kwh.sum().reset_index()
    daily["t"] = daily.day.map(tday)
    sl = daily.groupby("meter").apply(lambda x: np.polyfit(x.t, x.kwh, 1)[0] if x.t.nunique() > 5 else np.nan, include_groups=False)
    f["slope"] = sl
    cold = d[d.day.isin(tday[tday < -12].index)].groupby("meter").kwh.mean()
    f["cold_ratio"] = cold / (f["mean"] + 1e-6)
    return f.replace([np.inf, -np.inf], np.nan).fillna(0)


def _labels(d):
    return d.dropna(subset=["meter"]).groupby("meter").heating_type.first()


def u4_heating_classifier(orig, prot):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_predict
    o, p = _prep(orig), _prep(prot)
    if p is None or "heating_type" not in p or p["meter"].isna().all() or not _hourly(p):
        return not_answerable(["meter key", "ts (hourly)", "kwh", "heating_type"])
    w = _weather(orig)
    fo, fp = _meter_features(o, w), _meter_features(p, w)
    yo, yp = _labels(o).reindex(fo.index), _labels(p).reindex(fp.index)
    okp = yp.notna()
    if okp.sum() < 20:
        return not_answerable(["enough labelled meters"])
    # The protected release normally contains the same meters as the original, so training on it and
    # testing on the original is an in-sample test. Compare like with like: the reference model is also
    # trained and tested on the same (original) meters, using the same out-of-fold protocol on both sides.
    clf = RandomForestClassifier(n_estimators=200, min_samples_leaf=3, random_state=0, n_jobs=-1)
    base = float((cross_val_predict(clf, fo, yo.astype(str), cv=5) == yo.astype(str).values).mean())
    clf.fit(fp[okp], yp[okp].astype(str))
    acc = float((clf.predict(fo) == yo.astype(str).values).mean())
    cv_p = float((cross_val_predict(clf, fp[okp], yp[okp].astype(str), cv=5) == yp[okp].astype(str).values).mean())
    return result(min(1.0, min(acc, cv_p) / base),
                  "min(acc train-protected/test-original, 5-fold CV acc within protected) / 5-fold CV acc on original",
                  acc_tstr=acc, acc_cv_protected=cv_p, acc_original_cv=base,
                  note="meters overlap between protected and original; the CV term guards against memorised labels")


# ---------------------------------------------------------------- U5
def _profiles(d):
    d = d.dropna(subset=["kwh", "meter"])
    d = d[(d.kwh < 100) & (d.ts.dt.dayofweek < 5)]
    prof = d.groupby(["meter", d.ts.dt.hour]).kwh.mean().unstack().dropna()
    return prof.div(prof.sum(axis=1) + 1e-9, axis=0)


def cluster_agreement(Xo: np.ndarray, Xp: np.ndarray, k: int, seed: int = 0) -> dict:
    from scipy.optimize import linear_sum_assignment
    from sklearn.cluster import KMeans
    ko = KMeans(k, n_init=10, random_state=seed).fit(Xo)
    kp = KMeans(k, n_init=10, random_state=seed).fit(Xp)
    D = np.linalg.norm(ko.cluster_centers_[:, None, :] - kp.cluster_centers_[None, :, :], axis=2)
    ri, ci = linear_sum_assignment(D)
    spread = np.mean([np.linalg.norm(a - b) for i, a in enumerate(ko.cluster_centers_) for b in ko.cluster_centers_[i + 1:]])
    dn = float(D[ri, ci].mean() / (spread + 1e-12))
    so = np.bincount(ko.labels_, minlength=k) / len(Xo)
    sp = np.bincount(kp.labels_, minlength=k)[ci] / len(Xp)
    tvd = float(.5 * np.abs(so[ri] - sp).sum())
    return dict(score=.5 * max(0.0, 1 - dn) + .5 * (1 - tvd), centroid_distance_norm=dn, size_tvd=tvd)


def u5_profile_clusters(orig, prot):
    o, p = _prep(orig), _prep(prot)
    if p is None or p["meter"].isna().all() or not _hourly(p):
        return not_answerable(["meter key", "ts (hourly)", "kwh"])
    po, pp = _profiles(o), _profiles(p)
    if len(pp) < 20:
        return not_answerable(["≥20 complete meter profiles"])
    r = cluster_agreement(po.values, pp.values, 5)
    return result(r.pop("score"), "0.5*(1 - matched centroid distance / centroid spread) + 0.5*(1 - TVD of cluster sizes), k=5", **r)


# ---------------------------------------------------------------- U6
def _fc_frame(series, w):
    df = pd.DataFrame({"y": series})
    df["h"], df["dow"] = df.index.hour, df.index.dayofweek
    df["t"] = w.set_index("ts").temperature_c.reindex(df.index).values
    df["lag24"] = df.y.shift(24)
    df["lag168"] = df.y.shift(168)
    return df.dropna()


def u6_forecast(orig, prot):
    from sklearn.ensemble import HistGradientBoostingRegressor
    o, p = _prep(orig), _prep(prot)
    if p is None or not _hourly(p):
        return not_answerable(["ts (hourly)", "kwh"])
    w = _weather(orig)
    so, sp = _fc_frame(_system(o), w), _fc_frame(_system(p), w)
    cut = pd.Timestamp("2026-02-15")
    test = so[so.index >= cut]
    feats = ["h", "dow", "t", "lag24", "lag168"]

    def mape(train):
        if len(train) < 200:
            return np.nan
        m = HistGradientBoostingRegressor(max_iter=200, random_state=0).fit(train[feats], train.y)
        return float(np.mean(np.abs(m.predict(test[feats]) - test.y) / test.y))

    m_o, m_p = mape(so[so.index < cut]), mape(sp[sp.index < cut])
    if np.isnan(m_p):
        return not_answerable(["≥200 hourly training points before 2026-02-15"])
    return result(min(1.0, m_o / m_p), "MAPE(model trained on original) / MAPE(model trained on protected), tested on original 15-28 Feb",
                  mape_original=m_o, mape_protected=m_p)


# ---------------------------------------------------------------- U7
def _poverty(d):
    d = d.dropna(subset=["kwh", "late_payment_count", "heating_type"])
    d = d[d.kwh < 100]
    lp = parse.parse_numeric(d.late_payment_count)
    grp = pd.cut(lp, [-1, 0.5, 2.5, 1e9], labels=["0", "1-2", "3+"]).astype(str)
    el = d.heating_type.astype(str).str.contains("electric|heat_pump", regex=True).map({True: "electric", False: "other"})
    return (d.kwh * d.w).groupby([grp, el]).sum() / d.w.groupby([grp, el]).sum() * 24


def u7_energy_poverty(orig, prot):
    o, p = _prep(orig), _prep(prot)
    if p is None or "late_payment_count" not in p or "heating_type" not in p:
        return not_answerable(["late_payment_count", "heating_type", "kwh"])
    mape = parse.table_mape(_poverty(o), _poverty(p))
    return result(parse.score_from_rel_error(mape, .5), "1 - MAPE/0.5 of daily kWh by late-payment group x electric heating", mape=mape)


TASKS = [
    UtilityTask("ENERGY-U1", DS, R, "Mean load per 3-digit postcode area × hour of day", "aggregate", u1_postcode_hour,
                ["ts", "kwh", "postcode"], ["ENERGY-S1"]),
    UtilityTask("ENERGY-U2", DS, R, "System peak hours (top 50) and daily peak hour", "aggregate", u2_peaks, ["ts", "kwh"],
                ["ENERGY-S1", "ENERGY-S2"]),
    UtilityTask("ENERGY-U3", DS, R, "Temperature sensitivity (kWh/day per °C) by heating type", "relationship", u3_temperature,
                ["ts", "kwh", "heating_type"], ["ENERGY-S1", "ENERGY-S3"]),
    UtilityTask("ENERGY-U4", DS, R, "Heating-type classifier: train on protected, test on original", "model", u4_heating_classifier,
                ["metering_point_id", "ts", "kwh", "heating_type"], ["ENERGY-S2", "ENERGY-S3"]),
    UtilityTask("ENERGY-U5", DS, R, "Weekday load-profile clusters (k=5) agreement", "distribution", u5_profile_clusters,
                ["metering_point_id", "ts", "kwh"], ["ENERGY-S2"]),
    UtilityTask("ENERGY-U6", DS, R, "Day-ahead forecast of mean load per meter", "model", u6_forecast, ["ts", "kwh"], ["ENERGY-S2"]),
    UtilityTask("ENERGY-U7", DS, CU, "Winter consumption by late-payment group × electric heating", "relationship", u7_energy_poverty,
                ["late_payment_count", "heating_type", "kwh"], ["ENERGY-S3"]),
]
