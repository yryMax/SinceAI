"""Utility tasks for the cyber dataset (Meridian Logistics SOC logs).

Most tasks run a small REFERENCE DETECTION RULE on the original and on the protected logs and
compare detection quality (F1 against the ground-truth `attack_label`). Score = F1(protected) /
F1(original), capped to [0, 1]. Labels are taken from the protected table's `attack_label` column if
kept, otherwise from the original table via the record key (event_id / alert_id / message_id).

The rules are deliberately simple and transparent; you can import them to check your own output:
    from pets_eval.utility.cyber import rule_impossible_travel, rule_password_spray, ...
"""
from __future__ import annotations

import ipaddress
from functools import lru_cache

import numpy as np
import pandas as pd

from ..parse import parse_numeric, to_datetime, tvd
from . import UtilityTask, not_answerable, require, result

DS = "cyber"
KEYS = {"signin_logs": "event_id", "vpn_logs": "event_id", "proxy_logs": "event_id", "dns_logs": "event_id",
        "edr_alerts": "alert_id", "email_gateway": "message_id", "incident_tickets": "ticket_id", "identity": "identity_id"}

# same synthetic geo database as data/cyber/geoip_ranges.csv
GEO = [("100.64.0.0/12", "FI", "Turku", 60.4518, 22.2666, "residential"), ("100.80.0.0/12", "FI", "Helsinki", 60.1699, 24.9384, "residential"),
       ("100.96.0.0/12", "FI", "Turku", 60.4518, 22.2666, "mobile"), ("100.112.0.0/12", "FI", "Tampere", 61.4978, 23.7610, "residential"),
       ("192.0.2.0/27", "FI", "Turku", 60.4880, 22.2770, "corporate"), ("192.0.2.32/27", "FI", "Raisio", 60.4858, 22.1690, "corporate"),
       ("192.0.2.64/27", "EE", "Tallinn", 59.4370, 24.7536, "hotel"), ("192.0.2.96/27", "SE", "Stockholm", 59.3293, 18.0686, "mobile"),
       ("192.0.2.128/25", "DE", "Frankfurt", 50.1109, 8.6821, "hosting"), ("198.51.100.0/25", "NL", "Amsterdam", 52.3676, 4.9041, "hosting"),
       ("198.51.100.128/25", "US", "Ashburn", 39.0438, -77.4874, "hosting"), ("203.0.113.0/26", "ES", "Madrid", 40.4168, -3.7038, "hotel"),
       ("203.0.113.64/26", "US", "New York", 40.7128, -74.0060, "hotel"), ("203.0.113.128/26", "SG", "Singapore", 1.3521, 103.8198, "hotel"),
       ("203.0.113.192/26", "NG", "Lagos", 6.5244, 3.3792, "mobile")]
_NETS = [(ipaddress.ip_network(g[0]), g) for g in GEO]
CITY = {(g[1], g[2]): (g[3], g[4]) for g in GEO}
CITY_ONLY = {g[2]: (g[3], g[4]) for g in GEO}


@lru_cache(maxsize=200_000)
def geo_lookup(ip: str):
    try:
        a = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return None
    for n, g in _NETS:
        if a in n:
            return g
    return None


def _s(df, c):
    return df[c].astype(str).where(df[c].notna(), "")


def _labels(prot: pd.DataFrame, orig: pd.DataFrame, table: str):
    if "attack_label" in prot.columns:
        return prot["attack_label"].fillna("").astype(str)
    k = KEYS[table]
    if k in prot.columns and k in orig.columns:
        m = dict(zip(orig[k].astype(str), orig["attack_label"].fillna("").astype(str)))
        return prot[k].astype(str).map(m).fillna("")
    return None


def _has(labels: pd.Series, techniques) -> pd.Series:
    pat = "|".join(t.replace(".", r"\.") + r"(?![\d.])" for t in techniques)
    return labels.str.contains(pat, regex=True)


