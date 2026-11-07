"""Unit tests for the pets_eval toolkit core (toy data only; no dataset build needed)."""
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "toolkit"))

from pets_eval import attacks, check, detect, io, privacy, text  # noqa: E402

HETU_CHECK = "0123456789ABCDEFHJKLMNPRSTUVWXY"


def mk_hetu(d, n):
    base = f"{d.day:02d}{d.month:02d}{d.year % 100:02d}"
    return f"{base}{'-' if d.year < 2000 else 'A'}{n:03d}{HETU_CHECK[int(base + f'{n:03d}') % 31]}"


# ------------------------------------------------------------------ privacy
def test_k_anonymity_and_uniqueness():
    df = pd.DataFrame({"a": [1, 1, 1, 2, 2, 3], "b": ["x", "x", "x", "y", "y", "z"]})
    k = privacy.k_anonymity(df, ["a", "b"])
    assert k["min_k"] == 1 and k["n_classes"] == 3
    assert k["share_below"]["k<2"] == pytest.approx(1 / 6, abs=1e-3)
    assert k["share_below"]["k<5"] == 1.0
    assert privacy.sample_uniqueness(df, ["a"]) == pytest.approx(1 / 6, abs=1e-3)


def test_l_diversity_and_t_closeness():
    df = pd.DataFrame({"q": ["a"] * 4 + ["b"] * 4, "s": ["x", "x", "x", "x", "x", "y", "z", "w"]})
    l = privacy.l_diversity(df, ["q"], "s")
    assert l["min_distinct_l"] == 1 and l["share_classes_l1"] == 0.5
    t = privacy.t_closeness(df, ["q"], "s")
    assert 0 < t["max_t"] <= 1


def test_population_uniqueness_monotone():
    df = pd.DataFrame({"q": list(range(50)) + [99] * 50})
    lo = privacy.population_uniqueness(df, ["q"], 0.01)
    hi = privacy.population_uniqueness(df, ["q"], 0.9)
    assert hi["mean_record_risk"] > lo["mean_record_risk"]


def test_small_cells_and_differencing():
    a = pd.DataFrame({"m": ["T", "S", "K"], "n": [100, 7, 3]})
    sc = privacy.small_cells(a, "n", 5)
    assert sc["n_small"] == 1
    b = pd.DataFrame({"m": ["T", "S", "K"], "n": [99, 7, 0]})
    d = privacy.differencing_check(a, b, ["m"], "n")
    assert d["n_disclosive"] == 2


def test_dcr_and_mia_detect_copying():
    rng = np.random.default_rng(1)
    members = pd.DataFrame({"x": rng.normal(size=600), "y": rng.normal(size=600), "c": rng.choice(list("abc"), 600)})
    holdout = pd.DataFrame({"x": rng.normal(size=600), "y": rng.normal(size=600), "c": rng.choice(list("abc"), 600)})
    copy = members.copy()
    fresh = pd.DataFrame({"x": rng.normal(size=600), "y": rng.normal(size=600), "c": rng.choice(list("abc"), 600)})
    m_copy = privacy.membership_inference_auc(copy, members, holdout, ["x", "y", "c"])
    m_fresh = privacy.membership_inference_auc(fresh, members, holdout, ["x", "y", "c"])
    assert m_copy["auc"] > 0.9 and abs(m_fresh["auc"] - 0.5) < 0.1
    d = privacy.dcr_report(copy, members, holdout, ["x", "y", "c"])
    assert d["share_exact_copies"] == 1.0 and d["share_closer_to_train"] > 0.9


def test_trajectory_unicity():
    rows = []
    for u in range(30):
        for h in range(6):
            rows.append({"user": u, "ts": f"2025-10-06 {7 + h:02d}:10", "stop": f"S{(u * 7 + h) % 40}"})
    df = pd.DataFrame(rows)
    fine = privacy.trajectory_unicity(df, "user", "ts", place_col="stop", p=4, temporal="1h")
    coarse = privacy.trajectory_unicity(df.assign(stop="ALL"), "user", "ts", place_col="stop", p=4, temporal="1D")
    assert fine["unicity"] > 0.8 and coarse["unicity"] == 0.0


