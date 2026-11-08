"""Select + Transform: protect ANY folder of CSV tables for a recipient with a given trust level.

    python3 solution/pipeline.py data/health --trust controlled_research
    python3 solution/pipeline.py data/unseen --trust contractual --out out/release

Reads only the input tables. Each column's PET comes from one policy table (`select`), keyed by the privacy
role and subtype that detector.py inferred from the data; no column name is hard-coded. Output:
  <out>/<folder>/release/   the protected tables (the only thing to share)
  <out>/<folder>/private/   field_labels.csv, pet_plan.csv, stats.json, rowmap_*.csv (never share)
At the end it prints the pets-eval scorecard command, with the private row maps passed via --rowmap.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "solution"), str(ROOT / "toolkit")]
warnings.filterwarnings("ignore")

from detector import detect_tables  # noqa: E402
from pets_eval import parse as pz  # noqa: E402
from text_detector import TextDetector  # noqa: E402

# The wider the audience, the stricter the parameters.
TRUST = {
    "internal": dict(k=5, link_keys="token", keep_share=0.002),
    "controlled_research": dict(k=5, link_keys="token", keep_share=0.005),
    "contractual": dict(k=5, link_keys="token", keep_share=0.005),
    "public": dict(k=10, link_keys="drop", keep_share=0.01),
}
# Direct identifiers that also serve as join keys: pseudonymised for trusted recipients, never published.
LINK_KEYS = {"NATIONAL_ID", "PAYMENT_CARD", "IBAN", "EMAIL", "USERNAME", "LICENSE_PLATE"}
QI_RULES = {
    "BIRTH_DATE": ("birth_year", "birth date -> birth year"),
    "AGE": ("age_band", "age -> 10-year band"),
    "TIMESTAMP": ("hour", "exact time -> hour"),
    "DATE": ("month", "date -> month"),
    "POSTCODE": ("postcode3", "postcode -> first 3 digits"),
    "GPS_COORDINATE": ("gps2", "coordinates -> about 1 km"),
    "SEX": ("keep", "only two or three values"),
    "LANGUAGE": ("keep", "few values"),
    "MEASUREMENT": ("round2", "number -> 2 significant digits"),
    "FINANCIAL_DATA": ("round2", "amount -> 2 significant digits, so receipts cannot be matched exactly"),
}


def select(role: str, subtype: str, trust: str) -> tuple[str, str]:
    """The PET for one column, from its detected role and subtype only."""
    if role == "direct_identifier":
        if subtype in LINK_KEYS and TRUST[trust]["link_keys"] == "token":
            return "token", "identifies a person; replaced by a secret code so tables still join"
        return "drop", "identifies a person on its own"
    if role in ("technical_identifier", "record_key"):
        if subtype == "IP_ADDRESS":
            return "ip_prefix", "network identifier; pseudonymised but keeps subnet structure"
        if subtype == "USER_AGENT":
            return "top_values", "software string; rare values could single out a device"
        return "token", "system key; replaced by a secret code so tables still join"
    if role == "free_text":
        return "redact", "free text; detected names, numbers and addresses replaced by placeholders"
    if role == "quasi_identifier":
        return QI_RULES.get(subtype, ("top_values", "rare values merged into 'other'"))
    if role == "sensitive_attribute" and subtype == "DIAGNOSIS_CODE":
        return "icd3", "diagnosis code -> 3-character category (rare exact codes single people out)"
    if role == "sensitive_attribute":
        return "keep", "the fact being analysed; protected by unlinking it from the person"
    return "keep", "not sensitive"


class Transformer:
    def __init__(self, tables: dict, labels: pd.DataFrame, dataset: str, trust: str, key: bytes):
        self.tables, self.labels, self.dataset, self.trust, self.key = tables, labels, dataset, trust, key
        self.k = TRUST[trust]["k"]
        self._text = None

    def _code(self, value: str) -> str:
        return "t_" + hmac.new(self.key, value.encode(), hashlib.sha256).hexdigest()[:16]

    @staticmethod
    def _dates(s: pd.Series) -> pd.Series:
        try:
            return pz.to_datetime(s)
        except (ValueError, OverflowError):   # e.g. card expiry 'MM/YY' parsed as year 1: treat as not a date
            return pd.to_datetime(s, errors="coerce", format="mixed")

    def _top(self, s: pd.Series) -> pd.Series:
        counts = s.value_counts()
        keep = counts[(counts / max(len(s), 1) >= TRUST[self.trust]["keep_share"]) & (counts >= self.k)].index
        return s.where(s.isin(keep) | s.isna(), "other")

    def apply(self, table: str, col: str, pet: str) -> pd.Series | None:
        s = self.tables[table][col]
        if pet == "drop":
            return None
        if pet == "keep":
            return s
        if pet == "token":     # one key per release: equal raw values get equal codes in every table
            return s.map({v: self._code(str(v)) for v in s.dropna().unique()}).fillna("")
        if pet == "ip_prefix":
            def one(ip):
                parts = str(ip).split(".")
                if len(parts) != 4 or not all(p.isdigit() for p in parts):
                    return self._code(str(ip))
                return ".".join(str(hmac.new(self.key, ".".join(parts[:i + 1]).encode(), hashlib.sha256).digest()[0])
                                for i in range(4))
            return s.map({v: one(v) for v in s.dropna().unique()}).fillna("")
        if pet == "redact":
            self._text = self._text or TextDetector(self.tables, self.labels, dataset=self.dataset)
            return s.map({v: self._text.redact(v, table=table, column=col) for v in s.dropna().unique()}).fillna("")
        if pet == "birth_year":
            return self._dates(s).dt.year.astype("Int64").astype(str).replace("<NA>", "")
        if pet == "age_band":
            return pz.to_age_band(pz.parse_numeric(s)).fillna("")
        if pet == "hour":
            return self._dates(s).dt.floor("h").dt.strftime("%Y-%m-%d %H:00").fillna("")
        if pet == "month":
            d = self._dates(s)
            # Values that are not calendar dates ('2023K', '2022-23') are already coarse.
            return s if d.notna().sum() < 0.5 * s.notna().sum() else d.dt.strftime("%Y-%m").fillna("")
        if pet == "postcode3":
            return (pz.postcode_prefix(s, 3) + "**").fillna("")
        if pet == "gps2":
            return pz.parse_numeric(s).round(2)
        if pet == "round2":
            x = pz.parse_numeric(s)
            if x.notna().sum() < 0.5 * s.notna().sum():
                return self._top(s)
            step = 10 ** (np.floor(np.log10(x.abs().where(x != 0))) - 1)
            return (np.round(x / step) * step).where(x != 0, x)
        if pet == "icd3":
            return s.map(lambda v: "|".join(c.strip()[:3] for c in str(v).split("|") if c.strip()), na_action="ignore")
        if pet == "top_values":
            return self._top(s)
        raise ValueError(pet)

    def _record_ids(self, table: str) -> pd.Series | None:
        """Each row's own key (the detected record_key column), or None for tables without one (e.g. aggregates)."""
        df, lab = self.tables[table], self.labels
        keys = [c for c in lab[(lab.table == table) & (lab.privacy_role == "record_key")].column if df[c].is_unique]
        return df[keys[0]].astype(str) if keys else None

    def k_anonymise(self, df: pd.DataFrame, qis: list) -> tuple[pd.DataFrame, dict]:
        """Blank the most specific quasi-identifier in groups smaller than k; drop rows that stay too rare."""
        if not qis or not len(df):
            return df, {}
        df[qis] = df[qis].astype(str).replace({"nan": "", "<NA>": ""})
        small = lambda: df.groupby(qis, dropna=False)[qis[0]].transform("size") < self.k  # noqa: E731
        stats = {}
        for c in sorted(qis, key=lambda c: -df[c].nunique()):
            m = small()
            if not m.any():
                break
            stats[c] = int(m.sum())
            df.loc[m, c] = ""
        m = small()
        stats["rows_dropped"] = int(m.sum())
        return df[~m], stats

    def run(self) -> tuple[dict, dict, pd.DataFrame, dict]:
        release, rowmaps, plan, stats = {}, {}, [], {}
        for table, df in self.tables.items():
            lab = self.labels[self.labels.table == table].set_index("column")
            out, qis = {}, []
            for col in df.columns:
                role, sub = lab.loc[col, "privacy_role"], lab.loc[col, "subtype"]
                pet, why = select(role, sub, self.trust)
                plan.append(dict(table=table, column=col, detected_role=role, detected_subtype=sub, pet=pet, reason=why))
                v = self.apply(table, col, pet)
                if v is not None:
                    out[col] = v
                    qis += [col] if role == "quasi_identifier" else []
            o, st = self.k_anonymise(pd.DataFrame(out, index=df.index), qis)
            # Shuffle with the secret key, so the row order reveals nothing (e.g. arrival order).
            seed = int.from_bytes(hmac.new(self.key, f"order:{table}".encode(), hashlib.sha256).digest()[:8], "big")
            o = o.iloc[np.random.default_rng(seed).permutation(len(o))]
            ids = self._record_ids(table)
            if ids is not None:   # row map in the scorecard's format: released row -> original record id
                rowmaps[table] = pd.DataFrame({"protected_row": np.arange(len(o)), "original_record_id": ids[o.index].to_numpy()})
            release[table] = o.reset_index(drop=True)
            stats[table] = {"rows_in": len(df), "rows_out": len(o), "qis": qis, "k": self.k, "suppressed": st}
        return release, rowmaps, pd.DataFrame(plan), stats


