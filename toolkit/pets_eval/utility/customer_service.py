"""Utility tasks and span-scoring helpers for the customer_service dataset."""
from __future__ import annotations

import re
from collections import Counter

import numpy as np
import pandas as pd

from . import UtilityTask, not_answerable, require, result
from ..parse import score_from_rel_error, table_mape, tvd

D = "customer_service"
_CACHE: dict = {}


# ------------------------------------------------------------------ span scoring (reusable)
def _overlap(a, b):
    return max(0, min(a["end"], b["end"]) - max(a["start"], b["start"]))


def span_scores(gold: dict, pred: dict, labels=None, mode: str = "overlap", typed: bool = False, beta: float = 2.0) -> dict:
    """Score predicted PII spans against gold spans.

    gold, pred: {record_id: [ {start, end, label}, ... ]}. Records missing from pred = no predictions.
    mode 'overlap': a gold span is found if any predicted span overlaps it (and, if typed, has the same label);
         'exact': start/end must match. Precision counts predicted spans overlapping any gold span.
    Returns per-label and micro precision / recall / F-beta (beta=2 weights recall: missing PII is worse).
    """
    labels = labels or sorted({s["label"] for v in gold.values() for s in v})
    tp_g, n_g = Counter(), Counter()
    tp_p, n_p = Counter(), Counter()
    for rid in set(gold) | set(pred):
        g, p = gold.get(rid, []), pred.get(rid, [])
        for s in g:
            n_g[s["label"]] += 1
            hit = any(((_overlap(s, q) > 0) if mode == "overlap" else (s["start"] == q["start"] and s["end"] == q["end"]))
                      and (not typed or q.get("label") == s["label"]) for q in p)
            tp_g[s["label"]] += hit
        for q in p:
            lab = q.get("label", "ANY")
            n_p[lab] += 1
            hit = any(((_overlap(s, q) > 0) if mode == "overlap" else (s["start"] == q["start"] and s["end"] == q["end"]))
                      and (not typed or q.get("label") == s["label"]) for s in g)
            tp_p[lab] += hit

    def f(pr, rc):
        return 0.0 if pr + rc == 0 else (1 + beta ** 2) * pr * rc / (beta ** 2 * pr + rc)

    out = {}
    for lab in labels:
        rc = tp_g[lab] / n_g[lab] if n_g[lab] else np.nan
        pr = tp_p[lab] / n_p[lab] if n_p[lab] else np.nan
        out[lab] = {"gold": int(n_g[lab]), "recall": rc, "precision": pr,
                    f"f{beta:g}": f(pr if not np.isnan(pr) else 0, rc if not np.isnan(rc) else 0)}
    R = sum(tp_g.values()) / max(1, sum(n_g.values()))
    Pm = sum(tp_p.values()) / max(1, sum(n_p.values()))
    out["_micro"] = {"gold": int(sum(n_g.values())), "recall": R, "precision": Pm, f"f{beta:g}": f(Pm, R)}
    return out


def leak_rate(gold: dict, original_text: dict, protected_text: dict, min_len: int = 4) -> dict:
    """Fraction of gold PII values that still appear verbatim (case-insensitive) in the protected text of the same record.
    Works for any transformation (masking, surrogates, paraphrase) without needing predicted spans."""
    per, tot = Counter(), Counter()
    for rid, spans in gold.items():
        pt = str(protected_text.get(rid, "") or "").lower()
        for s in spans:
            v = s.get("text") or original_text.get(rid, "")[s["start"]:s["end"]]
            if len(v.strip()) < min_len:
                continue
            tot[s["label"]] += 1
            per[s["label"]] += v.lower() in pt
    out = {k: per[k] / tot[k] for k in tot}
    out["_overall"] = sum(per.values()) / max(1, sum(tot.values()))
    return out


def load_spans(path) -> dict:
    import json
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out[r["record_id"]] = r["spans"]
    return out


