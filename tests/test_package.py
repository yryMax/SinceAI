"""Integrity tests for the participant package. Run from the package root: python3 -m pytest -q tests/"""
import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
pytestmark = pytest.mark.skipif(not (ROOT / "MANIFEST.json").exists(), reason="run inside the assembled package")


def tables():
    return sorted(DATA.glob("*/*.csv"))


def test_manifest_checksums():
    man = json.loads((ROOT / "MANIFEST.json").read_text())
    bad = []
    for f in man["files"]:
        p = ROOT / f["path"]
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != f["sha256"]:
            bad.append(f["path"])
    assert not bad, bad[:10]


def test_no_private_material():
    names = {p.name for p in ROOT.rglob("*")}
    for forbidden in ("answer_keys", "labels", "master", "generator", "SPEC.md", "unseen_field_catalog.csv"):
        assert forbidden not in names, forbidden
    assert not list((ROOT / "truth").glob("unseen__*"))
    assert not (ROOT / "metadata" / "field_catalog.csv").read_text().count("\nunseen,")


def test_catalog_covers_every_column():
    cat = pd.read_csv(ROOT / "metadata" / "field_catalog.csv", dtype=str)
    have = set(zip(cat.dataset, cat.table, cat.column))
    missing = []
    for f in tables():
        if f.parent.name == "unseen":
            continue
        for c in pd.read_csv(f, nrows=0).columns:
            if (f.parent.name, f.stem, c) not in have:
                missing.append(f"{f.parent.name}/{f.stem}.{c}")
    assert not missing, missing[:20]


def test_record_keys_unique():
    cat = pd.read_csv(ROOT / "metadata" / "field_catalog.csv", dtype=str)
    for r in cat[cat.privacy_role == "record_key"].itertuples():
        f = DATA / r.dataset / f"{r.table}.csv"
        s = pd.read_csv(f, usecols=[r.column], dtype=str)[r.column]
        assert s.is_unique, f"{r.dataset}/{r.table}.{r.column}"


def test_spans_match_text():
    for f in sorted((ROOT / "metadata" / "pii_spans").glob("*.jsonl")):
        dom, table, col = f.stem.split("__")
        df = pd.read_csv(DATA / dom / f"{table}.csv", dtype=str, keep_default_na=False)
        cat = pd.read_csv(ROOT / "metadata" / "field_catalog.csv", dtype=str)
        key = cat[(cat.dataset == dom) & (cat.table == table) & (cat.privacy_role == "record_key")].column.iloc[0]
        text = dict(zip(df[key], df[col]))
        n = 0
        for line in open(f, encoding="utf-8"):
            r = json.loads(line)
            t = text[r["record_id"]]
            for s in r["spans"]:
                assert t[s["start"]:s["end"]] == s["text"], (f.name, r["record_id"], s)
            n += 1
            if n > 3000:
                break


def test_safe_identifier_ranges():
    email_rx = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
    hetu_rx = re.compile(r"\b\d{6}[-+A]\d{3}[0-9A-Y]\b")
    for f in tables():
        txt = f.read_text(encoding="utf-8")[:3_000_000]
        for dom in set(email_rx.findall(txt)):
            assert dom.endswith(".example") or dom.endswith(".example.com"), (f, dom)
        for h in set(hetu_rx.findall(txt)):
            assert 900 <= int(h[7:10]) <= 999, (f, h)
