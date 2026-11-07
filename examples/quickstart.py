"""10-minute quickstart: protect the ED visits table for a research scenario and measure the result.

Run from the package root:
    pip install -e ./toolkit          (or: export PYTHONPATH=$PWD/toolkit)
    python3 examples/quickstart.py
Then open results/quickstart/health/scorecard.html in a browser.
"""
import hashlib
import hmac
import re
from pathlib import Path

import pandas as pd

from pets_eval import io, parse, privacy
from pets_eval.scorecard import run_scorecard

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "quickstart" / "health"
KEY = b"replace-with-a-secret-from-a-vault"

# 1. Detect: read the field catalog (your tool should infer this itself; here we peek at the answers)
cat = io.load_catalog(ROOT)
visits = io.read_table(ROOT / "data" / "health" / "ed_visits.csv")
roles = cat[(cat.dataset == "health") & (cat.table == "ed_visits")].set_index("column").privacy_role
print(roles.value_counts().to_string(), "\n")

# How identifying are birth date + sex + postcode on their own?
qi = ["date_of_birth", "sex", "postcode"]
print(f"unique on {qi}: {privacy.sample_uniqueness(visits.drop_duplicates('patient_hetu'), qi):.1%} of patients\n")

# 2. Select + 3. Transform (scenario HEALTH-S1: researchers need revisits, LOS, diagnoses, age bands)
p = pd.DataFrame()
p["visit_id"] = visits.visit_id                                   # meaningless row key, kept for the row map
p["patient_pseudonym"] = visits.patient_hetu.map(                  # keyed pseudonym: revisits stay linkable
    lambda v: hmac.new(KEY, str(v).encode(), hashlib.sha256).hexdigest()[:16])
p["age"] = parse.to_age_band(parse.age_from_birth(visits.date_of_birth))  # 10-year bands, 80+ top-coded
p["sex"] = visits.sex
p["municipality"] = visits.municipality
p["arrival_ts"] = parse.to_datetime(visits.arrival_ts).dt.floor("h").dt.strftime("%Y-%m-%d %H:00")
for c in ["arrival_mode", "triage", "icd10_primary", "systolic_bp", "heart_rate", "temp_c", "spo2", "los_minutes",
          "disposition", "readmit_30d"]:
    p[c] = visits[c]
p["icd10_primary"] = p.icd10_primary.str[:3]                        # 3-character ICD-10 hides rare sub-codes
p["chief_complaint"] = visits.chief_complaint.fillna("").map(       # naive redaction (try to beat this!)
    lambda t: re.sub(r"\b\d{6}[-+A]\d{3}[0-9A-Y]\b|\+?\d[\d\s-]{7,}\d", "[ID]", t))

OUT.mkdir(parents=True, exist_ok=True)
p.to_csv(OUT / "ed_visits.csv", index=False)
pd.DataFrame({"protected_row": range(len(p)), "original_record_id": visits.visit_id}).to_csv(
    OUT / "rowmap_ed_visits.csv", index=False)                     # for scoring only, never publish

# 4. Demonstrate: privacy + utility scorecard against the shipped attackers and utility tasks
rep = run_scorecard(ROOT / "data" / "health", OUT, scenario="HEALTH-S1", root=ROOT)
print("summary:", rep["summary"])
for u in rep["utility"]:
    print(f"  {u['id']:6s} {u['score'] if u['score'] is None else round(u['score'], 3)!s:>6}  {u['description']}")
print("\nTasks on tables you did not release (here lab_results, H-U7) score 0 or 'not answerable': release them too if your scenario needs them.")
print(f"open {OUT / 'scorecard.html'}")