def _f1(flag: pd.Series, truth: pd.Series):
    tp = int((flag & truth).sum())
    fp = int((flag & ~truth).sum())
    fn = int((~flag & truth).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return f, dict(tp=tp, fp=fp, fn=fn, precision=round(p, 3), recall=round(r, 3))


def _ratio(fo, fp, detail_o, detail_p, metric):
    if fo == 0:
        return result(None, metric, note="rule finds nothing on original", original=detail_o)
    return result(min(1.0, fp / fo), metric, f1_original=round(fo, 3), f1_protected=round(fp, 3), original=detail_o, protected=detail_p)


# ------------------------------------------------------------------ reference rules (return boolean masks)
def _location(df: pd.DataFrame):
    if {"geo_lat", "geo_lon"} <= set(df.columns):
        lat, lon = parse_numeric(df["geo_lat"]), parse_numeric(df["geo_lon"])
        if lat.notna().any():
            return lat, lon
    if "geo_city" in df.columns:
        if "geo_country" in df.columns:
            xy = [CITY.get((c, t)) for c, t in zip(_s(df, "geo_country"), _s(df, "geo_city"))]
        else:
            xy = [CITY_ONLY.get(t) for t in _s(df, "geo_city")]
        lat = pd.Series([x[0] if x else np.nan for x in xy], index=df.index)
        lon = pd.Series([x[1] if x else np.nan for x in xy], index=df.index)
        if lat.notna().any():
            return lat, lon
    if "src_ip" in df.columns:
        g = [geo_lookup(x) for x in _s(df, "src_ip")]
        return (pd.Series([x[3] if x else np.nan for x in g], index=df.index),
                pd.Series([x[4] if x else np.nan for x in g], index=df.index))
    return None


def rule_impossible_travel(signin: pd.DataFrame, speed_kmh: float = 900, min_km: float = 500) -> pd.Series:
    """Flag sign-ins whose location is > min_km from the user's previous SUCCESSFUL sign-in at > speed_kmh."""
    loc = _location(signin)
    flag = pd.Series(False, index=signin.index)
    if loc is None:
        return flag
    lat, lon = loc
    ts = to_datetime(signin["ts_utc"])
    df = pd.DataFrame({"u": _s(signin, "upn"), "ts": ts, "lat": lat, "lon": lon,
                       "ok": _s(signin, "result").eq("success")}).dropna(subset=["ts"])
    df = df.sort_values(["u", "ts"], kind="stable")
    for _, g in df.groupby("u", sort=False):
        last = None
        for idx, r in zip(g.index, g.itertuples()):
            if np.isnan(r.lat):
                continue
            if last is not None:
                dkm = _hav(last[1], last[2], r.lat, r.lon)
                dh = max((r.ts - last[0]).total_seconds() / 3600, 1 / 60)
                if dkm > min_km and dkm / dh > speed_kmh:
                    flag.at[idx] = True
            if r.ok:
                last = (r.ts, r.lat, r.lon)
    return flag


def _hav(la1, lo1, la2, lo2):
    p1, p2 = np.radians(la1), np.radians(la2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lo2 - lo1) / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))


def rule_mfa_fatigue(signin: pd.DataFrame, n: int = 5, window_min: int = 30) -> pd.Series:
    """>= n denied MFA prompts for one user within window, plus the approval that follows within the window."""
    flag = pd.Series(False, index=signin.index)
    df = pd.DataFrame({"u": _s(signin, "upn"), "ts": to_datetime(signin["ts_utc"]), "m": _s(signin, "mfa_result")}).dropna(subset=["ts"])
    den = df[df.m.eq("denied")]
    w = pd.Timedelta(minutes=window_min)
    for u, g in den.groupby("u"):
        t = g.ts.sort_values()
        for i in range(len(t)):
            j = t[(t >= t.iloc[i]) & (t <= t.iloc[i] + w)]
            if len(j) >= n:
                flag.loc[j.index] = True
                after = df[(df.u == u) & df.m.eq("approved") & (df.ts >= j.iloc[-1]) & (df.ts <= j.iloc[-1] + w)]
                flag.loc[after.index] = True
    return flag


