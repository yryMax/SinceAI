"""Utility tasks for the education dataset."""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from ..parse import to_datetime
from . import UtilityTask, not_answerable, require, result

D = "education"


def _num_grade(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.extract(r"^\s*(\d+(?:[.,]\d+)?)")[0].str.replace(",", "."), errors="coerce")


def _general_grades(g: pd.DataFrame) -> pd.DataFrame:
    g = g.copy()
    if "grade_scale" in g.columns:
        g = g[g.grade_scale.astype(str) == "4-10"]
    g["_g"] = _num_grade(g["grade"])
    g = g[g._g.between(4, 10)]
    g["_subj"] = g["course_code"].astype(str).str.extract(r"^([A-Za-zÄÖäö]+)")[0].str.upper() if "course_code" in g.columns else np.nan
    return g


def _test_mask(ids: pd.Series, pct: int = 30) -> pd.Series:
    return ids.astype(str).map(lambda x: int(hashlib.sha256(x.encode()).hexdigest()[:8], 16) % 100 < pct)


# ------------------------------------------------------------------ U1
def u1_mean_grade_school_subject(orig, prot):
    p = prot.get("course_grades")
    miss = require(p, ["school_code", "course_code", "grade"])
    if miss:
        return not_answerable(miss)
    o, q = _general_grades(orig["course_grades"]), _general_grades(p)
    mo = o.groupby(["school_code", "_subj"])._g.agg(["mean", "size"])
    mo = mo[mo["size"] >= 20]["mean"]
    mq = q.groupby(["school_code", "_subj"])._g.mean()
    err = (mo - mq.reindex(mo.index)).abs().clip(upper=1.0).fillna(1.0)
    mae = float(err.mean())
    return result(1 - mae / 1.0, "1 - MAE of mean grade per (school, subject) / 1 grade", groups=len(mo), mae=round(mae, 3),
                  missing_groups=int(mq.reindex(mo.index).isna().sum()))


# ------------------------------------------------------------------ U2
def _features(t: dict) -> pd.DataFrame:
    s = t["students"].copy()
    X = pd.DataFrame(index=s.index)
    for c in ["sex", "programme", "special_support", "finnish_as_second_language", "home_language", "school_code"]:
        if c in s.columns:
            X[c] = s[c].astype(str)
    if "start_date" in s.columns:
        X["start_year"] = to_datetime(s.start_date).dt.year
        if "birth_date" in s.columns:
            X["age_at_start"] = (to_datetime(s.start_date) - to_datetime(s.birth_date)).dt.days / 365.25
    if "student_id" in s.columns:
        sid = s.student_id.astype(str)
        g = t.get("course_grades")
        if g is not None and "student_id" in g.columns and "grade" in g.columns:
            gg = _general_grades(g) if "course_code" in g.columns else g.assign(_g=_num_grade(g["grade"]))
            agg = gg.groupby(gg.student_id.astype(str))._g.agg(["mean", "size"])
            X["mean_grade"] = sid.map(agg["mean"]).values
            X["n_low_grades"] = sid.map(gg[gg._g <= 5].groupby(gg.student_id.astype(str)).size()).fillna(0).values
        a = t.get("absences")
        if a is not None and "student_id" in a.columns:
            for c in ("unexcused_hours", "late_arrivals", "excused_hours"):
                if c in a.columns:
                    X[c] = sid.map(pd.to_numeric(a[c], errors="coerce").groupby(a.student_id.astype(str)).sum()).values
    return X


