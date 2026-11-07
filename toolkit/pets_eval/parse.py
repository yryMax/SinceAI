"""Tolerant parsers so utility tasks still work on generalised / protected values.

Accepted generalised forms (document these to teams):
- ages: 37 | "37" | "30-39" | "30–39" | "[30,40)" | "30+" | "90+" -> band midpoint or band label
- dates/timestamps: ISO date/time, rounded times, "2025-03" (month), "2025-W12" (ISO week), "2025" (year)
- postcodes: "20100" | "201**" | "201" | "20100-20199"
- coordinates: floats with any precision; grid cell ids from latlon_to_grid
- numbers: 12.5 | "12,5" | "10-20" (range -> midpoint) | "<5" (-> 2.5 for counts) | "" -> NaN
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

_RANGE = re.compile(r"^\s*[\[(]?\s*(-?\d+(?:[.,]\d+)?)\s*(?:-|–|,|\.\.)\s*(-?\d+(?:[.,]\d+)?)\s*[\])]?\s*$")
_PLUS = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*\+\s*$")
_LT = re.compile(r"^\s*<\s*(\d+(?:[.,]\d+)?)\s*$")


def parse_numeric(s: pd.Series, open_upper_width: float = 10.0) -> pd.Series:
    """Numbers, ranges ('10-20' -> 15), open ranges ('90+' -> 95), '<5' -> 2.5."""
    if pd.api.types.is_numeric_dtype(s):
        return s.astype(float)

    def one(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return np.nan
        t = str(v).strip()
        if t == "" or t.lower() in ("nan", "none", "null", "*", "suppressed"):
            return np.nan
        try:
            return float(t.replace(",", ".").replace(" ", ""))
        except ValueError:
            pass
        m = _RANGE.match(t)
        if m:
            lo, hi = float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
            if t.startswith("[") and t.endswith(")"):
                hi -= 1e-9
            return (lo + hi) / 2
        m = _PLUS.match(t)
        if m:
            return float(m.group(1).replace(",", ".")) + open_upper_width / 2
        m = _LT.match(t)
        if m:
            return float(m.group(1).replace(",", ".")) / 2
        return np.nan

    return s.map(one).astype(float)


def to_age_band(s: pd.Series, width: int = 10, top: int = 80) -> pd.Series:
    """Map exact ages or any band notation to canonical bands '0-9', '10-19', ..., '80+'."""
    x = parse_numeric(s)
    lo = (np.floor(x / width) * width).clip(upper=top)
    lab = lo.map(lambda v: "" if np.isnan(v) else (f"{int(v)}+" if v >= top else f"{int(v)}-{int(v) + width - 1}"))
    return lab.replace("", np.nan)


def age_from_birth(s: pd.Series, ref: str = "2025-12-31") -> pd.Series:
    d = to_date(s)
    return ((pd.Timestamp(ref) - d).dt.days / 365.25).astype(float)


def _week_to_date(t: str):
    m = re.match(r"^(\d{4})-?W(\d{1,2})$", t)
    if m:
        return pd.Timestamp.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
    return None


def to_datetime(s: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(s):
        return s

    def one(v):
        if v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "":
            return pd.NaT
        t = str(v).strip()
        w = _week_to_date(t)
        if w is not None:
            return w
        if re.match(r"^\d{4}$", t):
            return pd.Timestamp(f"{t}-01-01")
        if re.match(r"^\d{4}-\d{2}$", t):
            return pd.Timestamp(f"{t}-01")
        try:
            return pd.Timestamp(t)
        except (ValueError, TypeError):
            return pd.NaT

    out = pd.to_datetime(s, errors="coerce", format="ISO8601")  # fast path for ISO values
    if out.isna().sum() > s.isna().sum():
        rest = s.where(out.isna()).astype("string")
        # Finnish day-first dates: 4.3.2025 / 04.03.2025 [12:30]
        rest = rest.str.replace(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+(?:klo\s+)?(\d{1,2})[.:](\d{2}))?",
                                lambda m: f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
                                + (f" {int(m.group(4)):02d}:{m.group(5)}" if m.group(4) else ""), regex=True)
        out2 = pd.to_datetime(rest, errors="coerce", format="mixed")
        out = out.fillna(out2)
    bad = out.isna() & s.notna() & (s.astype(str).str.strip() != "")
    if bad.any():
        out.loc[bad] = s[bad].map(one)
    return pd.to_datetime(out)


def to_date(s: pd.Series) -> pd.Series:
    return to_datetime(s).dt.normalize()


def to_week(s: pd.Series) -> pd.Series:
    d = to_datetime(s)
    iso = d.dt.isocalendar()
    return (iso.year.astype("Int64").astype(str) + "-W" + iso.week.astype("Int64").astype(str).str.zfill(2)).where(d.notna())


def to_month(s: pd.Series) -> pd.Series:
    d = to_datetime(s)
    return d.dt.strftime("%Y-%m").where(d.notna())


def to_hour(s: pd.Series) -> pd.Series:
    return to_datetime(s).dt.hour


def postcode_prefix(s: pd.Series, n: int = 3) -> pd.Series:
    t = s.astype(str).str.strip().str.replace(r"[^0-9]", "", regex=True).str[:n]
    return t.where(t.str.len() == n)


def latlon_to_grid(lat: pd.Series, lon: pd.Series, cell_m: int = 1000) -> pd.Series:
    """Equal-ish area grid id (approx. metres) usable for both exact and rounded coordinates."""
    la, lo = parse_numeric(lat), parse_numeric(lon)
    y = np.floor(la * 111_320 / cell_m)
    x = np.floor(lo * 111_320 * np.cos(np.radians(60.45)) / cell_m)
    g = y.astype("Int64").astype(str) + "_" + x.astype("Int64").astype(str)
    return g.where(la.notna() & lo.notna())


def rel_error(a: float, b: float) -> float:
    if a == 0 and b == 0:
        return 0.0
    return abs(a - b) / max(abs(a), 1e-9)


def score_from_rel_error(err: float, tolerance: float = 0.5) -> float:
    """1.0 at no error, linearly 0 at `tolerance` relative error (e.g. 50 %)."""
    if err is None or np.isnan(err):
        return 0.0
    return float(max(0.0, 1.0 - err / tolerance))


def tvd(p: pd.Series, q: pd.Series) -> float:
    """Total variation distance between two categorical distributions (value -> count)."""
    idx = p.index.union(q.index)
    p = p.reindex(idx, fill_value=0).astype(float)
    q = q.reindex(idx, fill_value=0).astype(float)
    if p.sum() == 0 or q.sum() == 0:
        return 1.0
    return float(0.5 * np.abs(p / p.sum() - q / q.sum()).sum())


def table_mape(orig: pd.Series, prot: pd.Series, min_count: float = 0) -> float:
    """Mean absolute percentage error over cells of an aggregate table (index-aligned); missing cells count as 0."""
    idx = orig.index.union(prot.index)
    o = orig.reindex(idx, fill_value=0).astype(float)
    p = prot.reindex(idx, fill_value=0).astype(float).fillna(0)
    m = o > min_count
    if m.sum() == 0:
        return np.nan
    return float((np.abs(o[m] - p[m]) / o[m]).mean())
