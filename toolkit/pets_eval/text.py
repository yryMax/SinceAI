"""Free-text PII scoring.

Two ways to score:
1. span_scores(gold, pred): you predicted spans ({record_id: [{start,end,label}]}).
   Exact match and overlap match, per label precision / recall / F1 / F2 (F2 weights recall,
   because a missed identifier is worse than an over-redaction).
2. redaction_leakage(gold, protected_texts): you only produced protected text. For every gold
   span we check whether its value survives in the protected text (normalised: case,
   whitespace and digit separators ignored). Works on any redaction / pseudonymisation output.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable, Optional

Spans = dict  # {record_id: [ {start, end, label, text?}, ... ]}

# Labels that identify or single out a person. LOCATION/DATE/ORG are context; HEALTH is sensitive content.
IDENTIFYING = {"PERSON", "NATIONAL_ID", "EMAIL", "PHONE", "ADDRESS", "IBAN", "PAYMENT_CARD", "ACCOUNT_NUMBER",
               "IP_ADDRESS", "LICENSE_PLATE", "USERNAME", "SECRET", "DEVICE_ID", "PROPERTY_ID", "URL"}


def _prf(tp: float, fp: float, fn: float) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    f2 = 5 * p * r / (4 * p + r) if (4 * p + r) else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4), "f2": round(f2, 4),
            "tp": int(tp), "fp": int(fp), "fn": int(fn)}


def _overlap(a, b) -> bool:
    return a["start"] < b["end"] and b["start"] < a["end"]


def span_scores(gold: Spans, pred: Spans, mode: str = "overlap", label_agnostic: bool = False,
                labels: Optional[Iterable[str]] = None) -> dict:
    """mode 'exact' = same start/end (and label); 'overlap' = any character overlap (and label).
    Records missing from `pred` count as predicting nothing. Records only in `pred` add false positives."""
    labels = set(labels) if labels else None
    stats = defaultdict(lambda: [0, 0, 0])  # tp, fp, fn
    for rid in set(gold) | set(pred):
        g = [s for s in gold.get(rid, []) if labels is None or s["label"] in labels]
        p = [s for s in pred.get(rid, []) if labels is None or s.get("label") in labels or label_agnostic]
        used = set()
        for gs in g:
            hit = None
            for j, ps in enumerate(p):
                if j in used:
                    continue
                same_label = label_agnostic or ps.get("label") == gs["label"]
                ok = (ps["start"] == gs["start"] and ps["end"] == gs["end"]) if mode == "exact" else _overlap(ps, gs)
                if ok and same_label:
                    hit = j
                    break
            if hit is None:
                stats[gs["label"]][2] += 1
            else:
                used.add(hit)
                stats[gs["label"]][0] += 1
        for j, ps in enumerate(p):
            if j not in used:
                # in overlap mode a prediction overlapping an already-matched gold span is not penalised twice
                if mode == "overlap" and any(_overlap(ps, gs) for gs in g):
                    continue
                stats[ps.get("label", "?") if not label_agnostic else "ANY"][1] += 1
    per = {k: _prf(*v) for k, v in sorted(stats.items())}
    tot = [sum(v[i] for v in stats.values()) for i in range(3)]
    micro = _prf(*tot)
    # flat layout identical to pets_eval.utility.customer_service.span_scores (label -> gold/recall/precision/f2, '_micro')
    flat = {k: {"gold": v["tp"] + v["fn"], "recall": v["recall"], "precision": v["precision"], "f2": v["f2"]} for k, v in per.items()}
    flat["_micro"] = {"gold": micro["tp"] + micro["fn"], "recall": micro["recall"], "precision": micro["precision"], "f2": micro["f2"]}
    return {"mode": mode, "per_label": per, "micro": micro, "flat": flat, "n_records": len(set(gold) | set(pred))}


_SEP = re.compile(r"[\s\-\.\(\)/_:]+")


def normalise(s: str) -> str:
    """Lower-case and strip separators so '040 123 4567' == '0401234567' and 'FI12 3456' == 'fi123456'."""
    return _SEP.sub("", str(s).lower())


def _variants(value: str, label: str) -> list[str]:
    v = normalise(value)
    out = {v}
    if label == "PHONE":
        digits = re.sub(r"\D", "", value)
        if digits.startswith("358"):
            out.add("0" + digits[3:])
        elif digits.startswith("0"):
            out.add("358" + digits[1:])
        out.add(digits)
    return [x for x in out if len(x) >= 2]


def redaction_leakage(gold: Spans, protected_texts: dict, labels: Optional[Iterable[str]] = None,
                      original_texts: Optional[dict] = None) -> dict:
    """Share of gold PII values that are still recoverable from the protected text.

    gold: {record_id: spans}, spans need 'text' (or original_texts to slice from).
    protected_texts: {record_id: protected text}. Records missing from protected_texts are
    treated as withheld (nothing leaks). Returns leakage by count and by characters, per label.
    """
    labels = set(labels) if labels else None
    per = defaultdict(lambda: [0, 0, 0, 0])  # n, leaked, chars, leaked_chars
    examples = []
    for rid, spans in gold.items():
        if rid not in protected_texts:
            continue
        pt = normalise(protected_texts.get(rid) or "")
        for s in spans:
            if labels is not None and s["label"] not in labels:
                continue
            val = s.get("text")
            if val is None and original_texts is not None:
                val = original_texts[rid][s["start"]:s["end"]]
            if not val:
                continue
            short = len(normalise(val)) < 3  # 1-2 character values (e.g. an initial) are not testable
            if short:
                continue
            leaked = any(v in pt for v in _variants(val, s["label"]))
            st = per[s["label"]]
            st[0] += 1
            st[2] += len(val)
            if leaked:
                st[1] += 1
                st[3] += len(val)
                if len(examples) < 20:
                    examples.append({"record_id": rid, "label": s["label"], "value": val})
    tot = [sum(v[i] for v in per.values()) for i in range(4)]
    ident = [sum(v[i] for k, v in per.items() if k in IDENTIFYING) for i in range(4)]

    def rate(a, b):
        return round(a / b, 4) if b else 0.0

    return {
        "leakage_rate": rate(tot[1], tot[0]),
        "leakage_rate_chars": rate(tot[3], tot[2]),
        "identifying_leakage_rate": rate(ident[1], ident[0]),
        "per_label": {k: {"n": v[0], "leaked": v[1], "rate": rate(v[1], v[0])} for k, v in sorted(per.items())},
        "n_values": tot[0],
        "examples": examples,
    }


def spans_from_redaction(original: str, protected: str) -> list[dict]:
    """Heuristic: recover redacted character ranges from an aligned original/protected pair using difflib.
    Useful to score a redactor that does not emit spans (label = 'ANY')."""
    import difflib
    sm = difflib.SequenceMatcher(a=original, b=protected, autojunk=False)
    out = []
    for tag, i1, i2, _, _ in sm.get_opcodes():
        if tag in ("replace", "delete") and i2 > i1:
            out.append({"start": i1, "end": i2, "label": "ANY"})
    return out
