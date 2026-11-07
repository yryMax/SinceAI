"""Shared helpers for the reference baselines (deliberately simple: they are the floor to beat)."""
from __future__ import annotations

import hashlib
import hmac
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "pets_eval_pkg", ROOT / "toolkit"):
    if p.exists():
        sys.path.insert(0, str(p))

from pets_eval import io  # noqa: E402
from pets_eval import parse as Pz  # noqa: E402

SECRET = b"baseline-demo-key-rotate-me"  # a real deployment keeps this key in a vault, never in code


def hmac_token(v, prefix: str = "", n: int = 16) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)) or str(v) == "":
        return ""
    return prefix + hmac.new(SECRET, str(v).encode(), hashlib.sha256).hexdigest()[:n]


def ipv4_prefix_preserving(ip: str) -> str:
    """Prefix-preserving pseudonymisation (Crypto-PAn style, simplified): equal prefixes stay equal."""
    if not isinstance(ip, str) or not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
        return hmac_token(ip, "ip_") if isinstance(ip, str) and ip else ""
    parts = ip.split(".")
    out = []
    for i in range(4):
        h = hmac.new(SECRET, ".".join(parts[: i + 1]).encode(), hashlib.sha256).digest()
        out.append(str(h[0]))
    return ".".join(out)


_RX = [
    ("NATIONAL_ID", re.compile(r"\b\d{6}[-+A-FU-Y]\d{3}[0-9A-Y]\b")),
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[0-9A-Z]{4}){2,7}(?: ?[0-9A-Z]{1,3})?\b")),
    ("URL", re.compile(r"https?://\S+")),
    ("PAYMENT_CARD", re.compile(r"\b(?:\d[ -]?){12,18}\d\b")),
    ("PHONE", re.compile(r"(?:\+\d{2,3}[\s-]?|\b0)\d{1,3}[\s-]?\d{3,4}[\s-]?\d{2,4}\b")),
    ("IP_ADDRESS", re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")),
    ("MAC", re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b")),
    ("LICENSE_PLATE", re.compile(r"\b[A-ZÅÄÖ]{2,3}-\d{1,3}\b")),
]


def regex_redact(text) -> str:
    if not isinstance(text, str) or not text:
        return text
    for label, rx in _RX:
        text = rx.sub(f"[{label}]", text)
    return text


DROP_SUBTYPES = {"PERSON_NAME", "EMAIL", "PHONE", "STREET_ADDRESS", "SECRET", "URL", "USER_AGENT"}
TOKEN_SUBTYPES = {"NATIONAL_ID", "IBAN", "PAYMENT_CARD", "LICENSE_PLATE", "CUSTOMER_ID", "ACCOUNT_ID", "EMPLOYEE_ID",
                  "STUDENT_ID", "PATIENT_ID", "CARD_ID", "DEVICE_ID", "MAC_ADDRESS", "IMEI", "HOSTNAME", "USERNAME",
                  "METER_ID", "PROPERTY_ID"}


def catalog_for(domain: str) -> pd.DataFrame:
    cat = io.load_catalog(ROOT)
    return cat[cat.dataset == domain]


def generalise(col: pd.Series, subtype: str) -> pd.Series:
    st = subtype or ""
    if st == "BIRTH_DATE":
        return Pz.to_datetime(col).dt.year.astype("Int64").astype(str).replace("<NA>", "")
    if st == "AGE":
        return Pz.to_age_band(col)
    if st == "POSTCODE":
        p = Pz.postcode_prefix(col, 3)
        return (p + "**").where(p.notna(), "")
    if st == "GPS_COORDINATE":
        return Pz.parse_numeric(col).round(2)
    if st == "TIMESTAMP":
        d = Pz.to_datetime(col)
        return d.dt.floor("h").dt.strftime("%Y-%m-%d %H:00").where(d.notna(), "")
    if st == "DATE":
        d = Pz.to_datetime(col)
        return d.dt.strftime("%Y-%m-%d").where(d.notna(), "")
    return col


def protect_table(domain: str, table: str, df: pd.DataFrame, cat: pd.DataFrame, level: str) -> pd.DataFrame:
    """level 'b0': drop direct identifiers only. 'b2': classic SDC pipeline. 'b2k': b2 + local suppression to k>=5."""
    if level == "b2k":
        out = protect_table(domain, table, df, cat, "b2")
        qis = list(cat[(cat.table == table) & (cat.privacy_role == "quasi_identifier")].column)
        return enforce_k(out, qis, 5) if qis else out
    c = cat[cat.table == table].set_index("column")
    out = df.copy()
    for col in df.columns:
        if col not in c.index:
            continue
        role, st = c.loc[col, "privacy_role"], str(c.loc[col, "subtype"])
        if level == "b0":
            if role == "direct_identifier":
                out = out.drop(columns=col)
            continue
        if role == "direct_identifier":
            if st in TOKEN_SUBTYPES:
                out[col] = df[col].map(lambda v: hmac_token(v, "t_"))
            else:
                out = out.drop(columns=col)
        elif role == "technical_identifier":
            out[col] = df[col].map(ipv4_prefix_preserving) if st == "IP_ADDRESS" else df[col].map(lambda v: hmac_token(v, "t_"))
        elif role == "quasi_identifier":
            out[col] = generalise(df[col], st)
        elif role == "free_text":
            out[col] = df[col].map(regex_redact)
    return out


def enforce_k(df: pd.DataFrame, qis: list, k: int = 5) -> pd.DataFrame:
    """Local suppression: blank the most detailed quasi-identifier of rows whose class is smaller than k,
    then the next one, until every row is in a class of at least k (or all its QIs are blank)."""
    out = df.copy()
    order = sorted([c for c in qis if c in out.columns], key=lambda c: -out[c].astype(str).nunique())
    for c in order:
        key = out[order].astype(str).fillna("").agg("|".join, axis=1)
        small = key.map(key.value_counts()) < k
        if not small.any():
            break
        out[c] = out[c].astype(object)
        out.loc[small, c] = None
    return out


def write_protected(tables: dict, originals: dict, out_dir: Path, cat: pd.DataFrame, domain: str):
    """Write protected tables plus row maps (built from the ORIGINAL keys; row order is preserved)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for t, df in tables.items():
        df.to_csv(out_dir / f"{t}.csv", index=False)
        o = originals.get(t)
        rk = io.record_key(cat, domain, t, o) if o is not None else None
        if rk and rk in o.columns and len(o) == len(df):
            pd.DataFrame({"protected_row": range(len(df)), "original_record_id": o[rk].astype(str).values}).to_csv(
                out_dir / f"rowmap_{t}.csv", index=False)
