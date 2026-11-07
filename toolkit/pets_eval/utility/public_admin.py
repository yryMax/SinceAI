"""Utility tasks for the public administration dataset."""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from ..parse import latlon_to_grid, postcode_prefix, table_mape, to_datetime, to_month
from . import UtilityTask, not_answerable, require, result

D = "public_admin"


def _sr(t):
    return t.get("service_requests")


def _counts(df):
    m = to_month(df.ts_created)
    pc = postcode_prefix(df.postcode, 3)
    return pd.DataFrame({"pc": pc, "cat": df.category.astype(str), "m": m}).dropna().groupby(["pc", "cat", "m"]).size()


def u1_counts_area_cat_month(orig, prot):
    p = _sr(prot)
    miss = require(p, ["ts_created", "category", "postcode"])
    if miss:
        return not_answerable(miss)
    o, q = _counts(_sr(orig)), _counts(p)
    mape = table_mape(o, q, min_count=4)
    return result(1 - mape / 0.5, "1 - MAPE over (3-digit postcode, category, month) cells with n>=5 / 0.5",
                  cells=int((o > 4).sum()), mape=round(mape, 4))


def _res_hours(df):
    if "resolution_hours" in df.columns:
        h = pd.to_numeric(df.resolution_hours, errors="coerce")
    elif "ts_closed" in df.columns and "ts_created" in df.columns:
        h = (to_datetime(df.ts_closed) - to_datetime(df.ts_created)).dt.total_seconds() / 3600
    else:
        return None
    return h.groupby(df.category.astype(str)).median()


def u2_median_resolution(orig, prot):
    p = _sr(prot)
    if p is None or "category" not in p.columns:
        return not_answerable(["category"])
    q = _res_hours(p)
    if q is None:
        return not_answerable(["ts_created + ts_closed (or resolution_hours)"])
    o = _res_hours(_sr(orig))
    err = ((o - q.reindex(o.index)).abs() / o).fillna(1.0).clip(upper=1.0)
    return result(1 - float(err.mean()) / 0.5, "1 - mean relative error of median resolution hours per category / 0.5",
                  per_category=dict(zip(o.index, err.round(3))))


def _top_cells(df, n=50):
    g = latlon_to_grid(df.lat, df.lon, 1000).dropna()
    return set(g.value_counts().head(n).index)


def u3_hotspots(orig, prot):
    p = _sr(prot)
    miss = require(p, ["lat", "lon"])
    if miss:
        return not_answerable(miss)
    a, b = _top_cells(_sr(orig)), _top_cells(p)
    j = len(a & b) / max(len(a | b), 1)
    return result(j, "Jaccard overlap of top-50 1 km grid cells by request count", overlap=len(a & b))


def _test_mask(ids, pct=20):
    return ids.astype(str).map(lambda x: int(hashlib.sha256(x.encode()).hexdigest()[:8], 16) % 100 < pct)


def _clf_acc(train_text, train_y, test_text, test_y):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    v = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, max_features=60000, sublinear_tf=True)
    X = v.fit_transform(train_text.fillna("").astype(str))
    m = LogisticRegression(max_iter=1000, C=4.0).fit(X, train_y)
    return float((m.predict(v.transform(test_text.fillna("").astype(str))) == test_y).mean())


def u4_topic_classification(orig, prot):
    p = _sr(prot)
    miss = require(p, ["description", "category"])
    if miss:
        return not_answerable(miss)
    o = _sr(orig)
    test = _test_mask(o.request_id)
    acc_o = _clf_acc(o.description[~test], o.category[~test], o.description[test], o.category[test])
    keep = ~p.request_id.astype(str).isin(set(o.request_id[test])) if "request_id" in p.columns else pd.Series(True, index=p.index)
    acc_p = _clf_acc(p.description[keep], p.category[keep].astype(str), o.description[test], o.category[test])
    return result(acc_p / max(acc_o, 1e-9), "accuracy retention: classifier trained on protected text, tested on original hold-out",
                  acc_original=round(acc_o, 4), acc_protected=round(acc_p, 4))


def _repeat_share(df, col, k=5):
    x = df[col].astype(str)
    x = x[(x != "") & (x.str.lower() != "nan")]
    if len(x) == 0:
        return None
    c = x.map(x.value_counts())
    return float((c >= k).mean())


def u5_repeat_reporters(orig, prot):
    p = _sr(prot)
    miss = require(p, ["reporter_account_id"])
    if miss:
        return not_answerable(miss)
    o = _repeat_share(_sr(orig), "reporter_account_id")
    q = _repeat_share(p, "reporter_account_id")
    if q is None:
        return not_answerable(["reporter_account_id (all empty)"])
    return result(1 - abs(o - q) / 0.15, "1 - |error| / 0.15 in share of account requests from accounts with >=5 requests",
                  share_original=round(o, 4), share_protected=round(q, 4))


def _permit_counts(df):
    d = to_datetime(df.submitted_date)
    qtr = d.dt.year.astype("Int64").astype(str) + "Q" + d.dt.quarter.astype("Int64").astype(str)
    return pd.DataFrame({"m": df.municipality.astype(str), "t": df.project_type.astype(str), "q": qtr.where(d.notna())}).dropna().groupby(["m", "t", "q"]).size()


def u6_permits(orig, prot):
    p = prot.get("building_permits")
    miss = require(p, ["submitted_date", "municipality", "project_type"])
    if miss:
        return not_answerable(miss)
    o, q = _permit_counts(orig["building_permits"]), _permit_counts(p)
    mape = table_mape(o, q, min_count=4)
    return result(1 - mape / 0.5, "1 - MAPE over (municipality, project type, quarter) cells with n>=5 / 0.5", mape=round(mape, 4))


TASKS = [
    UtilityTask("PUB-U1", D, "service_requests", "Request counts by area (3-digit postcode) x category x month", "aggregate",
                u1_counts_area_cat_month, ["ts_created", "category", "postcode"], ["PUB-S1", "PUB-S2", "PUB-S3"]),
    UtilityTask("PUB-U2", D, "service_requests", "Median resolution time by category", "aggregate", u2_median_resolution,
                ["ts_created", "ts_closed", "category"], ["PUB-S1", "PUB-S2", "PUB-S3"]),
    UtilityTask("PUB-U3", D, "service_requests", "Hotspot map: top-50 1 km grid cells", "distribution", u3_hotspots, ["lat", "lon"],
                ["PUB-S1", "PUB-S3"]),
    UtilityTask("PUB-U4", D, "service_requests", "Category classifier trained on protected description text", "text",
                u4_topic_classification, ["description", "category"], ["PUB-S1"]),
    UtilityTask("PUB-U5", D, "service_requests", "Share of requests from repeat reporters (>=5 requests per account)", "relationship",
                u5_repeat_reporters, ["reporter_account_id"], ["PUB-S2"]),
    UtilityTask("PUB-U6", D, "building_permits", "Permit counts by municipality x project type x quarter", "aggregate", u6_permits,
                ["submitted_date", "municipality", "project_type"], ["PUB-S2"]),
]
