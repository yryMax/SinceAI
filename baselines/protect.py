"""Run one catalog-driven baseline protection level on one dataset and score it.

usage: python3 baselines/protect.py --level b2 --dataset health [--scenario HEALTH-S1] [--out results/b2/health]
levels: b0 = drop direct identifiers; b2 = classic SDC (keyed pseudonyms, generalisation, regex redaction);
        b2k = b2 + local suppression to k >= 5 on the catalogued quasi-identifiers.
"""
import argparse
import shutil
from pathlib import Path

from _common import ROOT, catalog_for, io, protect_table, write_protected
from pets_eval.scorecard import run_scorecard

ap = argparse.ArgumentParser()
ap.add_argument("--level", choices=["b0", "b2", "b2k"], required=True)
ap.add_argument("--dataset", required=True)
ap.add_argument("--scenario")
ap.add_argument("--out")
a = ap.parse_args()
cat = catalog_for(a.dataset)
orig = io.load_tables(ROOT / "data" / a.dataset)
prot = {t: protect_table(a.dataset, t, df, cat, a.level) for t, df in orig.items()}
out = Path(a.out or ROOT / "results" / a.level / a.dataset)
if out.exists():
    shutil.rmtree(out)
write_protected(prot, orig, out, cat, a.dataset)
rep = run_scorecard(ROOT / "data" / a.dataset, out, scenario=a.scenario, root=ROOT, out_dir=out)
print(rep["summary"])
print("scorecard:", out / "scorecard.html")
