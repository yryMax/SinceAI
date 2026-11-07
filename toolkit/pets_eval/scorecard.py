"""One-command privacy + utility self-assessment of a protected release.

    pets-eval scorecard --original data/health --protected my_out/health --scenario HEALTH-S1

Protected folder conventions
- same table file names as the original (e.g. ed_visits.csv); a table you do not release is "withheld"
- keep original column names for columns you keep; generalised values are fine (see pets_eval.parse)
- row map per released microdata table: rowmap_<table>.csv with columns protected_row (0-based row
  index in your protected CSV) and original_record_id. It is used ONLY for scoring — never publish it.
- no row map + no original record ids => the table is treated as synthetic data (DCR / membership inference)

Composite (self-assessment, NOT the official judging score):
  privacy  = 1 - (0.5 * worst risk + 0.5 * mean risk) over the evaluated risk components
  utility  = mean score of the scenario's utility tasks (a required task you cannot answer scores 0)
  composite = weighted harmonic mean of privacy (weight 30) and utility (weight 25)
  -> a release must do well on BOTH to score well; withholding everything or releasing everything both score low.
"""
from __future__ import annotations

import html
import json
import time
import traceback
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from . import attacks, check, io, privacy, text
from .utility import all_tasks

PRIV_W, UTIL_W = 30, 25


def _cat_cols(cat: pd.DataFrame, table: str, role: str) -> list:
    if cat is None or cat.empty:
        return []
    return list(cat[(cat.table == table) & (cat.privacy_role == role)].column)


def _norm_vals(s: pd.Series) -> pd.Series:
    return s.dropna().astype(str).str.strip().str.lower().str.replace(r"[\s\-\.]", "", regex=True)


def _adversaries_for(root: Path, domain: str, scenario: Optional[dict]) -> list[str]:
    names = io.list_adversaries(root)
    have_truth = [n for n in names if (root / "truth" / f"adversary__{n}.csv").exists()]
    if scenario:
        tm = json.dumps(scenario.get("threat_model", ""))
        picked = [n for n in have_truth if n in tm]
        if picked:
            return picked
    dom = [n for n in have_truth if domain.split("_")[0] in n]
    return dom or have_truth


def _record_ids_for_rows(prot: pd.DataFrame, rowmap: Optional[pd.DataFrame], rk: Optional[str],
                         orig_ids: set) -> tuple[Optional[pd.DataFrame], str]:
    if rowmap is not None:
        return rowmap, "row map"
    if rk and rk in prot.columns:
        ids = prot[rk].astype(str)
        if ids.isin(orig_ids).mean() > 0.5:
            return pd.DataFrame({"protected_row": np.arange(len(prot)), "original_record_id": ids.values}), \
                "original record ids kept in the release (itself a linkage key)"
    return None, ""


