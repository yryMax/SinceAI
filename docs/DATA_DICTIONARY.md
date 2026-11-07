# Data dictionary

Generated from `metadata/field_catalog.csv`, which holds the same content in machine-readable form. Roles and subtypes follow `metadata/taxonomy.md`. Read every CSV with `dtype=str` first, because identifiers such as phone numbers, postcodes and IDs lose leading zeros or `+` signs when parsed as numbers.

## health

### health / ed_visits

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `visit_id` | record_key | RECORD_ID |  | Visit identifier ED25-NNNNNN |
| `patient_hetu` | direct_identifier | NATIONAL_ID |  | Finnish personal identity code (synthetic, individual number 900-999) |
| `patient_name` | direct_identifier | PERSON_NAME |  | Patient name, 'Lastname Given names' |
| `date_of_birth` | quasi_identifier | BIRTH_DATE |  | Date of birth |
| `sex` | quasi_identifier | SEX |  | M/F |
| `phone` | direct_identifier | PHONE |  | Patient mobile phone, mixed formats |
| `home_address` | direct_identifier | STREET_ADDRESS |  | Street address |
| `postcode` | quasi_identifier | POSTCODE |  | Home postcode (real Southwest Finland postcodes) |
| `municipality` | quasi_identifier | MUNICIPALITY |  | Home municipality |
| `arrival_ts` | quasi_identifier | TIMESTAMP |  | Arrival time (local) |
| `arrival_mode` | quasi_identifier | CATEGORY |  | walk-in / ambulance / helicopter / police |
| `ambulance_unit` | quasi_identifier | DEVICE_ID |  | Ambulance unit call sign AU-<base>-NN or MEDHELI-N |
| `triage` | sensitive_attribute | HEALTH_DATA | yes | Finnish ABCDE triage (A most urgent) |
| `chief_complaint` | free_text | FREE_TEXT | yes | Short free-text reason for visit (fi/sv/en) |
| `icd10_primary` | sensitive_attribute | DIAGNOSIS_CODE | yes | Primary ICD-10 diagnosis |
| `icd10_secondary` | sensitive_attribute | DIAGNOSIS_CODE | yes | Up to two secondary ICD-10 codes, pipe-separated |
| `systolic_bp` | sensitive_attribute | MEASUREMENT | yes | Systolic blood pressure mmHg |
| `diastolic_bp` | sensitive_attribute | MEASUREMENT | yes | Diastolic blood pressure mmHg |
| `heart_rate` | sensitive_attribute | MEASUREMENT | yes | Heart rate /min |
| `resp_rate` | sensitive_attribute | MEASUREMENT | yes | Respiratory rate /min |
| `temp_c` | sensitive_attribute | MEASUREMENT | yes | Body temperature °C |
| `spo2` | sensitive_attribute | MEASUREMENT | yes | Oxygen saturation % |
| `pain_nrs` | sensitive_attribute | MEASUREMENT | yes | Pain 0-10 |
| `attending_physician_id` | technical_identifier | EMPLOYEE_ID |  | Staff id of attending physician |
| `attending_physician_name` | direct_identifier | PERSON_NAME |  | Attending physician name |
| `discharge_ts` | quasi_identifier | TIMESTAMP |  | Discharge / departure time |
| `los_minutes` | sensitive_attribute | HEALTH_DATA | yes | Length of stay in minutes |
| `disposition` | sensitive_attribute | HEALTH_DATA | yes | home / admitted_ward / icu / transfer / died / left_without_being_seen / cancelled_duplicate |
| `readmit_30d` | sensitive_attribute | HEALTH_DATA | yes | 1 if the same patient returned within 30 days |

### health / lab_results

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `lab_id` | record_key | RECORD_ID |  | Lab result identifier |
| `visit_id` | technical_identifier | RECORD_ID |  | Foreign key to ed_visits |
| `test_code` | non_sensitive | CATEGORY |  | Finnish-style lab code (e.g. P-CRP) |
| `test_name` | non_sensitive | CATEGORY |  | Test name in English |
| `value` | sensitive_attribute | HEALTH_DATA | yes | Result; numeric for quantitative tests, POS/NEG for PCR, '<3'/'<5' below detection |
| `unit` | non_sensitive | CATEGORY |  | Unit |
| `ref_range` | non_sensitive | CATEGORY |  | Reference range |
| `abnormal_flag` | sensitive_attribute | HEALTH_DATA | yes | H / L / A (abnormal qualitative) / blank |
| `sampled_ts` | quasi_identifier | TIMESTAMP |  | Sample time |

### health / clinical_notes

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `note_id` | record_key | RECORD_ID |  | Note identifier |
| `visit_id` | technical_identifier | RECORD_ID |  | Foreign key to ed_visits |
| `note_type` | non_sensitive | CATEGORY |  | physician / nurse_triage |
| `author_staff_id` | technical_identifier | EMPLOYEE_ID |  | Author staff id |
| `author_name` | direct_identifier | PERSON_NAME |  | Author name |
| `written_ts` | quasi_identifier | TIMESTAMP |  | Time written |
| `language` | quasi_identifier | LANGUAGE |  | fi / sv / en |
| `note_text` | free_text | FREE_TEXT | yes | ED note (Tulosyy / Esitiedot / Nykytila / Status / Arvio) |

### health / published_weekly_stats

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `stat_id` | record_key | RECORD_ID |  | Row id |
| `week` | quasi_identifier | DATE |  | ISO week of arrival |
| `municipality` | quasi_identifier | MUNICIPALITY |  | Home municipality |
| `age_band` | quasi_identifier | AGE |  | 10-year age band |
| `sex` | quasi_identifier | SEX |  | M/F |
| `diagnosis_group` | sensitive_attribute | HEALTH_DATA | yes | Diagnosis group of primary ICD-10 |
| `visits` | non_sensitive | AGGREGATE |  | Number of visits |

## mobility