def _prefix24(ip: pd.Series) -> pd.Series:
    s = ip.astype(str)
    return s.str.extract(r"^(\d+\.\d+\.\d+)\.")[0].fillna(s)


def rule_password_spray(signin: pd.DataFrame, min_users: int = 10) -> pd.Series:
    """Failures from one /24 (or one opaque source value) against >= min_users accounts within an hour."""
    df = pd.DataFrame({"src": _prefix24(_s(signin, "src_ip")), "u": _s(signin, "upn"), "ts": to_datetime(signin["ts_utc"]),
                       "fail": ~_s(signin, "result").eq("success")})
    df["h"] = df.ts.dt.floor("h")
    f = df[df.fail & df.ts.notna()]
    nu = f.groupby(["src", "h"]).u.transform("nunique")
    flag = pd.Series(False, index=signin.index)
    flag.loc[nu[nu >= min_users].index] = True
    return flag


def rule_exfil_volume(proxy: pd.DataFrame, threshold_bytes: float = 1e9, window: str = "4h") -> pd.Series:
    """Upload volume from one source to one domain above threshold within a window."""
    df = pd.DataFrame({"src": _s(proxy, "src_ip"), "d": _s(proxy, "domain"), "ts": to_datetime(proxy["ts_utc"]),
                       "b": parse_numeric(proxy["bytes_sent"]).fillna(0)})
    df["w"] = df.ts.dt.floor(window)
    tot = df.groupby(["src", "d", "w"]).b.transform("sum")
    return (tot > threshold_bytes) & df.ts.notna()


def rule_phish_click_chain(email: pd.DataFrame, proxy: pd.DataFrame, max_domain_msgs: int = 60, burst: int = 10):
    """Bulk mail from a rarely seen sender domain, followed within 24 h by recipients visiting that domain."""
    e = pd.DataFrame({"dom": _s(email, "sender").str.split("@").str[-1].str.lower(), "rcpt": _s(email, "recipients"),
                      "ts": to_datetime(email["ts_utc"]), "dir": _s(email, "direction") if "direction" in email else "inbound"})
    e = e[e.ts.notna()]
    cnt = e.groupby("dom").dom.transform("size")
    e["h"] = e.ts.dt.floor("h")
    bh = e.groupby(["dom", "h"]).dom.transform("size")
    sus = e[(cnt <= max_domain_msgs) & (bh >= burst)]
    eflag = pd.Series(False, index=email.index)
    eflag.loc[sus.index] = True
    pflag = pd.Series(False, index=proxy.index)
    if sus.empty:
        return eflag, pflag
    p = pd.DataFrame({"d": _s(proxy, "domain").str.lower(), "u": _s(proxy, "upn"), "ts": to_datetime(proxy["ts_utc"])})
    for dom, g in sus.groupby("dom"):
        rc = set(x for s in g.rcpt for x in s.split(";") if x)
        t0 = g.ts.min()
        m = (p.d.eq(dom) | p.d.str.endswith("." + dom)) & p.u.isin(rc) & (p.ts >= t0) & (p.ts <= t0 + pd.Timedelta(hours=24))
        pflag.loc[p[m].index] = True
    return eflag, pflag


