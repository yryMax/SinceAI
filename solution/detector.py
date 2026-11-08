"""Privacy field inference from values, schema and relationships; no annotation inputs.

The existing subtype_detector supplies checksum validators, lexical evidence and
independent subtype judgers. Context resolution distinguishes public observations
from person-linked records before assigning privacy roles.
"""
from __future__ import annotations

import argparse
import ipaddress
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import pandas as pd

try:
    from .subtype_detector import Col, RX, hetu_valid, iban_valid, score_column, tokens
except ImportError:
    from subtype_detector import Col, RX, hetu_valid, iban_valid, score_column, tokens

OUTPUT_COLUMNS = ['dataset', 'table', 'column', 'privacy_role', 'data_kind', 'subtype', 'confidence', 'evidence']
DIRECT = {'NATIONAL_ID', 'EMAIL', 'PHONE', 'PERSON_NAME', 'IBAN', 'PAYMENT_CARD', 'LICENSE_PLATE', 'PROPERTY_ID', 'USERNAME'}
TECHNICAL = {'IP_ADDRESS', 'MAC_ADDRESS', 'HOSTNAME', 'USER_AGENT', 'IMEI', 'METER_ID', 'DEVICE_ID', 'RECORD_ID', 'ACCOUNT_ID', 'CUSTOMER_ID', 'STUDENT_ID', 'EMPLOYEE_ID', 'PATIENT_ID', 'CARD_ID'}
QUASI = {'BIRTH_DATE', 'AGE', 'SEX', 'LANGUAGE', 'NATIONALITY', 'POSTCODE', 'MUNICIPALITY', 'GPS_COORDINATE', 'LOCATION_NAME', 'TIMESTAMP', 'DATE', 'OCCUPATION', 'ORG_NAME'}
SENSITIVE = {'DIAGNOSIS_CODE', 'HEALTH_DATA', 'FINANCIAL_DATA', 'SOCIAL_DATA', 'EDUCATION_DATA'}
PERSON_KEYS = {'customer', 'patient', 'student', 'learner', 'employee', 'account', 'card', 'metering', 'upn', 'user'}

@dataclass
class TableContext:
    table: str
    columns: set[str]
    words: set[str]
    domain: str
    timestamped: bool
    public: bool
    aggregate: bool
    identity: bool
    primary: str | None

def _present_values(s):
    x = s.dropna().astype(str).str.strip()
    return x[x != '']

def _primary_key(df):
    for name in list(df.columns)[:2]:
        x = _present_values(df[name])
        if ('id' in tokens(name) or str(name).lower().endswith('id')) and len(x) == len(df) and len(x) > 0 and x.is_unique:
            return name
    if len(df) == 0 and len(df.columns) and 'id' in tokens(df.columns[0]):
        return df.columns[0]
    return None

def _context(df, table, dataset):
    w = set().union(*(tokens(x) for x in df.columns)) if len(df.columns) else set()
    tt = tokens(table)
    timestamped = any(_present_values(df[c]).head(100).str.match(RX['datetime']).mean() > .8 for c in df.columns)
    if w & {'triage', 'icd10', 'spo2', 'abnormal'} or tt & {'clinical', 'lab'}: domain = 'health'
    elif w & {'student', 'learner', 'matriculation', 'guardian1', 'guardian2'}: domain = 'education'
    elif w & {'iban', 'mcc', 'kyc', 'pan'} and not w & {'metering', 'accessibility', 'marketing'}: domain = 'finance'
    elif w & {'metering', 'kwh', 'gsrn', 'heating'}: domain = 'energy'
    elif w & {'upn', 'hostname', 'qtype', 'mitre', 'smtp'}: domain = 'cyber'
    else: domain = dataset
    aggregate = bool(w & {'count', 'counts', 'visits', 'total'}) and not bool(w & {'payment', 'patient', 'student', 'customer', 'upn', 'mac'})
    infrastructure = bool(tt & {'stops', 'stations', 'sensors', 'locations', 'weather', 'geoip'})
    person = bool(w & (PERSON_KEYS | {'hetu', 'birth', 'holder', 'reporter', 'applicant', 'guardian1'}))
    public = (infrastructure and not person) or (aggregate and not bool(w & {'diagnosis', 'sex', 'age'}))
    identity = bool(w & {'birth', 'hetu', 'given', 'surname', 'guardian1', 'holder', 'customer'}) and not timestamped
    return TableContext(table, set(df.columns), w, domain, timestamped, public, aggregate, identity, _primary_key(df))

