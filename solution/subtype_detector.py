"""Subtype detector: one judger per subtype; every judger scores a column 0..1, the highest score wins.

A judger answers "is this column of my subtype?". It looks first at the values (formats, checksums, gazetteers,
lexicons) and then at the column name and its context (position in the table, uniqueness, whether the table is
a timestamped log). Scores are heuristic confidences, not calibrated probabilities. It never reads
metadata/field_catalog.csv. detector.py turns the winning subtype into a privacy role; evaluate.py scores both.
"""
from __future__ import annotations

import re
from functools import cached_property

import numpy as np
import pandas as pd

SAMPLE = 1000
NROWS = 300_000


def tokens(s: str) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", str(s).lower()) if t}


# ------------------------------------------------------------------ value patterns and checks
RX = {
    "hetu": re.compile(r"^(\d{6})[-+A-FU-Y]?(\d{3})([0-9A-Y])$"),
    "email": re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$"),
    "iban": re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$"),
    "phone": re.compile(r"^(\+\d{2,3}[\s-]?|0)\d{1,3}[\s-]?\d{3,4}[\s-]?\d{2,4}$"),
    "ipv4": re.compile(r"^\d{1,3}(\.\d{1,3}){3}(/\d{1,2})?$"),
    "mac": re.compile(r"^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$"),
    "plate": re.compile(r"^[A-ZÅÄÖ]{2,3}-\d{1,3}$"),
    "url": re.compile(r"^https?://\S+$"),
    "domain": re.compile(r"^([a-z0-9-]+\.)+(example|com|fi|net|org|io|eu|se|ee|de|local|internal|corp)$"),
    "user_agent": re.compile(r"^[A-Za-z][\w.-]*/\d+(\.\d+)*(\s|$)"),
    "icd10": re.compile(r"^[A-Z]\d{2}(\.\d{1,2})?$"),
    "postcode": re.compile(r"^\d{5}$"),
    "datetime": re.compile(r"^(\d{4}-\d{2}-\d{2}[ T]\d{1,2}:\d{2}|\d{1,2}\.\d{1,2}\.\d{4}\s+\d{1,2}[:.]\d{2})"),
    "date": re.compile(r"^(\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-W\d{2}|"
                       r"\d{4}-\d{2}|(19|20)\d{2}[KS]|\d{2}/\d{2}|(19|20)\d{2})$"),
    "uuid": re.compile(r"^<?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(@[^>\s]+)?>?$"),
    "hash": re.compile(r"^([0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{64}|[0-9A-F]{32}|[0-9A-F]{40}|[0-9A-F]{64})$"),
    "code": re.compile(r"^(?=.*\d)[A-Z0-9][A-Z0-9_\-./]*$"),
    "digits": re.compile(r"^\d+$"),
    "masked_card": re.compile(r"^\d{4,6}[*Xx•]{2,9}\d{4}$"),
    "gps": re.compile(r"^-?\d{1,3}\.\d{4,}$"),
    "age_band": re.compile(r"^(\d{1,2})\s?[-–]\s?(\d{1,3})$|^\d{1,2}\+$"),
    "address": re.compile(r"^[A-ZÅÄÖ][\wåäöÅÄÖé.\-]+(\s[A-Za-zÅÄÖåäö][\wåäöé.\-]+)?\s\d{1,4}(\s?[A-Za-z]{1,2})?(\s?\d{1,4})?"
                          r"(,\s*\d{5}(\s+\S+)*)?$"),
    "y_tunnus": re.compile(r"^\d{7}-\d$"),
    "property": re.compile(r"^\d{3}-\d{3}-\d{4}-\d{4}$"),
    "money_fi": re.compile(r"^-?\d{1,3}(\s\d{3})*,\d{2}$"),
    "filename": re.compile(r"[\w\-]+\.(pdf|docx?|xlsx?|zip|jpg|png|txt|csv|exe|js)\b", re.I),
    "win_path": re.compile(r"[A-Za-z]:\\|\\\\"),
    "country": re.compile(r"^([A-Z]{2}|--)$"),
}
HETU_CHECK = "0123456789ABCDEFHJKLMNPRSTUVWXY"


def hetu_valid(v: str) -> bool:
    m = RX["hetu"].match(v)
    return bool(m) and HETU_CHECK[int(m.group(1) + m.group(2)) % 31] == m.group(3)


