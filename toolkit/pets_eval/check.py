"""Regex scan for residual direct identifiers in any file or folder (CSV, JSON, JSONL, TXT, MD).

Validators remove most false positives: HETU checksum, IBAN mod-97, Luhn for card numbers,
octet ranges for IPv4. Phone numbers and plates are pattern-only, so expect a few false positives.
Example values in the report are masked so the report itself does not leak.
"""
from __future__ import annotations

import ipaddress
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

HETU_CHECK = "0123456789ABCDEFHJKLMNPRSTUVWXY"

PATTERNS = {
    "NATIONAL_ID": re.compile(r"(?<![0-9A-Za-z])(\d{6}[-+ABCDEFUVWXY]\d{3}[0-9A-Y])(?![0-9A-Za-z])"),
    "IBAN": re.compile(r"(?<![A-Z0-9])([A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?)(?![A-Z0-9])"),
    "PAYMENT_CARD": re.compile(r"(?<![0-9A-Za-z])((?:\d[ -]?){12,18}\d)(?![0-9A-Za-z])"),
    "EMAIL": re.compile(r"(?<![\w.+-])([\w.+-]+@[\w-]+(?:\.[\w-]+)+)", re.I),
    "PHONE": re.compile(r"(?<![\d+])((?:\+358|00358|\b0)[ -]?(?:4\d|50)[ -]?\d{3,4}[ -]?\d{3,4})(?!\d)"),
    "IP_ADDRESS": re.compile(r"(?<![\d.])((?:\d{1,3}\.){3}\d{1,3})(?![\d.])"),
    "IPV6": re.compile(r"(?<![0-9a-f:])((?:[0-9a-f]{1,4}:){4,7}[0-9a-f]{1,4})(?![0-9a-f:])", re.I),
    "MAC_ADDRESS": re.compile(r"(?<![0-9A-F:-])((?:[0-9A-F]{2}[:-]){5}[0-9A-F]{2})(?![0-9A-F:-])", re.I),
    "LICENSE_PLATE": re.compile(r"(?<![A-ZÅÄÖ0-9-])([A-ZÅÄÖ]{2,3}-\d{1,3})(?![0-9-])"),
}


def hetu_ok(s: str) -> bool:
    try:
        return HETU_CHECK[int(s[:6] + s[7:10]) % 31] == s[10]
    except (ValueError, IndexError):
        return False


def iban_ok(s: str) -> bool:
    s = s.replace(" ", "")
    if not 15 <= len(s) <= 34:
        return False
    try:
        return int("".join(str(int(c, 36)) for c in s[4:] + s[:4])) % 97 == 1
    except ValueError:
        return False


_IIN = re.compile(r"^(4\d|5[1-5]|2(2[2-9]|[3-6]\d|7[01]|720)|3[47]|6011|65|64[4-9]|35(2[89]|[3-8]\d)|62)")


def luhn_ok(s: str) -> bool:
    d = re.sub(r"\D", "", s)
    if not 13 <= len(d) <= 19 or len(set(d)) == 1:
        return False
    if not _IIN.match(d):  # issuer prefixes of the major card schemes (Visa, Mastercard, Amex, Discover, JCB, UnionPay)
        return False
    tot = 0
    for i, ch in enumerate(reversed(d)):
        x = int(ch)
        if i % 2 == 1:
            x *= 2
            if x > 9:
                x -= 9
        tot += x
    return tot % 10 == 0


def ip_ok(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


VALIDATORS = {"NATIONAL_ID": hetu_ok, "IBAN": iban_ok, "PAYMENT_CARD": luhn_ok, "IP_ADDRESS": ip_ok, "IPV6": ip_ok}


def mask(v: str) -> str:
    v = str(v)
    return v[:2] + "…" + v[-2:] if len(v) > 5 else "…"


def scan_text(text: str, counts: Optional[dict] = None, examples: Optional[dict] = None) -> dict:
    counts = counts if counts is not None else defaultdict(int)
    for base_label, pat in PATTERNS.items():
        for m in pat.finditer(text):
            label = base_label
            v = m.group(1)
            ok = VALIDATORS.get(label)
            if ok and not ok(v):
                continue
            if label == "PAYMENT_CARD":
                d = re.sub(r"\D", "", v)
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", v) or (len(d) == 18 and d.startswith("643")):
                    continue  # dates, metering-point GSRNs
                if len(d) == 15 and d[:2] in ("35", "86", "01"):
                    label = "IMEI"
            counts[label] += 1
            if examples is not None and len(examples[label]) < 3:
                examples[label].append(mask(v))

    return counts


def scan_path(path, max_lines: Optional[int] = None, exts=(".csv", ".json", ".jsonl", ".txt", ".md", ".tsv")) -> dict:
    """Scan a file or folder. Returns {file: {label: count}} plus totals and masked examples."""
    path = Path(path)
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.suffix.lower() in exts)
    report = {"files": {}, "totals": defaultdict(int), "examples": defaultdict(list)}
    for f in files:
        counts = defaultdict(int)
        with open(f, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if max_lines and i >= max_lines:
                    break
                scan_text(line, counts, report["examples"])
        if counts:
            report["files"][str(f)] = dict(counts)
            for k, v in counts.items():
                report["totals"][k] += v
    report["totals"] = dict(report["totals"])
    report["examples"] = dict(report["examples"])
    report["n_files_scanned"] = len(files)
    report["note"] = ("Synthetic identifiers in this package use reserved formats; any hit means a value "
                      "survived your transformation. PHONE and LICENSE_PLATE are pattern-only (possible false positives).")
    return report