def _fit_auc(Xtr, ytr, Xte, yte):
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.preprocessing import StandardScaler
    cols = [c for c in Xtr.columns if c in Xte.columns]
    Xtr, Xte = Xtr[cols], Xte[cols]
    num = [c for c in cols if pd.api.types.is_numeric_dtype(Xtr[c])]
    cat = [c for c in cols if c not in num]
    A = pd.get_dummies(Xtr[cat].astype(str), dtype=float) if cat else pd.DataFrame(index=Xtr.index)
    B = pd.get_dummies(Xte[cat].astype(str), dtype=float).reindex(columns=A.columns, fill_value=0.0) if cat else pd.DataFrame(index=Xte.index)
    med = Xtr[num].astype(float).median()
    sc = StandardScaler()
    A = np.hstack([A.values, sc.fit_transform(Xtr[num].astype(float).fillna(med).fillna(0))]) if num else A.values
    B = np.hstack([B.values, sc.transform(Xte[num].astype(float).fillna(med).fillna(0))]) if num else B.values
    if len(set(ytr)) < 2:
        return 0.5
    m = LogisticRegression(max_iter=2000, C=0.5).fit(A, ytr)
    return float(roc_auc_score(yte, m.predict_proba(B)[:, 1]))


def u2_dropout_model(orig, prot):
    ps = prot.get("students")
    miss = require(ps, ["status"])
    if miss:
        return not_answerable(miss)
    os_ = orig["students"]
    test = _test_mask(os_.student_id)
    Xo = _features(orig)
    yo = (os_.status == "dropped_out").astype(int).values
    Xp = _features(prot)
    yp = (ps.status.astype(str) == "dropped_out").astype(int).values
    keep = ~ps.student_id.astype(str).isin(set(os_.student_id[test])) if "student_id" in ps.columns else pd.Series(True, index=ps.index)
    auc_o = _fit_auc(Xo[~test.values], yo[~test.values], Xo[test.values], yo[test.values])
    auc_p = _fit_auc(Xp[keep.values], yp[keep.values], Xo[test.values], yo[test.values])
    return result((auc_p - .5) / max(auc_o - .5, 1e-6), "AUC retention (train protected, test original)",
                  auc_original=round(auc_o, 4), auc_protected=round(auc_p, 4), features=list(Xp.columns))


# ------------------------------------------------------------------ U3
def _maths_by_sex(t):
    g = t.get("course_grades")
    if g is None or "grade" not in g.columns or "course_code" not in g.columns:
        return None
    g = _general_grades(g)
    g = g[g._subj.isin(["MAA", "MAB", "MAY"])]
    if "sex" not in g.columns:
        s = t.get("students")
        if s is None or "student_id" not in g.columns or "student_id" not in s.columns or "sex" not in s.columns:
            return None
        g = g.assign(student_id=g.student_id.astype(str)).merge(s[["student_id", "sex"]].astype(str), on="student_id", how="inner")
    m = g.groupby(g.sex.astype(str))._g.mean()
    if "F" not in m or "M" not in m:
        return None
    return float(m["F"] - m["M"]), m.to_dict()


def u3_gender_gap_maths(orig, prot):
    o = _maths_by_sex(orig)
    q = _maths_by_sex(prot)
    if q is None:
        return not_answerable(["course_grades.course_code/grade + sex (via students.student_id)"])
    d = abs(o[0] - q[0])
    return result(1 - d / 0.3, "1 - |gap error| / 0.3 grade (gap = mean F - mean M, maths modules)", gap_original=round(o[0], 3),
                  gap_protected=round(q[0], 3))


# ------------------------------------------------------------------ U4
def _abs_grade_corr(t):
    g, a = t.get("course_grades"), t.get("absences")
    if g is None or a is None or "student_id" not in g.columns or "student_id" not in a.columns or "unexcused_hours" not in a.columns:
        return None
    gg = _general_grades(g)
    mg = gg.groupby(gg.student_id.astype(str))._g.mean()
    ab = pd.to_numeric(a.unexcused_hours, errors="coerce").groupby(a.student_id.astype(str)).sum()
    j = pd.concat([mg.rename("g"), ab.rename("a")], axis=1, join="inner").dropna()
    if len(j) < 30:
        return None
    return float(j.g.corr(j.a, method="spearman")), len(j)


def u4_absence_grade_corr(orig, prot):
    o = _abs_grade_corr(orig)
    q = _abs_grade_corr(prot)
    if q is None:
        return not_answerable(["student_id join between course_grades and absences", "absences.unexcused_hours"])
    return result(1 - abs(o[0] - q[0]) / 0.3, "1 - |Spearman r error| / 0.3", r_original=round(o[0], 4), r_protected=round(q[0], 4),
                  students_joined=q[1])