def iban_valid(v: str) -> bool:
    s = v.replace(" ", "")
    if not RX["iban"].match(s):
        return False
    return int("".join(str(int(ch, 36)) for ch in s[4:] + s[:4])) % 97 == 1


def luhn(d: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(d)):
        x = int(ch)
        if i % 2:
            x = x * 2 - 9 if x > 4 else x * 2
        total += x
    return total % 10 == 0


# ------------------------------------------------------------------ lexicons (public knowledge, not the catalog)
FIRST_NAMES = set("""
aapo aaro aarne aatu aki aleksi ali anders antero anton antti ari arto arttu atte axel bengt christer daniel eemeli
eero eetu eino elias emil erik erkki esa esko hannu harri heikki henri henrik ilkka ilmari jaakko jalmari jani janne
jari jarkko jarmo jere jesse joel johan johannes joni jonne joona joonas jouko jouni juha juhani juho jukka jussi
juuso jyrki kai kalle kari kasper kalevi kimmo kristian lasse lauri leevi leo markku marko markus martti matias matti
mika mikael mikko niklas niko nils olavi oliver olli onni oscar oskari otto paavo pasi patrik pekka pentti pertti
petri petteri raimo rasmus reijo riku risto sami samuel santeri sebastian simo stefan taneli tapani tapio teemu timo
tomi toni topi tuomas valtteri veikko veli ville viljo väinö vesa ryan pablo mohamed ahmed omar hassan
aada aino aili alma amanda anna anneli annika anu aurora britt eeva eija elina elisa ella ellen elli emilia emma essi
eveliina hanna heidi heli helena helmi iida inka inkeri irja jenni johanna josefiina julia kaija kaisa katja kerttu
kirsi kristiina kristina laura leena liisa linnea lotta maija maria marika marja marjatta marjo merja milla minna mira
nea nelli niina noora oona outi paula pia piia pinja pirjo raija riikka ronja saara sanna sara sari satu seija siiri
sini sofia susanna suvi taina tarja terttu tiina tuija tuula ulla veera venla viivi elsa ingrid karin ananya narin
fatima aisha matilda wilma olivia lumi tiia jaana anja eila maarit sirpa
""".split())
SURNAME_SUFFIX = ("nen", "la", "lä", "oja", "mäki", "maki", "salo", "niemi", "koski", "vaara", "lahti", "harju", "aho",
                  "suo", "luoto", "korpi", "kallio", "kivi", "lampi", "vuori", "rinne", "ranta", "joki", "järvi",
                  "saari", "puro", "kangas", "nummi", "berg", "ström", "qvist", "lund", "dahl", "holm", "gren", "son")
SW_MUNICIPALITIES = set("""
aura kaarina kemiönsaari koski laitila lieto loimaa marttila masku mynämäki naantali nousiainen oripää paimio parainen
pyhäranta pöytyä raisio rusko salo sauvo somero taivassalo turku uusikaupunki vehmaa kustavi åbo nådendal pargas reso
s:t karins kimitoön nystad pemar virmo masko letala gustavs tövsala vemo sagu lundo nousis non-resident
""".split()) | {"koski tl", "s:t karins"}
ISO639 = set("fi sv en ru et ar so de fr es fa ku zh th vi uk pl tr sq bs hr sr ro hu it pt ne tl ur hi bn ti am".split())
OCCUPATION_SUFFIX = ("hoitaja", "opettaja", "insinööri", "johtaja", "päällikkö", "sihteeri", "työntekijä", "asiantuntija",
                     "kuljettaja", "myyjä", "avustaja", "ohjaaja", "lääkäri", "kokki", "siivooja", "neuvoja", "suunnittelija")
ORG_SUFFIX = re.compile(r"\b(oy|oyj|ab|tmi|ky|ry|ltd|inc|gmbh|llc|plc|group|isp)\b\.?\)?$", re.I)
STREET_SUFFIX = ("katu", "tie", "kuja", "polku", "rinne", "kaari", "puistikko", "väylä", "raitti", "aukio", "piha",
                 "gatan", "vägen", "gränd", "stigen", "backen", "ranta", "mäki", "tori")