def rule_vpn_new_country_then_server_alerts(vpn: pd.DataFrame, signin: pd.DataFrame | None, edr: pd.DataFrame):
    """VPN from a country never seen for that user, then high/critical alerts on servers within 24 h."""
    def country(df):
        if "geo_country" in df.columns:
            c = _s(df, "geo_country")
            if c.ne("").any():
                return c
        if "src_ip" in df.columns:
            return pd.Series([(geo_lookup(x) or (None, ""))[1] for x in _s(df, "src_ip")], index=df.index)
        return None
    vc = country(vpn)
    vflag = pd.Series(False, index=vpn.index)
    eflag = pd.Series(False, index=edr.index)
    if vc is None:
        return vflag, eflag
    v = pd.DataFrame({"u": _s(vpn, "upn"), "ts": to_datetime(vpn["ts_utc"]), "c": vc}).dropna(subset=["ts"]).sort_values("ts")
    hist = []
    if signin is not None and {"upn", "ts_utc"} <= set(signin.columns):
        sc = country(signin)
        if sc is not None:
            hist.append(pd.DataFrame({"u": _s(signin, "upn"), "ts": to_datetime(signin["ts_utc"]), "c": sc,
                                      "ok": _s(signin, "result").eq("success")}).query("ok")[["u", "ts", "c"]])
    hist.append(v[["u", "ts", "c"]])
    H = pd.concat(hist).dropna(subset=["ts"])
    H = H[H.c.ne("") & H.c.ne("--")]
    first_seen = H.groupby(["u", "c"]).ts.min()
    new_starts = []
    for idx, r in v.iterrows():
        if r.c in ("", "--", "FI"):
            continue
        fs = first_seen.get((r.u, r.c))
        if fs is not None and fs >= r.ts - pd.Timedelta(hours=1):
            vflag.at[idx] = True
            new_starts.append(r.ts)
    if new_starts and {"hostname", "severity", "ts_utc"} <= set(edr.columns):
        et = to_datetime(edr["ts_utc"])
        srv = ~_s(edr, "hostname").str.upper().str.startswith(("LT-", "WH-"))
        hi = _s(edr, "severity").isin(["high", "critical", "medium"]) & srv
        for t in new_starts:
            eflag |= hi & (et >= t) & (et <= t + pd.Timedelta(hours=24))
        # flag the whole VPN session rows from same user (connect + disconnect)
    return vflag, eflag


def rule_insider_bulk_download(proxy: pd.DataFrame, edr: pd.DataFrame | None, factor: float = 4.0, min_count: int = 100):
    p = pd.DataFrame({"u": _s(proxy, "upn"), "ts": to_datetime(proxy["ts_utc"]), "d": _s(proxy, "domain"), "m": _s(proxy, "method")})
    m = p.d.str.startswith("intra.") & p.m.eq("GET") & p.ts.notna()
    q = p[m].copy()
    q["day"] = q.ts.dt.floor("D")
    daily = q.groupby(["u", "day"]).size()
    med = daily.groupby(level=0).median()
    pflag = pd.Series(False, index=proxy.index)
    hot = [(u, d) for (u, d), n in daily.items() if n >= min_count and n > factor * max(med[u], 1)]
    if hot:
        hk = set(hot)
        sel = [i for i, u, d in zip(q.index, q.u, q.day) if (u, d) in hk]
        pflag.loc[sel] = True
    eflag = None
    if edr is not None and "rule_name" in edr.columns:
        eflag = _s(edr, "rule_name").str.contains("removable", case=False)
    return pflag, eflag


# ------------------------------------------------------------------ task wrappers
def _single(table, cols, rule, techniques, metric):
    def fn(orig, prot):
        o, p = orig.get(table), prot.get(table)
        miss = require(p, cols)
        if miss:
            return not_answerable(miss)
        lo, lp = _labels(o, o, table), _labels(p, o, table)
        if lp is None:
            return not_answerable([KEYS[table] + " or attack_label"])
        fo, do = _f1(rule(o), _has(lo, techniques))
        fp, dp = _f1(rule(p), _has(lp, techniques))
        return _ratio(fo, fp, do, dp, metric)
    return fn


