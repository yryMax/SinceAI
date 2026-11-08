"""Evaluate: the only program that reads the organisers' answers (metadata/, gold spans, attackers).

    python3 solution/evaluate.py detection     # field labels vs metadata/field_catalog.csv (with and without names)
    python3 solution/evaluate.py text          # free-text redaction vs gold PII spans, against the B2 regex
    python3 solution/evaluate.py scenarios     # all 27 scenarios: pipeline.py + pets-eval scorecard vs baselines
    python3 solution/evaluate.py scenarios --only HEALTH-S1,FIN-S3

Results go to out/evaluation/. The scorecard is the organisers' unmodified self-assessment tool.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "solution"), str(ROOT / "toolkit"), str(ROOT / "baselines")]
warnings.filterwarnings("ignore")

from detector import detect_tables  # noqa: E402
from pets_eval import detect as det, io, text as txt  # noqa: E402
from pipeline import TRUST, protect_folder, read_folder  # noqa: E402

OUT = ROOT / "out" / "evaluation"
KEY = ["dataset", "table", "column"]


# ------------------------------------------------------------------ 1. detection
def detect_all(hide_names: bool) -> pd.DataFrame:
    """Run the detector on every labelled dataset; optionally hide column/table names (like data/unseen)."""
    rows = []
    for ds in sorted(io.load_catalog(ROOT).dataset.unique()):
        tables = read_folder(ROOT / "data" / ds)
        if not hide_names:
            rows.append(detect_tables(tables, ds))
            continue
        renamed = {f"t{i:02d}": df.set_axis([f"c{j + 1:02d}" for j in range(df.shape[1])], axis=1)
                   for i, df in enumerate(tables.values())}
        p = detect_tables(renamed, "unseen")
        real = {(f"t{i:02d}", f"c{j + 1:02d}"): (t, c) for i, (t, df) in enumerate(tables.items()) for j, c in enumerate(df.columns)}
        p[["table", "column"]] = [real[(t, c)] for t, c in zip(p.table, p.column)]
        p["dataset"] = ds
        rows.append(p)
    return pd.concat(rows, ignore_index=True)


def detection():
    cat = io.load_catalog(ROOT)
    b1 = pd.read_csv(ROOT / "results" / "b1_field_labels.csv")
    rows = []
    for name, pred in [("ours, column names visible", detect_all(False)), ("ours, names hidden (like unseen)", detect_all(True)),
                       ("B1 baseline", b1)]:
        r = det.score_detection(pred, cat)
        rows.append({"detector": name, "fields": r["n_fields"], "role_accuracy": r["accuracy"], "macro_f1": r["macro_f1"],
                     "sensitive_recall": r["sensitive_recall"], "subtype_accuracy": r["subtype_accuracy"]})
        if name.startswith("ours"):
            m = cat.merge(pred, on=KEY, suffixes=("", "_pred"))
            m[(m.privacy_role != m.privacy_role_pred) | (m.subtype != m.subtype_pred)].to_csv(
                OUT / f"detection_errors_{'hidden' if 'hidden' in name else 'named'}.csv", index=False)
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "detection.csv", index=False)
    print(res.round(3).to_string(index=False))


# ------------------------------------------------------------------ 2. free text
def text():
    from _common import regex_redact            # B2's text redaction, for comparison
    from text_detector import TextDetector
    rows = []
    for path in sorted((ROOT / "metadata" / "pii_spans").glob("*.jsonl")):
        ds, table, column = path.stem.split("__")
        tables = read_folder(ROOT / "data" / ds)
        detector = TextDetector(tables, detect_tables(tables, ds), dataset=ds)
        frame = tables[table]
        rk = io.record_key(io.load_catalog(ROOT), ds, table, frame)
        values = dict(zip(frame[rk].astype(str), frame[column].fillna("")))
        gold = io.load_spans(path)            # loaded only after the detector is built
        ours = txt.redaction_leakage(gold, {r: detector.redact(v, table, column) for r, v in values.items()})
        b2 = txt.redaction_leakage(gold, {r: regex_redact(v) for r, v in values.items()})
        rows.append({"field": path.stem, "ours_identifying_leakage": ours["identifying_leakage_rate"],
                     "b2_identifying_leakage": b2["identifying_leakage_rate"]})
        print(rows[-1], flush=True)
    pd.DataFrame(rows).to_csv(OUT / "text.csv", index=False)


# ------------------------------------------------------------------ 3. scenarios
def score(scenario: dict, out: Path) -> dict:
    """The stock scorecard on our release, with our private row maps (same as the pets-eval CLI with --rowmap)."""
    from pets_eval.scorecard import run_scorecard
    rowmaps = {f.stem[len("rowmap_"):]: f for f in (out / "private").glob("rowmap_*.csv")}
    rep = run_scorecard(ROOT / "data" / scenario["dataset"], out / "release", scenario=scenario["id"], root=ROOT,
                        rowmaps=rowmaps, out_dir=out / "private" / "scorecard")
    return rep["summary"]


def scenarios(only: str = ""):
    base = json.loads((ROOT / "solution" / "baseline_scores.json").read_text())["scenarios"]
    rows = []
    for s in io.load_scenarios(ROOT):
        if only and s["id"] not in only.split(","):
            continue
        out = OUT / "scenarios" / s["id"]
        protect_folder(ROOT / "data" / s["dataset"], s["trust_level"], out)
        summ = score(s, out)
        best = max(base[s["id"]], key=lambda k: base[s["id"]][k])
        rows.append({"scenario": s["id"], "trust": s["trust_level"], "privacy": summ["privacy"], "utility": summ["utility"],
                     "composite": summ["composite"], "best_baseline": best, "baseline_composite": base[s["id"]][best]})
        print(rows[-1], flush=True)
    res = pd.DataFrame(rows)
    res["wins"] = res.composite > res.baseline_composite
    f = OUT / "scenarios.csv"
    if only and f.exists():   # a partial rerun updates its rows and keeps the others
        res = pd.concat([pd.read_csv(f).query("scenario not in @res.scenario"), res])
    order = [s["id"] for s in io.load_scenarios(ROOT)]
    res = res.set_index("scenario").loc[[s for s in order if s in set(res.scenario)]].reset_index()
    res.to_csv(f, index=False)
    print(res.to_string(index=False))
    print(f"\nmean composite {res.composite.mean():.3f} vs best baseline {res.baseline_composite.mean():.3f}; "
          f"wins {int(res.wins.sum())}/{len(res)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["detection", "text", "scenarios"])
    ap.add_argument("--only", default="", help="comma-separated scenario ids")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    {"detection": detection, "text": text, "scenarios": lambda: scenarios(a.only)}[a.what]()
