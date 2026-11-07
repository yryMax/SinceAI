"""Re-identification attacks for self-assessment.

linkage_attack  — an outsider with background knowledge (adversary file) tries to find each known
                  person's row in the protected table using quasi-identifiers that survived the
                  transformation. Generalised values (age bands, '201**', rounded times, rounded
                  coordinates) are matched as intervals, so coarsening genuinely helps — but only as
                  much as it actually widens the candidate sets.
hash attacks    — unsalted / unkeyed hashes of identifiers are reversible by enumeration.

Ground truth needed (all in the package): adversary truth (adv_row_id -> person_id), identity truth
(record_id -> person_id), and the team's row map (protected_row -> original record_id).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from . import parse

REF = pd.Timestamp("2025-12-31")
_MASKED = re.compile(r"^[\*x#\-_?]*$", re.I)


@dataclass
class QI:
    kind: str  # exact | name | postcode | age | sex | time | geo | number | suffix
    adv: tuple  # adversary column(s)
    prot: tuple  # protected column(s)
    window: Optional[tuple] = None  # time: (hours before, hours after) the adversary time; default (3, 3) / (24, 48)
    tol: Optional[float] = None  # age: years; number: relative tolerance; suffix: number of trailing digits


def qis_from_spec(spec: list, columns: Iterable[str]) -> list:
    """Build QIs from a JSON spec (metadata/attack_specs.json), keeping only those whose protected columns exist."""
    cols = set(columns)
    out = []
    for q in spec:
        prot = tuple(c for c in q["protected"] if c in cols)
        if not prot or (q["kind"] == "geo" and len(prot) < 2):
            continue
        out.append(QI(q["kind"], tuple(q["adversary"]), prot, tuple(q["window"]) if q.get("window") else None, q.get("tol")))
    return out


def _norm_str(s: pd.Series) -> np.ndarray:
    v = s.fillna("").astype(str).str.lower().str.strip().str.replace(r"[\s\-\.\(\)/_:]+", "", regex=True)
    return v.where(~v.str.fullmatch(r"[\*x#?]*") | (v == ""), "").to_numpy(dtype=object)


_SEP_RE = re.compile(r"[\s\-\.\(\)/_:]+")
_MASK_RE = re.compile(r"[\*x#?]*")
_SEX = {"m": "M", "male": "M", "mies": "M", "man": "M", "f": "F", "female": "F", "nainen": "F", "n": "F", "w": "F",
        "woman": "F", "kvinna": "F", "k": "F"}


def _norm_scalar(v) -> str:
    t = _SEP_RE.sub("", str(v).lower().strip())
    return "" if _MASK_RE.fullmatch(t) else t


def _sex(s: pd.Series) -> np.ndarray:
    m = {"m": "M", "male": "M", "mies": "M", "man": "M", "f": "F", "female": "F", "nainen": "F", "n": "F", "w": "F",
         "woman": "F", "kvinna": "F", "k": "F"}
    return s.fillna("").astype(str).str.strip().str.lower().map(lambda x: m.get(x, "")).to_numpy(dtype=object)


def _name_tokens(s: str) -> set:
    s = re.sub(r"[^\w\s\-]", " ", str(s).lower())
    return {t for t in re.split(r"[\s\-]+", s) if len(t) >= 2}


# ------------------------------------------------------------------ interval representations
def _age_interval_from_protected(df: pd.DataFrame, col: str) -> tuple[np.ndarray, np.ndarray]:
    """Age (at 2025-12-31) interval [lo, hi) per protected row from an age, age band or (truncated) birth date."""
    s = df[col]
    name = col.lower()
    raw = s.fillna("").astype(str).str.strip()
    lo = np.full(len(s), -1.0)
    hi = np.full(len(s), 200.0)
    if "birth" in name or "dob" in name:
        if "year" in name:
            y = parse.parse_numeric(s).values
            ok = ~np.isnan(y)
            lo[ok], hi[ok] = REF.year - y[ok] - 1, REF.year - y[ok] + 1
            return lo, hi
        ln = raw.str.len().values
        d = parse.to_datetime(s)
        ok = d.notna().values
        start = d.values
        end = np.where(ln == 4, (d + pd.DateOffset(years=1)).values,
                       np.where(ln == 7, (d + pd.DateOffset(months=1)).values, (d + pd.Timedelta(days=1)).values))
        age_hi = (REF.to_datetime64() - start) / np.timedelta64(1, "D") / 365.25
        age_lo = (REF.to_datetime64() - end) / np.timedelta64(1, "D") / 365.25
        lo[ok], hi[ok] = age_lo[ok], age_hi[ok]
        return lo, hi
    # ages / bands
    for i, v in enumerate(raw.values):
        if v == "" or _MASKED.match(v):
            continue
        m = re.match(r"^[\[(]?\s*(\d+(?:\.\d+)?)\s*(?:-|–|,|\.\.)\s*(\d+(?:\.\d+)?)\s*[\])]?$", v)
        if m:
            a, b = float(m.group(1)), float(m.group(2))
            lo[i], hi[i] = a, (b if v.endswith(")") else b + 1)
            continue
        m = re.match(r"^(\d+)\s*\+$", v)
        if m:
            lo[i], hi[i] = float(m.group(1)), 130.0
            continue
        m = re.match(r"^<\s*(\d+)$", v)
        if m:
            lo[i], hi[i] = 0.0, float(m.group(1))
            continue
        try:
            a = float(v.replace(",", "."))
            lo[i], hi[i] = a, a + 1  # age in completed years
        except ValueError:
            pass
    return lo, hi


def _age_interval_from_adversary(row: pd.Series, cols: tuple, tol: float = 1.0) -> Optional[tuple]:
    for c in cols:
        v = row.get(c)
        if v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "":
            continue
        cl = c.lower()
        try:
            if "year" in cl:
                y = float(v)
                return REF.year - y - 1 - tol, REF.year - y + 1 + tol
            if "birth" in cl or "dob" in cl:
                d = pd.Timestamp(str(v))
                a = (REF - d).days / 365.25
                return a - tol, a + tol
            a = parse.parse_numeric(pd.Series([v])).iloc[0]
            if not np.isnan(a):
                return a - tol, a + 1 + tol
        except (ValueError, TypeError):
            continue
    return None


def _time_interval_from_protected(s: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    raw = s.fillna("").astype(str).str.strip()
    d = parse.to_datetime(s)
    start = d.values.astype("datetime64[ns]")
    week = raw.str.contains(r"^\d{4}-?W\d", regex=True).values
    month = raw.str.fullmatch(r"\d{4}-\d{2}").values
    year = raw.str.fullmatch(r"\d{4}").values
    day = raw.str.fullmatch(r"\d{4}-\d{2}-\d{2}").values
    width = np.where(year, 366, np.where(month, 31, np.where(week, 7, np.where(day, 1, 0)))).astype("timedelta64[D]")
    end = start + width.astype("timedelta64[ns]")
    return start, end


def _geo_tolerance_m(s: pd.Series) -> float:
    dec = s.dropna().astype(str).str.split(".").str[1].str.len().dropna()
    if dec.empty:
        return 1000.0
    d = int(dec.median())
    return float(111_320 * 10 ** (-d))


# ------------------------------------------------------------------ automatic QI mapping
def auto_qi_map(adv_cols: Iterable[str], prot_cols: Iterable[str], temporal_cols: Iterable[str] = ()) -> list[QI]:
    """Pair adversary and protected columns by name. Override by passing your own QI list."""
    adv_cols, prot_cols = list(adv_cols), list(prot_cols)
    lower = {c.lower(): c for c in prot_cols}
    out: list[QI] = []
    used_adv: set = set()

    def pick(pred, cols):
        return [c for c in cols if pred(c.lower())]

    # names
    a_names = pick(lambda c: "name" in c and not any(x in c for x in ("street", "stop", "merchant", "place", "org", "company", "employer", "school", "user")), adv_cols)
    p_names = pick(lambda c: "name" in c and not any(x in c for x in ("street", "stop", "merchant", "place", "org", "company", "employer", "school", "user", "file", "host")), prot_cols)
    if a_names and p_names:
        out.append(QI("name", tuple(a_names), tuple(p_names)))
        used_adv |= set(a_names)
    # postcode
    a = pick(lambda c: any(x in c for x in ("postcode", "zip", "postal")), adv_cols)
    p = pick(lambda c: any(x in c for x in ("postcode", "zip", "postal")), prot_cols)
    if a and p:
        out.append(QI("postcode", (a[0],), (p[0],)))
        used_adv.add(a[0])
    # municipality / city
    a = pick(lambda c: c in ("city", "municipality", "home_municipality", "town", "kunta"), adv_cols)
    p = pick(lambda c: c in ("city", "municipality", "home_municipality", "town", "kunta", "patient_municipality"), prot_cols)
    if a and p:
        out.append(QI("exact", (a[0],), (p[0],)))
        used_adv.add(a[0])
    # age / birth
    a = pick(lambda c: c in ("age", "approx_age", "age_years", "birth_year", "birth_date", "date_of_birth", "dob", "year_of_birth"), adv_cols)
    p = pick(lambda c: c in ("age", "age_band", "age_group", "birth_year", "birth_date", "date_of_birth", "dob", "year_of_birth", "patient_age", "age_at_visit"), prot_cols)
    if a and p:
        out.append(QI("age", tuple(a), (p[0],)))
        used_adv |= set(a)
    # sex
    a = pick(lambda c: c in ("sex", "gender"), adv_cols)
    p = pick(lambda c: c in ("sex", "gender", "patient_sex"), prot_cols)
    if a and p:
        out.append(QI("sex", (a[0],), (p[0],)))
        used_adv.add(a[0])
    # geo
    alat = pick(lambda c: c in ("lat", "latitude") or c.endswith("_lat"), adv_cols)
    alon = pick(lambda c: c in ("lon", "lng", "longitude") or c.endswith("_lon"), adv_cols)
    plat = pick(lambda c: c in ("lat", "latitude") or c.endswith("_lat"), prot_cols)
    plon = pick(lambda c: c in ("lon", "lng", "longitude") or c.endswith("_lon"), prot_cols)
    if alat and alon and plat and plon:
        # prefer same-prefix pairs (e.g. start_lat with start_lat)
        pl = next((c for c in plat if c in alat), plat[0])
        pn = pl.replace("lat", "lon") if pl.replace("lat", "lon") in plon else plon[0]
        al = pl if pl in alat else alat[0]
        an = al.replace("lat", "lon") if al.replace("lat", "lon") in alon else alon[0]
        out.append(QI("geo", (al, an), (pl, pn)))
        used_adv |= {al, an}
    # time
    a = pick(lambda c: (any(x in c for x in ("date", "time", "_ts", "timestamp", "datetime")) or c == "ts") and "birth" not in c, adv_cols)
    if a:
        p = [c for c in prot_cols if c in a] or [c for c in temporal_cols if c in prot_cols and "birth" not in c.lower()] or \
            pick(lambda c: (any(x in c for x in ("date", "time", "_ts", "timestamp")) or c == "ts") and "birth" not in c, prot_cols)
        if p:
            out.append(QI("time", (a[0],), (p[0],)))
            used_adv.add(a[0])
    # identical column names not used yet -> exact
    for c in adv_cols:
        if c in used_adv or c.lower() in ("adv_row_id", "note", "notes", "text", "post_text", "source", "headline"):
            continue
        if c.lower() in lower and not c.lower().endswith("row_id"):
            out.append(QI("exact", (c,), (lower[c.lower()],)))
    return out


# ------------------------------------------------------------------ linkage attack
class _Prepared:
    def __init__(self, prot: pd.DataFrame, qis: list[QI]):
        self.n = len(prot)
        self.qis = qis
        self.data = {}
        for i, q in enumerate(qis):
            if q.kind in ("exact", "sex"):
                vals = _norm_str(prot[q.prot[0]]) if q.kind == "exact" else _sex(prot[q.prot[0]])
                codes, uniq = pd.factorize(vals)
                lut = {v: j for j, v in enumerate(uniq)}
                self.data[i] = (codes, lut, lut.get("", -9))
            elif q.kind == "postcode":
                d = prot[q.prot[0]].fillna("").astype(str).str.replace(r"[^0-9]", "", regex=True)
                vals = d.to_numpy(dtype=object)
                lens = d.str.len().to_numpy(dtype=int)
                groups = []
                for L in np.unique(lens[lens > 0]):
                    sel = lens == L
                    codes, uniq = pd.factorize(vals[sel])
                    groups.append((int(L), sel, codes, {v: j for j, v in enumerate(uniq)}))
                self.data[i] = (lens == 0, groups)
            elif q.kind == "age":
                self.data[i] = _age_interval_from_protected(prot, q.prot[0])
            elif q.kind == "time":
                self.data[i] = _time_interval_from_protected(prot[q.prot[0]])
            elif q.kind == "number":
                self.data[i] = parse.parse_numeric(prot[q.prot[0]]).values
            elif q.kind == "suffix":
                n = int(q.tol or 4)
                d = prot[q.prot[0]].fillna("").astype(str).str.replace(r"[^0-9]", "", regex=True)
                codes, uniq = pd.factorize(d.str[-n:].where(d.str.len() >= n, ""))
                self.data[i] = (codes, {v: j for j, v in enumerate(uniq)}, n)
            elif q.kind == "geo":
                la = parse.parse_numeric(prot[q.prot[0]]).values
                lo = parse.parse_numeric(prot[q.prot[1]]).values
                tol = max(_geo_tolerance_m(prot[q.prot[0]]), 150.0)
                self.data[i] = (la, lo, tol)
            elif q.kind == "name":
                full = prot[list(q.prot)].fillna("").astype(str).agg(" ".join, axis=1)
                toks = [_name_tokens(x) for x in full.tolist()]
                index: dict = {}
                for r, ts in enumerate(toks):
                    for t in ts:
                        index.setdefault(t, []).append(r)
                has_name = np.fromiter((len(t) > 0 for t in toks), bool, len(toks))
                self.data[i] = (toks, {k: np.array(v) for k, v in index.items()}, has_name)

    def candidates(self, row: pd.Series) -> tuple[np.ndarray, int]:
        mask = np.ones(self.n, dtype=bool)
        used = 0
        for i, q in enumerate(self.qis):
            d = self.data[i]
            if q.kind == "name":
                vals = " ".join(str(row.get(c, "")) for c in q.adv if pd.notna(row.get(c, "")))
                at = _name_tokens(vals)
                at = {t for t in at if len(t) >= 2}
                if not at:
                    continue
                toks, index, has_name = d
                # surname / longest token blocks; all adversary tokens of length > 2 must appear
                key = max(at, key=len)
                rows = index.get(key)
                m = np.zeros(self.n, dtype=bool)
                if rows is not None:
                    for r in rows:
                        pt = toks[r]
                        if all((t in pt) or (len(t) <= 2 and any(x.startswith(t[0]) for x in pt)) for t in at):
                            m[r] = True
                # protected names fully removed -> column empty -> no constraint
                mask &= m | ~has_name
                used += 1
                continue
            v = row.get(q.adv[0]) if q.kind != "geo" else None
            if q.kind == "time" and len(q.adv) > 1:
                parts = [str(row.get(c)) for c in q.adv if row.get(c) is not None and str(row.get(c)).strip() not in ("", "nan")]
                if len(parts) >= 2 and re.fullmatch(r"\d{1,2}[:.]\d{2}(:\d{2})?", parts[1].strip()):
                    v = parts[0] + " " + parts[1].strip().replace(".", ":")  # separate date and time columns
                else:
                    v = parts[0] if parts else None
            if q.kind in ("exact", "sex", "postcode", "time", "number", "suffix") and (v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == ""):
                continue
            if q.kind in ("exact", "sex"):
                a = _norm_scalar(v) if q.kind == "exact" else _SEX.get(str(v).strip().lower(), "")
                if not a:
                    continue
                codes, lut, empty = d
                mask &= (codes == lut.get(a, -2)) | (codes == empty)
            elif q.kind == "postcode":
                a = re.sub(r"[^0-9]", "", str(v))
                if not a:
                    continue
                wildcard, groups = d
                m = wildcard.copy()
                for L, sel, codes, lut in groups:
                    m[sel] = codes == lut.get(a[:L], -2)
                mask &= m
            elif q.kind == "age":
                iv = _age_interval_from_adversary(row, q.adv, q.tol if q.tol is not None else 1.0)
                if iv is None:
                    continue
                lo, hi = d
                mask &= (lo < iv[1]) & (hi > iv[0])
            elif q.kind == "time":
                t0 = parse.to_datetime(pd.Series([str(v)])).iloc[0]
                if pd.isna(t0):
                    continue
                s, e = d
                has_time = bool(re.search(r"\d{1,2}:\d{2}", str(v)))
                if q.window:
                    a0, a1 = t0 - pd.Timedelta(hours=q.window[0]), t0 + pd.Timedelta(hours=q.window[1])
                    if not has_time:
                        a1 += pd.Timedelta(days=1)
                else:
                    a0 = (t0 - pd.Timedelta(hours=3)) if has_time else (t0 - pd.Timedelta(days=1))
                    a1 = (t0 + pd.Timedelta(hours=3)) if has_time else (t0 + pd.Timedelta(days=2))
                ok = ~np.isnat(s)
                mm = np.ones(self.n, dtype=bool)
                mm[ok] = (s[ok] < a1.to_datetime64()) & (np.maximum(e[ok], s[ok]) >= a0.to_datetime64())
                mask &= mm
            elif q.kind == "number":
                a = parse.parse_numeric(pd.Series([str(v).replace("€", "").strip()])).iloc[0]
                if np.isnan(a):
                    continue
                rel = q.tol if q.tol is not None else 0.01
                x = d
                mask &= (np.abs(x - a) <= max(abs(a) * rel, 0.01)) | np.isnan(x)
            elif q.kind == "suffix":
                codes, lut, n = d
                a = re.sub(r"[^0-9]", "", str(v))[-n:]
                if len(a) < n:
                    continue
                mask &= codes == lut.get(a, -2)
            elif q.kind == "geo":
                la, lo, tol = d
                try:
                    alat, alon = float(row.get(q.adv[0])), float(row.get(q.adv[1]))
                except (ValueError, TypeError):
                    continue
                if np.isnan(alat) or np.isnan(alon):
                    continue
                dist = 6_371_000 * 2 * np.arcsin(np.sqrt(np.sin(np.radians(la - alat) / 2) ** 2 + np.cos(np.radians(alat)) *
                                                          np.cos(np.radians(la)) * np.sin(np.radians(lo - alon) / 2) ** 2))
                mask &= (dist <= tol + 250) | np.isnan(la)
            used += 1
        return np.flatnonzero(mask), used


def linkage_attack(adversary: pd.DataFrame, adv_truth: Optional[pd.DataFrame], protected: pd.DataFrame,
                   rowmap: Optional[pd.DataFrame], identity: pd.DataFrame, qis: Optional[list] = None,
                   original: Optional[pd.DataFrame] = None, record_key: Optional[str] = None,
                   sensitive: Optional[str] = None, temporal_cols: Iterable[str] = (), max_adversary: int = 3000,
                   seed: int = 0, entity: Optional[str] = None) -> dict:
    """Run a background-knowledge linkage attack.

    protected : protected table (rows in any order)
    rowmap    : DataFrame protected_row -> original_record_id (pets_eval.io.load_rowmap)
    identity  : DataFrame record_id -> person_id (truth/<domain>__<table>.csv)
    original  : original table (only needed for attribute inference)
    entity    : optional protected column that groups rows of one subject (e.g. a card or account pseudonym);
                when every candidate row shares one entity value, the attacker has singled out that entity.
    Returns re-identification rate among adversary targets present in the data, precision of the
    attacker's unique claims, candidate-set statistics and attribute-inference success.
    """
    if qis is None:
        qis = auto_qi_map(adversary.columns, protected.columns, temporal_cols)
    if not qis:
        return {"evaluated": False, "reason": "no overlapping quasi-identifiers between adversary and protected table"}
    if rowmap is None or adv_truth is None:
        return {"evaluated": False, "reason": "row map or adversary truth missing"}
    id_map = dict(zip(identity.iloc[:, 0].astype(str).tolist(), identity.iloc[:, 1].astype(str).tolist()))
    rm = rowmap.dropna()
    row_person = np.full(len(protected), "", dtype=object)
    row_record = np.full(len(protected), "", dtype=object)
    for pr, rid in zip(rm.protected_row.astype(int).tolist(), rm.original_record_id.astype(str).tolist()):
        if 0 <= pr < len(protected):
            row_person[pr] = id_map.get(rid, "")
            row_record[pr] = rid
    persons_in = set(row_person[row_person != ""])
    tmap = dict(zip(adv_truth.iloc[:, 0].astype(str).tolist(), adv_truth.iloc[:, 1].astype(str).tolist()))
    adv = adversary.copy()
    adv["_pid"] = adv.iloc[:, 0].astype(str).map(tmap).fillna("")
    rng = np.random.default_rng(seed)
    if len(adv) > max_adversary:
        # keep the in-data share realistic: sample uniformly
        adv = adv.iloc[np.sort(rng.choice(len(adv), max_adversary, replace=False))]
    prep = _Prepared(protected.reset_index(drop=True), qis)
    ent = protected[entity].fillna("").astype(str).to_numpy(dtype=object) if entity and entity in protected.columns else None
    sens_true = None
    if sensitive and original is not None and sensitive in original.columns and sensitive in protected.columns and record_key:
        o = original[[record_key, sensitive]].copy()
        o["_pid"] = o[record_key].astype(str).map(id_map)
        sens_true = o.groupby("_pid")[sensitive].apply(lambda s: set(s.astype(str)))
        prot_sens = protected[sensitive].astype(str).to_numpy(dtype=object)
    n_in = n_claim = n_correct = n_k5 = 0
    n_attr = n_attr_ok = 0
    sizes = []
    for r in adv.to_dict("records"):
        cand, used = prep.candidates(r)
        in_data = r["_pid"] in persons_in
        size = len(cand)
        if ent is not None and size > 1:
            ev = set(ent[cand])
            if len(ev) == 1 and "" not in ev:
                size = 1
        if in_data:
            n_in += 1
            sizes.append(size)
            if 0 < size <= 5 and any(row_person[c] == r["_pid"] for c in cand):
                n_k5 += 1
        if size == 1 and used > 0:
            n_claim += 1
            if in_data and any(row_person[c] == r["_pid"] for c in cand[:50]):
                n_correct += 1
        if sens_true is not None and in_data and 0 < size and used > 0:
            vals = set(prot_sens[cand])
            if len(vals) == 1:
                n_attr += 1
                if next(iter(vals)) in sens_true.get(r["_pid"], set()):
                    n_attr_ok += 1
    sizes = np.array(sizes) if sizes else np.array([0])
    res = {
        "evaluated": True,
        "qis_used": [{"kind": q.kind, "adversary": list(q.adv), "protected": list(q.prot)} for q in qis],
        "n_adversary_rows_tested": int(len(adv)),
        "n_targets_in_data": int(n_in),
        "reidentification_rate": round(n_correct / n_in, 4) if n_in else 0.0,
        "claim_precision": round(n_correct / n_claim, 4) if n_claim else None,
        "n_unique_claims": int(n_claim),
        "share_targets_in_candidate_set_le5": round(n_k5 / n_in, 4) if n_in else 0.0,
        "median_candidate_set": float(np.median(sizes)),
    }
    if sens_true is not None:
        # base rate: an attacker who always guesses the most common protected value
        maj = pd.Series(prot_sens).value_counts().index[0] if len(prot_sens) else None
        targets = [p for p in adv["_pid"] if p in persons_in]
        base = float(np.mean([maj in sens_true.get(p, set()) for p in targets])) if targets and maj is not None else 0.0
        succ = n_attr_ok / n_in if n_in else 0.0
        adv_ = max(0.0, (succ - base) / (1 - base)) if base < 1 else 0.0
        res["attribute_inference"] = {"sensitive": sensitive, "inferred": n_attr, "base_rate_majority_guess": round(base, 4),
                                      "advantage_over_base_rate": round(adv_, 4),
                                      "success_rate": round(n_attr_ok / n_in, 4) if n_in else 0.0}
    return res


# ------------------------------------------------------------------ hashes
_HEX = {32: "md5", 40: "sha1", 64: "sha256"}


def detect_hash_columns(df: pd.DataFrame, min_share: float = 0.9) -> dict:
    """Columns whose values look like hex digests -> {column: algorithm guess}."""
    out = {}
    for c in df.columns:
        s = df[c].dropna().astype(str).head(2000)
        if s.empty:
            continue
        m = s.str.fullmatch(r"[0-9a-fA-F]{32}|[0-9a-fA-F]{40}|[0-9a-fA-F]{64}")
        if m.mean() >= min_share:
            out[c] = _HEX.get(int(s[m].str.len().mode().iloc[0]), "unknown")
    return out


def _candidate_variants(v: str) -> set:
    v = str(v)
    out = {v, v.strip(), v.lower(), v.upper(), v.strip().lower()}
    digits = re.sub(r"\D", "", v)
    if len(digits) >= 7:
        out |= {digits, "+" + digits}
        if digits.startswith("358"):
            out.add("0" + digits[3:])
        if digits.startswith("0"):
            out |= {"+358" + digits[1:], "358" + digits[1:]}
    out.add(re.sub(r"\s+", "", v))
    return {x for x in out if x}


def hash_dictionary_attack(hashed: pd.Series, candidates: Iterable[str], max_candidates: int = 2_000_000) -> dict:
    """Try to reverse hex digests by hashing candidate values (and simple normalisations) with MD5, SHA-1,
    SHA-256. Keyed hashes (HMAC with a secret key) and salted hashes resist this; plain hashes do not."""
    target = set(hashed.dropna().astype(str).str.lower())
    if not target:
        return {"evaluated": False, "reason": "no values"}
    lens = {len(t) for t in target}
    algos = [a for L, a in _HEX.items() if L in lens]
    found = {}
    n = 0
    for c in candidates:
        for v in _candidate_variants(c):
            b = v.encode("utf-8")
            for a in algos:
                h = hashlib.new(a, b).hexdigest()
                if h in target and h not in found:
                    found[h] = (a, v)
            n += 1
        if n > max_candidates:
            break
    vals = hashed.dropna().astype(str).str.lower()
    share = float(vals.isin(found.keys()).mean()) if len(vals) else 0.0
    algo = pd.Series([a for a, _ in found.values()]).mode().iloc[0] if found else None
    return {"evaluated": True, "n_hashes": int(len(target)), "n_reversed_distinct": len(found),
            "share_values_reversed": round(share, 4), "algorithm": algo, "candidates_tried": int(n),
            "examples": [v for _, v in list(found.values())[:3]]}


HETU_CHECK = "0123456789ABCDEFHJKLMNPRSTUVWXY"


def enumerate_hetu(start: date, end: date, individual: Iterable[int] = range(2, 1000)) -> Iterable[str]:
    """Every syntactically valid Finnish personal identity code for birth dates in [start, end].
    One year ≈ 365 × 998 ≈ 364,000 codes — trivially enumerable, which is why hashing a HETU is not
    anonymisation."""
    ind = list(individual)
    d = start
    while d <= end:
        c = "+" if d.year < 1900 else ("-" if d.year < 2000 else "A")
        base = f"{d.day:02d}{d.month:02d}{d.year % 100:02d}"
        for n in ind:
            yield f"{base}{c}{n:03d}{HETU_CHECK[int(base + f'{n:03d}') % 31]}"
        d += timedelta(days=1)