def evaluate_table(domain, table, orig, prot, cat, root, scenario, rowmap, max_adversary) -> dict:
    t0 = time.time()
    r: dict = {"table": table, "status": "released", "rows_original": int(len(orig)), "rows_protected": int(len(prot))}
    rk = io.record_key(cat, domain, table, orig)
    r["columns_dropped"] = [c for c in orig.columns if c not in prot.columns]
    r["columns_added"] = [c for c in prot.columns if c not in orig.columns]
    risks: dict = {}

    # 1. residual direct identifiers (same values as in the original)
    retained = {}
    for c in _cat_cols(cat, table, "direct_identifier"):
        if c in prot.columns and c in orig.columns:
            ov = set(_norm_vals(orig[c]))
            pv = _norm_vals(prot[c])
            share = float(pv.isin(ov).mean()) if len(pv) else 0.0
            if share > 0:
                retained[c] = round(share, 4)
    r["direct_identifiers_retained"] = retained
    risks["direct identifiers retained"] = max(retained.values()) if retained else 0.0

    # 2. hashed identifiers that reverse by enumeration
    hcols = attacks.detect_hash_columns(prot)
    if hcols:
        cand_cols = [c for c in _cat_cols(cat, table, "direct_identifier") + _cat_cols(cat, table, "technical_identifier")
                     if c in orig.columns]
        cands = pd.unique(pd.concat([orig[c].dropna().astype(str) for c in cand_cols])) if cand_cols else []
        hr = {c: attacks.hash_dictionary_attack(prot[c], cands[:300000]) for c in hcols}
        r["hash_attack"] = hr
        risks["hashed ids reversible"] = max((v.get("share_values_reversed", 0) for v in hr.values()), default=0.0)

    # 3. equivalence classes on quasi-identifiers
    qis = [c for c in _cat_cols(cat, table, "quasi_identifier") if c in prot.columns]
    sens = [c for c in _cat_cols(cat, table, "sensitive_attribute") if c in prot.columns]
    if qis:
        r["k_anonymity"] = privacy.k_anonymity(prot, qis)
        oq = [c for c in qis if c in orig.columns]
        r["k_anonymity_original"] = privacy.k_anonymity(orig, oq)
        risks["records with k<5"] = r["k_anonymity"]["share_below"]["k<5"]
        if sens:
            r["l_diversity"] = privacy.l_diversity(prot, qis, sens[0])
    else:
        r["k_anonymity"] = {"note": "no catalogued quasi-identifier kept"}

    # 3b. trajectory unicity (mobility-type tables): how many subjects do a few known points single out?
    if root:
        f = Path(root) / "metadata" / "attack_specs.json"
        trs = json.loads(f.read_text(encoding="utf-8")).get("trajectories", []) if f.exists() else []
        for tr in [t for t in trs if t["dataset"] == domain and t["table"] == table]:
            kw = dict(user_col=tr["user"], time_col=tr["time"], lat_col=tr.get("lat"), lon_col=tr.get("lon"),
                      place_col=tr.get("place"), p=tr.get("p", 4), temporal=tr.get("temporal", "1h"),
                      spatial_m=tr.get("spatial_m", 500), n_users=1000)
            res = privacy.trajectory_unicity(prot, **kw) if tr["user"] in prot.columns else \
                {"evaluated": True, "unicity": 0.0, "note": f"{tr['user']} removed: traces cannot be linked"}
            base = privacy.trajectory_unicity(orig, **kw)
            res["unicity_original"] = base.get("unicity")
            res["attack"] = tr.get("description", "")
            r.setdefault("trajectory_unicity", {})[tr["user"]] = res
            if res.get("evaluated"):
                risks[f"trajectory unicity ({tr['user']})"] = res.get("unicity", 0.0)

    # 4. linkage attacks with background knowledge
    identity = io.load_identity_truth(root, domain, table) if root else None
    rm, rm_source = _record_ids_for_rows(prot, rowmap, rk, set(orig[rk].astype(str)) if rk else set())
    r["row_alignment"] = rm_source or "none"
    if rm is None and "records with k<5" in risks:
        # no link from released rows to real records (synthetic / aggregate release): k is reported, not scored
        risks.pop("records with k<5")
        r["k_anonymity"]["note"] = "not scored as a risk: rows are not linked to real records (synthetic or aggregate)"
    temporal = list(cat[(cat.table == table) & (cat.data_kind == "temporal")].column) if cat is not None and not cat.empty else []
    if rm is not None and identity is not None and identity.iloc[:, 1].astype(str).str.len().gt(0).any():
        r["linkage"] = {}
        orig_rm = pd.DataFrame({"protected_row": np.arange(len(orig)), "original_record_id": orig[rk].astype(str).values}) if rk else None
        worst = 0.0
        all_specs = io.load_attack_specs(root)
        specs = [sp for sp in all_specs if sp["dataset"] == domain and sp["table"] == table]
        if not specs and any(sp["dataset"] == domain for sp in all_specs):
            plan = []  # this table has no realistic background-knowledge attack in the package
            r["linkage"]["note"] = "no attack spec targets this table (metadata/attack_specs.json)"
        elif specs:
            names = _adversaries_for(root, domain, scenario)
            chosen = [sp for sp in specs if sp["adversary"] in names] or specs
            plan = [(sp["adversary"], sp) for sp in chosen]
        else:
            plan = [(n, None) for n in _adversaries_for(root, domain, scenario)]
        for adv_name, sp in plan:
            adv, truth = io.load_adversary(root, adv_name)
            try:
                sens_col = (sp.get("sensitive") if sp else None) or (sens[0] if sens else None)
                sens_col = sens_col if sens_col in orig.columns else None
                q_p = attacks.qis_from_spec(sp["qis"], prot.columns) if sp else None
                q_o = attacks.qis_from_spec(sp["qis"], orig.columns) if sp else None
                ent = sp.get("entity") if sp else None
                if sp and not q_p:
                    res = {"evaluated": True, "qis_used": [], "reidentification_rate": 0.0, "n_targets_in_data": None,
                           "note": "every attacker column this attack needs was removed from the release"}
                else:
                    res = attacks.linkage_attack(adv, truth, prot, rm, identity, qis=q_p, original=orig, record_key=rk,
                                                 sensitive=sens_col, temporal_cols=temporal, max_adversary=max_adversary,
                                                 entity=ent)
                if sp:
                    res["attack"] = sp.get("description", "")
                if res.get("evaluated") and orig_rm is not None:
                    base = attacks.linkage_attack(adv, truth, orig, orig_rm, identity, qis=q_o, temporal_cols=temporal,
                                                  max_adversary=max_adversary, entity=ent)
                    res["baseline_reidentification_rate_original"] = base.get("reidentification_rate")
                    if base.get("reidentification_rate"):
                        res["risk_reduction"] = round(1 - res["reidentification_rate"] / base["reidentification_rate"], 4)
                if res.get("evaluated"):
                    worst = max(worst, res["reidentification_rate"],
                                res.get("attribute_inference", {}).get("advantage_over_base_rate", 0.0))
            except Exception as e:  # noqa: BLE001
                res = {"evaluated": False, "reason": f"error: {e}"}
            r["linkage"][adv_name] = res
        if any(isinstance(v, dict) and v.get("evaluated") for v in r["linkage"].values()):
            risks["linkage re-identification"] = worst
    elif rm is None:
        r["linkage"] = {"note": "no row map: linkage not evaluated (treated as synthetic / aggregate release)"}

    # 5. free text
    tcols = [c for c in _cat_cols(cat, table, "free_text") if c in orig.columns]
    if tcols and root:
        r["free_text"] = {}
        worst = 0.0
        for c in tcols:
            sp_path = io.spans_path(root, domain, table, c)
            gold = io.load_spans(sp_path) if sp_path.exists() else {}
            if not gold:
                r["free_text"][c] = {"evaluated": False, "reason": "no gold spans in package"}
                continue
            if c not in prot.columns:
                r["free_text"][c] = {"evaluated": True, "status": "withheld", "identifying_leakage_rate": 0.0}
                continue
            if rm is None:
                r["free_text"][c] = {"evaluated": False, "reason": "needs a row map to align texts"}
                continue
            idx = rm.protected_row.astype(int).values
            ok = (idx >= 0) & (idx < len(prot))
            texts = dict(zip(rm.original_record_id.astype(str).values[ok], prot[c].fillna("").astype(str).values[idx[ok]]))
            res = text.redaction_leakage(gold, texts)
            res.pop("examples", None)
            r["free_text"][c] = {"evaluated": True, **res}
            worst = max(worst, res["identifying_leakage_rate"])
        if any(v.get("evaluated") for v in r["free_text"].values()):
            risks["free-text identifier leakage"] = worst

    # 6. synthetic data (no alignment)
    if rm is None and len(prot):
        excl = set(_cat_cols(cat, table, "direct_identifier") + _cat_cols(cat, table, "free_text") +
                   _cat_cols(cat, table, "record_key") + _cat_cols(cat, table, "technical_identifier"))
        cols = [c for c in prot.columns if c in orig.columns and c not in excl and orig[c].nunique() < 0.5 * len(orig)]
        hold = io.load_holdout(root, domain, table) if root else None
        if cols:
            r["synthetic"] = {"dcr": privacy.dcr_report(prot, orig, hold, cols)}
            if hold is not None and len(hold):
                mia = privacy.membership_inference_auc(prot, orig, hold, cols)
                r["synthetic"]["membership_inference"] = mia
                if mia.get("evaluated"):
                    risks["membership inference advantage"] = mia["advantage"]
            dcr = r["synthetic"]["dcr"]
            if dcr.get("evaluated"):
                risks["exact copies of original rows"] = dcr["share_exact_copies"]

    # 7. regex residual scan (direct identifiers anywhere, e.g. inside notes)
    hits = {}
    sample = prot.head(20000)
    for c in sample.columns:
        if not (pd.api.types.is_numeric_dtype(sample[c]) or pd.api.types.is_bool_dtype(sample[c])):
            counts = check.scan_text("\n".join(sample[c].dropna().astype(str).values))
            if counts:
                hits[c] = dict(counts)
    r["regex_residuals"] = hits
    r["risks"] = {k: round(float(v), 4) for k, v in risks.items()}
    r["seconds"] = round(time.time() - t0, 1)
    return r


