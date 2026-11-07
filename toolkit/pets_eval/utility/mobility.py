"""Utility tasks for the mobility dataset (Aura Transit taps, cards, city-bike trips).

Stops and bike stations are public infrastructure: tasks look up stop areas from the ORIGINAL
`stops` / `bike_stations` tables, so protected taps only need to keep `stop_id` (or an `area`
column). Aggregate-only releases: provide a table `od_matrix` with columns
origin_area, destination_area, hour_band, trips (weekday boardings, whole period).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..parse import parse_numeric, score_from_rel_error, table_mape, to_datetime, tvd
from . import UtilityTask, not_answerable, require, result

DATASET = "mobility"
HOUR_BANDS = [(0, 6, "00-06"), (6, 9, "06-09"), (9, 15, "09-15"), (15, 18, "15-18"), (18, 24, "18-24")]


def hour_band(h: pd.Series) -> pd.Series:
    out = pd.Series(np.nan, index=h.index, dtype=object)
    for lo, hi, lab in HOUR_BANDS:
        out[(h >= lo) & (h < hi)] = lab
    return out


def _with_area(taps: pd.DataFrame, stops: pd.DataFrame) -> pd.Series:
    if "area" in taps.columns:
        return taps["area"].astype(object)
    if "stop_id" in taps.columns:
        return taps["stop_id"].map(stops.set_index("stop_id")["area"])
    return None


def _journeys(taps: pd.DataFrame, stops: pd.DataFrame) -> pd.DataFrame | None:
    """Trip chaining: boardings of the same card within 60 min form one journey; destination of a
    journey = origin of the card's next journey that day (last journey -> first origin)."""
    if require(taps, ["card_id", "ts"]):
        return None
    area = _with_area(taps, stops)
    if area is None:
        return None
    d = pd.DataFrame({"card": taps["card_id"].astype(str), "ts": to_datetime(taps["ts"]), "area": area})
    if "fare_product" in taps.columns:
        d = d[taps["fare_product"].astype(str) != "double_tap"]
    d = d.dropna(subset=["ts", "area"])
    d = d[d.ts.dt.weekday < 5]
    d["day"] = d.ts.dt.date
    d = d.sort_values(["card", "ts"], kind="stable")
    gap = d.groupby(["card", "day"]).ts.diff().dt.total_seconds().fillna(1e9)
    d = d[gap > 3600]  # first boarding of each journey
    g = d.groupby(["card", "day"])
    d["dest"] = g.area.shift(-1)
    d["dest"] = d["dest"].fillna(g.area.transform("first"))
    d["hour_band"] = hour_band(d.ts.dt.hour)
    return d


def _od(orig, prot):
    st = orig["stops"]
    o = _journeys(orig["taps"], st)
    o = o.groupby(["area", "dest", "hour_band"]).size()
    if "od_matrix" in prot:
        m = prot["od_matrix"]
        if require(m, ["origin_area", "destination_area", "hour_band", "trips"]):
            return not_answerable(require(m, ["origin_area", "destination_area", "hour_band", "trips"]))
        p = m.groupby(["origin_area", "destination_area", "hour_band"]).trips.apply(lambda s: parse_numeric(s).sum())
        p.index.names = o.index.names
    else:
        pj = _journeys(prot.get("taps"), st) if "taps" in prot else None
        if pj is None:
            return not_answerable(["taps.card_id (any per-day pseudonym)", "taps.ts", "taps.stop_id or area"])
        p = pj.groupby(["area", "dest", "hour_band"]).size()
    e = table_mape(o, p, min_count=20)
    return result(score_from_rel_error(e, .5), "1 - MAPE/0.5 over OD cells with >=20 journeys", mape=e, cells=int((o > 20).sum()))


def _line_hour(orig, prot):
    t = prot.get("taps")
    miss = require(t, ["line", "ts"])
    if miss:
        return not_answerable(miss)

    def agg(df):
        ts = to_datetime(df["ts"])
        m = ts.dt.weekday < 5
        if "fare_product" in df.columns:
            m &= df["fare_product"].astype(str) != "double_tap"
        return df[m].groupby([df.loc[m, "line"].astype(str), ts[m].dt.hour]).size()

    e = table_mape(agg(orig["taps"]), agg(t), min_count=50)
    return result(score_from_rel_error(e, .5), "1 - MAPE/0.5 over line x hour cells with >=50 boardings", mape=e)