KW = {  # column-name vocabulary per subtype (matched against name tokens)
    "FINANCIAL": {"income", "salary", "wage", "wages", "amount", "fee", "cost", "price", "balance", "payment", "debt",
                  "default", "kyc", "loan", "credit", "palkka"},
    "HEALTH": {"triage", "disposition", "readmit", "los", "abnormal", "diagnosis", "medical", "accessibility",
               "health", "sick", "illness", "excused", "support", "disability", "symptom", "medication", "allergy"},
    "VITALS": {"bp", "systolic", "diastolic", "heart", "pulse", "resp", "temp", "spo2", "pain"},
    "EDUCATION": {"grade", "points", "course", "programme", "program", "class", "subject", "curriculum",
                  "unexcused", "arrivals", "matriculation"},
    "UNIT": {"kb", "ms", "m2", "kw", "kwh", "a", "c", "rate", "score", "size", "bytes", "distance", "capacity",
             "credits", "temperature", "wind", "oktas", "csat", "confidence", "dbm", "rssi", "fuse", "solar", "turns",
             "max", "in", "out", "sent", "received", "m", "pv", "area"},
    "CATCODE": {"code", "mcc", "type", "status", "line", "period", "direction", "zone", "level", "category",
                "priority", "verdict", "severity", "method", "channel", "flag", "split", "term", "scale", "quality"},
    "FREE": {"note", "notes", "text", "description", "message", "comment", "subject", "body", "response",
             "resolution", "title", "complaint", "command", "path", "attachment", "attachments", "summary", "remarks"},
    "PERSON": {"name", "names", "surname", "officer", "handler", "author", "reporter", "applicant", "holder",
               "guardian", "teacher", "agent", "physician", "display", "given", "first", "last", "sender"},
    "PLACE": {"stop", "station", "sensor", "park", "location", "office", "place", "country", "city", "area", "site"},
    "PLACE_TABLE": {"stops", "stations", "sensors", "locations", "places", "sites"},
    "ORG": {"employer", "organisation", "organization", "org", "company", "department", "school", "merchant",
            "business"},
    "OCCUPATION": {"occupation", "job", "profession", "role", "position", "ammatti"},
}


# ------------------------------------------------------------------ column view
class Col:
    def __init__(self, s: pd.Series, name: str, table: str, dataset: str, position: int, log_table: bool):
        v = s.dropna().astype(str).str.strip()
        self.all = v[v != ""]
        self.name, self.table, self.dataset, self.position, self.log_table = name, table, dataset, position, log_table
        self.n, self.nu = len(self.all), int(self.all.nunique())
        self.ur = self.nu / self.n if self.n else 0.0
        self.vals = self.all.sample(SAMPLE, random_state=0) if self.n > SAMPLE else self.all
        self.uniq = pd.Series(self.all.unique()[:SAMPLE])
        self.tok, self.ttok = tokens(name), tokens(table)
        self._share: dict = {}

    def share(self, key: str) -> float:
        if key not in self._share:
            rx = RX[key]
            self._share[key] = float(self.vals.map(lambda x: bool(rx.match(x))).mean()) if self.n else 0.0
        return self._share[key]

    def share_fn(self, fn) -> float:
        return float(self.vals.map(fn).mean()) if self.n else 0.0

    def has(self, *words) -> bool:
        return bool(self.tok & set(words))

    def kw(self, group: str) -> bool:
        return bool(self.tok & KW[group])

    @cached_property
    def numbers(self) -> pd.Series:
        return pd.to_numeric(self.vals.str.replace(",", ".", regex=False), errors="coerce")

    @cached_property
    def numeric(self) -> bool:
        return self.n > 0 and self.numbers.notna().mean() >= 0.95

    @cached_property
    def integer(self) -> bool:
        x = self.numbers.dropna()
        return self.numeric and len(x) > 0 and bool((x == x.round()).all())

    @cached_property
    def mean_len(self) -> float:
        return float(self.vals.str.len().mean()) if self.n else 0.0

    @cached_property
    def mean_words(self) -> float:
        return float(self.vals.str.split().str.len().mean()) if self.n else 0.0

    @cached_property
    def id_name(self) -> bool:
        return self.has("id", "number", "no", "ref", "reference", "nr") or self.name.lower().endswith("id")

    @cached_property
    def key_like(self) -> bool:  # identifier-looking values
        return self.share("code") >= 0.9 or self.share("uuid") >= 0.9 or self.share("digits") >= 0.9

    @cached_property
    def first_unique(self) -> bool:
        return self.position == 0 and self.ur >= 0.99 and self.n > 0

    @cached_property
    def person_share(self) -> float:
        def one(x):
            t = x.replace(",", " ").split()
            if not 1 <= len(t) <= 4 or not all(re.fullmatch(r"[A-Za-zÅÄÖåäöéüß'\-]+", w) for w in t):
                return False
            return any(w.lower() in FIRST_NAMES for w in t)
        return float(self.uniq.map(one).mean()) if self.n else 0.0

    @cached_property
    def surname_share(self) -> float:
        def one(x):
            return bool(re.fullmatch(r"[A-ZÅÄÖ][a-zåäöéü'\-]+", x)) and x.lower().endswith(SURNAME_SUFFIX)
        return float(self.uniq.map(one).mean()) if self.n else 0.0

    @cached_property
    def municipality_share(self) -> float:
        return float(self.vals.str.lower().isin(SW_MUNICIPALITIES).mean()) if self.n else 0.0

    @cached_property
    def year_median(self) -> float:
        y = pd.to_numeric(self.vals.str.extract(r"((?:19|20)\d{2})")[0], errors="coerce")
        y2 = pd.to_numeric(self.vals.str.extract(r"^\d{1,2}[./]\d{1,2}[./](\d{2})$")[0], errors="coerce")
        y = y.fillna(y2.map(lambda t: 1900 + t if t > 30 else 2000 + t))
        return float(y.median()) if y.notna().any() else np.nan