# ------------------------------------------------------------------ attacks
def toy_linkage():
    orig = pd.DataFrame({"visit_id": [f"V{i}" for i in range(6)],
                         "postcode": ["20100", "20100", "20500", "20500", "21200", "21200"],
                         "age": [34, 35, 70, 71, 22, 80], "sex": ["M", "F", "M", "F", "M", "F"],
                         "diag": ["J11", "S52", "I21", "N39", "S93", "I48"]})
    identity = pd.DataFrame({"record_id": orig.visit_id, "person_id": [f"P{i}" for i in range(6)]})
    adv = pd.DataFrame({"adv_row_id": ["A0", "A1", "A2"], "postcode": ["20100", "20500", "99999"], "age": [34, 70, 40],
                        "sex": ["M", "M", "F"]})
    truth = pd.DataFrame({"adv_row_id": ["A0", "A1", "A2"], "person_id": ["P0", "P2", "P99"]})
    return orig, identity, adv, truth


def test_linkage_exact_vs_generalised():
    orig, identity, adv, truth = toy_linkage()
    rm = pd.DataFrame({"protected_row": range(6), "original_record_id": orig.visit_id})
    res = attacks.linkage_attack(adv, truth, orig, rm, identity, original=orig, record_key="visit_id", sensitive="diag")
    assert res["n_targets_in_data"] == 2 and res["reidentification_rate"] == 1.0
    assert res["attribute_inference"]["success_rate"] == 1.0
    prot = orig.assign(postcode="2****", age="0-89", sex="")
    res2 = attacks.linkage_attack(adv, truth, prot, rm, identity, original=orig, record_key="visit_id", sensitive="diag")
    assert res2["reidentification_rate"] == 0.0 and res2["median_candidate_set"] >= 6


def test_linkage_age_band_and_shuffled_rows():
    orig, identity, adv, truth = toy_linkage()
    prot = orig.assign(age=["30-39", "30-39", "70-79", "70-79", "20-29", "80+"]).iloc[::-1].reset_index(drop=True)
    rm = pd.DataFrame({"protected_row": range(6), "original_record_id": prot.visit_id})
    res = attacks.linkage_attack(adv, truth, prot.drop(columns=["visit_id"]), rm, identity)
    assert res["reidentification_rate"] == 1.0  # postcode + band + sex still unique here


def test_hash_dictionary_attack():
    emails = ["aino.virtanen@kotiposti.example", "matti.laine@inbox.example"]
    hashed = pd.Series([hashlib.sha256(e.encode()).hexdigest() for e in emails])
    assert attacks.detect_hash_columns(pd.DataFrame({"h": hashed})) == {"h": "sha256"}
    r = attacks.hash_dictionary_attack(hashed, ["AINO.VIRTANEN@kotiposti.example", "x@y.example", "matti.laine@inbox.example"])
    assert r["share_values_reversed"] == 1.0 and r["algorithm"] == "sha256"
    keyed = pd.Series([hashlib.sha256(("secret" + e).encode()).hexdigest() for e in emails])
    assert attacks.hash_dictionary_attack(keyed, emails)["share_values_reversed"] == 0.0


def test_enumerate_hetu_contains_real_format():
    codes = list(attacks.enumerate_hetu(date(1990, 3, 1), date(1990, 3, 1), range(900, 1000)))
    assert len(codes) == 100 and mk_hetu(date(1990, 3, 1), 950) in codes