def _valid_ip(v):
    try:
        ipaddress.ip_network(v, strict=False) if '/' in v else ipaddress.ip_address(v)
        return True
    except ValueError:
        return False

def _subtype(c, ctx):
    ranked = score_column(c)
    # Format alone is insufficient for checksum-bearing identity codes. Keep
    # malformed values protected when the header supplies unambiguous semantics,
    # but do not call arbitrary similarly shaped strings validated identifiers.
    adjusted = []
    for st, score in ranked:
        if st == 'NATIONAL_ID' and not c.has('hetu', 'ssn', 'henkilotunnus'):
            score = max(c.share_fn(hetu_valid), .3 * c.share('hetu'))
        elif st == 'IBAN' and not c.has('iban'):
            score = max(c.share_fn(iban_valid), .3 * score)
        elif st == 'IP_ADDRESS':
            score = c.share_fn(_valid_ip)
        adjusted.append((st, score))
    ranked = sorted(adjusted, key=lambda item: -item[1])
    subtype, confidence = ranked[0]
    reason = f'value/name judgers: {subtype}={confidence:.2f}; next {ranked[1][0]}={ranked[1][1]:.2f}'
    t, w = c.tok, ctx.words
    def pick(st, why, conf=.95): return st, conf, why
    # Schema evidence survives empty columns; strong value candidates remain below.
    if t & {'hetu', 'ssn', 'henkilotunnus'}: return pick('NATIONAL_ID', f'national identity-code header; {c.share_fn(hetu_valid):.0%} pass checksum')
    if 'iban' in t: return pick('IBAN', f'bank-account header; {c.share_fn(iban_valid):.0%} pass IBAN checksum')
    if t & {'phone', 'mobile', 'puhelin'}: return pick('PHONE', 'telephone field')
    if 'pan' in t or ('card' in t and t & {'masked', 'number'}): return pick('PAYMENT_CARD', 'payment-card semantics and checksum/masking evidence')
    if t & {'icd', 'icd10'}: return pick('DIAGNOSIS_CODE', 'ICD diagnosis field')
    if 'diagnosis' in t: return pick('HEALTH_DATA', 'diagnosis grouping describes a health fact')
    if 'birth' in t or 'dob' in t: return pick('BIRTH_DATE', 'birth-date field')
    if t & {'timestamp', 'ts', 'utc'} or c.share('datetime') > .8: return pick('TIMESTAMP', 'timestamp format/header')
    if 'password' in t and t & {'last', 'change', 'changed'}: return pick('DATE', 'password-change date rather than secret')
    if 'academic' in t and 'year' in t: return pick('DATE', 'academic-year period')
    if t & {'date', 'expiry', 'installed', 'since'} or (t & {'start', 'end'} and not c.numeric and c.share('date') > .8): return pick('DATE', 'calendar-date field')
    if 'sex' in t: return pick('SEX', 'sex category')
    if 'second' in t and 'language' in t: return pick('SOCIAL_DATA', 'second-language support indicates social background')
    if t & {'language', 'lang', 'kieli'}: return pick('LANGUAGE', 'language field')
    if t & {'postcode', 'postal', 'zip', 'district'}: return pick('POSTCODE', 'postal geography')
    if t & {'municipality', 'kunta', 'town'} or (t == {'city'} and not ctx.public): return pick('MUNICIPALITY', 'municipality of residence')
    if t & {'lat', 'lon', 'lng', 'latitude', 'longitude'}: return pick('GPS_COORDINATE', 'geographic-coordinate field')
    if 'age' in t: return pick('AGE', 'age or age band')
    if t & {'address', 'street', 'osoite'} and not t & {'ip', 'email', 'mac'}: return pick('STREET_ADDRESS', 'street-address semantics')
    if 'property' in t and c.id_name: return pick('PROPERTY_ID', 'property register identifier')
    if 'business' in t and c.id_name: return pick('ORG_NAME', 'business register identifier')
    if t & {'hostname', 'host'} or ('device' in t and 'name' in t): return pick('HOSTNAME', 'host/device name')
    if 'user' in t and 'agent' in t: return pick('USER_AGENT', 'client user-agent string')
    if 'mac' in t: return pick('MAC_ADDRESS', 'MAC address')
    if 'ip' in t or 'network' in t or ('answer' in t and c.share_fn(_valid_ip) > .5):
        if c.share_fn(_valid_ip) > .5 or 'ip' in t: return pick('IP_ADDRESS', f'network-address semantics; {c.share_fn(_valid_ip):.0%} validate as IPv4/IPv6/network')
    if t & {'domain', 'query'} and not c.numeric: return pick('URL', 'network destination/domain')
    if 'ssid' in t: return pick('OTHER', 'wireless network name')
    if t & {'sha256', 'sha1', 'md5', 'seq', 'sequence'}: return pick('OTHER', 'hash/sequence rather than personal identifier')
    if 'upn' in t or t & {'username', 'login'}: return pick('USERNAME' if ctx.timestamped else 'EMAIL', 'account activity identity' if ctx.timestamped else 'directory contact identity')
    if t & {'email', 'sender', 'recipients'} and not t & {'display', 'name'}: return pick('EMAIL', 'email-address field, including recipient lists')
    if 'ambulance' in t and 'unit' in t: return pick('DEVICE_ID', 'observable emergency-unit call sign')
    if 'ref' in t and 'range' in t: return pick('CATEGORY', 'test reference interval rather than a reference identifier')
    if c.id_name:
        if t & {'stop', 'station', 'sensor'}: return pick('LOCATION_NAME', 'foreign key denotes a public place')
        if 'vehicle' in t: return pick('OTHER', 'shared public-fleet identifier')
        if 'bike' in t: return pick('DEVICE_ID', 'shared bicycle identifier')
        for words, st in [({'student', 'learner'}, 'STUDENT_ID'), ({'staff', 'employee', 'agent', 'physician', 'teacher', 'author'}, 'EMPLOYEE_ID'), ({'meter', 'metering', 'gsrn'}, 'METER_ID'), ({'customer', 'client'}, 'CUSTOMER_ID'), ({'patient'}, 'PATIENT_ID'), ({'account', 'contract', 'reference'}, 'ACCOUNT_ID'), ({'device'}, 'DEVICE_ID')]:
            if t & words: return pick(st, f'{st.lower()} schema semantics')
        if 'card' in t and 'ref' not in t: return pick('CARD_ID', 'travel-card identifier')
        if 'campaign' in t: return pick('CATEGORY', 'security campaign category')
        return pick('RECORD_ID', 'row/foreign identifier schema')
    if t & {'stop', 'station', 'sensor', 'park', 'office', 'country', 'city', 'location', 'area'} and not c.numeric: return pick('LOCATION_NAME', 'location or infrastructure name')
    if 'name' in t and ctx.public and w & {'lat', 'lon'}: return pick('LOCATION_NAME', 'name of public infrastructure')
    if t & {'occupation', 'job'} or ('role' in t and not c.id_name): return pick('OCCUPATION', 'occupation/job-role category')
    if t & {'school', 'employer', 'department', 'organisation', 'organization', 'org', 'merchant'} and not t & {'city', 'country'}: return pick('ORG_NAME', 'organisation semantics')
    if 'to' in t and 'name' in t and 'iban' in w: return pick('ORG_NAME', 'mixed person/organisation financial-counterparty field')
    if t & {'name', 'names', 'surname', 'officer', 'display'} and not t & {'test', 'course', 'subject', 'file', 'attachment', 'rule', 'process'}: return pick('PERSON_NAME', 'person-name schema and lexical evidence')
    if t & {'note', 'notes', 'text', 'complaint', 'description', 'message', 'command', 'path', 'attachment', 'attachments', 'subject', 'response', 'resolution', 'title'} and not t & {'id', 'type', 'code', 'name', 'scale'}:
        if 'title' not in t or 'job' not in t: return pick('FREE_TEXT', 'unstructured narrative')
    if 'attachment' in t and 'names' in t: return pick('FREE_TEXT', 'attachment filename list')
    if t & {'special', 'medical', 'accessibility', 'excused', 'triage', 'disposition', 'readmit', 'los', 'abnormal'} and t & {'support', 'device', 'needs', 'hours', 'triage', 'disposition', 'readmit', 'los', 'abnormal'}: return pick('HEALTH_DATA', 'health/support outcome')
    if ctx.domain == 'health' and t & {'value', 'result'}: return pick('HEALTH_DATA', 'clinical result')
    if ctx.domain == 'education' and t & {'programme', 'program', 'class', 'course', 'subject', 'grade', 'points', 'unexcused', 'arrivals', 'status'} and not t & {'max', 'scale', 'credits'}: return pick('EDUCATION_DATA', 'education participation or outcome')
    if 'pep' in t: return pick('OTHER', 'politically exposed person status')
    if t & {'income', 'salary', 'kyc', 'default', 'debt', 'cost', 'fee', 'balance'} or ('payment' in t and t & {'late', 'plan'}): return pick('FINANCIAL_DATA', 'financial status or amount')
    if 'amount' in t: return pick('FINANCIAL_DATA' if ctx.domain == 'finance' else 'MEASUREMENT', 'transaction amount')
    if t & {'duration', 'seconds'} or ('time' in t and t & {'s', 'sec', 'min', 'ms'}): return pick('DURATION', 'elapsed duration')
    if c.numeric and t & {'count', 'visits', 'total', 'sum'}: return pick('AGGREGATE', 'aggregate count')
    if t & {'type', 'status', 'method', 'flag', 'quality', 'code', 'period', 'scale', 'level', 'category', 'risk', 'line', 'registered', 'consent', 'enabled', 'resolved', 'label', 'decision', 'direction', 'sentiment', 'intent', 'channel', 'term', 'zone'}: return pick('CATEGORY', 'categorical code/state')
    if t & {'test', 'ref', 'unit'} and not c.numeric: return pick('CATEGORY', 'test definition/reference category')
    return subtype, max(0., min(1., confidence)), reason

