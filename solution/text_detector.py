"""Local, metadata-free PII detection for multilingual operational text.

Evidence comes from raw structured columns, identifier syntax and nearby words.
Neither construction nor prediction opens files, loads annotation data, or uses a
record id. The caller controls the input tables; dictionaries stay in memory.
"""
from __future__ import annotations

from functools import lru_cache
import re
from typing import Any

import pandas as pd

_WORD = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*|\d+", re.UNICODE)
_TERM = re.compile(r"[\wåäöÅÄÖéü'’\-]+", re.UNICODE)
_MISSING = {"", "nan", "none", "null", "nat", "<na>"}
# Name tokens that also act as frequent English/Swedish/Finnish function words.
_AMBIGUOUS = {"i", "a", "an", "on", "in", "is", "it", "as", "at", "to", "he", "hi", "my", "me", "so",
              "no", "ja", "ei", "en", "se", "de", "det", "ni", "vi", "du", "han", "hon", "man", "som",
              "per", "may", "will", "bin", "van", "von", "al", "el", "tämä", "asia", "kun", "nyt", "olen"}
_DIGITS = "nolla yksi kaksi kolme neljä viisi kuusi seitsemän kahdeksan yhdeksän zero oh one two three four five six seven eight nine noll ett en två tre fyra fem sex sju åtta nio".split()
_DW = "(?:" + "|".join(sorted(_DIGITS, key=len, reverse=True)) + ")"
_LETTER = r"(?:aa|bee|cee|dee|ee|äf|gee|hoo|ii|jii|koo|äl|äm|än|oo|pee|kuu|är|äs|tee|uu|vee|äks|yy|zet|[a-zåäö])"
_SPOKEN = re.compile(r"(?<!\w)" + _DW + r"(?:[\s,]+" + _DW + r")+(?:[\s,]+(?:viiva|dash|streck|plus|aa)[\s,]+(?:" + _DW + r"|\d)+(?:[\s,]+(?:" + _DW + r"|\d))*(?:[\s,]+" + _LETTER + r")?)?(?!\w)", re.I)
_PATTERNS = [
    ("URL", re.compile(r"https?://[^\s<>\[\]]+", re.I)),
    ("EMAIL", re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.I)),
    ("NATIONAL_ID", re.compile(r"(?<!\w)\d{6}\s*(?:[-+a-fu-y]|(?:viiva|dash|streck)\s*)\s*\d{3}\s*[0-9a-y](?!\w)", re.I)),
    ("NATIONAL_ID", re.compile(r"(?<!\w)(?:[-+]\s*\d{3}\s*[0-9a-y]|a\s*\d{3}\s*[0-9a-y])(?!\w)", re.I)),
    ("IBAN", re.compile(r"(?<!\w)[a-z]{2}\s*\d{2}(?:[ \t]*\d){11,30}(?!\w)", re.I)),
    ("PROPERTY_ID", re.compile(r"(?<!\w)\d{1,3}-\d{1,3}-\d{1,4}-\d{1,4}(?!\w)")),
    ("LICENSE_PLATE", re.compile(r"(?<!\w)[a-zåäö]{2,3}-\d{1,3}(?!\w)", re.I)),
    ("IP_ADDRESS", re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")),
    ("DATE", re.compile(r"(?<![\w.])(?:\d{4}-\d{2}-\d{2}|(?:[12]?\d|3[01])\.(?:0?[1-9]|1[0-2])\.(?:\d{2,4})?)(?![\w.])")),
    ("DATE", re.compile(r"(?<!\w)\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december|januari|februari|mars|maj|juni|juli|augusti|oktober|december)(?!\w)", re.I)),
    ("AGE", re.compile(r"(?<!\w)\d{1,3}(?=[ -]*(?:vuotias|vuotiaan|årig|years? old))", re.I)),
]
_STREET = r"(?:katu|tie|kuja|polku|rinne|kaari|puistikko|väylä|raitti|aukio|piha|tanhu[aå]|ranta|mäki|tori|gatan|vägen|gränd|stigen|backen|strand|street|road|avenue|lane)"
_ADDRESS = re.compile(r"(?<!\w)[\wåäöéü'’\-]+" + _STREET + r"\s+\d{1,4}(?:\s+[a-z](?!\w)(?:\s+\d{1,4})?)?(?:,?\s+\d{5}\s+[\wåäöéü'’\-]+)?", re.I)
# A named street without house number still pinpoints the request location.
_LOCATION = re.compile(r"(?<!\w)[\wåäöéü'’\-]+(?:kadun|tien|kujan|polun|rinteen|kaaren|puistikon|väylän|pihan|tanhuan|rannan|mäen)\s+(?:bussipysäkki|kierrätyspiste|leikkipuisto|pysäköintialue)(?:llä|ssä|n)?", re.I)
_NUMERIC = re.compile(r"(?<![\w.])\+?\d+(?:[ \t-]+\d+)*(?!\w|\.\d)")
_EMAIL_SPOKEN = re.compile(r"(?<!\w)[\wåäöéü'\-]+(?:\s+(?:piste|dot|punkt|alaviiva|underscore)\s+[\wåäöéü'\-]+)*\s+(?:ät|at|snabel-a)\s+[\w\-]+(?:\s+(?:piste|dot|punkt)\s+[\w\-]+)+", re.I)
_CUES = {
    "NATIONAL_ID": re.compile(r"hetu|henkilötunn|person.?beteckn|personal (?:id|identity)|id code|identity code", re.I),
    "PHONE": re.compile(r"puhel|numer(?:o|osta|oon|onsa|osi|on|et|ret)|phone|call|number|nummer|ringa|ring|yhteys", re.I),
    "ACCOUNT_NUMBER": re.compile(r"asiakasnumer|kundnum|customer (?:erm )?number|lasku|laskun|lakun|invoice|faktura|sopimusnumer|contract|order number|tilausnumer", re.I),
    "DEVICE_ID": re.compile(r"imei|iccid|serial|sarjanumer|sim.?kort|sim number", re.I),
    "PAYMENT_CARD": re.compile(r"kort(?:ti|in|illa|tini|tets|nummer|et)|card|last four|last 4|viimeiset neljä|sista fyra|päättyy|slutar på|ending", re.I),
    "IBAN": re.compile(r"iban|tilinumer|tilille|account number|bank account|kontonum", re.I),
    "SECRET": re.compile(r"pin|puk|salasana|password|lösenord|wifi key|wifin avain", re.I),
}
# Detect values after a credential cue while retaining the cue and ordinary prose.
_CREDENTIAL = re.compile(r"\b(?:salasana(?:ni)?|password|lösenord|pin(?:-koodi|-koden)?|puk(?:-koodi|-koden)?|wifi[- ]?key|käyttäjätunnukseni|username|usernmae|användarnamn)(?:[\s,:]+(?:on|is|är|there|three|probably|varmaan|tota|niinku|ja|so)){0,5}[\s:]+([^\s,;]+)", re.I)
_HEALTH = re.compile(r"diabet\w*|gluko\w*|glucose|sokerimittar\w*|kuulolai\w*|hearing aid|hörapparat\w*|aivoinfarkt\w*|stroke|syöpä\w*|cancer\w*|sairausloma\w*|sjukskriv\w*|sick leave|masennu\w*|depress\w*|muistisair\w*|dementia|sydänleikkau\w*|heart surgery|hjärtoperation\w*|pyörätuol\w*|rollaattor\w*|wheelchair|rullstol\w*|näkövamma\w*|huonokunto\w*|astma\w*|asthma\w*|dialyysi\w*|ihottum\w*|jatkuva yskä|constant cough|heart condition|sekaval\w*", re.I)