### mobility / stops

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `stop_id` | record_key | RECORD_ID |  | Stop identifier |
| `name` | non_sensitive | LOCATION_NAME |  | Stop name (Finnish), usually a street name |
| `name_sv` | non_sensitive | LOCATION_NAME |  | Swedish stop name where the municipality is bilingual |
| `lat` | non_sensitive | GPS_COORDINATE |  | Stop latitude (synthetic placement) |
| `lon` | non_sensitive | GPS_COORDINATE |  | Stop longitude (synthetic placement) |
| `postcode` | non_sensitive | POSTCODE |  | Postcode area the stop lies in |
| `municipality` | non_sensitive | MUNICIPALITY |  | Municipality |
| `district` | non_sensitive | POSTCODE |  | District key (= nearest postcode centroid) |
| `area` | non_sensitive | LOCATION_NAME |  | Coarse area: municipality + 3-digit postcode prefix (used by OD tasks) |
| `zone` | non_sensitive | CATEGORY |  | Fare zone A/B |
| `lines` | non_sensitive | CATEGORY |  | Day lines serving the stop, pipe-separated |

### mobility / bike_stations

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `station_id` | record_key | RECORD_ID |  | Bike parking zone id |
| `name` | non_sensitive | LOCATION_NAME |  | Zone name |
| `lat` | non_sensitive | GPS_COORDINATE |  | Zone centre latitude |
| `lon` | non_sensitive | GPS_COORDINATE |  | Zone centre longitude |
| `capacity` | non_sensitive | MEASUREMENT |  | Nominal capacity |

### mobility / cards

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `card_id` | record_key | CARD_ID |  | Printed 16-digit travel card number (Luhn-valid). Also the join key to taps. |
| `card_type` | quasi_identifier | CATEGORY | yes | Fare category: adult, child, student, senior, disability_discount |
| `registered` | non_sensitive | CATEGORY |  | Personalised card (holder registered) yes/no |
| `issued_date` | quasi_identifier | DATE |  | Card issue date |
| `holder_name` | direct_identifier | PERSON_NAME |  | Registered holder name |
| `holder_birth_date` | quasi_identifier | BIRTH_DATE |  | Holder birth date (for discount eligibility) |
| `holder_email` | direct_identifier | EMAIL |  | Holder email |
| `holder_phone` | direct_identifier | PHONE |  | Holder phone, mixed formats |
| `holder_postcode` | quasi_identifier | POSTCODE |  | Holder home postcode |
| `status` | non_sensitive | CATEGORY |  | active / replaced |

### mobility / taps

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `tap_id` | record_key | RECORD_ID |  | Boarding event id |
| `card_id` | technical_identifier | CARD_ID |  | Card number of the boarding |
| `ts` | quasi_identifier | TIMESTAMP |  | Boarding time (local, seconds) |
| `stop_id` | quasi_identifier | LOCATION_NAME |  | Boarding stop; blank = GPS fault (~3 %) |
| `line` | quasi_identifier | CATEGORY |  | Line; N1-N4 are Friday/Saturday night lines |
| `direction` | non_sensitive | CATEGORY |  | Route direction 1/2 (lines run through the centre) |
| `vehicle_id` | non_sensitive | OTHER |  | Bus fleet number |
| `fare_product` | quasi_identifier | CATEGORY |  | season, value_*, transfer, double_tap |
| `amount_eur` | non_sensitive | MEASUREMENT |  | Amount charged |

### mobility / bike_trips

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `trip_id` | record_key | RECORD_ID |  | Trip id |
| `user_account` | direct_identifier | EMAIL |  | App account name |
| `bike_id` | non_sensitive | DEVICE_ID |  | Bike id |
| `start_ts` | quasi_identifier | TIMESTAMP |  | Trip start |
| `end_ts` | quasi_identifier | TIMESTAMP |  | Trip end |
| `start_lat` | quasi_identifier | GPS_COORDINATE |  | Start latitude, ~1 m precision |
| `start_lon` | quasi_identifier | GPS_COORDINATE |  | Start longitude |
| `end_lat` | quasi_identifier | GPS_COORDINATE |  | End latitude |
| `end_lon` | quasi_identifier | GPS_COORDINATE |  | End longitude |
| `start_station` | quasi_identifier | LOCATION_NAME |  | Parking zone at start (blank = outside zones) |
| `end_station` | quasi_identifier | LOCATION_NAME |  | Parking zone at end |
| `distance_m` | non_sensitive | MEASUREMENT |  | Ridden distance |
| `duration_s` | non_sensitive | DURATION |  | Duration in seconds |

## smart_city

### smart_city / sensors

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `sensor_id` | record_key | RECORD_ID |  | Sensor id |
| `location_name` | non_sensitive | LOCATION_NAME |  | Sensor location |
| `zone` | non_sensitive | CATEGORY |  | Zone type |
| `lat` | non_sensitive | GPS_COORDINATE |  | Sensor latitude |
| `lon` | non_sensitive | GPS_COORDINATE |  | Sensor longitude |
| `installed` | non_sensitive | DATE |  | Installation date |

### smart_city / wifi_probes

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `probe_id` | record_key | RECORD_ID |  | Probe record id |
| `sensor_id` | quasi_identifier | LOCATION_NAME |  | Detecting sensor |
| `ts` | quasi_identifier | TIMESTAMP |  | Probe time (seconds) |
| `mac` | technical_identifier | MAC_ADDRESS |  | Wi-Fi MAC address in the probe request |
| `rssi_dbm` | non_sensitive | MEASUREMENT |  | Signal strength |
| `ssid_probed` | quasi_identifier | OTHER |  | Network name in a directed probe (mostly blank) |

### smart_city / footfall_15min

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `count_id` | record_key | RECORD_ID |  | Row id |
| `sensor_id` | non_sensitive | LOCATION_NAME |  | Sensor |
| `interval_start` | non_sensitive | TIMESTAMP |  | Start of 15-min interval |
| `device_count` | non_sensitive | AGGREGATE |  | Distinct MACs seen in the interval; -1 = sensor outage |