def _daily(orig, prot):
    t = prot.get("taps")
    if require(t, ["ts"]):
        return not_answerable(["taps.ts"])

    def agg(df):
        return df.groupby(to_datetime(df["ts"]).dt.date).size()

    e = table_mape(agg(orig["taps"]), agg(t))
    o, p = agg(orig["taps"]), agg(t).reindex(agg(orig["taps"]).index, fill_value=0)
    corr = float(np.corrcoef(o.values, p.values)[0, 1]) if p.std() > 0 else 0.0
    return result(score_from_rel_error(e, .3) * max(corr, 0), "(1 - MAPE/0.3) x Pearson r of daily boardings", mape=e, r=corr)


def _bike_duration(df):
    if "duration_s" in df.columns:
        d = parse_numeric(df["duration_s"])
    elif not require(df, ["start_ts", "end_ts"]):
        d = (to_datetime(df["end_ts"]) - to_datetime(df["start_ts"])).dt.total_seconds()
    else:
        return None
    return pd.cut(d / 60, bins=list(range(0, 62, 2)) + [1e9], right=False).value_counts()


def _duration(orig, prot):
    b = prot.get("bike_trips")
    if b is None:
        return not_answerable(["bike_trips"])
    p = _bike_duration(b)
    if p is None:
        return not_answerable(["bike_trips.duration_s or start_ts+end_ts"])
    t = tvd(_bike_duration(orig["bike_trips"]), p)
    return result(1 - 2 * t, "1 - 2*TVD of duration histogram (2-min bins)", tvd=t)


def _commute(orig, prot):
    def flows(taps):
        j = _journeys(taps, orig["stops"])
        if j is None:
            return None
        am = j[j.ts.dt.hour < 10].groupby(["card", "day"]).area.first()
        pm = j[j.ts.dt.hour >= 13].groupby(["card", "day"]).area.first()
        both = pd.concat([am.rename("home"), pm.rename("work")], axis=1).dropna()
        return both.groupby(["home", "work"]).size()

    t = prot.get("taps")
    p = flows(t) if t is not None else None
    if p is None:
        return not_answerable(["taps.card_id (per-day pseudonym is enough)", "taps.ts", "taps.stop_id or area"])
    e = table_mape(flows(orig["taps"]), p, min_count=10)
    return result(score_from_rel_error(e, .5), "1 - MAPE/0.5 over home-area x work-area card-day flows (>=10)", mape=e)


def _station(df, stations):
    if "start_station" in df.columns:
        s = df["start_station"].astype(object)
        if s.notna().any():
            return s
    if not require(df, ["start_lat", "start_lon"]):
        la, lo = parse_numeric(df["start_lat"]).values, parse_numeric(df["start_lon"]).values
        sl, so = stations.lat.values, stations.lon.values
        out = np.full(len(df), None, dtype=object)
        for i0 in range(0, len(df), 5000):
            d = np.hypot((la[i0:i0 + 5000, None] - sl[None]) * 111_320,
                         (lo[i0:i0 + 5000, None] - so[None]) * 55_000)
            k = d.argmin(1)
            ok = d[np.arange(len(k)), k] < 250
            out[i0:i0 + 5000] = np.where(ok, stations.station_id.values[k], None)
        return pd.Series(out, index=df.index)
    return None


def _zone_demand(orig, prot):
    b = prot.get("bike_trips")
    if b is None or require(b, ["start_ts"]):
        return not_answerable(["bike_trips.start_ts"])
    st = orig["bike_stations"]
    ps = _station(b, st)
    if ps is None:
        return not_answerable(["bike_trips.start_station or start_lat/start_lon"])
    ob = orig["bike_trips"]
    o = ob.groupby([ob["start_station"], hour_band(to_datetime(ob["start_ts"]).dt.hour)]).size()
    p = b.groupby([ps, hour_band(to_datetime(b["start_ts"]).dt.hour)]).size()
    e = table_mape(o, p, min_count=20)
    return result(score_from_rel_error(e, .5), "1 - MAPE/0.5 over zone x hour-band starts (>=20)", mape=e)