def _u5(orig, prot):
    need = {"email_gateway": ["sender", "recipients", "ts_utc"], "proxy_logs": ["domain", "upn", "ts_utc"]}
    miss = [f"{t}.{c}" for t, cs in need.items() for c in require(prot.get(t), cs)]
    if miss:
        return not_answerable(miss)
    res = []
    for src in (orig, prot):
        e, p = src["email_gateway"], src["proxy_logs"]
        le, lp = _labels(e, orig["email_gateway"], "email_gateway"), _labels(p, orig["proxy_logs"], "proxy_logs")
        if le is None or lp is None:
            return not_answerable(["event_id/message_id or attack_label"])
        ef, pf = rule_phish_click_chain(e, p)
        flag = pd.concat([ef, pf], ignore_index=True)
        truth = pd.concat([_has(le, ["T1566.002"]), _has(lp, ["T1204.001", "T1566.002"])], ignore_index=True)
        res.append(_f1(flag, truth))
    return _ratio(res[0][0], res[1][0], res[0][1], res[1][1], "F1 ratio, phishing e-mail -> click chain (joins e-mail and proxy)")


def _u6(orig, prot):
    need = {"vpn_logs": ["upn", "ts_utc"], "edr_alerts": ["hostname", "severity", "ts_utc"]}
    miss = [f"{t}.{c}" for t, cs in need.items() for c in require(prot.get(t), cs)]
    if miss:
        return not_answerable(miss)
    res = []
    for src in (orig, prot):
        v, e = src["vpn_logs"], src["edr_alerts"]
        lv, le = _labels(v, orig["vpn_logs"], "vpn_logs"), _labels(e, orig["edr_alerts"], "edr_alerts")
        if lv is None or le is None:
            return not_answerable(["event_id/alert_id or attack_label"])
        vf, ef = rule_vpn_new_country_then_server_alerts(v, src.get("signin_logs"), e)
        flag = pd.concat([vf, ef], ignore_index=True)
        truth = pd.concat([_has(lv, ["T1133"]), _has(le, ["T1021.002", "T1003.001", "T1078.002", "T1560.001"])], ignore_index=True)
        res.append(_f1(flag, truth))
    return _ratio(res[0][0], res[1][0], res[0][1], res[1][1], "F1 ratio, foreign VPN -> server alerts (lateral movement)")


def _u7(orig, prot):
    miss = require(prot.get("proxy_logs"), ["upn", "ts_utc", "domain", "method"])
    if miss:
        return not_answerable(miss)
    res = []
    for src in (orig, prot):
        p, e = src["proxy_logs"], src.get("edr_alerts")
        lp = _labels(p, orig["proxy_logs"], "proxy_logs")
        if lp is None:
            return not_answerable(["event_id or attack_label"])
        pf, ef = rule_insider_bulk_download(p, e)
        flags, truths = [pf], [_has(lp, ["T1213"])]
        if ef is not None:
            le = _labels(e, orig["edr_alerts"], "edr_alerts")
            if le is not None:
                flags.append(ef)
                truths.append(_has(le, ["T1052.001"]))
        res.append(_f1(pd.concat(flags, ignore_index=True), pd.concat(truths, ignore_index=True)))
    return _ratio(res[0][0], res[1][0], res[0][1], res[1][1], "F1 ratio, insider bulk download / removable media")


def _iocs(orig):
    s = orig["signin_logs"]
    lab = s.attack_label.fillna("").astype(str).ne("")
    ips = set(_s(s[lab], "src_ip"))
    v = orig["vpn_logs"]
    lv = v.attack_label.fillna("").astype(str).ne("")
    ips |= set(_s(v[lv], "src_ip"))
    ips = {i for i in ips if (geo_lookup(i) or (0, 0, 0, 0, 0, "internal"))[5] in ("hosting", "mobile", "hotel") and not i.startswith("10.")}
    p = orig["proxy_logs"]
    lp = p.attack_label.fillna("").astype(str).ne("") & _s(p, "category").str.startswith("Uncategorized")
    doms = set(_s(p[lp], "domain"))
    devs = set(_s(v[lv], "device_name")) - {""}
    uas = set(_s(s[lab], "user_agent")) - {""}
    return {"src_ip": ips, "domain": doms, "device_name": devs, "user_agent": uas}