### smart_city / anpr_parking

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `event_id` | record_key | RECORD_ID |  | Parking event id |
| `car_park` | quasi_identifier | LOCATION_NAME |  | Car park |
| `plate` | direct_identifier | LICENSE_PLATE |  | Registration plate read by the camera |
| `read_confidence` | non_sensitive | MEASUREMENT |  | ANPR read confidence |
| `entry_ts` | quasi_identifier | TIMESTAMP |  | Entry time |
| `exit_ts` | quasi_identifier | TIMESTAMP |  | Exit time (blank = still parked at period end) |
| `fee_eur` | non_sensitive | FINANCIAL_DATA |  | Fee charged |
| `payment_method` | non_sensitive | CATEGORY |  | card / app / permit / unpaid |
| `payment_card_masked` | direct_identifier | PAYMENT_CARD |  | Masked card number (first 6 + last 4) |
| `payer_phone` | direct_identifier | PHONE |  | Phone number of the parking-app account |

## energy

### energy / customers

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `customer_id` | record_key | CUSTOMER_ID |  | DSO customer number (contract holder). |
| `metering_point_id` | technical_identifier | METER_ID |  | 18-digit GSRN metering point ID (prefix 643 = Finland); joins customers to readings. |
| `customer_name` | direct_identifier | PERSON_NAME |  | Contract holder name; order varies ('Last Given names' or 'First Last'). |
| `hetu` | direct_identifier | NATIONAL_ID |  | Finnish personal identity code (synthetic, temporary range 900-999); blank for ~12 %. |
| `birth_date` | quasi_identifier | BIRTH_DATE |  | Filled only when hetu is missing. |
| `street_address` | direct_identifier | STREET_ADDRESS |  | Supply address (= home address), incl. staircase/apartment. |
| `postcode` | quasi_identifier | POSTCODE |  | Postcode of the supply address (real GeoNames postcode). |
| `municipality` | quasi_identifier | MUNICIPALITY |  | Municipality of the supply address. |
| `email` | direct_identifier | EMAIL |  | Invoice/contact e-mail (.example domains). |
| `phone` | direct_identifier | PHONE |  | Contact phone; several formats (+358…, 040 …). |
| `contract_type` | non_sensitive | CATEGORY |  | spot / fixed / time_of_use (night tariff). |
| `heating_type` | quasi_identifier | CATEGORY |  | Main heating: district, direct_electric, ground_source_heat_pump, air_to_water_heat_pump, oil_and_electric. |
| `floor_area_m2` | quasi_identifier | MEASUREMENT |  | Heated floor area (m²). |
| `main_fuse_a` | non_sensitive | MEASUREMENT |  | Main fuse size (A). |
| `ev_charger` | quasi_identifier | CATEGORY |  | Registered EV charger (yes/no). |
| `solar_pv_kw` | quasi_identifier | MEASUREMENT |  | Installed PV capacity (kW), 0 if none. |
| `payment_method` | non_sensitive | CATEGORY |  | e_invoice / direct_debit / email_invoice / paper_invoice. |
| `iban` | direct_identifier | IBAN |  | Bank account for direct debit (synthetic, bank id 9xx). |
| `late_payment_count` | sensitive_attribute | FINANCIAL_DATA |  | Late payments in the last 24 months. |
| `payment_plan` | sensitive_attribute | FINANCIAL_DATA |  | Active payment plan (true/false). |
| `medical_device_priority` | sensitive_attribute | HEALTH_DATA | yes | Customer registered life-supporting medical equipment (priority outage notification). |
| `contract_start` | quasi_identifier | DATE |  | Contract start date (≈ moving-in date). |
| `dso_notes` | free_text | FREE_TEXT | yes | Free-text operator notes (Finnish, Swedish, English). |

### energy / meter_readings_hourly

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `reading_id` | record_key | RECORD_ID |  | Row id of the hourly reading. |
| `metering_point_id` | technical_identifier | METER_ID |  | GSRN; foreign key to customers. |
| `ts` | quasi_identifier | TIMESTAMP |  | Start of the hour (local time, Europe/Helsinki; no DST change in this period). |
| `kwh` | sensitive_attribute | MEASUREMENT |  | Net energy taken from the grid during the hour (kWh, 3 decimals); blank when missing. |
| `quality` | non_sensitive | CATEGORY |  | '' = measured, E = estimated, M = missing, S = suspicious (meter swap). |

### energy / weather_hourly

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `obs_id` | record_key | RECORD_ID |  | Row id. |
| `ts` | non_sensitive | TIMESTAMP |  | Hour (local time). |
| `temperature_c` | non_sensitive | MEASUREMENT |  | SYNTHETIC outdoor temperature for the Turku area (not FMI observations); includes a cold spell 6-13 Jan 2026. |
| `wind_ms` | non_sensitive | MEASUREMENT |  | SYNTHETIC wind speed (m/s). |
| `cloud_oktas` | non_sensitive | MEASUREMENT |  | SYNTHETIC cloud cover (0-8 oktas). |

## finance

### finance / customers

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `customer_id` | record_key | CUSTOMER_ID |  | Bank customer number. |
| `hetu` | direct_identifier | NATIONAL_ID |  | Finnish personal identity code (synthetic, range 900-999). |
| `full_name` | direct_identifier | PERSON_NAME |  | All given names + surname (KYC). |
| `birth_date` | quasi_identifier | BIRTH_DATE |  | Date of birth (KYC). |
| `street_address` | direct_identifier | STREET_ADDRESS |  | Home address incl. apartment. |
| `postcode` | quasi_identifier | POSTCODE |  | Postcode. |
| `city` | quasi_identifier | MUNICIPALITY |  | Municipality. |
| `email` | direct_identifier | EMAIL |  | Personal e-mail (.example). |
| `phone` | direct_identifier | PHONE |  | Mobile phone (E.164). |
| `iban` | direct_identifier | IBAN |  | Customer's main account (synthetic, bank id 9xx). |
| `income_band` | sensitive_attribute | FINANCIAL_DATA |  | Declared annual gross income band. |
| `occupation` | quasi_identifier | OCCUPATION |  | Occupation group / life situation (KYC). |
| `employer` | quasi_identifier | ORG_NAME |  | Employer name (KYC). |
| `pep_flag` | sensitive_attribute | OTHER |  | Politically exposed person (AML). |
| `kyc_risk` | sensitive_attribute | FINANCIAL_DATA |  | AML/KYC risk rating. |
| `account_open_date` | quasi_identifier | DATE |  | Date the customer relationship began. |
| `preferred_language` | quasi_identifier | LANGUAGE |  | Service language fi/sv/en. |