def read_folder(folder: Path) -> dict:
    return {f.stem: pd.read_csv(f, dtype=str, keep_default_na=False, na_values=[""]) for f in sorted(Path(folder).glob("*.csv"))}


def protect_folder(folder: Path, trust: str, out: Path) -> pd.DataFrame:
    """Detect -> Select -> Transform one folder; returns the PET plan."""
    folder, out = Path(folder), Path(out)
    tables = read_folder(folder)
    labels = detect_tables(tables, folder.name)
    key = os.environ.get("PETS_HMAC_KEY", "").encode() or secrets.token_bytes(32)
    release, rowmaps, plan, stats = Transformer(tables, labels, folder.name, trust, key).run()
    for d in ("release", "private"):
        (out / d).mkdir(parents=True, exist_ok=True)
    for f in (out / "private").glob("rowmap_*.csv"):   # no stale maps from an earlier run
        f.unlink()
    for t, df in release.items():
        df.to_csv(out / "release" / f"{t}.csv", index=False)
    for t, rm in rowmaps.items():
        rm.to_csv(out / "private" / f"rowmap_{t}.csv", index=False)
    labels.to_csv(out / "private" / "field_labels.csv", index=False)
    plan.to_csv(out / "private" / "pet_plan.csv", index=False)
    (out / "private" / "stats.json").write_text(json.dumps(stats, indent=2))
    return plan


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path, help="folder of CSV tables")
    ap.add_argument("--trust", choices=list(TRUST), default="contractual")
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "release")
    a = ap.parse_args()
    out = a.out / a.folder.name
    plan = protect_folder(a.folder, a.trust, out)
    pd.set_option("display.width", 200)
    print(plan.to_string(index=False))
    rel = os.path.relpath
    maps = " ".join(f"--rowmap {rel(f)}" for f in sorted((out / "private").glob("rowmap_*.csv")))
    print(f"\nrelease written to {rel(out / 'release')}\n\nself-assessment (choose the scenario id):\n"
          f"pets-eval scorecard --original {rel(a.folder)} --protected {rel(out / 'release')} --scenario <ID> "
          f"{maps} --out {rel(out / 'private' / 'scorecard')}")
