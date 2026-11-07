# Label taxonomy

Field labels are in `metadata/field_catalog.csv`, and free-text span labels are in `metadata/pii_spans/*.jsonl`. Use the same vocabulary in your detector output so that `pets-eval detect` and `pets-eval text` can score it.

## privacy_role (one per column)

| Role | Meaning | Examples |
|---|---|---|
| `direct_identifier` | Identifies a person on its own | name, HETU, email, phone, IBAN, card number, plate |
| `quasi_identifier` | Identifies in combination with others | birth date, age, sex, postcode, timestamps, coordinates, employer |
| `sensitive_attribute` | The protected fact itself (incl. GDPR Art. 9) | diagnosis, special support, income, union fee, fraud flag |
| `technical_identifier` | Device, network or system identifiers that single out a person or device | IP, MAC, hostname, card ID, metering point ID, user account |
| `free_text` | Unstructured text that may contain anything | clinical notes, chat turns, complaint descriptions |
| `record_key` | Row identifier with no meaning outside the table | visit_id, tx_id |
| `non_sensitive` | Safe to share as is in typical scenarios | product category, line number, weather |

## data_kind

`identifier`, `name`, `contact`, `temporal`, `location`, `categorical`, `numerical`, `text`, `aggregate`, `code`, `secret`

## subtype (columns)

```
PERSON_NAME, NATIONAL_ID, EMAIL, PHONE, STREET_ADDRESS, POSTCODE, MUNICIPALITY, GPS_COORDINATE,
LOCATION_NAME, BIRTH_DATE, AGE, SEX, LANGUAGE, NATIONALITY, IBAN, PAYMENT_CARD, CUSTOMER_ID,
ACCOUNT_ID, EMPLOYEE_ID, STUDENT_ID, PATIENT_ID, CARD_ID, DEVICE_ID, IP_ADDRESS, MAC_ADDRESS,
IMEI, HOSTNAME, USERNAME, URL, USER_AGENT, LICENSE_PLATE, PROPERTY_ID, METER_ID, TIMESTAMP,
DATE, DURATION, HEALTH_DATA, DIAGNOSIS_CODE, FINANCIAL_DATA, EDUCATION_DATA, SOCIAL_DATA,
OCCUPATION, ORG_NAME, MEASUREMENT, CATEGORY, AGGREGATE, SECRET, FREE_TEXT, RECORD_ID, OTHER
```

## Span labels (free text)

```
PERSON, NATIONAL_ID, EMAIL, PHONE, ADDRESS, LOCATION, DATE, AGE, IBAN, PAYMENT_CARD,
ACCOUNT_NUMBER, IP_ADDRESS, LICENSE_PLATE, ORG, URL, USERNAME, SECRET, HEALTH, DEVICE_ID, PROPERTY_ID
```

The full annotation rules are in `metadata/pii_span_guidelines.md`: span boundaries, spoken numbers, partial identifiers, and when health information counts as `HEALTH`.

## Detector output format (for `pets-eval detect`)

The output is a CSV with these columns: `dataset,table,column,privacy_role,subtype`. Give one row per column you classified. Columns you leave out count as wrong.