def run_utility(domain: str, orig: dict, prot: dict, scenario: Optional[dict]) -> list[dict]:
    tasks = [t for t in all_tasks([domain]) if t.dataset == domain]
    required = set(scenario.get("utility_requirements", [])) if scenario else set()
    if scenario:
        sel = [t for t in tasks if t.id in required or scenario["id"] in (t.scenarios or [])]
        tasks = sel or tasks
    out = []
    for t in tasks:
        try:
            res = t.fn(orig, prot)
        except Exception as e:  # noqa: BLE001
            res = {"score": None, "metric": "error", "detail": {"error": f"{type(e).__name__}: {e}",
                                                                 "trace": traceback.format_exc(limit=2)}}
        out.append({"id": t.id, "table": t.table, "kind": t.kind, "description": t.description,
                    "required": t.id in required or not required, **res})
    return out


def composite(risks: dict, utility: list) -> dict:
    vals = [v for v in risks.values() if v is not None]
    if vals:
        privacy_score = 1 - (0.5 * max(vals) + 0.5 * float(np.mean(vals)))
    else:
        privacy_score = None
    us = [(u["score"] if u["score"] is not None else 0.0) for u in utility if u.get("required")]
    us += [u["score"] for u in utility if not u.get("required") and u["score"] is not None]
    utility_score = float(np.mean(us)) if us else None
    comp = None
    if privacy_score is not None and utility_score is not None:
        p, u = max(privacy_score, 1e-9), max(utility_score, 1e-9)
        comp = (PRIV_W + UTIL_W) / (PRIV_W / p + UTIL_W / u)
        if privacy_score <= 0 or utility_score <= 0:
            comp = 0.0
    rnd = lambda x: None if x is None else round(float(x), 4)  # noqa: E731
    return {"privacy": rnd(privacy_score), "utility": rnd(utility_score), "composite": rnd(comp),
            "label": "self-assessment, not the official judging score",
            "method": "privacy = 1 - (0.5*worst + 0.5*mean risk); utility = mean task score (required unanswerable = 0); "
                      "composite = weighted harmonic mean (privacy 30, utility 25)"}