def _role(c, ctx, st, target):
    t, w = c.tok, ctx.words
    if c.name == ctx.primary: return 'record_key', 'complete unique row key'
    if ctx.public: return 'non_sensitive', 'public infrastructure/weather/aggregate reference table'
    if st in DIRECT: return 'direct_identifier', 'direct identity/contact value'
    if st == 'STREET_ADDRESS':
        role = 'quasi_identifier' if 'reporter' in w and not w & {'applicant', 'birth', 'hetu'} else 'direct_identifier'
        return role, 'issue location' if role == 'quasi_identifier' else 'person/property address'
    if st in TECHNICAL:
        if t & {'bike', 'vehicle'}: return 'non_sensitive', 'public shared fleet asset'
        if st == 'EMPLOYEE_ID' and ctx.identity: return 'direct_identifier', 'directory employee identity'
        if t & {'learner'} or (t & {'customer', 'contract'} and 'number' in t): return 'direct_identifier', 'external personal/account identifier'
        if st == 'DEVICE_ID' and 'ambulance' in t: return 'quasi_identifier', 'observable emergency-unit call sign'
        return 'technical_identifier', 'linked person/device/account key' + (f' referencing {target.table}' if target else '')
    if st == 'URL': return ('free_text', 'full URL can contain identifiers/query text') if 'url' in t or c.share('url') > .8 else ('quasi_identifier', 'observed network destination')
    if st == 'FREE_TEXT':
        template = t & {'title', 'resolution'} and c.nu <= 30 and c.mean_len < 100
        return ('non_sensitive', 'finite operational template vocabulary') if template else ('free_text', 'unstructured narrative may contain personal information')
    if st == 'ORG_NAME' and ('merchant' in t or ('to' in t and 'name' in t)): return 'sensitive_attribute', 'counterparty reveals spending/recipient behaviour'
    if st == 'ORG_NAME' and 'business' in t and c.id_name: return 'technical_identifier', 'business register identity'
    if st == 'EDUCATION_DATA': return ('quasi_identifier', 'course/class membership identifies learner') if t & {'course', 'subject', 'programme', 'program', 'class'} else ('sensitive_attribute', 'individual educational outcome')
    if st == 'FINANCIAL_DATA':
        if 'fee' in t: return 'non_sensitive', 'standard service/parking fee'
        if 'amount' in t: return 'quasi_identifier', 'observable transaction amount useful for linkage'
        return 'sensitive_attribute', 'individual financial circumstance'
    if st in SENSITIVE: return 'sensitive_attribute', 'individual protected fact'
    if st == 'MEASUREMENT':
        if ctx.domain == 'health' and t & {'bp', 'systolic', 'diastolic', 'heart', 'pulse', 'resp', 'temp', 'spo2', 'pain', 'bmi'}: return 'sensitive_attribute', 'clinical vital measurement'
        if 'kwh' in t and w & {'metering', 'meter'}: return 'sensitive_attribute', 'household meter consumption'
        if t & {'floor', 'solar'}: return 'quasi_identifier', 'observable property feature'
    if st == 'DATE' and {'academic', 'year'} <= t: return 'non_sensitive', 'shared academic-year period'
    if st == 'MUNICIPALITY' and ('reporter' in w or 'applicant' in w): return 'non_sensitive', 'municipal service jurisdiction'
    if st == 'OCCUPATION' and 'author' in t: return 'non_sensitive', 'operational author-role vocabulary'
    if st in QUASI: return 'quasi_identifier', 'person-linked demographic/time/place circumstance'
    if st == 'CATEGORY':
        if 'mcc' in t or (t == {'category'} and 'url' in w): return 'sensitive_attribute', 'browsing/spending category'
        if t & {'arrival', 'heating', 'charger', 'shift', 'currency'} or t == {'line'} or t == {'fare', 'product'}: return 'quasi_identifier', 'observable circumstance useful for linkage'
        if 'card' in t and 'type' in t and 'holder' in w: return 'quasi_identifier', 'personal travel-card entitlement'
    if 'ssid' in t: return 'quasi_identifier', 'wireless network reveals previous locations'
    if 'pep' in t: return 'sensitive_attribute', 'political exposure status'
    return 'non_sensitive', 'operational/public measurement or category'

