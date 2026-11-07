"""Utility task registry.

A utility task answers one analytical question on the ORIGINAL tables and on the PROTECTED
tables and scores how well the protected version preserves the answer (1.0 = identical,
0.0 = useless, None = not answerable because required columns were removed or coarsened
beyond what the task needs).

orig / prot are dicts {table_name: DataFrame}. Protected tables keep original column names for
the columns they keep; values may be generalised (see pets_eval.parse for accepted formats).
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Callable, Optional

DOMAINS = ["health", "mobility", "smart_city", "energy", "finance", "cyber", "education", "public_admin",
           "customer_service"]


@dataclass
class UtilityTask:
    id: str
    dataset: str
    table: str
    description: str
    kind: str  # aggregate | distribution | relationship | model | detection | text
    fn: Callable[[dict, dict], dict]
    needs: list = field(default_factory=list)  # columns used (informational)
    scenarios: list = field(default_factory=list)


def result(score: Optional[float], metric: str, **detail) -> dict:
    if score is not None:
        score = float(max(0.0, min(1.0, score)))
    return {"score": score, "metric": metric, "detail": detail}


def not_answerable(missing) -> dict:
    return result(None, "not answerable", missing=list(missing))


def require(df, cols) -> list:
    return [c for c in cols if df is None or c not in df.columns]


def all_tasks(domains=None) -> list:
    out = []
    for d in domains or DOMAINS:
        try:
            mod = importlib.import_module(f"pets_eval.utility.{d}")
        except ModuleNotFoundError:
            continue
        out += list(mod.TASKS)
    return out