# ------------------------------------------------------------------ judgers
JUDGES: dict = {}


def judge(subtype):
    def deco(fn):
        JUDGES[subtype] = fn
        return fn
    return deco


@judge("NATIONAL_ID")
def j_national_id(c):
    return max(c.share_fn(hetu_valid), 0.9 * c.share("hetu"), 0.8 * c.has("hetu", "ssn", "henkilotunnus"))


@judge("EMAIL")
def j_email(c):
    return 0.95 * c.share("email")


@judge("USERNAME")
def j_username(c):  # an account acting in a timestamped log, written as an e-mail address or a login name
    account = c.has("upn", "username", "login", "user") and not c.has("account")
    return c.share("email") * (1.0 if account and c.log_table else 0.0) + (0.7 if account and not c.share("email") else 0)


@judge("IBAN")
def j_iban(c):
    return max(c.share_fn(iban_valid), 0.85 * c.share_fn(lambda x: bool(RX["iban"].match(x.replace(" ", "")))))


@judge("PHONE")
def j_phone(c):
    return c.share("phone") * (1.0 if not c.share("digits") > 0.9 or c.has("phone", "mobile", "puhelin") else 0.8)


@judge("IP_ADDRESS")
def j_ip(c):
    return c.share("ipv4")


@judge("MAC_ADDRESS")
def j_mac(c):
    return c.share("mac")


@judge("LICENSE_PLATE")
def j_plate(c):
    return c.share("plate")


@judge("URL")
def j_url(c):
    return max(c.share("url"), 0.9 * c.share("domain"))


@judge("USER_AGENT")
def j_ua(c):
    return c.share("user_agent")


@judge("DIAGNOSIS_CODE")
def j_icd(c):
    if not c.n:
        return 0.0
    parts = c.vals.str.split("|").explode().str.strip()
    parts = parts[parts != ""]
    if not len(parts):
        return 0.0
    share = float(parts.map(lambda x: bool(RX["icd10"].match(x))).mean())
    # real diagnoses span several ICD chapters; S01..S12 school codes or A1/B2 grid labels do not
    chapters = parts.str[0].nunique()
    return share if chapters >= 3 or c.has("icd", "icd10", "diagnosis") else 0.3 * share


@judge("PAYMENT_CARD")
def j_card(c):
    pan = c.share_fn(lambda x: x.isdigit() and 13 <= len(x) <= 19 and x[0] in "23456" and luhn(x))
    return max(pan, c.share("masked_card"), 0.6 * c.has("pan"))


@judge("CARD_ID")
def j_card_id(c):
    travel = c.share_fn(lambda x: x.isdigit() and 10 <= len(x) <= 19 and x[0] not in "23456" and luhn(x))
    return max(0.95 * travel, 0.55 * (c.has("card") and c.id_name))


@judge("METER_ID")
def j_meter(c):
    gsrn = c.share_fn(lambda x: x.isdigit() and len(x) == 18)
    return max(gsrn * (1.0 if c.has("meter", "metering", "gsrn") else 0.85), 0.8 * c.has("meter", "metering", "gsrn"))


@judge("IMEI")
def j_imei(c):
    return 0.9 * c.share_fn(lambda x: x.isdigit() and len(x) == 15 and luhn(x))