def _kind(c, st, role):
    if st == 'DEVICE_ID' and 'ambulance' in c.tok: return 'code'
    if role == 'record_key' or c.id_name and not c.tok & {'ref'} or st in TECHNICAL | {'NATIONAL_ID', 'IBAN', 'PAYMENT_CARD', 'LICENSE_PLATE', 'PROPERTY_ID'} or c.tok & {'sha256', 'sha1', 'md5'}: return 'identifier'
    if st == 'PERSON_NAME': return 'name'
    if st in {'EMAIL', 'PHONE', 'USERNAME'}: return 'contact'
    if st in {'DATE', 'TIMESTAMP', 'BIRTH_DATE'}: return 'temporal'
    if st in {'POSTCODE', 'MUNICIPALITY', 'GPS_COORDINATE', 'STREET_ADDRESS'}: return 'location'
    if st == 'LOCATION_NAME': return 'location' if c.tok & {'id', 'stop', 'station', 'sensor', 'park', 'office', 'geo', 'merchant', 'area'} else 'categorical'
    if st == 'AGGREGATE': return 'aggregate'
    if st == 'SECRET': return 'secret'
    if st == 'FREE_TEXT' or st == 'URL' and role == 'free_text' or 'ssid' in c.tok: return 'text'
    if st == 'DIAGNOSIS_CODE' or c.tok & {'code', 'mcc'} and st != 'ORG_NAME': return 'code'
    if st in {'MEASUREMENT', 'DURATION'}: return 'numerical'
    if st == 'OTHER' and c.numeric: return 'numerical'
    if st in SENSITIVE and c.tok & {'value', 'points', 'hours', 'minutes', 'count', 'cost', 'amount'}: return 'numerical'
    if st in SENSITIVE and c.numeric and not c.tok & {'grade', 'triage', 'flag', 'status', 'risk', 'support', 'priority', 'readmit'}: return 'numerical'
    return 'categorical'