def _distance(df):
    if "distance_m" in df.columns:
        d = parse_numeric(df["distance_m"])
    elif not require(df, ["start_lat", "start_lon", "end_lat", "end_lon"]):
        la1, lo1 = parse_numeric(df["start_lat"]), parse_numeric(df["start_lon"])
        la2, lo2 = parse_numeric(df["end_lat"]), parse_numeric(df["end_lon"])
        d = np.hypot((la2 - la1) * 111_320, (lo2 - lo1) * 55_000) * 1.3
    else:
        return None
    return pd.cut(d, bins=list(range(0, 15001, 500)) + [1e12], right=False).value_counts()


def _bike_distance(orig, prot):
    b = prot.get("bike_trips")
    p = _distance(b) if b is not None else None
    if p is None:
        return not_answerable(["bike_trips.distance_m or coordinates"])
    t = tvd(_distance(orig["bike_trips"]), p)
    return result(1 - 2 * t, "1 - 2*TVD of ridden distance histogram (500 m bins)", tvd=t)


def _card_mix(orig, prot):
    c = prot.get("cards")
    if require(c, ["card_type"]):
        return not_answerable(["cards.card_type"])
    t = tvd(orig["cards"].card_type.value_counts(), c["card_type"].value_counts())
    return result(1 - 4 * t, "1 - 4*TVD of card-type mix", tvd=t)


TASKS = [
    UtilityTask("MOB-U1", DATASET, "taps", "Weekday OD matrix area x area x hour band (trip chaining)", "aggregate", _od,
                ["card_id", "ts", "stop_id"], ["MOB-S1", "MOB-S2"]),
    UtilityTask("MOB-U2", DATASET, "taps", "Weekday boardings by line x hour", "aggregate", _line_hour, ["line", "ts"], ["MOB-S1", "MOB-S2"]),
    UtilityTask("MOB-U3", DATASET, "taps", "Daily boardings time series (school break dip, weekends)", "aggregate", _daily, ["ts"], ["MOB-S1"]),
    UtilityTask("MOB-U4", DATASET, "bike_trips", "Bike trip duration distribution", "distribution", _duration,
                ["duration_s"], ["MOB-S2", "MOB-S3"]),
    UtilityTask("MOB-U5", DATASET, "taps", "Home-area -> work-area commuting flows (card-days)", "relationship", _commute,
                ["card_id", "ts", "stop_id"], ["MOB-S2"]),
    UtilityTask("MOB-U6", DATASET, "bike_trips", "Bike zone demand: starts by zone x hour band", "aggregate", _zone_demand,
                ["start_station|start_lat,start_lon", "start_ts"], ["MOB-S3"]),
    UtilityTask("MOB-U7", DATASET, "bike_trips", "Bike ridden-distance distribution", "distribution", _bike_distance,
                ["distance_m"], ["MOB-S3"]),
    UtilityTask("MOB-U8", DATASET, "cards", "Card-type mix (fare policy)", "distribution", _card_mix, ["card_type"], ["MOB-S3"]),
]


def trajectory_unicity(taps: pd.DataFrame, k: int = 4, time_res_min: int = 60, n_sample: int = 2000,
                       seed: int = 0, id_col: str = "card_id") -> float:
    """Share of sampled cards uniquely identified by k random (stop, time bucket) points of their own
    trajectory (de Montjoye et al. 2013). Run it on your protected taps with the same parameters."""
    d = pd.DataFrame({"id": taps[id_col].astype(str), "ts": to_datetime(taps["ts"]), "stop": taps["stop_id"].astype(str)})
    d = d.dropna()
    d["pt"] = d.stop + "@" + (d.ts.dt.floor(f"{time_res_min}min")).astype(str)
    sets = d.groupby("id").pt.apply(set)
    sets = sets[sets.map(len) >= k]
    if len(sets) == 0:
        return float("nan")
    rng = np.random.default_rng(seed)
    ids = rng.choice(sets.index.values, size=min(n_sample, len(sets)), replace=False)
    inv: dict = {}
    for i, s in sets.items():
        for p in s:
            inv.setdefault(p, set()).add(i)
    uniq = 0
    for i in ids:
        pts = rng.choice(sorted(sets[i]), size=k, replace=False)
        cand = set.intersection(*(inv[p] for p in pts))
        uniq += len(cand) == 1
    return uniq / len(ids)
