"""B1: rule-based field detector (column-name keywords + value sniffing).

usage: python3 baselines/b1_detect_rules.py [--data data] [--out results/b1_field_labels.csv] [--only DOMAIN]
Output format = the format `pets-eval detect --pred` expects.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from _common import ROOT

NAME_RULES = [  # (regex on column name, role, subtype)
    (r"hetu|ssn|personal_id|national|henkilotunnus", "direct_identifier", "NATIONAL_ID"),
    (r"(^|_)name$|first_?name|last_?name|surname|given|patient_name|holder|guardian", "direct_identifier", "PERSON_NAME"),
    (r"e_?mail", "direct_identifier", "EMAIL"),
    (r"phone|mobile|puhelin", "direct_identifier", "PHONE"),
    (r"address|street|osoite", "direct_identifier", "STREET_ADDRESS"),
    (r"iban|account_no|bank_account", "direct_identifier", "IBAN"),
    (r"pan$|card_number|card_pan", "direct_identifier", "PAYMENT_CARD"),
    (r"plate", "direct_identifier", "LICENSE_PLATE"),
    (r"(^|_)ip($|_)|src_ip|dst_ip|client_ip", "technical_identifier", "IP_ADDRESS"),
    (r"mac", "technical_identifier", "MAC_ADDRESS"),
    (r"host", "technical_identifier", "HOSTNAME"),
    (r"upn|user(name)?$|login|account$", "technical_identifier", "USERNAME"),
    (r"imei|device", "technical_identifier", "DEVICE_ID"),
    (r"gsrn|metering|meter_id", "technical_identifier", "METER_ID"),
    (r"birth|dob|syntym", "quasi_identifier", "BIRTH_DATE"),
    (r"(^|_)age($|_)", "quasi_identifier", "AGE"),
    (r"(^|_)sex$|gender", "quasi_identifier", "SEX"),
    (r"postcode|zip|postal", "quasi_identifier", "POSTCODE"),
    (r"municipality|city|town", "quasi_identifier", "MUNICIPALITY"),
    (r"(^|_)lat|(^|_)lon|latitude|longitude", "quasi_identifier", "GPS_COORDINATE"),
    (r"_ts$|timestamp|time$|_at$", "quasi_identifier", "TIMESTAMP"),
    (r"date", "quasi_identifier", "DATE"),
    (r"icd|diagnos", "sensitive_attribute", "DIAGNOSIS_CODE"),
    (r"income|salary|wage|balance|amount|fee", "sensitive_attribute", "FINANCIAL_DATA"),
    (r"note|text|description|message|comment|reason|subject|complaint|body", "free_text", "FREE_TEXT"),
]
VALUE_RULES = [
    (re.compile(r"^\d{6}[-+A-FU-Y]\d{3}[0-9A-Y]$"), "direct_identifier", "NATIONAL_ID"),
    (re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$"), "direct_identifier", "EMAIL"),
    (re.compile(r"^FI\d{2} ?\d{4}"), "direct_identifier", "IBAN"),
    (re.compile(r"^(\+358|0)\s?\d"), "direct_identifier", "PHONE"),
    (re.compile(r"^\d{1,3}(\.\d{1,3}){3}$"), "technical_identifier", "IP_ADDRESS"),
    (re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$", re.I), "technical_identifier", "MAC_ADDRESS"),
    (re.compile(r"^[a-f0-9]{64}$"), "technical_identifier", "OTHER"),
    (re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}"), "quasi_identifier", "TIMESTAMP"),
    (re.compile(r"^\d{4}-\d{2}-\d{2}$|^\d{1,2}\.\d{1,2}\.\d{4}$"), "quasi_identifier", "DATE"),
    (re.compile(r"^\d{5}$"), "quasi_identifier", "POSTCODE"),
    (re.compile(r"^[A-ZÅÄÖ]{2,3}-\d{1,3}$"), "direct_identifier", "LICENSE_PLATE"),
]


def classify(col: str, s: pd.Series, table: str) -> tuple[str, str]:
    name = col.lower()
    vals = s.dropna().astype(str)
    vals = vals[vals.str.len() > 0].head(400)
    # value sniffing first for obfuscated headers
    for rx, role, st in VALUE_RULES:
        if len(vals) and vals.map(lambda v: bool(rx.match(v))).mean() > .6:
            return role, st
    if len(vals) and vals.str.len().mean() > 40 and vals.str.contains(" ").mean() > .8:
        return "free_text", "FREE_TEXT"
    if re.search(r"(^|_)id$", name) and name.split("_")[0] in table:
        return "record_key", "RECORD_ID"
    for rx, role, st in NAME_RULES:
        if re.search(rx, name):
            return role, st
    if name.endswith("_id"):
        return "technical_identifier", "OTHER"
    return "non_sensitive", "CATEGORY" if not pd.api.types.is_numeric_dtype(s) else "MEASUREMENT"


def run(data_dir: Path, only: str | None = None) -> pd.DataFrame:
    rows = []
    for d in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        if only and d.name != only:
            continue
        for f in sorted(d.glob("*.csv")):
            df = pd.read_csv(f, dtype=str, nrows=3000)
            for c in df.columns:
                role, st = classify(c, df[c], f.stem)
                rows.append(dict(dataset=d.name, table=f.stem, column=c, privacy_role=role, subtype=st))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--out", default=str(ROOT / "results" / "b1_field_labels.csv"))
    ap.add_argument("--only")
    a = ap.parse_args()
    out = run(Path(a.data), a.only)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(a.out, index=False)
    print(f"wrote {len(out)} labels -> {a.out}")