def detect_tables(tables: Mapping[str, pd.DataFrame], dataset: str = '') -> pd.DataFrame:
    """Classify in-memory tables using only their schema and values."""
    contexts = {name: _context(df, name, dataset) for name, df in tables.items()}
    keys = {}
    for ctx in contexts.values():
        if ctx.primary is not None: keys.setdefault(ctx.primary, []).append(ctx)
    rows = []
    for table, df in tables.items():
        ctx = contexts[table]
        for i, name in enumerate(df.columns):
            c = Col(df[name], name, table, ctx.domain, i, ctx.timestamped)
            st, confidence, evidence = _subtype(c, ctx)
            target = None
            for candidate in keys.get(name, []):
                if candidate.table == table or not c.n:
                    continue
                parent_values = set(_present_values(tables[candidate.table][name]))
                # Sampled exports need not contain the full referenced entity
                # population. A shared header plus observed value containment
                # confirms the relationship without relying on a schema file.
                overlap = float(c.vals.isin(parent_values).mean())
                if overlap >= .5:
                    target = candidate
                    evidence += f'; {overlap:.0%} sampled values found in {candidate.table}.{name}'
                    break
            if name == ctx.primary:
                if st not in {'CUSTOMER_ID', 'STUDENT_ID', 'CARD_ID'} or st == 'CUSTOMER_ID' and 'customer_number' in ctx.columns: st = 'RECORD_ID'
            role, why = _role(c, ctx, st, target)
            rows.append(dict(dataset=dataset, table=table, column=name, privacy_role=role, data_kind=_kind(c, st, role), subtype=st, confidence=round(confidence, 3), evidence=f'{evidence}; {why}'))
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)

if __name__ == '__main__':  # python3 solution/detector.py data/unseen
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('folder', type=Path)
    folder = ap.parse_args().folder
    tables = {f.stem: pd.read_csv(f, dtype=str, keep_default_na=False, na_values=['']) for f in sorted(folder.glob('*.csv'))}
    print(detect_tables(tables, folder.name).drop(columns='evidence').to_string(index=False))