def _words(value: str) -> tuple[str, ...]:
    return tuple(x.group().lower() for x in _WORD.finditer(value))


def _present(value: Any) -> bool:
    return str(value).strip().lower() not in _MISSING


def _schema_label(name: str) -> str | None:
    n = name.lower()
    if re.search(r"(?:full|first|last|given|family|agent|handler|reporter|applicant|holder|guardian|teacher|physician|officer|author|display)_?name|(?:^|_)name$|case_officer", n):
        return "PERSON"
    if re.search(r"street_address|postal_address|home_address", n):
        return "ADDRESS"
    if re.search(r"(?:^|_)(?:hetu|ssn|national_id|personal_id)(?:$|_)", n):
        return "NATIONAL_ID"
    if "email" in n:
        return "EMAIL"
    if "phone" in n or "mobile_number" in n:
        return "PHONE"
    if "iban" in n:
        return "IBAN"
    if re.search(r"customer_number|contract_number|account_number|invoice_number", n):
        return "ACCOUNT_NUMBER"
    if re.search(r"(?:^|_)(?:username|user_name|login)(?:$|_)", n):
        return "USERNAME"
    if "property_id" in n:
        return "PROPERTY_ID"
    if "license_plate" in n or "registration_plate" in n:
        return "LICENSE_PLATE"
    return None