# ------------------------------------------------------------------ helpers
def _docs(turns, convs, ids):
    t = turns[turns.conversation_id.isin(ids)].sort_values(["conversation_id", "seq"]) if "seq" in turns else turns[turns.conversation_id.isin(ids)]
    return t.groupby("conversation_id")["text"].apply(lambda s: " \n ".join(s.fillna("").astype(str)))


def _intent_f1(train_docs, train_y, test_docs, test_y):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score
    vec = TfidfVectorizer(sublinear_tf=True, min_df=2, ngram_range=(1, 2), max_features=60000)
    X = vec.fit_transform(train_docs)
    clf = LogisticRegression(max_iter=2000, C=4.0)
    clf.fit(X, train_y)
    return f1_score(test_y, clf.predict(vec.transform(test_docs)), average="macro")


def u1_intent(orig, prot):
    ot, oc = orig.get("turns"), orig.get("conversations")
    pt, pc = prot.get("turns"), prot.get("conversations")
    miss = require(pt, ["conversation_id", "text"]) + require(pc, ["conversation_id", "intent"])
    if miss:
        return not_answerable(miss)
    split = oc.set_index("conversation_id").split
    tr_ids = oc.conversation_id[oc.split == "train"]
    ev_ids = oc.conversation_id[oc.split == "eval"]
    test_docs = _docs(ot, oc, ev_ids)
    test_y = oc.set_index("conversation_id").intent.reindex(test_docs.index)
    key = ("u1", id(ot), len(ot))
    if key not in _CACHE:
        tr = _docs(ot, oc, tr_ids)
        _CACHE[key] = _intent_f1(tr, oc.set_index("conversation_id").intent.reindex(tr.index), test_docs, test_y)
    f_o = _CACHE[key]
    pc_ids = pc.conversation_id[pc.conversation_id.map(split) == "train"] if "split" not in pc else pc.conversation_id[pc.split == "train"]
    ptr = _docs(pt, pc, pc_ids)
    if len(ptr) < 50:
        return not_answerable(["train conversations"])
    y = pc.set_index("conversation_id").intent.reindex(ptr.index)
    f_p = _intent_f1(ptr, y, test_docs, test_y)
    return result(f_p / f_o if f_o else None, "macro-F1 ratio (protected-trained / original-trained) on original eval",
                  f1_original=round(f_o, 4), f1_protected=round(f_p, 4))


_SENT = {"negative": 0, "neutral": 1, "positive": 2}


def u2_sent_csat(orig, prot):
    oc, pc = orig["conversations"], prot.get("conversations")
    miss = require(pc, ["sentiment", "csat"])
    if miss:
        return not_answerable(miss)
    from scipy.stats import spearmanr

    def rho(c):
        x = c.dropna(subset=["csat"])
        s = x.sentiment.map(_SENT)
        y = pd.to_numeric(x.csat, errors="coerce")
        m = s.notna() & y.notna()
        return spearmanr(s[m], y[m]).statistic if m.sum() > 10 else np.nan

    ro, rp = rho(oc), rho(pc)
    if np.isnan(rp):
        return result(0.0, "Spearman(sentiment, csat) difference", rho_original=ro, rho_protected=rp)
    return result(1 - abs(ro - rp) / 0.5, "1 - |Δ Spearman(sentiment, CSAT)| / 0.5", rho_original=round(ro, 4), rho_protected=round(rp, 4))


def u3_intent_mix(orig, prot):
    pc = prot.get("conversations")
    miss = require(pc, ["intent"])
    if miss:
        return not_answerable(miss)
    d = tvd(orig["conversations"].intent.value_counts(), pc.intent.value_counts())
    return result(1 - 2 * d, "1 - 2·TVD of intent distribution", tvd=round(d, 4))


def u4_aht(orig, prot):
    pc = prot.get("conversations")
    miss = require(pc, ["intent", "handle_time_s"])
    if miss:
        return not_answerable(miss)
    from ..parse import parse_numeric
    o = orig["conversations"].groupby("intent").handle_time_s.mean()
    p = pc.assign(h=parse_numeric(pc.handle_time_s)).groupby("intent").h.mean()
    e = table_mape(o, p)
    return result(score_from_rel_error(e, .5), "mean handle time by intent, MAPE (0.5 → score 0)", mape=round(e, 4))