# ------------------------------------------------------------------ text
def test_span_scores_and_leakage():
    gold = {"r1": [{"start": 0, "end": 4, "label": "PERSON", "text": "Aino"},
                   {"start": 10, "end": 21, "label": "PHONE", "text": "040 1234567"}]}
    pred = {"r1": [{"start": 0, "end": 4, "label": "PERSON"}, {"start": 10, "end": 14, "label": "PHONE"}]}
    ex = text.span_scores(gold, pred, "exact")
    ov = text.span_scores(gold, pred, "overlap")
    assert ex["micro"]["recall"] == 0.5 and ov["micro"]["recall"] == 1.0
    leak = text.redaction_leakage(gold, {"r1": "[PERSON] soitti 0401234567"})
    assert leak["per_label"]["PHONE"]["leaked"] == 1 and leak["per_label"]["PERSON"]["leaked"] == 0
    leak2 = text.redaction_leakage(gold, {"r1": "[PERSON] soitti +358401234567"})
    assert leak2["per_label"]["PHONE"]["leaked"] == 1  # international form of the same number


# ------------------------------------------------------------------ detect
def test_detect_scoring():
    cat = pd.DataFrame({"dataset": ["d"] * 3, "table": ["t"] * 3, "column": ["hetu", "age", "notes"],
                        "privacy_role": ["direct_identifier", "quasi_identifier", "free_text"],
                        "subtype": ["NATIONAL_ID", "AGE", "FREE_TEXT"]})
    pred = pd.DataFrame({"dataset": ["d", "d"], "table": ["t", "t"], "column": ["hetu", "age"],
                         "privacy_role": ["direct_identifier", "non_sensitive"], "subtype": ["NATIONAL_ID", "AGE"]})
    r = detect.score_detection(pred, cat)
    assert r["accuracy"] == pytest.approx(1 / 3, abs=1e-3)
    assert r["per_role"]["direct_identifier"]["f1"] == 1.0
    assert r["sensitive_recall"] == pytest.approx(1 / 3, abs=1e-3)


# ------------------------------------------------------------------ check
def test_regex_check_validators():
    good_hetu = mk_hetu(date(1985, 7, 14), 921)
    bad_hetu = good_hetu[:-1] + ("A" if good_hetu[-1] != "A" else "B")
    s = (f"id {good_hetu} wrong {bad_hetu} card 4111 1111 1111 1111 notcard 4111 1111 1111 1112 "
         "iban FI21 1234 5600 0007 85 badiban FI22 1234 5600 0007 85 mail a.b@x.example ip 10.0.0.300 ip2 192.0.2.7 "
         "mac A4:83:E7:12:34:56 plate ABC-123 phone 040 123 4567 imei 356938035643809")
    c = check.scan_text(s)
    assert c["NATIONAL_ID"] == 1 and c["PAYMENT_CARD"] == 1 and c["IBAN"] == 1
    assert c["EMAIL"] == 1 and c["IP_ADDRESS"] == 1 and c["MAC_ADDRESS"] == 1
    assert c["LICENSE_PLATE"] == 1 and c["PHONE"] == 1 and c["IMEI"] == 1


