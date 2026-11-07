"""Run every reference baseline and write results/benchmark.json (docs/BENCHMARK.md summarises it).

usage: python3 baselines/run_all.py [--domains health,finance] [--quick]
Run from the package root (the folder that contains data/, metadata/, toolkit/).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ROOT, catalog_for, io, protect_table, write_protected  # noqa: E402
from pets_eval import detect  # noqa: E402
from pets_eval.scorecard import run_scorecard  # noqa: E402

DOMAINS = ["health", "mobility", "smart_city", "energy", "finance", "cyber", "education", "public_admin", "customer_service"]
RES = ROOT / "results"


def scen_ids(domain: str) -> list[str]:
    return [s["id"] for s in io.load_scenarios(ROOT) if s["dataset"] == domain]


def summarise(rep: dict) -> dict:
    s = rep["summary"]
    risks = rep.get("risk_components", {})
    reid = [v for k, v in risks.items() if "reid" in k.lower() or "linkage" in k.lower()]
    resid = [v for k, v in risks.items() if "residual" in k.lower() or "direct" in k.lower()]
    return {"privacy": s["privacy"], "utility": s["utility"], "composite": s["composite"],
            "worst_reid": max(reid) if reid else None, "residual_identifiers": max(resid) if resid else None,
            "utility_tasks": {u["id"]: (None if u["score"] is None else round(u["score"], 3)) for u in rep["utility"]}}


def run_protect(domain: str, level: str, scenario: str | None = None) -> dict:
    cat = catalog_for(domain)
    orig = io.load_tables(ROOT / "data" / domain)
    prot = {t: protect_table(domain, t, df, cat, level) for t, df in orig.items()}
    out = RES / level / domain
    if out.exists():
        shutil.rmtree(out)
    write_protected(prot, orig, out, cat, domain)
    rep = run_scorecard(ROOT / "data" / domain, out, scenario=scenario, root=ROOT, out_dir=out)
    return summarise(rep)


def per_scenario(domain: str, summ: dict) -> dict:
    """Utility per scenario from one all-task run: mean of the scenario's required tasks (unanswerable = 0)."""
    out = {}
    for s in io.load_scenarios(ROOT):
        if s["dataset"] != domain:
            continue
        req = s.get("utility_requirements") or []
        vals = [summ["utility_tasks"].get(t) for t in req if t in summ["utility_tasks"]]
        out[s["id"]] = round(sum(v or 0 for v in vals) / len(vals), 3) if vals else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", default=",".join(DOMAINS))
    a = ap.parse_args()
    RES.mkdir(exist_ok=True)
    bench: dict = {"generated": time.strftime("%Y-%m-%d %H:%M"), "baselines": {}}

    # B1 detection
    import b1_detect_rules as b1
    pred = b1.run(ROOT / "data")
    pred.to_csv(RES / "b1_field_labels.csv", index=False)
    cat = io.load_catalog(ROOT)
    det = detect.score_detection(pred[pred.dataset != "unseen"], cat)
    bench["baselines"]["B1_detection_public"] = {k: det[k] for k in det if k in ("macro_f1", "subtype_accuracy", "sensitive_recall", "per_role")}
    print("B1", json.dumps(bench["baselines"]["B1_detection_public"])[:300], flush=True)

    for d in [x for x in a.domains.split(",") if x]:
        for level in ("b0", "b2", "b2k"):
            t = time.time()
            try:
                r = run_protect(d, level)
                r["utility_by_scenario"] = per_scenario(d, r)
            except Exception as e:  # noqa: BLE001
                r = {"error": f"{type(e).__name__}: {e}"}
            r["runtime_s"] = round(time.time() - t, 1)
            bench["baselines"][f"{level.upper()}_{d}"] = r
            print(level, d, {k: r.get(k) for k in ("privacy", "utility", "composite", "worst_reid", "utility_by_scenario", "runtime_s", "error")}, flush=True)

    if "health" in a.domains:
        import b3_dp_health as b3
        import b4_synth_health as b4
        from pets_eval.utility.health import udp_workload
        visits = io.read_table(ROOT / "data" / "health" / "ed_visits.csv")
        wl = json.loads((ROOT / "metadata" / "dp_query_workload_health.json").read_text())
        dp = {}
        for eps in (0.25, 0.5, 1.0, 2.0, 5.0):
            ans = b3.answer(visits, wl, eps)
            r = udp_workload({"ed_visits": visits}, {"dp_answers": ans})
            dp[str(eps)] = {"score": r["score"], **r["detail"]}
        bench["baselines"]["B3_dp_health"] = dp
        print("B3", dp, flush=True)
        out = RES / "b4" / "health"
        out.mkdir(parents=True, exist_ok=True)
        syn = b4.decode(b4.fit_sample(b4.prepare(visits), 40000))
        syn.to_csv(out / "ed_visits.csv", index=False)
        rep = run_scorecard(ROOT / "data" / "health", out, scenario="HEALTH-S3", root=ROOT, out_dir=out)
        bench["baselines"]["B4_synth_health"] = summarise(rep) | {"risk_components": rep.get("risk_components")}
        print("B4", bench["baselines"]["B4_synth_health"], flush=True)

    (RES / "benchmark.json").write_text(json.dumps(bench, indent=2, default=str))
    print("wrote", RES / "benchmark.json")


if __name__ == "__main__":
    main()