def run_scorecard(original_dir, protected_dir, scenario: Optional[str] = None, root=None, rowmaps: Optional[dict] = None,
                  out_dir=None, max_adversary: int = 3000) -> dict:
    original_dir, protected_dir = Path(original_dir), Path(protected_dir)
    root = Path(root) if root else io.find_package_root(original_dir)
    domain = original_dir.name
    cat = io.load_catalog(root) if root and (root / "metadata" / "field_catalog.csv").exists() else pd.DataFrame(
        columns=["dataset", "table", "column", "privacy_role", "data_kind", "subtype"])
    cat = cat[cat.dataset == domain]
    scen = io.get_scenario(scenario, root) if scenario and root else None
    orig = io.load_tables(original_dir)
    prot = io.load_tables(protected_dir)
    rowmaps = dict(rowmaps or {})
    for f in protected_dir.glob("rowmap_*.csv"):
        rowmaps.setdefault(f.stem[len("rowmap_"):], f)
    rms = {k: io.load_rowmap(v) for k, v in rowmaps.items()}
    report = {"tool": "pets-eval 1.0.0", "dataset": domain, "scenario": scen or scenario,
              "original": str(original_dir), "protected": str(protected_dir), "tables": {}}
    all_risks: dict = {}
    for t, odf in orig.items():
        if t not in prot:
            report["tables"][t] = {"table": t, "status": "withheld", "rows_original": int(len(odf))}
            continue
        try:
            tr = evaluate_table(domain, t, odf, prot[t], cat, root, scen, rms.get(t), max_adversary)
        except Exception as e:  # noqa: BLE001
            tr = {"table": t, "status": "error", "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(limit=3)}
        report["tables"][t] = tr
        for k, v in tr.get("risks", {}).items():
            all_risks[f"{t}: {k}"] = v
    report["extra_protected_files"] = [t for t in prot if t not in orig]
    report["utility"] = run_utility(domain, orig, prot, scen)
    report["summary"] = composite(all_risks, report["utility"])
    report["risk_components"] = all_risks
    out_dir = Path(out_dir or protected_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "scorecard.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (out_dir / "scorecard.html").write_text(render_html(report), encoding="utf-8")
    return report


# ------------------------------------------------------------------ HTML
def _bar_svg(items: list[tuple[str, Optional[float]]], color: str, invert: bool = False, width: int = 640) -> str:
    rowh, lab = 26, 300
    h = rowh * max(len(items), 1) + 8
    parts = [f'<svg viewBox="0 0 {width} {h}" width="100%" role="img" xmlns="http://www.w3.org/2000/svg">']
    for i, (name, v) in enumerate(items):
        y = 4 + i * rowh
        parts.append(f'<text x="0" y="{y + 17}" font-size="12" fill="#333">{html.escape(name[:46])}</text>')
        parts.append(f'<rect x="{lab}" y="{y + 4}" width="{width - lab - 60}" height="16" fill="#eee" rx="3"/>')
        if v is None:
            parts.append(f'<text x="{lab + 6}" y="{y + 17}" font-size="11" fill="#888">not answerable / not evaluated</text>')
            continue
        w = (width - lab - 60) * max(0.0, min(1.0, v))
        parts.append(f'<rect x="{lab}" y="{y + 4}" width="{w:.1f}" height="16" fill="{color}" rx="3"/>')
        parts.append(f'<text x="{width - 52}" y="{y + 17}" font-size="12" fill="#333">{v:.0%}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _tile(label, v, good_high=True):
    if v is None:
        return f'<div class="tile"><div class="v">–</div><div class="l">{label}</div></div>'
    col = "#2e7d32" if (v >= .7) == good_high else ("#b26a00" if .4 <= v < .7 else "#c62828")
    return f'<div class="tile"><div class="v" style="color:{col}">{v:.0%}</div><div class="l">{label}</div></div>'


def render_html(rep: dict) -> str:
    e = html.escape
    s = rep["summary"]
    scen = rep.get("scenario")
    scen_txt = e(f"{scen.get('id')} — {scen.get('title', '')}") if isinstance(scen, dict) else e(str(scen or "none"))
    risk_items = [(k, v) for k, v in rep.get("risk_components", {}).items()]
    util_items = [(f"{u['id']}{'' if u.get('required') else ' (optional)'}", u["score"]) for u in rep.get("utility", [])]
    rows = []
    for t, tr in rep["tables"].items():
        st = tr.get("status")
        k = tr.get("k_anonymity", {})
        link = tr.get("linkage", {})
        best = [f"{n}: {v['reidentification_rate']:.0%}" + (f" (original {v['baseline_reidentification_rate_original']:.0%})"
                                                              if v.get("baseline_reidentification_rate_original") is not None else "")
                for n, v in link.items() if isinstance(v, dict) and v.get("evaluated")]
        rows.append(f"<tr><td>{e(t)}</td><td>{e(str(st))}</td><td>{tr.get('rows_protected', '')}</td>"
                    f"<td>{e(', '.join(tr.get('direct_identifiers_retained', {}).keys()) or '–')}</td>"
                    f"<td>{k.get('min_k', '–')} / {k.get('share_below', {}).get('k<5', '–')}</td>"
                    f"<td>{e('; '.join(best) or '–')}</td>"
                    f"<td>{e(', '.join(f'{c}:{sum(v.values())}' for c, v in tr.get('regex_residuals', {}).items()) or '–')}</td></tr>")
    util_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            e(u["id"]), e(u["description"]), "" if u["score"] is None else "%.2f" % u["score"], e(str(u.get("metric", ""))))
        for u in rep.get("utility", []))
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>PETs scorecard — {e(rep['dataset'])}</title>
<style>body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:980px;margin:24px auto;padding:0 16px;color:#222}}
h1{{font-size:22px}}h2{{font-size:17px;margin-top:28px}}.tiles{{display:flex;gap:12px}}.tile{{flex:1;border:1px solid #ddd;border-radius:8px;padding:12px;text-align:center}}
.v{{font-size:28px;font-weight:600}}.l{{font-size:12px;color:#666}}table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{border-bottom:1px solid #eee;padding:6px;text-align:left;vertical-align:top}}.note{{font-size:12px;color:#666;background:#f7f7f7;padding:8px;border-radius:6px}}</style></head>
<body><h1>PETs self-assessment scorecard — {e(rep['dataset'])}</h1>
<p>Scenario: <b>{scen_txt}</b><br>Protected release: <code>{e(rep['protected'])}</code></p>
<div class="tiles">{_tile('Privacy (1 − risk)', s['privacy'])}{_tile('Utility retained', s['utility'])}{_tile('Composite', s['composite'])}</div>
<p class="note">{e(s['label'])}. {e(s['method'])}.</p>
<h2>Risk components (lower is better)</h2>{_bar_svg(risk_items, '#c62828')}
<h2>Utility tasks (higher is better)</h2>{_bar_svg(util_items, '#1565c0')}
<h2>Tables</h2><table><tr><th>Table</th><th>Status</th><th>Rows</th><th>Direct ids retained</th><th>min k / share k&lt;5</th><th>Linkage re-identification</th><th>Regex residuals</th></tr>{''.join(rows)}</table>
<h2>Utility detail</h2><table><tr><th>Task</th><th>Question</th><th>Score</th><th>Metric</th></tr>{util_rows}</table>
<p class="note">Full detail in scorecard.json. Attack results use the public adversary files and ground truth shipped with the
dataset; organisers may evaluate with a different, stronger attacker. Row maps are for scoring only — never publish them.</p>
</body></html>"""
