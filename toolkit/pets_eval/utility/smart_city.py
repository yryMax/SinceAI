"""Utility tasks for the smart-city dataset (Wi-Fi probes, footfall, ANPR car parks).

Sensors are public infrastructure: zone look-ups use the ORIGINAL `sensors` table. Protected
footfall may keep `sensor_id` or replace it with `zone`; counts may be noisy, rounded or
suppressed ('<5', blank)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..parse import parse_numeric, rel_error, score_from_rel_error, table_mape, to_datetime, tvd
from . import UtilityTask, not_answerable, require, result

DATASET = "smart_city"
BF, REF_FRI = "2025-11-28", "2025-11-21"
PERIOD_END = pd.Timestamp("2025-12-01")


def _footfall(orig, prot):
    """Footfall as (zone, time) -> count, from footfall_15min or derived from wifi_probes."""
    zone = orig["sensors"].set_index("sensor_id")["zone"]
    f = prot.get("footfall_15min")
    if f is not None and "device_count" in f.columns and ("interval_start" in f.columns):
        z = f["zone"] if "zone" in f.columns else (f["sensor_id"].map(zone) if "sensor_id" in f.columns else None)
        if z is not None:
            c = parse_numeric(f["device_count"])
            return pd.DataFrame({"zone": z, "t": to_datetime(f["interval_start"]), "n": c.where(c >= 0)})
    w = prot.get("wifi_probes")
    if w is not None and not require(w, ["sensor_id", "ts", "mac"]):
        t = to_datetime(w["ts"]).dt.floor("15min")
        g = pd.DataFrame({"s": w["sensor_id"], "t": t, "m": w["mac"]}).groupby(["s", "t"]).m.nunique().reset_index()
        return pd.DataFrame({"zone": g.s.map(zone), "t": g.t, "n": g.m.astype(float)})
    return None


def _zone_hour(orig, prot):
    o, p = _footfall(orig, orig), _footfall(orig, prot)
    if p is None:
        return not_answerable(["footfall_15min (sensor_id|zone, interval_start, device_count) or wifi_probes (sensor_id, ts, mac)"])

    def agg(d):
        d = d.dropna(subset=["t"])
        dt = np.where(d.t.dt.weekday < 5, "weekday", "weekend")
        return d.groupby([d.zone, d.t.dt.hour, dt]).n.sum(min_count=1).fillna(0)

    e = table_mape(agg(o), agg(p), min_count=30)
    return result(score_from_rel_error(e, .5), "1 - MAPE/0.5 over zone x hour x day-type footfall (cells >=30)", mape=e)


def _dwell_hist(w):
    d = pd.DataFrame({"m": w["mac"].astype(str), "t": to_datetime(w["ts"])}).dropna()
    d["day"] = d.t.dt.date
    g = d.groupby(["m", "day"]).t.agg(["min", "max", "count"])
    g = g[g["count"] >= 2]
    span = (g["max"] - g["min"]).dt.total_seconds() / 60
    return pd.cut(span, [0, 5, 15, 30, 60, 120, 240, 600, 1e9], right=False).value_counts()


def _dwell(orig, prot):
    w = prot.get("wifi_probes")
    if require(w, ["mac", "ts"]):
        return not_answerable(["wifi_probes.mac (per-day pseudonym is enough)", "wifi_probes.ts"])
    t = tvd(_dwell_hist(orig["wifi_probes"]), _dwell_hist(w))
    return result(1 - 2 * t, "1 - 2*TVD of per-device-day dwell span histogram", tvd=t)


def _intervals(a):
    t0 = to_datetime(a["entry_ts"])
    if "exit_ts" in a.columns:
        t1 = to_datetime(a["exit_ts"]).fillna(PERIOD_END)
    elif "duration_h" in a.columns:
        t1 = t0 + pd.to_timedelta(parse_numeric(a["duration_h"]), unit="h")
    else:
        return None
    return pd.DataFrame({"cp": a["car_park"].values, "t0": t0.values, "t1": t1.values}).dropna()


def _occupancy(orig, prot):
    a = prot.get("anpr_parking")
    if require(a, ["car_park", "entry_ts"]):
        return not_answerable(["anpr_parking.car_park", "anpr_parking.entry_ts", "exit_ts or duration_h"])

    def occ(df):
        iv = _intervals(df)
        if iv is None:
            return None
        hours = pd.date_range("2025-11-17", "2025-11-30 23:00", freq="h")
        out = {}
        for cp, g in iv.groupby("cp"):
            s0 = np.searchsorted(np.sort(g.t0.values), hours.values + np.timedelta64(30, "m"))
            s1 = np.searchsorted(np.sort(g.t1.values), hours.values + np.timedelta64(30, "m"))
            ser = pd.Series(s0 - s1, index=hours)
            for h, v in ser.groupby(ser.index.hour).mean().items():
                out[(cp, h)] = v
        return pd.Series(out)

    p = occ(a)
    if p is None:
        return not_answerable(["anpr_parking.exit_ts or duration_h"])
    e = table_mape(occ(orig["anpr_parking"]), p, min_count=5)
    return result(score_from_rel_error(e, .5), "1 - MAPE/0.5 of mean occupancy by car park x hour", mape=e)


def _repeat(orig, prot):
    a = prot.get("anpr_parking")
    if require(a, ["plate", "entry_ts"]):
        return not_answerable(["anpr_parking.plate (pseudonym consistent across days)", "entry_ts"])

    def share(df):
        d = pd.DataFrame({"p": df["plate"].astype(str), "d": to_datetime(df["entry_ts"]).dt.date})
        n = d.groupby("p").d.nunique()
        return float((n >= 2).mean())

    o, p = share(orig["anpr_parking"]), share(a)
    e = rel_error(o, p)
    return result(score_from_rel_error(e, .3), "1 - relerr/0.3 of share of plates seen on >=2 days", orig=o, prot=p)


def _bf(orig, prot):
    p = _footfall(orig, prot)
    if p is None:
        return not_answerable(["footfall_15min or wifi_probes"])

    def uplift(d):
        day = d.t.dt.strftime("%Y-%m-%d")
        a, b = d.n[day == BF].sum(), d.n[day == REF_FRI].sum()
        return float(a / b) if b else np.nan

    o, q = uplift(_footfall(orig, orig)), uplift(p)
    e = rel_error(o, q) if not np.isnan(q) else np.nan
    return result(score_from_rel_error(e, .3), "1 - relerr/0.3 of Black Friday / previous Friday footfall ratio", orig=o, prot=q)


def _dur_hist(a):
    iv = _intervals(a)
    if iv is None:
        return None
    h = (iv.t1 - iv.t0).dt.total_seconds() / 3600
    return pd.cut(h, [0, .5, 1, 2, 3, 5, 8, 12, 1e9], right=False).value_counts()


def _duration(orig, prot):
    a = prot.get("anpr_parking")
    if require(a, ["entry_ts", "car_park"]):
        return not_answerable(["anpr_parking.entry_ts", "exit_ts or duration_h"])
    p = _dur_hist(a)
    if p is None:
        return not_answerable(["anpr_parking.exit_ts or duration_h"])
    t = tvd(_dur_hist(orig["anpr_parking"]), p)
    return result(1 - 2 * t, "1 - 2*TVD of parking duration histogram", tvd=t)


TASKS = [
    UtilityTask("CITY-U1", DATASET, "footfall_15min", "Footfall by zone x hour x weekday/weekend", "aggregate", _zone_hour,
                ["sensor_id|zone", "interval_start", "device_count"], ["CITY-S1", "CITY-S2"]),
    UtilityTask("CITY-U2", DATASET, "wifi_probes", "Dwell-time distribution per device-day", "distribution", _dwell,
                ["mac", "ts"], ["CITY-S2"]),
    UtilityTask("CITY-U3", DATASET, "anpr_parking", "Mean car-park occupancy by hour of day", "aggregate", _occupancy,
                ["car_park", "entry_ts", "exit_ts"], ["CITY-S2", "CITY-S3"]),
    UtilityTask("CITY-U4", DATASET, "anpr_parking", "Share of repeat visitors (plates seen on >=2 days)", "relationship", _repeat,
                ["plate", "entry_ts"], ["CITY-S2"]),
    UtilityTask("CITY-U5", DATASET, "footfall_15min", "Black Friday uplift vs previous Friday", "aggregate", _bf,
                ["interval_start", "device_count"], ["CITY-S1", "CITY-S2"]),
    UtilityTask("CITY-U6", DATASET, "anpr_parking", "Parking duration distribution", "distribution", _duration,
                ["entry_ts", "exit_ts"], ["CITY-S2"]),
]