### finance / cards

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `card_ref_id` | record_key | RECORD_ID |  | Card record id. |
| `customer_id` | technical_identifier | CUSTOMER_ID |  | Owner (FK customers). |
| `card_pan` | direct_identifier | PAYMENT_CARD |  | Primary account number (public test BINs, Luhn-valid). |
| `card_type` | non_sensitive | CATEGORY |  | debit / credit. |
| `issued_date` | quasi_identifier | DATE |  | Card issue date. |
| `expiry` | quasi_identifier | DATE |  | Expiry MM/YY. |
| `status` | non_sensitive | CATEGORY |  | active / closed_fraud. |

### finance / card_transactions

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `tx_id` | record_key | RECORD_ID |  | Transaction id. |
| `card_pan` | direct_identifier | PAYMENT_CARD |  | Card number used (FK cards). |
| `ts` | quasi_identifier | TIMESTAMP |  | Authorisation time (local, to the second). |
| `amount_eur` | quasi_identifier | FINANCIAL_DATA |  | Amount in EUR. |
| `original_amount` | quasi_identifier | FINANCIAL_DATA |  | Amount in merchant currency. |
| `currency` | quasi_identifier | CATEGORY |  | Merchant currency. |
| `merchant_name` | sensitive_attribute | ORG_NAME | yes | Merchant (fictional). |
| `mcc` | sensitive_attribute | CATEGORY | yes | ISO 18245 merchant category code. |
| `merchant_city` | quasi_identifier | LOCATION_NAME |  | Merchant city. |
| `merchant_country` | quasi_identifier | LOCATION_NAME |  | Merchant country (ISO 3166). |
| `channel` | non_sensitive | CATEGORY |  | chip / contactless / ecom. |
| `pos_lat` | quasi_identifier | GPS_COORDINATE |  | Merchant terminal latitude (card present). |
| `pos_lon` | quasi_identifier | GPS_COORDINATE |  | Merchant terminal longitude. |
| `device_id` | technical_identifier | DEVICE_ID |  | E-commerce device fingerprint (UUID). |
| `ip_address` | technical_identifier | IP_ADDRESS |  | Shopper IP (CGNAT 100.64/10; fraud from RFC 5737 ranges). |
| `is_fraud` | non_sensitive | CATEGORY |  | 1 = confirmed fraud (chargeback). |
| `fraud_type` | non_sensitive | CATEGORY |  | card_testing / cnp_cashout / account_takeover / skimming / lost_stolen. |

### finance / transfers

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `transfer_id` | record_key | RECORD_ID |  | Transfer id. |
| `booking_ts` | quasi_identifier | TIMESTAMP |  | Booking time. |
| `direction` | non_sensitive | CATEGORY |  | incoming / outgoing relative to the bank customer. |
| `from_iban` | direct_identifier | IBAN |  | Payer account. |
| `from_name` | direct_identifier | PERSON_NAME |  | Payer name (persons and organisations). |
| `to_iban` | direct_identifier | IBAN |  | Payee account (also LT/EE/LV for some outflows). |
| `to_name` | sensitive_attribute | ORG_NAME | yes | Payee name (persons and organisations). |
| `amount_eur` | quasi_identifier | FINANCIAL_DATA |  | Amount (EUR). |
| `reference_number` | technical_identifier | ACCOUNT_ID |  | Finnish creditor reference (check digit). |
| `message` | free_text | FREE_TEXT | yes | Payer's free-text message (fi/sv/en). |
| `transfer_type` | non_sensitive | CATEGORY |  | salary / pension / standing_order / e_invoice / loan_payment / sepa / instant. |

## cyber