# ------------------------------------------------------------------ U5
def _matric_dist(m):
    col = "grade" if "grade" in m.columns else ("grade_points" if "grade_points" in m.columns else None)
    if col is None or "subject_code" not in m.columns:
        return None
    v = m[col].astype(str)
    if col == "grade_points":
        v = v.map({"7": "L", "6": "E", "5": "M", "4": "C", "3": "B", "2": "A", "0": "I"}).fillna(v)
    return pd.crosstab(m.subject_code.astype(str), v)


def u5_matric_distribution(orig, prot):
    p = prot.get("matriculation_results")
    if p is None:
        return not_answerable(["matriculation_results"])
    o, q = _matric_dist(orig["matriculation_results"]), _matric_dist(p)
    if q is None:
        return not_answerable(["subject_code", "grade or grade_points"])
    subs = o.index[o.sum(axis=1) >= 50]
    tv = []
    for s in subs:
        if s not in q.index:
            tv.append(1.0)
            continue
        a = o.loc[s] / o.loc[s].sum()
        b = q.loc[s].reindex(a.index, fill_value=0)
        b = b / b.sum() if b.sum() else b
        tv.append(float(.5 * (a - b).abs().sum() + .5 * q.loc[s].drop(a.index, errors="ignore").sum() / max(q.loc[s].sum(), 1)))
    m = float(np.mean(tv))
    return result(1 - m / 0.3, "1 - mean TVD of grade distribution per subject / 0.3", subjects=len(subs), mean_tvd=round(m, 4))


# ------------------------------------------------------------------ U6
def u6_dropout_by_programme(orig, prot):
    p = prot.get("students")
    miss = require(p, ["programme", "status"])
    if miss:
        return not_answerable(miss)
    o = orig["students"]
    ro = o.groupby("programme").status.agg(lambda s: (s == "dropped_out").mean())
    no = o.groupby("programme").size()
    ro = ro[no >= 20]
    rq = p.groupby(p.programme.astype(str)).status.agg(lambda s: (s.astype(str) == "dropped_out").mean())
    err = (ro - rq.reindex(ro.index)).abs().fillna(1.0)
    return result(1 - float(err.mean()) / 0.1, "1 - mean abs error of drop-out rate per programme / 0.10",
                  programmes=len(ro), mae=round(float(err.mean()), 4))


TASKS = [
    UtilityTask("EDU-U1", D, "course_grades", "Mean grade (4-10 scale) by school x subject", "aggregate", u1_mean_grade_school_subject,
                ["school_code", "course_code", "grade", "grade_scale"], ["EDU-S1", "EDU-S3"]),
    UtilityTask("EDU-U2", D, "students", "Drop-out prediction AUC: train on protected, test on original hold-out", "model", u2_dropout_model,
                ["students.*", "course_grades.student_id", "absences.student_id"], ["EDU-S2"]),
    UtilityTask("EDU-U3", D, "course_grades", "Gender gap in maths module grades", "relationship", u3_gender_gap_maths,
                ["course_code", "grade", "student_id", "students.sex"], ["EDU-S1", "EDU-S3"]),
    UtilityTask("EDU-U4", D, "absences", "Spearman correlation of unexcused absence hours with mean grade", "relationship",
                u4_absence_grade_corr, ["absences.student_id", "unexcused_hours", "course_grades.student_id", "grade"], ["EDU-S2"]),
    UtilityTask("EDU-U5", D, "matriculation_results", "Matriculation grade distribution by subject", "distribution",
                u5_matric_distribution, ["subject_code", "grade"], ["EDU-S1", "EDU-S3"]),
    UtilityTask("EDU-U6", D, "students", "Drop-out rate by programme", "aggregate", u6_dropout_by_programme, ["programme", "status"],
                ["EDU-S1"]),
]