def _u8(orig, prot):
    ioc = _iocs(orig)
    found, total = 0, 0
    detail = {}
    for col, vals in ioc.items():
        present = set()
        for t, df in prot.items():
            if df is not None and col in df.columns:
                present |= set(_s(df, col))
        hit = len(vals & present)
        detail[col] = f"{hit}/{len(vals)}"
        found += hit
        total += len(vals)
    return result(found / total if total else None, "share of attacker IoCs kept verbatim", **detail)


JOIN_COLS = [("signin_logs", "upn"), ("vpn_logs", "upn"), ("proxy_logs", "upn"), ("edr_alerts", "upn"), ("email_gateway", "sender"),
             ("incident_tickets", "reporter_upn")]


def _u9(orig, prot, n_pairs: int = 4000):
    frames = []
    for t, c in JOIN_COLS:
        o, p = orig.get(t), prot.get(t)
        k = KEYS[t]
        if p is None or c not in p.columns or k not in p.columns:
            continue
        m = pd.DataFrame({"k": p[k].astype(str), "pv": _s(p, c)}).merge(
            pd.DataFrame({"k": o[k].astype(str), "ov": _s(o, c)}), on="k")
        m = m[m.ov.str.endswith("@meridian-logistics.example")]
        if len(m):
            frames.append(m.assign(t=t).sample(min(len(m), 30000), random_state=0))
    if len(frames) < 2:
        return not_answerable(["record keys + user columns in at least two log tables"])
    A = pd.concat(frames, ignore_index=True)
    rng = np.random.default_rng(0)
    groups = A.groupby("ov").indices
    multi = [g for g in groups.values() if len(set(A.t.values[g])) > 1]
    pos, neg = [], []
    for _ in range(n_pairs):
        g = multi[int(rng.integers(len(multi)))]
        i, j = rng.choice(g, 2, replace=True)
        if A.t.values[i] == A.t.values[j]:
            continue
        pos.append(A.pv.values[i] == A.pv.values[j])
        a, b = rng.integers(len(A), size=2)
        if A.ov.values[a] != A.ov.values[b]:
            neg.append(A.pv.values[a] != A.pv.values[b])
    pr, nr = float(np.mean(pos)), float(np.mean(neg))
    return result(pr * nr, "same user -> same pseudonym across tables x different users -> different pseudonyms",
                  same_user_same_value=round(pr, 3), different_users_different_value=round(nr, 3), tables=sorted(set(A.t)))


def _u10(orig, prot):
    miss = require(prot.get("signin_logs"), ["ts_utc"])
    if miss:
        return not_answerable(miss)
    o = to_datetime(orig["signin_logs"]["ts_utc"]).dt.floor("h").value_counts()
    p = to_datetime(prot["signin_logs"]["ts_utc"]).dt.floor("h").value_counts()
    return result(1 - tvd(o, p), "1 - TVD of hourly sign-in volume")


def _u11(orig, prot):
    cols = ["rule_name", "analyst_verdict", "severity"]
    miss = require(prot.get("edr_alerts"), cols)
    if miss:
        return not_answerable(miss)
    key = lambda df: df[cols].astype(str).agg("|".join, axis=1).value_counts()  # noqa: E731
    return result(1 - tvd(key(orig["edr_alerts"]), key(prot["edr_alerts"])), "1 - TVD of (rule, verdict, severity) distribution")


