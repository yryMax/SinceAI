"""Utility tasks for the health dataset (Aurajoki Regional Hospital ED, 2025).

All tasks tolerate generalised values: ages as bands, dates as weeks/months, ICD-10 codes truncated to 3
characters or replaced by diagnosis groups, pseudonymised keys (as long as they are consistent).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import parse as Pz
from . import UtilityTask, not_answerable, require, result

DATASET = "health"

DIAGNOSIS_GROUPS = {
    "R07.4": "cardiovascular", "I21.4": "cardiovascular", "I48.9": "cardiovascular", "I50.9": "cardiovascular", "I26.9": "cardiovascular",
    "I63.9": "neurological", "G45.9": "neurological", "G40.9": "neurological", "R51": "neurological", "R55": "other",
    "J18.9": "respiratory", "J44.1": "respiratory", "J45.9": "respiratory", "J10.1": "ILI", "U07.1": "ILI", "J06.9": "ILI",
    "J21.0": "RSV", "H66.9": "other_infection", "R50.9": "other_infection", "A08.4": "gastrointestinal", "R10.4": "gastrointestinal",
    "K35.8": "gastrointestinal", "K80.2": "gastrointestinal", "N20.0": "urological", "N39.0": "urological", "S52.5": "injury",
    "S72.0": "injury", "S93.4": "injury", "S82.6": "injury", "S42.0": "injury", "S06.0": "injury", "S01.8": "injury", "S61.0": "injury",
    "S05.1": "injury", "T23.2": "injury", "F10.0": "intoxication", "T78.2": "allergy", "T63.4": "allergy", "F41.0": "mental_health",
    "F32.9": "mental_health", "F05.9": "mental_health", "F20.0": "mental_health", "E10.1": "endocrine", "E87.1": "endocrine",
    "M54.5": "musculoskeletal", "L03.1": "skin", "O20.0": "pregnancy", "O21.0": "pregnancy", "A41.9": "infection_severe", "Z03.9": "other",
}
GROUP_NAMES = set(DIAGNOSIS_GROUPS.values())
_PREFIX3 = {}
for _c, _g in DIAGNOSIS_GROUPS.items():
    _PREFIX3.setdefault(_c.replace(".", "")[:3], _g)
_CHAPTER = {"I": "cardiovascular", "J": "respiratory", "S": "injury", "T": "injury", "F": "mental_health", "G": "neurological",
            "N": "urological", "K": "gastrointestinal", "A": "gastrointestinal", "O": "pregnancy", "E": "endocrine", "R": "other",
            "H": "other_infection", "M": "musculoskeletal", "L": "skin", "U": "ILI", "Z": "other"}


def diagnosis_group(s: pd.Series) -> pd.Series:
    """Map exact codes, truncated codes (J18), chapters (J) or already-grouped values to diagnosis groups."""
    def one(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return np.nan
        t = str(v).strip()
        if t in GROUP_NAMES:
            return t
        if t in DIAGNOSIS_GROUPS:
            return DIAGNOSIS_GROUPS[t]
        u = t.replace(".", "").upper()
        if u[:3] in _PREFIX3:
            return _PREFIX3[u[:3]]
        if u[:1] in _CHAPTER:
            return _CHAPTER[u[:1]]
        return np.nan
    return s.map(one)


def derive(v: pd.DataFrame) -> pd.DataFrame:
    """Canonical analysis fields from an original or protected ed_visits table."""
    v = v.copy()
    if "disposition" in v.columns:
        v = v[v.disposition.astype(str) != "cancelled_duplicate"]
    out = pd.DataFrame(index=v.index)
    arr = Pz.to_datetime(v["arrival_ts"]) if "arrival_ts" in v.columns else pd.Series(pd.NaT, index=v.index)
    out["arrival"] = arr
    out["week"] = Pz.to_week(arr) if "arrival_ts" in v.columns else np.nan
    out["month"] = Pz.to_month(arr) if "arrival_ts" in v.columns else np.nan
    has_time = "arrival_ts" in v.columns and v["arrival_ts"].astype(str).str.contains(r"\d{1,2}:\d{2}").mean() > .5
    out["hour"] = arr.dt.hour if has_time else np.nan
    if "age" in v.columns:
        age = Pz.parse_numeric(v["age"])
    elif "date_of_birth" in v.columns and "arrival_ts" in v.columns:
        dob = Pz.to_datetime(v["date_of_birth"])
        age = ((arr - dob).dt.days / 365.25).astype(float)
    elif "age_band" in v.columns:
        age = Pz.parse_numeric(v["age_band"])
    else:
        age = pd.Series(np.nan, index=v.index)
    out["age"] = age
    out["age_band"] = Pz.to_age_band(age)
    if "icd10_primary" in v.columns:
        out["diagnosis_group"] = diagnosis_group(v["icd10_primary"])
    elif "diagnosis_group" in v.columns:
        out["diagnosis_group"] = diagnosis_group(v["diagnosis_group"])
    else:
        out["diagnosis_group"] = np.nan
    for c in ("triage", "municipality", "sex", "arrival_mode", "disposition"):
        out[c] = v[c].astype(str).where(v[c].notna()) if c in v.columns else np.nan
    if "los_minutes" in v.columns:
        out["los"] = Pz.parse_numeric(v["los_minutes"])
    elif "arrival_ts" in v.columns and "discharge_ts" in v.columns:
        out["los"] = (Pz.to_datetime(v["discharge_ts"]) - arr).dt.total_seconds() / 60
    else:
        out["los"] = np.nan
    out.loc[out.los < 0, "los"] = np.nan
    out["admitted"] = out.disposition.isin(["admitted_ward", "icu"]).astype(float).where(out.disposition.notna()) if "disposition" in v.columns else np.nan
    for c in ("systolic_bp", "heart_rate", "resp_rate", "temp_c", "spo2", "pain_nrs"):
        out[c] = Pz.parse_numeric(v[c]) if c in v.columns else np.nan
    for c in ("visit_id", "patient_hetu", "readmit_30d"):
        if c in v.columns:
            out[c] = v[c]
    return out


# ------------------------------------------------------------------ DP workload
def build_workload(v: pd.DataFrame) -> dict:
    d = derive(v)
    q = []
    weeks = sorted(w for w in d.week.dropna().unique() if str(w).startswith("2025"))
    for w in weeks:
        q.append(dict(id=f"HQ-ILI-{w}", type="count", filters={"week": w, "diagnosis_group": "ILI"},
                      description=f"ED visits for influenza-like illness in {w}"))
    bands = ["0-9", "10-19", "20-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80+"]
    for m in range(1, 13):
        for b in bands:
            q.append(dict(id=f"HQ-M{m:02d}-{b}", type="count", filters={"month": f"2025-{m:02d}", "age_band": b},
                          description=f"ED visits in 2025-{m:02d}, age {b}"))
    for t in "ABCDE":
        q.append(dict(id=f"HQ-LOS-{t}", type="mean", value="los", filters={"triage": t}, bounds=[0, 2880],
                      description=f"Mean length of stay (minutes), triage {t}"))
    munis = d[~d.municipality.isin(["", "non-resident", "nan"]) & d.municipality.notna()].municipality.value_counts().index[:8]
    groups = ["cardiovascular", "respiratory", "ILI", "injury", "gastrointestinal", "neurological", "intoxication", "mental_health",
              "urological", "other"]
    for mu in munis:
        for g in groups:
            q.append(dict(id=f"HQ-MG-{mu}-{g}", type="count", filters={"municipality": mu, "diagnosis_group": g},
                          description=f"Visits by residents of {mu}, diagnosis group {g}"))
    for b in bands:
        q.append(dict(id=f"HQ-ADM-{b}", type="mean", value="admitted", filters={"age_band": b}, bounds=[0, 1],
                      description=f"Share admitted to ward or ICU, age {b}"))
    return {"version": "1.0", "table": "ed_visits",
            "derived_fields": {"week": "ISO week of arrival_ts", "month": "YYYY-MM of arrival_ts",
                               "age_band": "10-year band of age at arrival (from date_of_birth, age or age_band)",
                               "diagnosis_group": "group of icd10_primary (pets_eval.utility.health.DIAGNOSIS_GROUPS)",
                               "los": "los_minutes (or discharge_ts - arrival_ts)",
                               "admitted": "1 if disposition in {admitted_ward, icu} else 0"},
            "excluded_rows": "disposition == cancelled_duplicate",
            "evaluate_with": "pets_eval.utility.health.evaluate_workload(ed_visits_df, workload)",
            "answer_format": "CSV or JSON with columns/keys: id, value",
            "queries": q}


def evaluate_workload(v: pd.DataFrame, workload: dict) -> dict:
    d = derive(v)
    out = {}
    for q in workload["queries"]:
        m = pd.Series(True, index=d.index)
        ok = True
        for k, val in q["filters"].items():
            if k not in d.columns or d[k].isna().all():
                ok = False
                break
            m &= d[k].astype(str) == str(val)
        if not ok:
            out[q["id"]] = np.nan
            continue
        if q["type"] == "count":
            out[q["id"]] = float(m.sum())
        else:
            col = d.loc[m, q["value"]] if q["value"] in d.columns else pd.Series(dtype=float)
            out[q["id"]] = float(col.mean()) if col.notna().any() else np.nan
    return out


def score_workload(true: dict, answers: dict, min_count: float = 10) -> dict:
    errs = []
    for k, t in true.items():
        if np.isnan(t):
            continue
        a = answers.get(k, np.nan)
        if k.startswith(("HQ-ILI", "HQ-M", "HQ-MG")):
            if t < min_count:
                continue
            errs.append(np.nan if a is None or np.isnan(a) else abs(a - t) / t)
        else:
            errs.append(np.nan if a is None or np.isnan(a) else abs(a - t) / max(abs(t), 1e-9))
    e = np.array(errs, dtype=float)
    answered = np.isfinite(e)
    if answered.sum() == 0:
        return result(None, "not answerable", n_queries=len(e))
    mre = float(np.mean(np.where(answered, np.minimum(e, 1), 1)))
    return result(Pz.score_from_rel_error(mre, .5), "mean relative error over workload (unanswered = 1)", mean_rel_error=round(mre, 4),
                  answered=int(answered.sum()), n_queries=len(e))


# ------------------------------------------------------------------ tasks
def _visits(dd, key="ed_visits"):
    return dd.get(key) if dd else None


def u1_weekly_ili(orig, prot):
    o, p = _visits(orig), _visits(prot)
    miss = require(p, ["arrival_ts"]) + ([] if p is not None and any(c in p.columns for c in ("icd10_primary", "diagnosis_group")) else ["icd10_primary"])
    if miss:
        return not_answerable(miss)
    do, dp = derive(o), derive(p)
    if dp.age_band.isna().all() or dp.week.isna().all():
        return not_answerable(["age"])
    to = do[do.diagnosis_group == "ILI"].groupby(["week", "age_band"]).size()
    tp = dp[dp.diagnosis_group == "ILI"].groupby(["week", "age_band"]).size()
    m = Pz.table_mape(to, tp, min_count=3)
    return result(Pz.score_from_rel_error(m, .5), "MAPE of weekly ILI counts by age band (cells >=3)", mape=round(m, 4), cells=int((to > 3).sum()))


def u2_los_by_triage(orig, prot):
    p = _visits(prot)
    if p is None or "triage" not in p.columns or not ({"los_minutes"} <= set(p.columns) or {"arrival_ts", "discharge_ts"} <= set(p.columns)):
        return not_answerable(["triage", "los_minutes"])
    do, dp = derive(_visits(orig)), derive(p)
    mo, mp = do.groupby("triage").los.median(), dp.groupby("triage").los.median()
    errs = [Pz.rel_error(mo[t], mp.get(t, np.nan)) if not np.isnan(mp.get(t, np.nan)) else 1.0 for t in mo.index]
    e = float(np.mean(errs))
    return result(Pz.score_from_rel_error(e, .3), "mean relative error of median LOS by triage", rel_error=round(e, 4),
                  orig=mo.round(1).to_dict(), prot=mp.round(1).to_dict())


FEATS = ["age", "hour", "systolic_bp", "heart_rate", "resp_rate", "temp_c", "spo2", "pain_nrs"]
CATS = ["sex", "triage", "arrival_mode", "diagnosis_group", "month"]


def _xy(d, cats_levels):
    X = d[FEATS].astype(float).copy()
    for c in FEATS:
        if X[c].isna().all():
            X[c] = 0.0
    for c in CATS:
        for lv in cats_levels[c]:
            X[f"{c}={lv}"] = (d[c].astype(str) == lv).astype(float)
    return X.values, d.admitted.values


def u3_admission_model(orig, prot):
    p = _visits(prot)
    if p is None or "disposition" not in p.columns:
        return not_answerable(["disposition"])
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    do = derive(_visits(orig))
    hold = orig.get("holdout__ed_visits")
    if hold is not None and len(hold) > 500:
        test, train_o = derive(hold), do
    else:
        h = pd.Series(np.arange(len(do)) % 10, index=do.index)
        test, train_o = do[h < 3], do[h >= 3]
    dp = derive(p)
    dp = dp[dp.admitted.notna()]
    levels = {c: sorted(train_o[c].dropna().astype(str).unique().tolist()) for c in CATS}
    Xt, yt = _xy(test, levels)
    aucs = {}
    for name, tr in (("orig", train_o), ("prot", dp)):
        X, y = _xy(tr, levels)
        if len(np.unique(y)) < 2:
            return result(0.0, "AUC ratio", reason=f"{name} training data has one class")
        clf = HistGradientBoostingClassifier(max_iter=150, learning_rate=.08, random_state=0)
        clf.fit(X, y)
        aucs[name] = float(roc_auc_score(yt, clf.predict_proba(Xt)[:, 1]))
    s = (aucs["prot"] - .5) / max(aucs["orig"] - .5, 1e-6)
    return result(s, "(AUC_protected-0.5)/(AUC_original-0.5), train on X, test on original", auc_orig=round(aucs["orig"], 4),
                  auc_prot=round(aucs["prot"], 4), test_rows=len(test))


def u4_mix_by_municipality(orig, prot):
    p = _visits(prot)
    if p is None or "municipality" not in p.columns:
        return not_answerable(["municipality"])
    do, dp = derive(_visits(orig)), derive(p)
    if dp.diagnosis_group.isna().all():
        return not_answerable(["icd10_primary"])
    top = do[~do.municipality.isin(["", "non-resident"]) & do.municipality.notna()].municipality.value_counts().index[:8]
    t = [Pz.tvd(do[do.municipality == m].diagnosis_group.value_counts(), dp[dp.municipality == m].diagnosis_group.value_counts()) for m in top]
    mt = float(np.mean(t))
    return result(1 - mt / .15, "1 - mean TVD/0.15 of diagnosis-group mix in top-8 municipalities", mean_tvd=round(mt, 4))


def u5_vitals(orig, prot):
    from scipy.stats import wasserstein_distance
    p = _visits(prot)
    cols = [c for c in ("systolic_bp", "heart_rate", "temp_c", "spo2") if p is not None and c in p.columns]
    if not cols:
        return not_answerable(["systolic_bp", "heart_rate", "temp_c", "spo2"])
    do, dp = derive(_visits(orig)), derive(p)
    ws = {}
    for c in ("systolic_bp", "heart_rate", "temp_c", "spo2"):
        a = do[c].dropna().values
        if c not in cols or dp[c].dropna().empty:
            ws[c] = 1.0
            continue
        b = dp[c].dropna().values
        iqr = np.subtract(*np.percentile(a, [75, 25])) or 1
        ws[c] = float(min(1.0, wasserstein_distance(a, b) / iqr))
    m = float(np.mean(list(ws.values())))
    return result(1 - m, "1 - mean Wasserstein distance / IQR over 4 vitals", per_vital={k: round(v, 4) for k, v in ws.items()})


def _revisit_rates(d):
    if "readmit_30d" in d.columns and d.readmit_30d.notna().any():
        x = Pz.parse_numeric(d.readmit_30d)
        return pd.DataFrame({"band": d.age_band, "r": x}).groupby("band").r.mean()
    if "patient_hetu" in d.columns and d.arrival.notna().any():
        e = d[d.patient_hetu.notna() & (d.patient_hetu.astype(str) != "")].sort_values(["patient_hetu", "arrival"])
        nxt = e.groupby("patient_hetu").arrival.shift(-1)
        r = ((nxt - e.arrival) <= pd.Timedelta(days=30)).astype(float)
        return pd.DataFrame({"band": e.age_band, "r": r}).groupby("band").r.mean()
    return None


def u6_revisits(orig, prot):
    p = _visits(prot)
    if p is None:
        return not_answerable(["ed_visits"])
    do, dp = derive(_visits(orig)), derive(p)
    ro, rp = _revisit_rates(do), _revisit_rates(dp)
    if rp is None or dp.age_band.isna().all():
        return not_answerable(["readmit_30d or consistent patient pseudonym", "age"])
    overall = float(Pz.parse_numeric(do.readmit_30d).mean())
    diffs = [abs(ro[b] - rp.get(b, np.nan)) if not np.isnan(rp.get(b, np.nan)) else overall for b in ro.index]
    e = float(np.mean(diffs) / overall)
    return result(Pz.score_from_rel_error(e, .5), "mean |revisit rate diff| by age band / overall rate", rel_error=round(e, 4),
                  orig=ro.round(4).to_dict(), prot=rp.round(4).to_dict())


def _crp_temp(visits, labs):
    if labs is None or not {"visit_id", "test_code", "value"} <= set(labs.columns) or "visit_id" not in visits.columns:
        return None
    l = labs[labs.test_code.astype(str) == "P-CRP"][["visit_id", "value"]].copy()
    l["crp"] = Pz.parse_numeric(l.value.astype(str).str.replace("<", "", regex=False))
    dv = derive(visits)
    j = dv[["visit_id", "temp_c", "diagnosis_group"]].merge(l[["visit_id", "crp"]], on="visit_id")
    j = j[(j.temp_c > 34) & (j.temp_c < 42.5)].dropna(subset=["crp"])
    if len(j) < 30:
        return None
    return j


def u7_crp_temperature(orig, prot):
    jp = _crp_temp(_visits(prot), prot.get("lab_results") if prot else None)
    if jp is None:
        return not_answerable(["lab_results joinable to ed_visits via visit_id", "temp_c"])
    jo = _crp_temp(_visits(orig), orig.get("lab_results"))
    ro = jo[["crp", "temp_c"]].corr(method="spearman").iloc[0, 1]
    rp = jp[["crp", "temp_c"]].corr(method="spearman").iloc[0, 1]
    mo = jo.groupby("diagnosis_group").crp.median()
    mp = jp.groupby("diagnosis_group").crp.median()
    errs = [min(1, abs(np.log1p(mo[g]) - np.log1p(mp.get(g, 0)))) for g in mo.index if (jo.diagnosis_group == g).sum() >= 30]
    s = .5 * max(0, 1 - abs(ro - rp) / .3) + .5 * (1 - float(np.mean(errs)))
    return result(s, "Spearman(CRP, temp) difference + CRP median by diagnosis group (log scale)", spearman_orig=round(ro, 4),
                  spearman_prot=round(rp, 4), joined_rows=len(jp))


def u8_hour_curve(orig, prot):
    p = _visits(prot)
    if p is None or "arrival_ts" not in p.columns:
        return not_answerable(["arrival_ts"])
    dp = derive(p)
    if dp.hour.isna().all():
        return not_answerable(["arrival time of day"])
    do = derive(_visits(orig))
    t = Pz.tvd(do.hour.value_counts(), dp.hour.value_counts())
    return result(1 - t / .3, "TVD of hour-of-day arrival distribution", tvd=round(t, 4))


def udp_workload(orig, prot):
    o = _visits(orig)
    wl = build_workload(o)
    true = evaluate_workload(o, wl)
    if prot and "dp_answers" in prot:
        a = prot["dp_answers"]
        answers = dict(zip(a["id"].astype(str), Pz.parse_numeric(a["value"])))
    elif _visits(prot) is not None:
        answers = evaluate_workload(_visits(prot), wl)
    else:
        return not_answerable(["dp_answers or ed_visits"])
    return score_workload(true, answers)


TASKS = [
    UtilityTask("H-U1", DATASET, "ed_visits", "Weekly influenza-like-illness visits by 10-year age band", "aggregate", u1_weekly_ili,
                ["arrival_ts", "date_of_birth|age", "icd10_primary|diagnosis_group"], ["HEALTH-S2"]),
    UtilityTask("H-U2", DATASET, "ed_visits", "Median length of stay by triage level", "aggregate", u2_los_by_triage,
                ["triage", "los_minutes|arrival_ts+discharge_ts"], ["HEALTH-S1", "HEALTH-S3"]),
    UtilityTask("H-U3", DATASET, "ed_visits", "Admission prediction: train on protected, test on original/holdout (AUC ratio)", "model",
                u3_admission_model, ["disposition", "vitals", "triage", "age", "sex", "arrival_mode", "icd10_primary"], ["HEALTH-S3"]),
    UtilityTask("H-U4", DATASET, "ed_visits", "Diagnosis-group mix in the eight largest municipalities", "distribution",
                u4_mix_by_municipality, ["municipality", "icd10_primary"], ["HEALTH-S1"]),
    UtilityTask("H-U5", DATASET, "ed_visits", "Distributions of systolic BP, heart rate, temperature and SpO2", "distribution", u5_vitals,
                ["systolic_bp", "heart_rate", "temp_c", "spo2"], ["HEALTH-S3"]),
    UtilityTask("H-U6", DATASET, "ed_visits", "30-day revisit rate by age band (needs readmit_30d or a consistent patient pseudonym)",
                "relationship", u6_revisits, ["readmit_30d|patient_hetu", "age"], ["HEALTH-S1"]),
    UtilityTask("H-U7", DATASET, "lab_results", "CRP vs temperature relationship and CRP by diagnosis group (needs visit join)",
                "relationship", u7_crp_temperature, ["lab_results.visit_id", "ed_visits.visit_id", "temp_c"], ["HEALTH-S1"]),
    UtilityTask("H-U8", DATASET, "ed_visits", "Hour-of-day arrival curve", "distribution", u8_hour_curve, ["arrival_ts (time of day)"],
                ["HEALTH-S1", "HEALTH-S2"]),
    UtilityTask("H-DP", DATASET, "ed_visits", "DP query workload (metadata/dp_query_workload_health.json): mean relative error",
                "aggregate", udp_workload, ["dp_answers (id,value) or ed_visits"], ["HEALTH-S2"]),
]
