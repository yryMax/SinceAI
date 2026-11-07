"""Command line interface: pets-eval <command>

  scorecard  privacy + utility self-assessment of a protected release (JSON + HTML)
  detect     score your field classification against metadata/field_catalog.csv
  text       score PII spans (--pred) or redacted text (--protected) against gold spans
  check      scan files/folders for residual direct identifiers
  tasks      list utility tasks (optionally for one dataset)
  scenarios  list sharing scenarios
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from . import check, detect, io, scorecard, text


def _print(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_scorecard(a):
    rowmaps = {}
    for r in a.rowmap or []:
        if "=" in r:
            t, p = r.split("=", 1)
        else:
            p = r
            t = Path(r).stem.replace("rowmap_", "")
        rowmaps[t] = p
    rep = scorecard.run_scorecard(a.original, a.protected, a.scenario, a.root, rowmaps, a.out, a.max_adversary)
    out = Path(a.out or a.protected)
    s = rep["summary"]
    print(f"privacy {s['privacy']}  utility {s['utility']}  composite {s['composite']}  ({s['label']})")
    for k, v in rep["risk_components"].items():
        print(f"  risk  {v:6.1%}  {k}")
    for u in rep["utility"]:
        sc = "n/a " if u["score"] is None else f"{u['score']:.2f}"
        print(f"  util  {sc}  {u['id']}  {u.get('metric', '')}")
    print(f"wrote {out / 'scorecard.json'} and {out / 'scorecard.html'}")


def cmd_detect(a):
    cat = io.load_catalog(a.root, a.catalog)
    pred = pd.read_csv(a.pred, dtype=str)
    res = detect.score_detection(pred, cat, a.datasets.split(",") if a.datasets else None)
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2, default=str))
    res.pop("errors", None)
    res.pop("confusion", None)
    _print(res)


def _load_pred_spans(path):
    return io.load_spans(path)


def cmd_text(a):
    gold = io.load_spans(a.gold)
    if a.pred:
        pred = _load_pred_spans(a.pred)
        res = {"exact": text.span_scores(gold, pred, "exact"), "overlap": text.span_scores(gold, pred, "overlap"),
               "overlap_label_agnostic": text.span_scores(gold, pred, "overlap", label_agnostic=True)}
    elif a.protected:
        df = io.read_table(a.protected)
        if a.rowmap:
            rm = io.load_rowmap(a.rowmap)
            texts = dict(zip(rm.original_record_id, df[a.text_col].fillna("").astype(str).values[rm.protected_row.astype(int).values]))
        else:
            texts = dict(zip(df[a.id_col].astype(str), df[a.text_col].fillna("").astype(str)))
        res = text.redaction_leakage(gold, texts)
    else:
        sys.exit("give --pred spans.jsonl or --protected file.csv --text-col COL (--id-col ID | --rowmap R)")
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2, ensure_ascii=False))
    _print(res)


def cmd_check(a):
    rep = check.scan_path(a.path, a.max_lines)
    if a.out:
        Path(a.out).write_text(json.dumps(rep, indent=2))
    print(f"scanned {rep['n_files_scanned']} files")
    for k, v in sorted(rep["totals"].items(), key=lambda x: -x[1]):
        print(f"  {k:15s} {v:8d}  e.g. {', '.join(rep['examples'].get(k, []))}")
    if not rep["totals"]:
        print("  no residual direct identifiers found by the regex scan")
    print(rep["note"])


def cmd_tasks(a):
    from .utility import all_tasks
    for t in all_tasks([a.dataset] if a.dataset else None):
        print(f"{t.id:28s} {t.dataset:16s} {t.table:22s} {t.description}")


def cmd_scenarios(a):
    for s in io.load_scenarios(a.root):
        if a.dataset and s.get("dataset") != a.dataset:
            continue
        print(f"{s['id']:14s} {s.get('trust_level', ''):20s} {s.get('title', '')}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pets-eval", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scorecard", help="privacy + utility self-assessment")
    s.add_argument("--original", required=True, help="original dataset folder, e.g. data/health")
    s.add_argument("--protected", required=True, help="folder with your protected tables")
    s.add_argument("--rowmap", action="append", help="rowmap CSV (or table=path); auto-detected rowmap_<table>.csv")
    s.add_argument("--scenario", help="scenario id, e.g. HEALTH-S1")
    s.add_argument("--root", help="package root (auto-detected)")
    s.add_argument("--out", help="output folder (default: protected folder)")
    s.add_argument("--max-adversary", type=int, default=3000)
    s.set_defaults(fn=cmd_scorecard)
    d = sub.add_parser("detect", help="score field classification")
    d.add_argument("--pred", required=True)
    d.add_argument("--catalog")
    d.add_argument("--root")
    d.add_argument("--datasets")
    d.add_argument("--out")
    d.set_defaults(fn=cmd_detect)
    t = sub.add_parser("text", help="score spans or redacted text")
    t.add_argument("--gold", required=True, help="metadata/pii_spans/<domain>__<table>__<column>.jsonl")
    t.add_argument("--pred", help="your spans JSONL (record_id, spans)")
    t.add_argument("--protected", help="CSV with your protected texts")
    t.add_argument("--text-col")
    t.add_argument("--id-col")
    t.add_argument("--rowmap")
    t.add_argument("--out")
    t.set_defaults(fn=cmd_text)
    c = sub.add_parser("check", help="scan for residual direct identifiers")
    c.add_argument("path")
    c.add_argument("--max-lines", type=int)
    c.add_argument("--out")
    c.set_defaults(fn=cmd_check)
    k = sub.add_parser("tasks", help="list utility tasks")
    k.add_argument("--dataset")
    k.set_defaults(fn=cmd_tasks)
    sc = sub.add_parser("scenarios", help="list sharing scenarios")
    sc.add_argument("--dataset")
    sc.add_argument("--root")
    sc.set_defaults(fn=cmd_scenarios)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