_TOK = re.compile(r"[a-zåäöéü]{3,}")


def u5_vocab(orig, prot):
    ot, pt = orig["turns"], prot.get("turns")
    miss = require(pt, ["turn_id", "text"])
    if miss:
        return not_answerable(miss)
    key = ("u5", id(ot), len(ot))
    if key not in _CACHE:
        # common vocabulary = tokens used in >= 25 different conversations (not identifying by construction)
        df = Counter()
        for cid, txt in ot.groupby("conversation_id").text:
            df.update(set(_TOK.findall(" ".join(txt.fillna("").astype(str)).lower())))
        _CACHE[key] = {w for w, c in df.items() if c >= 25}
    common = _CACHE[key]
    sample = ot.sample(min(20000, len(ot)), random_state=7)
    pmap = pt.set_index("turn_id").text
    kept = total = 0
    for tid, txt in zip(sample.turn_id, sample.text.fillna("")):
        toks = [w for w in _TOK.findall(str(txt).lower()) if w in common]
        if not toks:
            continue
        ptoks = Counter(_TOK.findall(str(pmap.get(tid, "") or "").lower()))
        oc = Counter(toks)
        kept += sum(min(c, ptoks[w]) for w, c in oc.items())
        total += sum(oc.values())
    r = kept / total if total else 0
    return result(r, "share of common (non-identifying) word tokens retained, matched by turn_id", retained=round(r, 4))


def u6_channel_lang(orig, prot):
    pc = prot.get("conversations")
    miss = require(pc, ["channel", "language"])
    if miss:
        return not_answerable(miss)
    o = orig["conversations"].groupby(["channel", "language"]).size()
    p = pc.groupby(["channel", "language"]).size()
    e = table_mape(o, p)
    return result(score_from_rel_error(e, .5), "contacts by channel × language, MAPE", mape=round(e, 4))


def u7_resolution(orig, prot):
    pc = prot.get("conversations")
    miss = require(pc, ["intent", "resolved"])
    if miss:
        return not_answerable(miss)
    tob = lambda s: s.astype(str).str.lower().isin(["true", "1", "yes"])  # noqa: E731
    o = tob(orig["conversations"].resolved).groupby(orig["conversations"].intent).mean()
    p = tob(pc.resolved).groupby(pc.intent).mean()
    idx = o.index
    err = float(np.abs(o - p.reindex(idx)).fillna(1).mean())
    return result(1 - err / .2, "first-contact resolution rate by intent, mean abs. difference (0.2 → score 0)", mae=round(err, 4))


TASKS = [
    UtilityTask("CS-U1", D, "turns", "Intent classifier (TF-IDF + logistic regression) trained on protected train text, tested on original eval text.",
                "model", u1_intent, ["turns.text", "conversations.intent"], ["CS-S1", "CS-S2"]),
    UtilityTask("CS-U2", D, "conversations", "Relationship between sentiment and CSAT preserved.", "relationship", u2_sent_csat,
                ["sentiment", "csat"], ["CS-S2"]),
    UtilityTask("CS-U3", D, "conversations", "Contact-reason (intent) mix preserved.", "distribution", u3_intent_mix, ["intent"], ["CS-S1"]),
    UtilityTask("CS-U4", D, "conversations", "Average handle time by intent.", "aggregate", u4_aht, ["intent", "handle_time_s"], ["CS-S1", "CS-S3"]),
    UtilityTask("CS-U5", D, "turns", "Ordinary vocabulary retained in text (redaction should remove identifiers, not meaning).", "text",
                u5_vocab, ["turns.text"], ["CS-S1", "CS-S2"]),
    UtilityTask("CS-U6", D, "conversations", "Contact volumes by channel × language.", "aggregate", u6_channel_lang, ["channel", "language"], ["CS-S3"]),
    UtilityTask("CS-U7", D, "conversations", "First-contact resolution rate by intent.", "aggregate", u7_resolution, ["intent", "resolved"], ["CS-S3"]),
]
