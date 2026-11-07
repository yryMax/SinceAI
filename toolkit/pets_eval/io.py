"""Loading the PETs Proving Ground package.

Package layout (participant ZIP):
  data/<domain>/<table>.csv            original synthetic tables
  metadata/field_catalog.csv           field labels (dataset, table, column, privacy_role, subtype, ...)
  metadata/scenarios.json              sharing scenarios
  metadata/pii_spans/<domain>__<table>__<column>.jsonl   gold PII spans per free-text record
  adversary/<name>.csv                 public attacker knowledge
  truth/adversary__<name>.csv          adv_row_id -> person_id (self-assessment ground truth)
  truth/<domain>__<table>.csv          record_id -> person_id
  holdout/<domain>/<table>.csv         non-member records (membership-inference self-test)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

import pandas as pd

# columns whose values must stay strings (leading zeros, long digit strings, codes)
_STRINGY = re.compile(r"(^|_)(id|ids|hetu|ssn|postcode|zip|phone|mobile|iban|pan|card|plate|gsrn|meter|mac|imei|"
                      r"ip|code|icd|number|no|account|msisdn|ref|reference|property)($|_)|_id$|^id_", re.I)


def find_package_root(start: Optional[os.PathLike] = None) -> Optional[Path]:
    """Walk upwards from `start` (or CWD / $PETS_ROOT) to the folder holding data/ and metadata/."""
    env = os.environ.get("PETS_ROOT")
    if env and (Path(env) / "metadata").exists():
        return Path(env).resolve()
    p = Path(start or Path.cwd()).resolve()
    if p.is_file():
        p = p.parent
    for q in [p, *p.parents]:
        if (q / "metadata").is_dir() and ((q / "data").is_dir() or (q / "adversary").is_dir()):
            return q
    return None


def read_table(path: os.PathLike) -> pd.DataFrame:
    """Read a CSV (or parquet) keeping identifier-like columns as strings."""
    path = Path(path)
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    head = pd.read_csv(path, nrows=0)
    dtype = {c: str for c in head.columns if _STRINGY.search(str(c))}
    return pd.read_csv(path, dtype=dtype, low_memory=False, keep_default_na=True)


def load_tables(folder: os.PathLike, tables: Optional[list] = None) -> dict[str, pd.DataFrame]:
    """Load all CSV/parquet files of a folder into {table_name: DataFrame} (rowmap_* files skipped)."""
    folder = Path(folder)
    out = {}
    if not folder.exists():
        return out
    for f in sorted(list(folder.glob("*.csv")) + list(folder.glob("*.parquet"))):
        name = f.stem
        if name.startswith("rowmap_") or name.startswith("_"):
            continue
        if tables and name not in tables:
            continue
        out[name] = read_table(f)
    return out


def load_catalog(root: Optional[os.PathLike] = None, path: Optional[os.PathLike] = None) -> pd.DataFrame:
    if path is None:
        root = Path(root or find_package_root() or ".")
        path = root / "metadata" / "field_catalog.csv"
    df = pd.read_csv(path, dtype=str).fillna("")
    if "art9_special_category" in df:
        df["art9_special_category"] = df.art9_special_category.str.lower().isin(["true", "1", "yes"])
    return df


def load_scenarios(root: Optional[os.PathLike] = None) -> list[dict]:
    root = Path(root or find_package_root() or ".")
    f = root / "metadata" / "scenarios.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def get_scenario(scenario_id: str, root: Optional[os.PathLike] = None) -> Optional[dict]:
    for s in load_scenarios(root):
        if s.get("id") == scenario_id:
            return s
    return None


def spans_path(root: os.PathLike, domain: str, table: str, column: str) -> Path:
    return Path(root) / "metadata" / "pii_spans" / f"{domain}__{table}__{column}.jsonl"


def load_spans(path: os.PathLike) -> dict[str, list[dict]]:
    """{record_id: [ {start,end,label,text}, ... ]} from a spans JSONL file."""
    out: dict[str, list[dict]] = {}
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"spans file not found: {path} (see metadata/pii_spans/ for available files)")
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out[str(r["record_id"])] = r.get("spans", [])
    return out


def list_span_files(root: os.PathLike, domain: Optional[str] = None) -> list[tuple[str, str, str, Path]]:
    """[(domain, table, column, path)] for every spans file."""
    d = Path(root) / "metadata" / "pii_spans"
    out = []
    for f in sorted(d.glob("*.jsonl")) if d.exists() else []:
        parts = f.stem.split("__")
        if len(parts) == 3 and (domain is None or parts[0] == domain):
            out.append((parts[0], parts[1], parts[2], f))
    return out


def list_adversaries(root: os.PathLike) -> list[str]:
    d = Path(root) / "adversary"
    return sorted(f.stem for f in d.glob("*.csv")) if d.exists() else []


def load_adversary(root: os.PathLike, name: str) -> tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    """(adversary table, truth adv_row_id->person_id or None)."""
    root = Path(root)
    adv = read_table(root / "adversary" / f"{name}.csv")
    t = root / "truth" / f"adversary__{name}.csv"
    truth = pd.read_csv(t, dtype=str) if t.exists() else None
    return adv, truth


def load_identity_truth(root: os.PathLike, domain: str, table: str) -> Optional[pd.DataFrame]:
    f = Path(root) / "truth" / f"{domain}__{table}.csv"
    return pd.read_csv(f, dtype=str).fillna("") if f.exists() else None


def load_holdout(root: os.PathLike, domain: str, table: str) -> Optional[pd.DataFrame]:
    f = Path(root) / "holdout" / domain / f"{table}.csv"
    return read_table(f) if f.exists() else None


def load_rowmap(path: os.PathLike) -> pd.DataFrame:
    """Row map: protected_row (0-based row index in the protected CSV) -> original_record_id.
    Accepted column names: (protected_row | row | index) and (original_record_id | record_id)."""
    df = pd.read_csv(path, dtype=str)
    cols = {c.lower(): c for c in df.columns}
    pr = next((cols[c] for c in ("protected_row", "row", "index", "protected_index") if c in cols), df.columns[0])
    rid = next((cols[c] for c in ("original_record_id", "record_id", "original_id") if c in cols), df.columns[-1])
    out = pd.DataFrame({"protected_row": pd.to_numeric(df[pr], errors="coerce").astype("Int64"),
                        "original_record_id": df[rid].astype(str)})
    return out.dropna()


def record_key(catalog: Optional[pd.DataFrame], domain: str, table: str, df: pd.DataFrame) -> Optional[str]:
    """Primary-key column of a table: catalog role record_key, else first column ending in _id."""
    if catalog is not None and len(catalog):
        m = catalog[(catalog.dataset == domain) & (catalog.table == table) & (catalog.privacy_role == "record_key")]
        for c in m.column:
            if c in df.columns:
                return c
    for c in df.columns:
        if str(c).endswith("_id") and df[c].is_unique:
            return c
    return None


def load_attack_specs(root: Optional[os.PathLike]) -> list[dict]:
    """Linkage-attack specifications (metadata/attack_specs.json); empty list if absent."""
    if root is None:
        return []
    f = Path(root) / "metadata" / "attack_specs.json"
    if not f.exists():
        return []
    import json
    return json.loads(f.read_text(encoding="utf-8")).get("attacks", [])
