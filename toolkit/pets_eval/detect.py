"""Score the Detect step: a team's field classification against the field catalog.

Prediction CSV columns: dataset, table, column, privacy_role [, subtype]
privacy_role is one of ROLES. Columns present in the catalog but missing from the
prediction count as wrong (predicted role "missing").
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

ROLES = ["direct_identifier", "quasi_identifier", "sensitive_attribute", "technical_identifier", "free_text",
         "record_key", "non_sensitive"]
# roles whose miss is a privacy failure (used for the "sensitive recall" headline)
PROTECT_ROLES = ["direct_identifier", "quasi_identifier", "sensitive_attribute", "technical_identifier", "free_text"]


def _norm(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip().str.lower().str.replace(" ", "_").str.replace("-", "_")


def score_detection(pred: pd.DataFrame, catalog: pd.DataFrame, datasets: Optional[list] = None) -> dict:
    """Return per-role precision/recall/F1, macro-F1, accuracy, subtype accuracy, confusion matrix, errors."""
    cat = catalog.copy()
    if datasets:
        cat = cat[cat.dataset.isin(datasets)]
    key = ["dataset", "table", "column"]
    p = pred.copy()
    for k in key:
        if k not in p.columns:
            raise ValueError(f"prediction file lacks column '{k}'")
        p[k] = p[k].astype(str).str.strip()
    for k in key:
        cat[k] = cat[k].astype(str).str.strip()
    p = p.drop_duplicates(key, keep="last")
    m = cat.merge(p[key + [c for c in ("privacy_role", "subtype") if c in p.columns]], on=key, how="left",
                  suffixes=("", "_pred"))
    gold = _norm(m["privacy_role"])
    pr = _norm(m["privacy_role_pred"]) if "privacy_role_pred" in m else pd.Series("", index=m.index)
    pr = pr.replace("", "missing")
    per_role = {}
    f1s = []
    for r in ROLES:
        tp = int(((gold == r) & (pr == r)).sum())
        fp = int(((gold != r) & (pr == r)).sum())
        fn = int(((gold == r) & (pr != r)).sum())
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        if tp + fn > 0:
            f1s.append(f1)
        per_role[r] = {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4), "support": tp + fn}
    sens = gold.isin(PROTECT_ROLES)
    flagged = pr.isin(PROTECT_ROLES)
    out = {
        "n_fields": int(len(m)),
        "n_predicted": int((pr != "missing").sum()),
        "accuracy": round(float((gold == pr).mean()), 4) if len(m) else 0.0,
        "macro_f1": round(sum(f1s) / len(f1s), 4) if f1s else 0.0,
        "sensitive_recall": round(float((flagged & sens).sum() / max(sens.sum(), 1)), 4),
        "per_role": per_role,
        "confusion": pd.crosstab(gold, pr).to_dict(),
    }
    if "subtype" in m and "subtype_pred" in m:
        gs, ps = _norm(m["subtype"]).str.upper(), _norm(m["subtype_pred"]).str.upper()
        has = gs != ""
        out["subtype_accuracy"] = round(float((gs[has] == ps[has]).mean()), 4) if has.any() else None
    err = m[gold != pr][key + ["privacy_role"]].copy()
    err["predicted"] = pr[gold != pr].values
    out["errors"] = err.head(200).to_dict("records")
    return out