@judge("PROPERTY_ID")
def j_property(c):
    return max(c.share("property"), 0.7 * c.has("property", "kiinteistotunnus"))


@judge("STUDENT_ID")
def j_student(c):
    return 0.95 if c.has("student", "learner") and c.id_name else 0.0


@judge("EMPLOYEE_ID")
def j_employee(c):
    return 0.95 if c.has("staff", "employee", "agent", "physician", "author", "teacher") and c.id_name else 0.0


@judge("CUSTOMER_ID")
def j_customer(c):
    return 0.92 if c.has("customer", "client") and c.id_name else 0.0


@judge("PATIENT_ID")
def j_patient(c):
    return 0.92 if c.has("patient") and c.id_name else 0.0


@judge("ACCOUNT_ID")
def j_account(c):
    return 0.9 if c.has("account", "contract", "reference") and c.id_name else 0.0


@judge("DEVICE_ID")
def j_device(c):
    if c.has("device") and c.share("uuid") >= 0.8:
        return 0.95
    if c.has("unit", "bike", "imei") and c.key_like and c.ur < 0.5:
        return 0.85
    return 0.0


@judge("HOSTNAME")
def j_host(c):
    host_name = c.has("host", "hostname") or (c.has("device") and c.has("name"))
    return 0.9 if host_name and c.share("code") >= 0.5 else 0.0


@judge("RECORD_ID")
def j_record(c):
    if c.first_unique and (c.key_like or c.id_name):
        return 0.9
    if c.share("uuid") >= 0.9:
        return 0.8
    if c.id_name and c.key_like and c.nu > 10:
        return 0.6
    return 0.3 if c.key_like and c.ur > 0.9 else 0.0


@judge("OTHER")
def j_other(c):
    if c.share("hash") >= 0.9:
        return 0.9
    if c.has("seq", "ssid", "sequence"):
        return 0.6
    return 0.05


@judge("POSTCODE")
def j_postcode(c):
    return c.share("postcode") * (1.0 if c.has("postcode", "zip", "postal", "district") or c.nu > 10 else 0.6)


@judge("TIMESTAMP")
def j_ts(c):
    return c.share("datetime")


@judge("BIRTH_DATE")
def j_birth(c):
    d = c.share("date")
    if c.has("birth", "dob", "syntymäaika", "born"):
        return d
    return 0.8 * d if c.year_median <= 2009 and c.nu > 50 else 0.0


@judge("DATE")
def j_date(c):
    return 0.75 * c.share("date") + (0.15 if c.has("date", "week", "year", "session", "expiry", "since", "start",
                                                 "end", "installed") else 0)


@judge("DURATION")
def j_duration(c):
    if not c.numeric:
        return 0.0
    return 0.8 if c.has("duration", "seconds") or (c.has("time") and c.has("s", "sec", "min", "ms")) else 0.0


@judge("GPS_COORDINATE")
def j_gps(c):
    if not c.numeric:
        return 0.0
    x = c.numbers.dropna()
    in_range = float(((x.abs() <= 180)).mean()) if len(x) else 0
    if c.has("lat", "lon", "lng", "latitude", "longitude"):
        return 0.95 * in_range
    return 0.7 * c.share("gps") * float(x.between(19, 71).mean()) if len(x) else 0.0


@judge("SEX")
def j_sex(c):
    vals = set(c.uniq.str.lower())
    return 0.95 if c.n and c.nu <= 3 and vals <= {"m", "f", "x", "male", "female", "mies", "nainen", "muu"} else 0.0


@judge("LANGUAGE")
def j_language(c):
    codes = float(c.vals.isin(ISO639).mean()) if c.n else 0
    return max(0.95 * codes if c.nu <= 40 else 0.0, 0.5 * c.has("language", "lang", "kieli"))


@judge("AGE")
def j_age(c):
    band = c.share("age_band")
    if c.has("age", "ikä"):
        return max(0.95 * band, 0.8 * c.numeric)
    return 0.7 * band if c.nu >= 5 else 0.0


@judge("PERSON_NAME")
def j_person(c):
    ps = c.person_share
    if c.kw("PERSON") and not c.has("test", "file", "rule", "process", "station", "school", "course", "subject",
                                    "location", "stop", "merchant", "product"):
        if ps >= 0.3 or c.surname_share >= 0.4:
            return 0.95
    if ps >= 0.6:
        return 0.85 * ps
    if c.surname_share >= 0.5 and c.nu >= 100:
        return 0.7
    return 0.0