TASKS = [
    UtilityTask("CYBER-U1", DS, "signin_logs", "Impossible-travel detection on sign-ins (reference rule, F1 vs labels T1078.004/T1621).",
                "detection", _single("signin_logs", ["upn", "ts_utc", "result"], rule_impossible_travel, ["T1078.004", "T1621"],
                                     "F1 ratio, impossible travel"), ["upn", "ts_utc", "result", "geo_lat/geo_lon or geo_city or src_ip"],
                ["CYBER-S1", "CYBER-S3"]),
    UtilityTask("CYBER-U2", DS, "signin_logs", "MFA-fatigue detection: >=5 denied pushes in 30 min then approval (labels T1621).",
                "detection", _single("signin_logs", ["upn", "ts_utc", "mfa_result"], rule_mfa_fatigue, ["T1621"], "F1 ratio, MFA fatigue"),
                ["upn", "ts_utc", "mfa_result"], ["CYBER-S1", "CYBER-S3"]),
    UtilityTask("CYBER-U3", DS, "signin_logs", "Password-spray detection: failures from one /24 against >=10 accounts per hour (T1110.003).",
                "detection", _single("signin_logs", ["upn", "ts_utc", "result", "src_ip"], rule_password_spray, ["T1110.003"],
                                     "F1 ratio, password spray"), ["src_ip", "upn", "ts_utc", "result"], ["CYBER-S1", "CYBER-S2", "CYBER-S3"]),
    UtilityTask("CYBER-U4", DS, "proxy_logs", "Exfiltration detection: >1 GB uploaded from one source to one domain within 4 h (T1567.002).",
                "detection", _single("proxy_logs", ["src_ip", "domain", "ts_utc", "bytes_sent"], rule_exfil_volume, ["T1567.002"],
                                     "F1 ratio, exfiltration volume"), ["src_ip", "domain", "ts_utc", "bytes_sent"], ["CYBER-S1", "CYBER-S2"]),
    UtilityTask("CYBER-U5", DS, "email_gateway+proxy_logs", "Phishing chain: bulk mail from a rare domain followed by recipients' clicks (needs consistent user pseudonyms across e-mail and proxy).",
                "detection", _u5, ["email_gateway.sender/recipients/ts_utc", "proxy_logs.domain/upn/ts_utc"], ["CYBER-S1", "CYBER-S3"]),
    UtilityTask("CYBER-U6", DS, "vpn_logs+edr_alerts", "Lateral movement: VPN from a never-seen country followed by server alerts within 24 h.",
                "detection", _u6, ["vpn_logs.upn/ts_utc/geo_country or src_ip", "edr_alerts.hostname/severity/ts_utc"], ["CYBER-S1", "CYBER-S3"]),
    UtilityTask("CYBER-U7", DS, "proxy_logs+edr_alerts", "Insider: per-user daily intranet downloads > 4x own median (and >=100) plus removable-media alerts.",
                "detection", _u7, ["proxy_logs.upn/ts_utc/domain/method", "edr_alerts.rule_name"], ["CYBER-S1"]),
    UtilityTask("CYBER-U8", DS, "*", "Indicators of compromise (attacker IPs, phishing domain, attacker device, tool user agents) kept verbatim for sharing.",
                "aggregate", _u8, ["src_ip", "domain", "device_name", "user_agent"], ["CYBER-S2"]),
    UtilityTask("CYBER-U9", DS, "*", "Cross-log join consistency of user identifiers (keyed pseudonyms pass, random tokens fail).",
                "relationship", _u9, ["record keys", "upn/sender/reporter_upn"], ["CYBER-S1", "CYBER-S3"]),
    UtilityTask("CYBER-U10", DS, "signin_logs", "Sign-in volume by hour (capacity / anomaly baselines).", "distribution", _u10, ["ts_utc"],
                ["CYBER-S1", "CYBER-S3"]),
    UtilityTask("CYBER-U11", DS, "edr_alerts", "Alert triage statistics: distribution of rule x verdict x severity.", "distribution", _u11,
                ["rule_name", "analyst_verdict", "severity"], ["CYBER-S1"]),
]