### cyber / identity

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `identity_id` | record_key | RECORD_ID |  | Row key of the directory export. |
| `employee_id` | direct_identifier | EMPLOYEE_ID |  | HR employee number (MLX-#####). |
| `upn` | direct_identifier | EMAIL |  | User principal name = work e-mail firstname.lastname@meridian-logistics.example. |
| `display_name` | direct_identifier | PERSON_NAME |  | Full name. |
| `given_name` | direct_identifier | PERSON_NAME |  | First name. |
| `surname` | direct_identifier | PERSON_NAME |  | Surname. |
| `department` | quasi_identifier | ORG_NAME |  | Department. |
| `job_title` | quasi_identifier | OCCUPATION |  | Job title. |
| `manager_upn` | direct_identifier | EMAIL |  | Manager's UPN (reveals org chart). |
| `office` | quasi_identifier | LOCATION_NAME |  | Work site. |
| `work_pattern` | non_sensitive | CATEGORY |  | office / site / service. |
| `shift` | quasi_identifier | CATEGORY |  | Shift for site workers. |
| `laptop_hostname` | technical_identifier | HOSTNAME |  | Laptop hostname LT-<3 letters first><3 letters last>-####. |
| `mobile_phone` | direct_identifier | PHONE |  | Work mobile number (often the personal number). |
| `account_enabled` | non_sensitive | CATEGORY |  | Account status. |
| `last_password_change` | quasi_identifier | DATE |  | Date of last password change. |
| `employment_start` | quasi_identifier | DATE |  | Employment start date. |

### cyber / signin_logs

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `event_id` | record_key | RECORD_ID |  | Sign-in event id. |
| `ts_utc` | quasi_identifier | TIMESTAMP |  | Sign-in time (UTC). |
| `upn` | direct_identifier | USERNAME |  | Signing-in account. |
| `src_ip` | technical_identifier | IP_ADDRESS |  | Source IP (CGNAT home/mobile, office, hotel, hosting). |
| `geo_country` | quasi_identifier | LOCATION_NAME |  | Country of src_ip (synthetic geo database). |
| `geo_city` | quasi_identifier | LOCATION_NAME |  | City of src_ip. |
| `geo_lat` | quasi_identifier | GPS_COORDINATE |  | City latitude. |
| `geo_lon` | quasi_identifier | GPS_COORDINATE |  | City longitude. |
| `user_agent` | technical_identifier | USER_AGENT |  | Client user agent. |
| `client_app` | non_sensitive | CATEGORY |  | Application signed into. |
| `device_name` | technical_identifier | HOSTNAME |  | Device name (laptop hostname, kiosk, iPhone/Android). |
| `result` | non_sensitive | CATEGORY |  | success / failure / interrupted. |
| `failure_reason` | non_sensitive | CATEGORY |  | Error code and text. |
| `mfa_method` | non_sensitive | CATEGORY |  | MFA method. |
| `mfa_result` | non_sensitive | CATEGORY |  | MFA outcome (approved/denied/pending/timeout). |
| `risk_level` | non_sensitive | CATEGORY |  | Identity-protection risk level. |
| `correlation_id` | technical_identifier | RECORD_ID |  | Random correlation GUID (not linking). |
| `attack_label` | non_sensitive | CATEGORY |  | Ground-truth MITRE ATT&CK technique id(s) for synthetic attack events, '/'-separated; empty = benign. Self-assessment only. |
| `campaign_id` | non_sensitive | CATEGORY |  | Ground-truth campaign (C1 phishing chain, C2 password spray, C3 insider); empty = benign. |

### cyber / vpn_logs

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `event_id` | record_key | RECORD_ID |  | VPN event id. |
| `ts_utc` | quasi_identifier | TIMESTAMP |  | Event time (UTC). |
| `upn` | direct_identifier | USERNAME |  | VPN user. |
| `src_ip` | technical_identifier | IP_ADDRESS |  | Public source IP. |
| `geo_country` | quasi_identifier | LOCATION_NAME |  | Country of src_ip. |
| `geo_city` | quasi_identifier | LOCATION_NAME |  | City of src_ip. |
| `assigned_ip` | technical_identifier | IP_ADDRESS |  | Internal VPN address (10.30.0.0/16). |
| `action` | non_sensitive | CATEGORY |  | connect / disconnect. |
| `session_id` | technical_identifier | RECORD_ID |  | VPN session GUID. |
| `bytes_in` | non_sensitive | MEASUREMENT |  | Bytes received in session. |
| `bytes_out` | non_sensitive | MEASUREMENT |  | Bytes sent in session. |
| `client_version` | non_sensitive | CATEGORY |  | VPN client version. |
| `device_name` | technical_identifier | HOSTNAME |  | Client device name. |
| `attack_label` | non_sensitive | CATEGORY |  | Ground-truth MITRE ATT&CK technique id(s) for synthetic attack events, '/'-separated; empty = benign. Self-assessment only. |
| `campaign_id` | non_sensitive | CATEGORY |  | Ground-truth campaign (C1 phishing chain, C2 password spray, C3 insider); empty = benign. |

### cyber / proxy_logs

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `event_id` | record_key | RECORD_ID |  | Proxy event id. |
| `ts_utc` | quasi_identifier | TIMESTAMP |  | Request time (UTC). |
| `src_ip` | technical_identifier | IP_ADDRESS |  | Internal client IP (laptop or VPN address). |
| `upn` | direct_identifier | USERNAME |  | Authenticated proxy user. |
| `method` | non_sensitive | CATEGORY |  | HTTP method. |
| `url` | free_text | URL |  | Full URL including query string. |
| `domain` | quasi_identifier | URL |  | Destination domain. |
| `category` | sensitive_attribute | CATEGORY | yes | Web category. |
| `http_status` | non_sensitive | CATEGORY |  | HTTP status. |
| `bytes_sent` | non_sensitive | MEASUREMENT |  | Upload bytes. |
| `bytes_received` | non_sensitive | MEASUREMENT |  | Download bytes. |
| `user_agent` | technical_identifier | USER_AGENT |  | Client user agent. |
| `action` | non_sensitive | CATEGORY |  | allowed / blocked. |
| `attack_label` | non_sensitive | CATEGORY |  | Ground-truth MITRE ATT&CK technique id(s) for synthetic attack events, '/'-separated; empty = benign. Self-assessment only. |
| `campaign_id` | non_sensitive | CATEGORY |  | Ground-truth campaign (C1 phishing chain, C2 password spray, C3 insider); empty = benign. |

### cyber / dns_logs

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `event_id` | record_key | RECORD_ID |  | DNS event id. |
| `ts_utc` | quasi_identifier | TIMESTAMP |  | Query time (UTC). |
| `client_ip` | technical_identifier | IP_ADDRESS |  | Client internal IP. |
| `client_hostname` | technical_identifier | HOSTNAME |  | Client hostname. |
| `query` | quasi_identifier | URL |  | Queried name. |
| `qtype` | non_sensitive | CATEGORY |  | Record type. |
| `rcode` | non_sensitive | CATEGORY |  | Response code. |
| `answer` | technical_identifier | IP_ADDRESS |  | Resolved address. |
| `attack_label` | non_sensitive | CATEGORY |  | Ground-truth MITRE ATT&CK technique id(s) for synthetic attack events, '/'-separated; empty = benign. Self-assessment only. |
| `campaign_id` | non_sensitive | CATEGORY |  | Ground-truth campaign (C1 phishing chain, C2 password spray, C3 insider); empty = benign. |

### cyber / edr_alerts

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `alert_id` | record_key | RECORD_ID |  | EDR alert id. |
| `ts_utc` | quasi_identifier | TIMESTAMP |  | Alert time (UTC). |
| `hostname` | technical_identifier | HOSTNAME |  | Endpoint hostname. |
| `device_ip` | technical_identifier | IP_ADDRESS |  | Endpoint IP. |
| `upn` | direct_identifier | USERNAME |  | Logged-on user. |
| `severity` | non_sensitive | CATEGORY |  | Alert severity. |
| `rule_name` | non_sensitive | CATEGORY |  | Detection rule. |
| `mitre_technique` | non_sensitive | CATEGORY |  | Technique the EDR rule maps to (vendor mapping, not ground truth). |
| `process_name` | non_sensitive | CATEGORY |  | Process. |
| `command_line` | free_text | FREE_TEXT |  | Process command line. |
| `file_path` | free_text | FREE_TEXT |  | File path. |
| `sha256` | non_sensitive | OTHER |  | File/command hash (synthetic). |
| `analyst_verdict` | non_sensitive | CATEGORY |  | SOC triage verdict. |
| `attack_label` | non_sensitive | CATEGORY |  | Ground-truth MITRE ATT&CK technique id(s) for synthetic attack events, '/'-separated; empty = benign. Self-assessment only. |
| `campaign_id` | non_sensitive | CATEGORY |  | Ground-truth campaign (C1 phishing chain, C2 password spray, C3 insider); empty = benign. |

### cyber / email_gateway

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `message_id` | record_key | RECORD_ID |  | Gateway message id. |
| `ts_utc` | quasi_identifier | TIMESTAMP |  | Delivery time (UTC). |
| `direction` | non_sensitive | CATEGORY |  | inbound / outbound / internal. |
| `sender` | direct_identifier | EMAIL |  | Sender address. |
| `sender_display` | direct_identifier | PERSON_NAME |  | Sender display name. |
| `recipients` | direct_identifier | EMAIL |  | Recipient addresses, ';'-separated. |
| `subject` | free_text | FREE_TEXT | yes | Subject line. |
| `attachment_names` | free_text | FREE_TEXT |  | Attachment file names, ';'-separated. |
| `size_kb` | non_sensitive | MEASUREMENT |  | Message size. |
| `verdict` | non_sensitive | CATEGORY |  | Gateway verdict. |
| `spam_score` | non_sensitive | MEASUREMENT |  | Spam score. |
| `smtp_message_id` | technical_identifier | RECORD_ID |  | SMTP Message-ID header. |
| `attack_label` | non_sensitive | CATEGORY |  | Ground-truth MITRE ATT&CK technique id(s) for synthetic attack events, '/'-separated; empty = benign. Self-assessment only. |
| `campaign_id` | non_sensitive | CATEGORY |  | Ground-truth campaign (C1 phishing chain, C2 password spray, C3 insider); empty = benign. |

### cyber / incident_tickets

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `ticket_id` | record_key | RECORD_ID |  | Service-desk ticket id. |
| `created_utc` | quasi_identifier | TIMESTAMP |  | Creation time (UTC). |
| `reporter_upn` | direct_identifier | USERNAME |  | Reporter. |
| `reporter_name` | direct_identifier | PERSON_NAME |  | Reporter name. |
| `assignee_upn` | direct_identifier | USERNAME |  | IT staff assigned. |
| `category` | non_sensitive | CATEGORY |  | Ticket category. |
| `priority` | non_sensitive | CATEGORY |  | Priority. |
| `status` | non_sensitive | CATEGORY |  | Status. |
| `title` | non_sensitive | FREE_TEXT |  | Short title (templated). |
| `description` | free_text | FREE_TEXT |  | Free-text description (Finnish/English). |
| `resolution` | non_sensitive | FREE_TEXT |  | Resolution note. |
| `attack_label` | non_sensitive | CATEGORY |  | Ground-truth MITRE ATT&CK technique id(s) for synthetic attack events, '/'-separated; empty = benign. Self-assessment only. |
| `campaign_id` | non_sensitive | CATEGORY |  | Ground-truth campaign (C1 phishing chain, C2 password spray, C3 insider); empty = benign. |

### cyber / geoip_ranges

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `range_id` | record_key | RECORD_ID |  | Row key. |
| `network` | non_sensitive | IP_ADDRESS |  | CIDR block (documentation/shared ranges). |
| `country` | non_sensitive | LOCATION_NAME |  | Country code (synthetic assignment). |
| `city` | non_sensitive | LOCATION_NAME |  | City. |
| `lat` | non_sensitive | GPS_COORDINATE |  | City latitude. |
| `lon` | non_sensitive | GPS_COORDINATE |  | City longitude. |
| `organisation` | non_sensitive | ORG_NAME |  | Network owner (fictional). |
| `network_type` | non_sensitive | CATEGORY |  | residential / mobile / corporate / hotel / hosting / internal. |

## education

### education / students

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `student_id` | record_key | STUDENT_ID |  | School-system student number; first two digits are the start year. |
| `learner_id` | direct_identifier | STUDENT_ID |  | National learner number (fictional OID-style format 1.9.999.24.x). |
| `hetu` | direct_identifier | NATIONAL_ID |  | Finnish personal identity code (temporary range 900-999). |
| `first_names` | direct_identifier | PERSON_NAME |  | All given names. |
| `last_name` | direct_identifier | PERSON_NAME |  | Surname. |
| `birth_date` | quasi_identifier | BIRTH_DATE |  | Date of birth. |
| `sex` | quasi_identifier | SEX |  | Registered sex (M/F). |
| `home_language` | quasi_identifier | LANGUAGE |  | Registered mother tongue (ISO 639-1). |
| `street_address` | direct_identifier | STREET_ADDRESS |  | Home street address. |
| `postcode` | quasi_identifier | POSTCODE |  | Home postcode. |
| `municipality` | quasi_identifier | MUNICIPALITY |  | Home municipality. |
| `guardian1_name` | direct_identifier | PERSON_NAME |  | Guardian name (third party). |
| `guardian1_phone` | direct_identifier | PHONE |  | Guardian phone, as typed (mixed formats). |
| `guardian2_name` | direct_identifier | PERSON_NAME |  | Second guardian name. |
| `guardian2_phone` | direct_identifier | PHONE |  | Second guardian phone. |
| `school_code` | quasi_identifier | ORG_NAME |  | School code S01-S12. |
| `school_name` | quasi_identifier | ORG_NAME |  | School name (fictional). |
| `programme` | quasi_identifier | EDUCATION_DATA |  | Programme or vocational field. |
| `class_group` | quasi_identifier | EDUCATION_DATA |  | Homeroom group; encodes school and start year. |
| `start_date` | quasi_identifier | DATE |  | Start of studies. |
| `special_support` | sensitive_attribute | HEALTH_DATA | yes | Level of special support (none/intensified/special). |
| `finnish_as_second_language` | sensitive_attribute | SOCIAL_DATA |  | Studies Finnish as a second language (S2). |
| `status` | sensitive_attribute | EDUCATION_DATA |  | active / graduated / dropped_out. |
| `end_date` | quasi_identifier | DATE |  | Graduation or drop-out date. |

### education / course_grades

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `grade_id` | record_key | RECORD_ID |  | Grade row id. |
| `student_id` | technical_identifier | STUDENT_ID |  | Links to students. |
| `school_code` | quasi_identifier | ORG_NAME |  | School code. |
| `academic_year` | non_sensitive | DATE |  | Academic year. |
| `period` | non_sensitive | CATEGORY |  | Period 1-5 (general), term/unit order elsewhere. |
| `course_code` | quasi_identifier | EDUCATION_DATA | yes | Course/module code (approximate 2021 curriculum style). |
| `course_name` | quasi_identifier | EDUCATION_DATA | yes | Course name. |
| `credits` | non_sensitive | MEASUREMENT |  | Credits (opintopisteet / osaamispisteet); 0 for IB. |
| `grade` | sensitive_attribute | EDUCATION_DATA |  | Grade: 4-10, S/H, vocational 1-5, IB 1-7. |
| `grade_scale` | non_sensitive | CATEGORY |  | Scale of the grade. |
| `assessed_date` | quasi_identifier | DATE |  | Date grade was recorded. |
| `teacher_name` | direct_identifier | PERSON_NAME |  | Teacher (staff member, third party). |

### education / absences

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `absence_id` | record_key | RECORD_ID |  | Row id. |
| `student_id` | technical_identifier | STUDENT_ID |  | Links to students. |
| `academic_year` | non_sensitive | DATE |  | Academic year. |
| `term` | non_sensitive | CATEGORY |  | autumn / spring. |
| `excused_hours` | sensitive_attribute | HEALTH_DATA |  | Excused absence hours (mostly illness). |
| `unexcused_hours` | sensitive_attribute | EDUCATION_DATA |  | Unexcused absence hours. |
| `late_arrivals` | sensitive_attribute | EDUCATION_DATA |  | Count of late arrivals. |
| `school_code` | quasi_identifier | ORG_NAME |  | School code. |

### education / matriculation_results

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `exam_result_id` | record_key | RECORD_ID |  | Row id. |
| `student_id` | technical_identifier | STUDENT_ID |  | Links to students. |
| `exam_session` | quasi_identifier | DATE |  | Session, e.g. 2024K (spring) / 2024S (autumn). |
| `subject_code` | quasi_identifier | EDUCATION_DATA | yes | Exam subject code. |
| `subject_name` | quasi_identifier | EDUCATION_DATA | yes | Exam subject. |
| `raw_points` | sensitive_attribute | EDUCATION_DATA |  | Raw points. |
| `max_points` | non_sensitive | MEASUREMENT |  | Maximum points for the exam. |
| `grade` | sensitive_attribute | EDUCATION_DATA |  | Grade L/E/M/C/B/A/I. |
| `grade_points` | sensitive_attribute | EDUCATION_DATA |  | Grade as number 0-7. |
| `exam_language` | quasi_identifier | LANGUAGE |  | Exam language fi/sv. |

### education / counsellor_notes

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `note_id` | record_key | RECORD_ID |  | Note id. |
| `student_id` | technical_identifier | STUDENT_ID |  | Links to students. |
| `note_date` | quasi_identifier | DATE |  | Date of the meeting. |
| `author_name` | direct_identifier | PERSON_NAME |  | Staff member who wrote the note. |
| `author_role` | non_sensitive | OCCUPATION |  | Role of the author. |
| `language` | quasi_identifier | LANGUAGE |  | Language of the note (fi/sv/en). |
| `note_text` | free_text | FREE_TEXT | yes | Student-welfare / guidance note. Contains names of the student, guardians and staff, phone numbers, addresses, dates, ages and health information. |

## public_admin

### public_admin / service_requests

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `request_id` | record_key | RECORD_ID |  | Request id SR-<year>-<n>; '-D' suffix marks duplicate submissions. |
| `ts_created` | quasi_identifier | TIMESTAMP |  | Creation time (local). |
| `channel` | non_sensitive | CATEGORY |  | web / app / phone / email. |
| `category` | non_sensitive | CATEGORY |  | Request category (9 classes). |
| `language` | quasi_identifier | LANGUAGE |  | Language of the request (fi/sv/en). |
| `description` | free_text | FREE_TEXT | yes | Citizen's own description. Names of neighbours and relatives, addresses, phone numbers, emails, licence plates, health mentions. |
| `reporter_name` | direct_identifier | PERSON_NAME |  | Reporter name (optional). |
| `reporter_phone` | direct_identifier | PHONE |  | Reporter phone, as typed. |
| `reporter_email` | direct_identifier | EMAIL |  | Reporter email. |
| `reporter_account_id` | technical_identifier | ACCOUNT_ID |  | Persistent e-service account of a logged-in reporter. |
| `street_address` | quasi_identifier | STREET_ADDRESS |  | Address of the issue (often the reporter's own home or street). |
| `postcode` | quasi_identifier | POSTCODE |  | Postcode of the issue location. |
| `municipality` | non_sensitive | MUNICIPALITY |  | Municipality of the issue location. |
| `lat` | quasi_identifier | GPS_COORDINATE |  | Latitude of the issue (~25 m precision). |
| `lon` | quasi_identifier | GPS_COORDINATE |  | Longitude of the issue. |
| `handler_name` | direct_identifier | PERSON_NAME |  | Staff member handling the request. |
| `status` | non_sensitive | CATEGORY |  | closed / in_progress / forwarded / rejected / open. |
| `ts_closed` | quasi_identifier | TIMESTAMP |  | Closing time. |
| `response_text` | free_text | FREE_TEXT |  | City's reply: repeats reporter first name, addresses, plates, handler name/phone/email. |

### public_admin / building_permits

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `permit_id` | record_key | RECORD_ID |  | Permit id RL-<year>-<n>. |
| `submitted_date` | quasi_identifier | DATE |  | Application date. |
| `applicant_type` | non_sensitive | CATEGORY |  | private person / company. |
| `applicant_name` | direct_identifier | PERSON_NAME |  | Applicant (person or company name). |
| `applicant_hetu` | direct_identifier | NATIONAL_ID |  | Personal identity code of a private applicant. |
| `applicant_business_id` | technical_identifier | ORG_NAME |  | Business ID (Y-tunnus format, fictional range) of a company applicant. |
| `property_id` | direct_identifier | PROPERTY_ID |  | Property identifier (kiinteistötunnus format; municipality code first). |
| `street_address` | direct_identifier | STREET_ADDRESS |  | Property address. |
| `postcode` | quasi_identifier | POSTCODE |  | Postcode. |
| `municipality` | non_sensitive | MUNICIPALITY |  | Municipality. |
| `lat` | quasi_identifier | GPS_COORDINATE |  | Latitude (building). |
| `lon` | quasi_identifier | GPS_COORDINATE |  | Longitude (building). |
| `project_type` | non_sensitive | CATEGORY |  | Type of project. |
| `floor_area_m2` | quasi_identifier | MEASUREMENT |  | Floor area added (m²). |
| `cost_estimate_eur` | sensitive_attribute | FINANCIAL_DATA |  | Cost estimate (EUR). |
| `decision` | non_sensitive | CATEGORY |  | Decision. |
| `decision_date` | quasi_identifier | DATE |  | Decision date. |
| `case_officer` | direct_identifier | PERSON_NAME |  | Building inspector handling the case. |

## customer_service

### customer_service / customers

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `customer_id` | record_key | RECORD_ID |  | Row key of the customer extract. |
| `customer_number` | direct_identifier | CUSTOMER_ID |  | 8-digit customer number printed on invoices; customers read it out on calls. |
| `full_name` | direct_identifier | PERSON_NAME |  | Customer name (calling name + surname). |
| `hetu` | direct_identifier | NATIONAL_ID |  | Finnish personal identity code (synthetic, 900–999 range). |
| `street_address` | direct_identifier | STREET_ADDRESS |  | Street, house number and apartment. |
| `postcode` | quasi_identifier | POSTCODE |  | Postcode (real postcode, synthetic resident). |
| `city` | quasi_identifier | MUNICIPALITY |  | Municipality. |
| `email` | direct_identifier | EMAIL |  | Personal email (.example domains). |
| `phone` | direct_identifier | PHONE |  | Mobile number; ~8 % stored in non-E.164 formats. |
| `preferred_language` | quasi_identifier | LANGUAGE |  | Service language fi/sv/en. |
| `customer_since` | quasi_identifier | DATE |  | Contract start date. |
| `products` | non_sensitive | CATEGORY |  | Pipe-separated products. |
| `contract_number` | direct_identifier | ACCOUNT_ID |  | Contract number. |
| `payment_method` | non_sensitive | CATEGORY |  | Payment method. |
| `iban` | direct_identifier | IBAN |  | Bank account for direct debit (synthetic, bank id 9xx). |
| `marketing_consent` | non_sensitive | CATEGORY |  | Marketing consent flag. |
| `payment_default_flag` | sensitive_attribute | FINANCIAL_DATA |  | Customer has an overdue/defaulted payment record. |
| `accessibility_needs` | sensitive_attribute | HEALTH_DATA | yes | Service adjustment (hearing/visual). |

### customer_service / conversations

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `conversation_id` | record_key | RECORD_ID |  | Conversation key. |
| `customer_id` | technical_identifier | CUSTOMER_ID |  | Foreign key to customers. |
| `agent_id` | technical_identifier | EMPLOYEE_ID |  | Agent employee code. |
| `agent_name` | direct_identifier | PERSON_NAME |  | Agent's full name. |
| `channel` | non_sensitive | CATEGORY |  | chat / phone (ASR transcript) / email. |
| `language` | quasi_identifier | LANGUAGE |  | Conversation language. |
| `started_ts` | quasi_identifier | TIMESTAMP |  | Start time (local). |
| `intent` | non_sensitive | CATEGORY |  | Labelled contact reason (15 classes). |
| `sentiment` | non_sensitive | CATEGORY |  | Labelled customer sentiment. |
| `csat` | non_sensitive | MEASUREMENT |  | Survey score 1–5 (~58 % missing). |
| `resolved` | non_sensitive | CATEGORY |  | Resolved on first contact. |
| `handle_time_s` | non_sensitive | DURATION |  | Agent handling time in seconds. |
| `n_turns` | non_sensitive | MEASUREMENT |  | Number of turns. |
| `split` | non_sensitive | CATEGORY |  | train (spans public) / eval (spans private). |
| `agent_note` | free_text | FREE_TEXT | yes | Agent's CRM wrap-up note (mostly Finnish). |

### customer_service / turns

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `turn_id` | record_key | RECORD_ID |  | Turn key. |
| `conversation_id` | technical_identifier | RECORD_ID |  | Foreign key. |
| `seq` | non_sensitive | OTHER |  | Order within conversation. |
| `speaker` | non_sensitive | CATEGORY |  | customer / agent / bot. |
| `ts` | quasi_identifier | TIMESTAMP |  | Turn time. |
| `text` | free_text | FREE_TEXT | yes | Utterance text (chat, ASR transcript, or email body). |