# ------------------------------------------------------------------ CLI smoke on a toy package
@pytest.fixture()
def toy_pkg(tmp_path):
    orig, identity, adv, truth = toy_linkage()
    orig = orig.assign(name=["Aino Laine", "Ella Laine", "Matti Salo", "Liisa Salo", "Eetu Aho", "Kerttu Aho"],
                       note=["Aino Laine soitti 0401234567", "", "", "", "", ""])
    (tmp_path / "data" / "toy").mkdir(parents=True)
    orig.to_csv(tmp_path / "data" / "toy" / "visits.csv", index=False)
    (tmp_path / "metadata" / "pii_spans").mkdir(parents=True)
    cat = pd.DataFrame([
        ("toy", "visits", "visit_id", "record_key", "identifier", "RECORD_ID"),
        ("toy", "visits", "postcode", "quasi_identifier", "location", "POSTCODE"),
        ("toy", "visits", "age", "quasi_identifier", "numerical", "AGE"),
        ("toy", "visits", "sex", "quasi_identifier", "categorical", "SEX"),
        ("toy", "visits", "diag", "sensitive_attribute", "code", "DIAGNOSIS_CODE"),
        ("toy", "visits", "name", "direct_identifier", "name", "PERSON_NAME"),
        ("toy", "visits", "note", "free_text", "text", "FREE_TEXT")],
        columns=["dataset", "table", "column", "privacy_role", "data_kind", "subtype"])
    cat.to_csv(tmp_path / "metadata" / "field_catalog.csv", index=False)
    (tmp_path / "metadata" / "scenarios.json").write_text(json.dumps([{"id": "TOY-S1", "dataset": "toy", "title": "toy",
                                                                       "threat_model": "toy_dir", "utility_requirements": []}]))
    with open(tmp_path / "metadata" / "pii_spans" / "toy__visits__note.jsonl", "w") as f:
        f.write(json.dumps({"record_id": "V0", "spans": [{"start": 0, "end": 10, "label": "PERSON", "text": "Aino Laine"},
                                                          {"start": 18, "end": 28, "label": "PHONE", "text": "0401234567"}]}) + "\n")
    (tmp_path / "adversary").mkdir()
    (tmp_path / "truth").mkdir()
    adv.to_csv(tmp_path / "adversary" / "toy_dir.csv", index=False)
    truth.to_csv(tmp_path / "truth" / "adversary__toy_dir.csv", index=False)
    identity.to_csv(tmp_path / "truth" / "toy__visits.csv", index=False)
    prot = tmp_path / "prot" / "toy"
    prot.mkdir(parents=True)
    p = orig.drop(columns=["visit_id", "name"]).assign(note=["[PERSON] soitti [PHONE]", "", "", "", "", ""],
                                                        postcode=lambda d: d.postcode.str[:3] + "**")
    p.to_csv(prot / "visits.csv", index=False)
    pd.DataFrame({"protected_row": range(6), "original_record_id": orig.visit_id}).to_csv(prot / "rowmap_visits.csv", index=False)
    return tmp_path


def run_cli(*args, cwd=None):
    env = {"PYTHONPATH": str(ROOT / "toolkit"), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    return subprocess.run([sys.executable, "-m", "pets_eval", *args], capture_output=True, text=True, cwd=cwd, env=env)


def test_cli_scorecard_and_check(toy_pkg):
    r = run_cli("scorecard", "--original", str(toy_pkg / "data" / "toy"), "--protected", str(toy_pkg / "prot" / "toy"),
                "--scenario", "TOY-S1", "--root", str(toy_pkg))
    assert r.returncode == 0, r.stderr
    rep = json.loads((toy_pkg / "prot" / "toy" / "scorecard.json").read_text())
    t = rep["tables"]["visits"]
    assert t["direct_identifiers_retained"] == {}
    assert t["free_text"]["note"]["identifying_leakage_rate"] == 0.0
    assert "toy_dir" in t["linkage"] and t["linkage"]["toy_dir"]["evaluated"]
    assert (toy_pkg / "prot" / "toy" / "scorecard.html").read_text().startswith("<!DOCTYPE html>")
    r = run_cli("check", str(toy_pkg / "data" / "toy"))
    assert r.returncode == 0 and "PHONE" in r.stdout
    pred = toy_pkg / "pred.csv"
    pd.DataFrame({"dataset": ["toy"], "table": ["visits"], "column": ["name"], "privacy_role": ["direct_identifier"]}).to_csv(pred, index=False)
    r = run_cli("detect", "--pred", str(pred), "--root", str(toy_pkg))
    assert r.returncode == 0 and '"macro_f1"' in r.stdout


def test_io_helpers(toy_pkg):
    assert io.find_package_root(toy_pkg / "data" / "toy") == toy_pkg
    t = io.load_tables(toy_pkg / "prot" / "toy")
    assert set(t) == {"visits"}  # rowmap skipped
    assert not pd.api.types.is_numeric_dtype(t["visits"]["postcode"])
    assert io.read_table(toy_pkg / "data" / "toy" / "visits.csv")["postcode"].iloc[0] == "20100"
    adv, truth = io.load_adversary(toy_pkg, "toy_dir")
    assert len(adv) == 3 and len(truth) == 3
