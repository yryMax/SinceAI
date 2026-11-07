"""Utility tasks for the finance dataset (Saaristo Bank, Jul-Dec 2025).

Tables: customers, cards, card_transactions, transfers. Protected tables keep original column names for the
columns they keep. Card / IBAN pseudonyms only need to be consistent within the protected release.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import parse
from . import UtilityTask, not_answerable, result
from .energy import cluster_agreement

DS = "finance"
TX, TR, CA, CU = "card_transactions", "transfers", "cards", "customers"
_CACHE: dict = {}
CHANNELS = {"chip": 0, "contactless": 1, "ecom": 2}


def _dt(s):
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    out = pd.to_datetime(s, format="ISO8601", errors="coerce")
    if out.isna().sum() > s.isna().sum() + 0.01 * len(s):
        out = parse.to_datetime(s)
    return out


def _tx(tabs):
    t = tabs.get(TX)
    if t is None or "amount_eur" not in t.columns:
        return None
    if id(t) in _CACHE:
        return _CACHE[id(t)][1]
    d = pd.DataFrame({"amount": parse.parse_numeric(t.amount_eur)})
    d["ts"] = _dt(t.ts) if "ts" in t.columns else pd.NaT
    if "mcc" in t.columns:
        m = t.mcc.astype(str).str.replace(r"[^0-9]", "", regex=True)
        d["mcc2"] = m.str[:2].where(m.str.len() >= 2)
    for c in ("channel", "merchant_city", "merchant_country", "currency", "is_fraud", "card_pan"):
        if c in t.columns:
            d[c] = t[c].values
    if len(_CACHE) > 6:
        _CACHE.clear()
    _CACHE[id(t)] = (t, d)
    return d


def _has_time(d):
    return d is not None and d.ts.notna().any() and d.ts.dt.hour.nunique() > 1


# ---------------------------------------------------------------- U1 fraud model
def _features(d):
    X = pd.DataFrame(index=d.index)
    X["amount"] = d.amount
    X["log_amount"] = np.log1p(d.amount.clip(lower=0))
    timed = _has_time(d)
    X["hour"] = d.ts.dt.hour if timed else -1
    X["dow"] = d.ts.dt.dayofweek
    X["channel"] = d.channel.map(CHANNELS).fillna(3) if "channel" in d else 3
    X["mcc2"] = pd.to_numeric(d.mcc2, errors="coerce").fillna(-1) if "mcc2" in d else -1
    X["foreign"] = (d.merchant_country.astype(str) != "FI").astype(int) if "merchant_country" in d else -1
    X["fx"] = (d.currency.astype(str) != "EUR").astype(int) if "currency" in d else -1
    if "card_pan" in d and timed:
        hour_key = d.ts.dt.floor("h")
        X["card_tx_hour"] = d.groupby([d.card_pan, hour_key]).amount.transform("size")
        X["card_tx_day"] = d.groupby([d.card_pan, d.ts.dt.normalize()]).amount.transform("size")
        med = d.groupby(d.card_pan).amount.transform("median")
        X["amount_vs_card_median"] = d.amount / (med + 1)
        X["card_countries_day"] = d.groupby([d.card_pan, d.ts.dt.normalize()]).merchant_country.transform("nunique") if "merchant_country" in d else -1
    else:
        X["card_tx_hour"] = X["card_tx_day"] = X["amount_vs_card_median"] = X["card_countries_day"] = -1
    return X.fillna(-1)


def _fit_ap(train, test_X, test_y):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import average_precision_score
    y = parse.parse_numeric(train.is_fraud).fillna(0).astype(int)
    if y.sum() < 10:
        return np.nan
    X = _features(train)
    neg = np.where(y == 0)[0]
    rs = np.random.default_rng(0)
    keep = np.sort(np.concatenate([np.where(y == 1)[0], rs.choice(neg, min(len(neg), 120_000), replace=False)]))
    clf = HistGradientBoostingClassifier(max_iter=250, learning_rate=.08, random_state=0).fit(X.iloc[keep], y.iloc[keep])
    return float(average_precision_score(test_y, clf.predict_proba(test_X[X.columns])[:, 1]))


def u1_fraud(orig, prot):
    o, p = _tx(orig), _tx(prot)
    if p is None or "is_fraud" not in p:
        return not_answerable(["amount_eur", "is_fraud"])
    cut = pd.Timestamp("2025-11-01")
    o_tr, o_te = o[o.ts < cut], o[o.ts >= cut]
    te_X = _features(o).loc[o_te.index]
    te_y = parse.parse_numeric(o_te.is_fraud).fillna(0).astype(int)
    leak = False
    if p.ts.notna().any():
        p_tr = p[p.ts < cut]
    else:
        p_tr, leak = p, True
    ap_o = _fit_ap(o_tr, te_X, te_y)
    ap_p = _fit_ap(p_tr, te_X, te_y)
    if np.isnan(ap_p):
        return not_answerable(["≥10 labelled fraud rows in protected Jul-Oct"])
    return result(min(1.0, ap_p / ap_o), "PR-AUC(train protected Jul-Oct, test original Nov-Dec) / PR-AUC(train original)",
                  ap_protected=ap_p, ap_original=ap_o, possible_leakage=leak)


# ---------------------------------------------------------------- U2 spend table
def _spend_table(d):
    d = d.dropna(subset=["amount", "mcc2", "merchant_city", "ts"])
    return d.groupby([d.mcc2, d.merchant_city.astype(str), d.ts.dt.strftime("%Y-%m")]).amount.sum()


def u2_spend_mcc_region_month(orig, prot):
    o, p = _tx(orig), _tx(prot)
    if p is None or "mcc2" not in p or "merchant_city" not in p or not p.ts.notna().any():
        return not_answerable(["amount_eur", "mcc", "merchant_city", "ts (month)"])
    mape = parse.table_mape(_spend_table(o), _spend_table(p), min_count=1000)
    return result(parse.score_from_rel_error(mape, .5), "1 - MAPE/0.5 of spend by MCC group × city × month (cells ≥ 1,000 €)", mape=mape)


# ---------------------------------------------------------------- U3 payday
def _dom(d):
    d = d.dropna(subset=["amount", "ts"])
    s = d.groupby(d.ts.dt.day).amount.sum() / d.groupby(d.ts.dt.day).ts.apply(lambda x: x.dt.normalize().nunique())
    return s.reindex(range(1, 32)).fillna(0)


def u3_payday(orig, prot):
    o, p = _tx(orig), _tx(prot)
    if p is None or not p.ts.notna().any() or p.ts.dt.day.nunique() < 20:
        return not_answerable(["ts (day)", "amount_eur"])
    so, sp = _dom(o), _dom(p)
    corr = float(np.corrcoef(so.values, sp.values)[0, 1])
    upl = lambda s: s.loc[15:17].mean() / s.loc[10:12].mean()
    err = parse.rel_error(upl(so) - 1, upl(sp) - 1)
    return result(.5 * max(0.0, corr) + .5 * parse.score_from_rel_error(err, 1.0),
                  "0.5*corr(spend per day of month) + 0.5*(1 - rel.error of payday uplift (15-17 vs 10-12))",
                  corr=corr, uplift_orig=float(upl(so)), uplift_prot=float(upl(sp)))


# ---------------------------------------------------------------- U4 segmentation
def _card_feats(d, groups):
    d = d.dropna(subset=["amount", "card_pan"])
    g = d.groupby("card_pan")
    f = pd.DataFrame({"n": np.log1p(g.size()), "avg": np.log1p(g.amount.mean())})
    f["ecom"] = (d.channel.astype(str) == "ecom").groupby(d.card_pan).mean() if "channel" in d else 0
    if "mcc2" in d:
        share = d.groupby(["card_pan", "mcc2"]).amount.sum().unstack(fill_value=0)
        share = share.div(share.sum(axis=1) + 1e-9, axis=0)
        for gname in groups:
            f[f"m{gname}"] = share[gname] if gname in share else 0.0
    return f.fillna(0)


def u4_segmentation(orig, prot):
    from sklearn.preprocessing import StandardScaler
    o, p = _tx(orig), _tx(prot)
    if p is None or "card_pan" not in p:
        return not_answerable(["card_pan (any consistent pseudonym)", "amount_eur"])
    groups = o.groupby("mcc2").amount.sum().nlargest(8).index.tolist()
    fo, fp = _card_feats(o, groups), _card_feats(p, groups)
    fp = fp.reindex(columns=fo.columns, fill_value=0)
    if len(fp) < 50:
        return not_answerable(["≥50 cards"])
    sc = StandardScaler().fit(fo)
    r = cluster_agreement(sc.transform(fo), sc.transform(fp), 6)
    return result(r.pop("score"), "cluster agreement of card spending profiles (k=6)", **r)


# ---------------------------------------------------------------- U5 AML
def aml_flags(tr: pd.DataFrame) -> set:
    d = pd.DataFrame({"amt": parse.parse_numeric(tr.amount_eur), "ts": _dt(tr.booking_ts).dt.normalize(),
                      "src": tr.from_iban.astype(str), "dst": tr.to_iban.astype(str)})
    d = d.dropna(subset=["amt", "ts"])
    flags = set()
    s = d[(d.amt >= 9000) & (d.amt < 10000)].sort_values("ts")
    for src, x in s.groupby("src"):
        t = x.ts.values
        for i in range(len(t)):
            if ((t >= t[i]) & (t <= t[i] + np.timedelta64(7, "D"))).sum() >= 3:
                flags.add(("structuring", src))
                break
    inc = d.groupby("dst")
    out_by = d.groupby("src")
    for acc, x in inc:
        if acc not in out_by.groups or x.src.nunique() < 4:
            continue
        x = x.sort_values("ts")
        for t0 in x.ts.unique():
            win = x[(x.ts >= t0) & (x.ts <= t0 + pd.Timedelta(days=3))]
            if win.src.nunique() >= 4:
                o = out_by.get_group(acc)
                o = o[(o.ts >= t0) & (o.ts <= t0 + pd.Timedelta(days=4))]
                if o.amt.sum() >= .7 * win.amt.sum():
                    flags.add(("pass_through", acc))
                    break
    return flags


def u5_aml(orig, prot):
    o, p = orig.get(TR), prot.get(TR)
    need = ["amount_eur", "booking_ts", "from_iban", "to_iban"]
    if p is None or any(c not in p.columns for c in need):
        return not_answerable(need)
    fo, fp = aml_flags(o), aml_flags(p)
    co = pd.Series([f[0] for f in fo]).value_counts()
    cp = pd.Series([f[0] for f in fp], dtype=object).value_counts()
    errs = [parse.rel_error(co.get(k, 0), cp.get(k, 0)) for k in ("structuring", "pass_through")]
    return result(parse.score_from_rel_error(float(np.mean(errs)), 1.0),
                  "1 - mean relative error of flagged-account counts per AML rule (structuring, pass-through)",
                  flags_orig=co.to_dict(), flags_prot=cp.to_dict())


# ---------------------------------------------------------------- U6 spend by income x age
def _income_age(tabs):
    d, ca, cu = _tx(tabs), tabs.get(CA), tabs.get(CU)
    if d is None or ca is None or cu is None or "card_pan" not in d or "income_band" not in cu.columns:
        return None
    if not {"card_pan", "customer_id"} <= set(ca.columns) or "customer_id" not in cu.columns:
        return None
    if "birth_date" in cu.columns:
        age = parse.age_from_birth(cu.birth_date)
    elif "age" in cu.columns:
        age = parse.parse_numeric(cu.age)
    elif "age_band" in cu.columns:
        age = parse.parse_numeric(cu.age_band)
    else:
        return None
    cust = pd.DataFrame({"cid": cu.customer_id.astype(str), "inc": cu.income_band.astype(str), "ab": parse.to_age_band(age, 20, 60)})
    c2c = dict(zip(ca.card_pan.astype(str), ca.customer_id.astype(str)))
    spend = d.assign(cid=d.card_pan.astype(str).map(c2c)).dropna(subset=["cid"]).groupby("cid").amount.sum() / 6
    cust["spend"] = cust.cid.map(spend).fillna(0)
    g = cust.groupby(["inc", "ab"])
    return g.spend.mean()[g.size() >= 10]


def u6_income_age(orig, prot):
    so, sp = _income_age(orig), _income_age(prot)
    if sp is None:
        return not_answerable(["customers.income_band", "customers age/birth_date", "cards.customer_id", "cards.card_pan", "card_transactions.card_pan"])
    mape = parse.table_mape(so, sp)
    return result(parse.score_from_rel_error(mape, .5), "1 - MAPE/0.5 of mean monthly card spend by income band × age band (20 y)", mape=mape)


TASKS = [
    UtilityTask("FIN-U1", DS, TX, "Fraud model: train on protected Jul–Oct, test on original Nov–Dec (PR-AUC ratio)", "model", u1_fraud,
                ["ts", "amount_eur", "mcc", "channel", "merchant_country", "card_pan", "is_fraud"], ["FIN-S1", "FIN-S2"]),
    UtilityTask("FIN-U2", DS, TX, "Spend by MCC group × merchant city × month", "aggregate", u2_spend_mcc_region_month,
                ["ts", "amount_eur", "mcc", "merchant_city"], ["FIN-S3"]),
    UtilityTask("FIN-U3", DS, TX, "Payday effect: spend by day of month", "relationship", u3_payday, ["ts", "amount_eur"], ["FIN-S3"]),
    UtilityTask("FIN-U4", DS, TX, "Card spending-profile segmentation (k=6) agreement", "distribution", u4_segmentation,
                ["card_pan", "amount_eur", "mcc", "channel"], ["FIN-S2"]),
    UtilityTask("FIN-U5", DS, TR, "AML rule hits (structuring, rapid pass-through)", "detection", u5_aml,
                ["booking_ts", "amount_eur", "from_iban", "to_iban"], ["FIN-S1"]),
    UtilityTask("FIN-U6", DS, CU, "Mean monthly card spend by income band × age band", "relationship", u6_income_age,
                ["income_band", "birth_date", "customer_id", "card_pan"], ["FIN-S2", "FIN-S3"]),
]