def _edit_close(left: str, right: str, limit=1) -> bool:
    """Bounded edit distance for short cue/filler words, never for PII values."""
    if abs(len(left) - len(right)) > limit:
        return False
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j-1] + (a != b)))
        if min(current) > limit:
            return False
        previous = current
    return previous[-1] <= limit


def _fuzzy_credential_cue(value: str) -> str | None:
    if len(value) < 6 or not value.isalpha():
        return None
    for canonical in ("salasana", "salasanani", "password", "lösenord", "username", "käyttäjätunnukseni", "användarnamn"):
        if value[:1] == canonical[:1] and _edit_close(value, canonical, 2):
            return "USERNAME" if canonical in {"username", "käyttäjätunnukseni", "användarnamn"} else "SECRET"
    return None


def _filler(value: str) -> bool:
    if value in {"on", "is", "är", "there", "three", "probably", "varmaan", "tota", "niinku", "ja", "so", "siis", "joo", "ööh", "öö", "erm", "um", "well", "uh"}:
        return True
    return any(len(value) >= 4 and _edit_close(value, word) for word in ("probably", "varmaan", "there", "niinku"))


class TextDetector:
    """Resolve entities from raw relational data plus format and context rules.

    Optional field predictions enrich the dictionary. They are never required;
    column-name evidence remains useful when a predicted subtype is uncertain.
    Span offsets always refer to the input string and are non-overlapping.
    """

    def __init__(self, tables: dict, field_labels: pd.DataFrame | None = None, dataset: str = ""):
        self.dataset = dataset
        self._trie: dict = {}
        self._first: set[str] = set()
        labels = {}
        subtype_aliases = {"PERSON_NAME": "PERSON", "STREET_ADDRESS": "ADDRESS", "ORG_NAME": "ORG",
                           "MAC_ADDRESS": "DEVICE_ID", "IMEI": "DEVICE_ID", "CUSTOMER_ID": "ACCOUNT_NUMBER",
                           "ACCOUNT_ID": "ACCOUNT_NUMBER"}
        if field_labels is not None:
            for row in field_labels.to_dict("records"):
                key = (str(row["table"]), str(row["column"]))
                predicted = str(row.get("subtype", ""))
                labels[key] = subtype_aliases.get(predicted, predicted)
        for table, frame in tables.items():
            for col in frame.columns:
                label = _schema_label(str(col))
                predicted = labels.get((table, str(col)))
                if label == "PERSON" and predicted in {"ORG", "LOCATION_NAME", "LOCATION"}:
                    label = "ORG" if predicted == "ORG" else None
                    if label is None:
                        continue
                # Public stops/stations/merchant names are not personal names.
                if label == "PERSON" and str(col).lower() in {"stop_name", "station_name", "sensor_name", "merchant_name", "organisation_name", "organization_name", "company_name", "business_name"}:
                    continue
                if label is None and predicted in {"PERSON", "NATIONAL_ID", "EMAIL", "PHONE", "ADDRESS", "IBAN", "PAYMENT_CARD", "LICENSE_PLATE", "PROPERTY_ID", "USERNAME"}:
                    label = predicted
                if label is None:
                    continue
                for raw in frame[col].dropna().unique():
                    if not _present(raw):
                        continue
                    value = str(raw).strip()
                    # Organisations in a mixed applicant-name field use ORG.
                    actual = "ORG" if label == "PERSON" and re.search(r"\b(?:oy|oyj|ab|tmi|ky|ry|ltd|inc|gmbh|llc)\b", value, re.I) else label
                    words = _words(value)
                    if not words or (len(words) == 1 and len(words[0]) < 2):
                        continue
                    self._add(words, actual)
                    if actual == "PERSON":
                        # First names and surnames can reappear alone in replies.
                        for word in words:
                            if len(word) >= 2 and word not in _AMBIGUOUS:
                                self._first.add(word)
                                self._add((word,), "PERSON")
        # The instance-local wrappers avoid sharing private dictionaries between runs.
        self._detect_cached = lru_cache(maxsize=120000)(self._detect)

    def _add(self, words: tuple[str, ...], label: str):
        node = self._trie
        for word in words:
            node = node.setdefault(word, {})
        node[None] = label

    @staticmethod
    def _number_label(value: str, before: str, spoken=False) -> str | None:
        digits = re.sub(r"\D", "", value)
        count = sum(w.lower() in _DIGITS for w in re.findall(r"\w+", value)) if spoken else len(digits)
        if _CUES["SECRET"].search(before[-65:]):
            return "SECRET" if count >= 3 else None
        for label in ("DEVICE_ID", "PAYMENT_CARD", "NATIONAL_ID", "IBAN", "ACCOUNT_NUMBER", "PHONE"):
            if _CUES[label].search(before[-70:]):
                if count >= (2 if spoken else 3):
                    return label
        if not spoken and ((digits.startswith("358") and count >= 11) or (digits.startswith("0") and (count >= 9 or count == 3))):
            return "PHONE"
        if count >= 13:
            return "PAYMENT_CARD" if count in (13, 16, 19) else "DEVICE_ID"
        if count >= 8:
            return "ACCOUNT_NUMBER"
        if count == 6 and not spoken:
            return "NATIONAL_ID"
        if count >= 3 and spoken:
            return "PHONE"
        return None

    def _detect(self, text: str, table: str, column: str) -> tuple:
        found: list[tuple[int, int, str, int]] = []

        def add(start, end, label, priority=50):
            if end > start:
                found.append((start, end, label, priority))

        for label, rx in _PATTERNS:
            for m in rx.finditer(text):
                end = m.end()
                if label == "URL":
                    while end > m.start() and text[end - 1] in ".,;!?)]}":
                        end -= 1
                    # Ordinary public help pages carry no person-specific data.
                    url = text[m.start():end].lower()
                    if "?" not in url and re.search(r"(?:^https?://)(?:www\.)?(?:aallokko\.example|oma\.aallokko\.example)/(?:help|support|tuki|ohjeet|privacy|contact)/?$", url):
                        continue
                if label == "IP_ADDRESS":
                    ip = text[m.start():end]
                    if ip in {"192.168.1.1", "192.168.0.1", "127.0.0.1"} or any(int(v) > 255 for v in ip.split(".")):
                        continue
                add(m.start(), end, label, 100)
        for rx, label in ((_ADDRESS, "ADDRESS"), (_LOCATION, "LOCATION"), (_EMAIL_SPOKEN, "EMAIL")):
            for m in rx.finditer(text):
                add(m.start(), m.end(), label, 95)
        # Scan the known-entity trie using word offsets; punctuation and case vary
        # between contact records, ASR, chat and e-mail signatures.
        words = list(_WORD.finditer(text))
        for i, word in enumerate(words):
            node = self._trie
            best = None
            for j in range(i, min(i + 12, len(words))):
                # Never join known names across sentence boundaries or prose.
                if j > i and not re.fullmatch(r"[ \t-]*", text[words[j-1].end():words[j].start()]):
                    break
                node = node.get(words[j].group().lower())
                if node is None:
                    break
                if None in node:
                    best = (word.start(), words[j].end(), node[None])
            if best:
                add(*best, 75)
        # Unknown third-party names often follow these language-specific cues.
        # Only consume capitalised tokens, or tokens already evidenced as names.
        cue = re.compile(r"\b(?:naapuri|grannen|neighbor|nimellä|nimeni on|namn är|heter|name is|name|lapseni|äitini|isäni|puolisoni|tyttärelleni|poikani|daughter|son|mother|father|wife|husband|partner)\s+", re.I)
        for m in cue.finditer(text):
            start, end = m.end(), m.end()
            for w in _TERM.finditer(text, start):
                if w.start() > end and text[end:w.start()].strip():
                    break
                value = w.group()
                if not value[0].isupper() and value.lower() not in self._first:
                    # Relatives can be outside every supplied contact table.
                    # Their name is followed by a verb or contact details.
                    rest = text[w.end():w.end()+35]
                    relative = re.search(r"lapseni|äitini|isäni|puolisoni|tyttärelleni|poikani|daughter|son|mother|father|wife|husband|partner", m.group(), re.I)
                    if w.start() != start or not relative or not re.match(r"\s+(?:passed|died|usually|hoitaa|on|at|\+?\d)", rest, re.I):
                        break
                if value.lower() in _AMBIGUOUS:
                    break
                end = w.end()
                if len(text[start:end].split()) >= 4:
                    break
            if end > start:
                add(start, end, "PERSON", 65)
        for m in _NUMERIC.finditer(text):
            value = m.group()
            before = text[max(0, m.start() - 90):m.start()]
            label = self._number_label(value, before)
            digits = re.sub(r"\D", "", value)
            if len(digits) < 8 and (re.search(r"(?:€|\beur(?:o)?\b)", text[m.end():m.end()+12], re.I) or before.endswith("€")):
                label = None
            # A standalone continuation is a partial identifier, not a price.
            if label is None and re.fullmatch(r"\s*\d{3,7}\s*[.!]?\s*", text):
                label = "PHONE" if len(re.sub(r"\D", "", value)) != 6 else "NATIONAL_ID"
            if label:
                add(m.start(), m.end(), label, 55)
        for m in _SPOKEN.finditer(text):
            value = m.group()
            before = text[max(0, m.start() - 90):m.start()]
            label = self._number_label(value, before, spoken=True)
            if re.search(r"viiva|dash|streck", value, re.I):
                label = "NATIONAL_ID"
            if label is None and not text[:m.start()].strip() and not text[m.end():].strip(" .!?"):
                label = "NATIONAL_ID"
            if label:
                start = m.start()
                if re.search(r"[Ff]\s+[Ii]\s*$", text[max(0, start-5):start]):
                    prefix = re.search(r"[Ff]\s+[Ii]\s*$", text[max(0, start-5):start])
                    start = max(0, start-5) + prefix.start()
                    label = "IBAN"
                add(start, m.end(), label, 85)
        for m in _CREDENTIAL.finditer(text):
            value = m.group(1).rstrip(".?!")
            # Values must look like credentials, not a request for a password.
            if value.lower() in {"on", "is", "är", "the", "not", "don't", "en", "ole", "ei", "olemaan", "wrong", "väärä", "forgotten", "unohtunut", "lähetetty", "varmaan", "probably"}:
                continue
            label = "USERNAME" if re.search(r"käyttäj|usern|användar", m.group(), re.I) else "SECRET"
            if label == "SECRET" and not (re.search(r"\d", value) or len(value) >= 8):
                continue
            add(m.start(1), m.start(1) + len(value), label, 110)
        # Compact employee initials in a note signature are identifying too.
        for m in re.finditer(r"/([a-zåäö][a-zåäö-]{1,5})(?=\s|[.!?]|$)", text, re.I):
            add(m.start(1), m.end(1), "PERSON", 80)
        # Typographical/ASR errors around credential cues are common. Match the
        # cue approximately, then skip speech fillers before taking its value.
        if re.search(r"sal|sla|pass|lösen|lsen|usern|käytt|använd", text, re.I):
            terms = list(re.finditer(r"[^\s,;:]+", text))
            for i, token in enumerate(terms):
                cue_value = token.group().strip(".!?-").lower()
                cue_label = _fuzzy_credential_cue(cue_value)
                if cue_label is None:
                    continue
                for following in terms[i+1:i+8]:
                    candidate = following.group().rstrip(".?,;")
                    if _filler(candidate.lower()):
                        continue
                    if cue_label == "USERNAME" or re.search(r"\d", candidate) or (len(candidate) >= 8 and candidate.isalnum()):
                        add(following.start(), following.start()+len(candidate), cue_label, 115)
                    break
        # Sensitive medical content: redact the sentence/clause containing a
        # medical term, retaining surrounding service intent and action words.
        for m in _HEALTH.finditer(text):
            start = max(text.rfind(".", 0, m.start()), text.rfind("\n", 0, m.start()), text.rfind(";", 0, m.start())) + 1
            end_candidates = [p for p in (text.find(".", m.end()), text.find("\n", m.end()), text.find(";", m.end())) if p >= 0]
            end = min(end_candidates) if end_candidates else len(text)
            # Common service-intent prefixes are independent of medical details.
            prefix = re.search(r"(?:koska|eftersom|because|maksusuunnitelman[,]?|betalningsplan[,]?|payment plan[,]?|jos olen hidas[,]?|if i.m slow[,]?)\s+", text[start:m.start()], re.I)
            if prefix:
                start += prefix.end()
            suffix = re.search(r"\s+(?:ja rahat|och ekonomin|and money)\b", text[m.end():end], re.I)
            if suffix:
                end = m.end() + suffix.start()
            while start < end and text[start].isspace():
                start += 1
            add(start, end, "HEALTH", 40)
        # Choose the most specific candidate, then make intervals disjoint.
        # Higher priority wins; a larger same-priority match wins over fragments.
        selected = []
        for start, end, label, priority in sorted(found, key=lambda x: (-x[3], -(x[1]-x[0]), x[0])):
            overlaps = [(a, b) for a, b, _, _ in selected if start < b and a < end]
            if overlaps and label == "HEALTH":
                # An address/name elsewhere in a medical clause must not make
                # us discard the medical information itself.
                cursor = start
                for a, b in sorted(overlaps):
                    if a > cursor:
                        selected.append((cursor, a, label, priority))
                    cursor = max(cursor, b)
                if cursor < end:
                    selected.append((cursor, end, label, priority))
            elif not overlaps:
                selected.append((start, end, label, priority))
        selected.sort()
        # Neighbouring single name matches combine into a full name span.
        merged = []
        for start, end, label, _ in selected:
            if merged and label == "PERSON" == merged[-1][2] and re.fullmatch(r"[ \t-]+", text[merged[-1][1]:start]):
                merged[-1] = (merged[-1][0], end, label)
            else:
                merged.append((start, end, label))
        return tuple(merged)

    def detect(self, text, table: str = "", column: str = "") -> list[dict]:
        value = "" if not _present(text) else str(text)
        return [{"start": start, "end": end, "label": label, "text": value[start:end]}
                for start, end, label in self._detect_cached(value, table, column)]

    def redact(self, text, table: str = "", column: str = "") -> str:
        value = "" if not _present(text) else str(text)
        pieces, end = [], 0
        for start, stop, label in self._detect_cached(value, table, column):
            pieces.extend((value[end:start], "[" + label + "]"))
            end = stop
        pieces.append(value[end:])
        return "".join(pieces)