@judge("STREET_ADDRESS")
def j_address(c):
    a = c.share("address")
    street = c.share_fn(lambda x: x.split(" ")[0].lower().endswith(STREET_SUFFIX))
    if c.has("address", "street", "osoite"):
        return max(a, 0.8)
    return 0.9 * a if c.nu >= 30 and street >= 0.5 else 0.5 * a


@judge("MUNICIPALITY")
def j_municipality(c):
    m = c.municipality_share
    return 0.92 * m if m >= 0.9 else 0.0


@judge("LOCATION_NAME")
def j_location(c):
    if c.numeric:
        return 0.0
    if c.share("country") >= 0.95 and c.has("country", "geo"):
        return 0.9
    place_col = c.kw("PLACE") or (c.has("name", "sv") and bool(c.ttok & KW["PLACE_TABLE"]))
    if place_col and not c.first_unique:
        return 0.85
    return 0.0


@judge("FREE_TEXT")
def j_free(c):
    if not c.n:
        return 0.3 if c.kw("FREE") else 0.0
    if c.kw("FREE") and not c.has("code", "name", "type", "scale", "group", "id", "job"):
        return 0.9
    long = c.mean_len >= 30 and c.mean_words >= 4 and c.nu >= 30
    if long or c.share_fn(lambda x: bool(RX["win_path"].search(x))) >= 0.5:
        return 0.8
    if c.share_fn(lambda x: bool(RX["filename"].search(x))) >= 0.5 and c.nu >= 20:
        return 0.6
    return 0.0


@judge("FINANCIAL_DATA")
def j_financial(c):
    if c.kw("FINANCIAL") and not c.has("method", "type"):
        return 0.82
    return 0.65 * c.share("money_fi")


@judge("HEALTH_DATA")
def j_health(c):
    if c.kw("HEALTH") and not c.has("type", "method"):
        return 0.85
    if c.dataset == "health" and c.has("value", "result"):
        return 0.8
    return 0.0


@judge("EDUCATION_DATA")
def j_education(c):
    if c.kw("EDUCATION") and not c.has("scale", "max", "credits"):
        return 0.8
    if c.dataset == "education" and c.has("status"):
        return 0.8
    return 0.0


@judge("SOCIAL_DATA")
def j_social(c):
    if (c.has("second") and c.has("language")) or c.has("religion", "ethnic", "ethnicity", "migrant", "union"):
        return 0.9
    return 0.0


@judge("OCCUPATION")
def j_occupation(c):
    if c.kw("OCCUPATION"):
        return 0.88
    return 0.7 * c.share_fn(lambda x: x.lower().endswith(OCCUPATION_SUFFIX))


@judge("ORG_NAME")
def j_org(c):
    if c.share("y_tunnus") >= 0.9:
        return 0.88
    if c.kw("ORG") and not c.has("city", "country"):
        return 0.8
    return 0.7 * min(1.0, 2 * c.share_fn(lambda x: bool(ORG_SUFFIX.search(x))))


@judge("NATIONALITY")
def j_nationality(c):
    return 0.85 if c.has("nationality", "citizenship", "kansalaisuus") else 0.0


@judge("SECRET")
def j_secret(c):
    named = c.has("password", "secret", "token", "apikey", "passwd")
    return 0.85 if named and not (c.share("date") > 0.5 or c.share("datetime") > 0.5 or c.numeric) else 0.0


@judge("AGGREGATE")
def j_aggregate(c):
    return 0.7 if c.numeric and c.has("count", "visits", "total", "sum") else 0.0


@judge("MEASUREMENT")
def j_measurement(c):
    if not c.numeric:
        return 0.0
    if c.kw("VITALS") or c.kw("UNIT"):
        return 0.72
    if c.kw("CATCODE") or c.id_name:
        return 0.3
    return 0.45 if not c.integer or c.nu > 25 else 0.4


@judge("CATEGORY")
def j_category(c):
    if not c.n:
        return 0.3
    if c.kw("CATCODE") and c.nu <= 100:
        return 0.62
    if c.id_name and c.nu <= 10:
        return 0.65
    if c.nu <= 50:
        return 0.42 if c.numeric else 0.5
    return 0.35 if c.nu <= 200 else 0.1


# ------------------------------------------------------------------ prediction
def score_column(c: Col) -> list[tuple[str, float]]:
    out = [(st, float(fn(c))) for st, fn in JUDGES.items()]
    return sorted(out, key=lambda t: -t[1])
