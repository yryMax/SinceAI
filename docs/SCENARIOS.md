# Sharing scenarios

A PET choice is only right or wrong for a given recipient and purpose. Pick one scenario per dataset you work on and design for it. `pets-eval scorecard --scenario <ID>` runs the utility tasks that scenario needs.

The privacy targets below are suggestions to design against. They are not legal advice and not official thresholds.

## health

### HEALTH-S1: Secondary-use research in a controlled environment

- **Recipient:** University research group studying ED crowding and revisits
- **Purpose:** Analyse length of stay, revisits and diagnosis patterns
- **Trust level:** controlled_research
- **Threat model:** Researcher with access to public_directory, news_clips_health and social_posts_health; may try record linkage on QIs (age, sex, municipality, arrival time).
- **Legal context:** Pseudonymised data remains personal data (GDPR Recital 26); health data is Art. 9 special category. Comparable to a permit-based secure processing environment.
- **Utility tasks:** H-U2, H-U4, H-U6, H-U7, H-U8
- **Suggested privacy targets:** No direct identifiers; consistent pseudonymous patient key; QIs generalised so that k>=5 on (age band, sex, municipality, arrival week); free text redacted (recall >=0.95 on PERSON/PHONE/ADDRESS/NATIONAL_ID).
- **Notes:** Revisit analysis needs a stable patient pseudonym and joinable visit/lab keys.

### HEALTH-S2: Public weekly dashboard

- **Recipient:** Anyone (open data portal)
- **Purpose:** Weekly ED load, influenza-like illness and injury trends by age band and municipality
- **Trust level:** public
- **Threat model:** Any outsider with news clips, social posts and the public directory; can download every weekly release and difference them.
- **Legal context:** Must be anonymous in the GDPR sense (not reasonably re-identifiable). Small cells and repeated releases are the main risk.
- **Utility tasks:** H-U1, H-U8, H-DP
- **Suggested privacy targets:** Aggregate only; differential privacy with a stated mechanism and ε (e.g. ε<=1 per weekly release, documented composition) or suppression of cells <5 with complementary suppression.
- **Notes:** Compare against data/health/published_weekly_stats.csv, which is an example of what NOT to publish.

### HEALTH-S3: AI vendor training a triage-support model

- **Recipient:** External AI vendor under a data-processing agreement
- **Purpose:** Train a model predicting admission from triage-time information
- **Trust level:** contractual
- **Threat model:** Vendor staff or a breach; membership inference on synthetic data; memorised rare patients.
- **Legal context:** Processor relationship; data minimisation; synthetic data must not reproduce real records (check distance to closest record and membership inference).
- **Utility tasks:** H-U3, H-U5, H-U2
- **Suggested privacy targets:** Fully synthetic or strongly generalised training table without free text; membership-inference AUC close to 0.5 against holdout; no record closer to a real one than real records are to each other.
- **Notes:** Use holdout/health as non-members for membership-inference tests.

## mobility

### MOB-S1: Open data: public-transport origin-destination matrices

- **Recipient:** Anyone (municipal open data portal, CC BY 4.0)
- **Purpose:** Publish weekly OD flows between areas by hour band for journey planners, researchers and citizens.
- **Trust level:** public
- **Threat model:** Any outsider with public_directory, social_checkins and fitness_app_leak; can see a neighbour at a stop.
- **Legal context:** Only anonymous data may be published openly (GDPR Recital 26). Pseudonymised card ids are personal data.
- **Utility tasks:** MOB-U1, MOB-U2, MOB-U3
- **Suggested privacy targets:** No row-level data; no card ids; suppress or noise OD cells < 10 trips; consider ε-DP counts per release.
- **Notes:** Taps are boardings only; destinations require trip chaining before aggregation.

### MOB-S2: Urban planning consultancy: row-level journeys under contract

- **Recipient:** Planning consultancy (processor under a data processing agreement)
- **Purpose:** Redesign of the bus network: transfers, commuting corridors, peak loads.
- **Trust level:** contractual
- **Threat model:** Curious analyst with public_directory + social_checkins; must not be able to single out riders.
- **Legal context:** Pseudonymised data is still personal data; data minimisation and purpose limitation apply (GDPR Art. 5, 28).
- **Utility tasks:** MOB-U1, MOB-U2, MOB-U4, MOB-U5
- **Suggested privacy targets:** Keyed (HMAC) card pseudonyms rotated per week; no holder fields; times rounded to 5-15 min; trajectory unicity < 5 % with 4 known points.
- **Notes:** Linking trips of the same card within a day is needed for transfers; across weeks it mostly adds risk.

### MOB-S3: Academic research on mobility and bikes

- **Recipient:** University research group (controlled research environment)
- **Purpose:** Study mode choice between bus and city bike, weather effects, commuting distances.
- **Trust level:** controlled_research
- **Threat model:** Researcher with all public adversary files; private evaluation adds colleague knowledge (employer + arrival time).
- **Legal context:** Scientific research safeguards (GDPR Art. 89); pseudonymisation expected; publication of results must be anonymous.
- **Utility tasks:** MOB-U4, MOB-U6, MOB-U7, MOB-U8
- **Suggested privacy targets:** No email-like accounts; GPS start/end snapped to ≥250 m grid or zones; k ≥ 5 on (home area, work area, card type).
- **Notes:** Bike GPS end points near homes are the main re-identification risk.

## smart_city

### CITY-S1: Open data: city-centre footfall

- **Recipient:** Anyone (open data portal)
- **Purpose:** Publish hourly footfall by zone for businesses, events and citizens.
- **Trust level:** public
- **Threat model:** Outsider with public plate_sightings and knowledge of when a neighbour walks home.
- **Legal context:** MAC addresses are personal data (online identifiers, GDPR Recital 30); only anonymous aggregates can be open data.
- **Utility tasks:** CITY-U1, CITY-U5
- **Suggested privacy targets:** Hourly zone-level counts only; suppress or noise counts < 5 (night-time); no MACs, no SSIDs.
- **Notes:** Counting distinct randomised MACs over-counts people; say so in the release notes.

### CITY-S2: Share with the city-centre retail association

- **Recipient:** Retail association (contract, marketing analytics)
- **Purpose:** Dwell time, repeat visits, Black Friday and Christmas market effects, parking demand.
- **Trust level:** contractual
- **Threat model:** Association member with its own loyalty-app device list (private adversary) and plate sightings.
- **Legal context:** Re-identifying visitors for marketing would need a new lawful basis; minimise and pseudonymise (GDPR Art. 5, 6, 25).
- **Utility tasks:** CITY-U1, CITY-U2, CITY-U3, CITY-U4, CITY-U5, CITY-U6
- **Suggested privacy targets:** Daily-rotating keyed pseudonyms for MACs and plates; drop SSIDs and payment fields; coarsen times to 15 min.
- **Notes:** Repeat-visitor share needs linkage across days; consider computing it inside the controller and sharing the result.

### CITY-S3: Request from police / parking enforcement

- **Recipient:** Police or parking enforcement unit
- **Purpose:** A request for all plates and payment details at P-Riverside over two weeks, 'for an investigation'.
- **Trust level:** internal
- **Threat model:** Function creep: data collected for parking fees reused for surveillance.
- **Legal context:** Purpose limitation (GDPR Art. 5(1)(b)); disclosures to authorities need a specific legal basis and are assessed case by case (Law Enforcement Directive). Not legal advice.
- **Utility tasks:** CITY-U3
- **Suggested privacy targets:** Show what a minimal, case-specific disclosure would contain versus the bulk request; log the disclosure.
- **Notes:** A good demo explains why the PET answer here is mostly 'share less', not 'transform more'.

## energy

### ENERGY-S1: Open data: neighbourhood electricity load

- **Recipient:** Anyone (municipal open-data portal)
- **Purpose:** Urban energy planning, journalism, research on heating transition.
- **Trust level:** public
- **Threat model:** Public: vacation_posts + public_directory; neighbours who know their own consumption (differencing).
- **Legal context:** Only anonymous information may be published; aggregated small areas with few households can still be personal data.
- **Utility tasks:** ENERGY-U1, ENERGY-U2, ENERGY-U3
- **Suggested privacy targets:** Aggregate ≥10 metering points per cell; no individual series; consider DP noise on hourly sums (state ε).
- **Notes:** Weather table is public context.

### ENERGY-S2: Row-level hourly data to a flexibility aggregator

- **Recipient:** Demand-response aggregator (processor under contract)
- **Purpose:** Identify flexible loads (heat pumps, EV) and forecast them.
- **Trust level:** contractual
- **Threat model:** Curious insider at the recipient with public_directory and vacation_posts; private: neighbour_knowledge.
- **Legal context:** Pseudonymised personal data (GDPR Art. 4(5)); minimisation and purpose limitation apply.
- **Utility tasks:** ENERGY-U2, ENERGY-U4, ENERGY-U5, ENERGY-U6
- **Suggested privacy targets:** No names/addresses/contacts; keyed pseudonym for metering point; generalise location to ≥3-digit postcode; coarsen or suppress rare attributes; assess absence inference.
- **Notes:** Series must remain linkable over time for forecasting.

### ENERGY-S3: Energy-poverty research dataset

- **Recipient:** University research group (controlled research environment)
- **Purpose:** Relate heating type, payment problems and winter consumption.
- **Trust level:** controlled_research
- **Threat model:** Researcher with public_directory; private: broker_profiles.
- **Legal context:** Scientific research (GDPR Art. 89) with safeguards; health flag needs special care (Art. 9).
- **Utility tasks:** ENERGY-U3, ENERGY-U4, ENERGY-U7
- **Suggested privacy targets:** k≥5 on {postcode area, heating_type, floor area band, ev, solar}; remove or noise medical flag; daily rather than hourly values may suffice.

## finance

### FIN-S1: Cross-bank fraud consortium

- **Recipient:** Fraud data-sharing consortium of several banks
- **Purpose:** Pool card transactions to detect fraud patterns that span banks.
- **Trust level:** contractual
- **Threat model:** Consortium member analyst with receipt_photos_ocr and public_directory; private: merchant_knowledge.
- **Legal context:** Fraud prevention as legitimate interest (GDPR Art. 6(1)(f), Recital 47); pseudonymised data; PCI DSS for PANs.
- **Utility tasks:** FIN-U1, FIN-U5
- **Suggested privacy targets:** Keyed tokens (HMAC with consortium key) for PAN/device/IP so the same card links across banks; drop names/contacts; coarsen time to minute; no raw PAN.
- **Notes:** Linkability across banks is the point — random tokens destroy it.

### FIN-S2: External AI vendor builds a fraud / spending model

- **Recipient:** AI vendor (processor)
- **Purpose:** Train and evaluate a fraud model and a spending-category model.
- **Trust level:** contractual
- **Threat model:** Vendor staff with public receipts and directory; private: merchant_knowledge, broker_profiles.
- **Legal context:** Processor under Art. 28; minimisation; special-category inferences must not be exposed.
- **Utility tasks:** FIN-U1, FIN-U4, FIN-U6
- **Suggested privacy targets:** No direct identifiers; tokenised card; generalise merchant to MCC group for sensitive MCCs; k-anonymity on customer profile; consider synthetic data with DCR/MIA checks.

### FIN-S3: Statistics office: consumer spending statistics

- **Recipient:** National statistics office / public release
- **Purpose:** Monthly spending by category and region; payday and seasonal effects.
- **Trust level:** public
- **Threat model:** Anyone with public receipts; differencing between releases.
- **Legal context:** Published outputs must be anonymous.
- **Utility tasks:** FIN-U2, FIN-U3, FIN-U6
- **Suggested privacy targets:** Aggregate tables with ≥10 cardholders per cell; dominance rule for merchants; DP noise on sums (state ε and clipping bound).

## cyber

### CYBER-S1: Outsource 24/7 monitoring to an external MSSP

- **Recipient:** Managed security service provider under a data processing agreement
- **Purpose:** Detect and investigate threats across sign-in, VPN, proxy, DNS, EDR and e-mail telemetry
- **Trust level:** contractual
- **Threat model:** Curious MSSP analyst with company_website_staff.csv (public) and general OSINT; may try to learn who is who or what employees browse.
- **Legal context:** Processor under GDPR Art. 28; pseudonymised data is still personal data. Employee monitoring must be proportionate (in Finland, the Act on the Protection of Privacy in Working Life).
- **Utility tasks:** CYBER-U1, CYBER-U2, CYBER-U3, CYBER-U4, CYBER-U5, CYBER-U6, CYBER-U7, CYBER-U9, CYBER-U10, CYBER-U11
- **Suggested privacy targets:** Keyed (HMAC) pseudonyms for users, hosts and internal IPs, consistent across all tables; secrets and e-mails removed from URLs and command lines; sensitive web categories generalised; re-identification only by the company holding the key.
- **Notes:** Random per-row tokens look safer but make every cross-log detection impossible.

### CYBER-S2: Share indicators with the national CERT / sector ISAC

- **Recipient:** National CERT and other logistics companies (threat-intelligence sharing community)
- **Purpose:** Share attacker infrastructure and TTPs from campaigns C1 and C2 so others can block them
- **Trust level:** controlled_research
- **Threat model:** Other community members are competitors; anything about Meridian staff, customers or internal network layout is out of scope.
- **Legal context:** Legitimate interest in network security (GDPR Recital 49); share the minimum necessary.
- **Utility tasks:** CYBER-U3, CYBER-U4, CYBER-U8
- **Suggested privacy targets:** Only external attacker IoCs (IPs, domains, user agents, hashes, techniques, timestamps); no employee identifiers, no internal IPs or hostnames, victim count only as aggregate.
- **Notes:** Attacker IPs are not personal data of employees and must stay exact - masking them destroys the value.

### CYBER-S3: Publish an open research dataset for detection research

- **Recipient:** Anyone (public download)
- **Purpose:** Benchmark for detection of phishing chains, spraying and insider exfiltration
- **Trust level:** public
- **Threat model:** Motivated outsider with company_website_staff.csv and breach/OSINT data (private broker file used in evaluation) trying to identify employees, their browsing, sick leaves or the insider.
- **Legal context:** Must be anonymous in the GDPR Recital 26 sense: no means reasonably likely to re-identify.
- **Utility tasks:** CYBER-U1, CYBER-U2, CYBER-U3, CYBER-U5, CYBER-U6, CYBER-U9, CYBER-U10
- **Suggested privacy targets:** No direct identifiers or secrets; prefix-preserving IP anonymisation with a discarded key; time-shifted or coarsened timestamps; sensitive categories and subjects removed; check that no employee is unique on (department, job_title, site, shift); e-mail subjects and ticket text removed or fully redacted.
- **Notes:** Labelled campaigns must stay detectable after protection.

## education

### EDU-S1: Statistics publication for the education authority

- **Recipient:** Public (published statistics tables)
- **Purpose:** Publish grade, completion and drop-out statistics by school, programme, sex and language group.
- **Trust level:** public
- **Threat model:** Anyone, with graduation lists and sports rosters (public adversary files); differencing between tables.
- **Legal context:** Output must be anonymous (GDPR Recital 26). Traditional practice is suppressing cells with n<5; compare with differential privacy.
- **Utility tasks:** EDU-U1, EDU-U5, EDU-U6, EDU-U3
- **Suggested privacy targets:** No cell below 5 unless noise-protected; no microdata; state ε if DP is used; consistent totals across tables.
- **Notes:** Small schools and programmes are the hard part.

### EDU-S2: Ed-tech vendor training a drop-out early-warning model

- **Recipient:** External ed-tech company under a data processing agreement
- **Purpose:** Train a model that predicts drop-out risk from grades and absences.
- **Trust level:** contractual
- **Threat model:** Vendor staff with classmate-level knowledge (private adversary) and public lists.
- **Legal context:** Pseudonymised data is still personal data; minimise fields; special categories (religion, health) need a separate legal basis.
- **Utility tasks:** EDU-U2, EDU-U4
- **Suggested privacy targets:** No direct identifiers or free text; religion/S2/support removed or justified; k>=5 on (school, programme, start year, sex, birth year).
- **Notes:** Keyed pseudonyms must keep the student_id join across tables.

### EDU-S3: Researcher studying grade gaps

- **Recipient:** University research group in a controlled environment
- **Purpose:** Analyse gender and language-group gaps in maths and matriculation results.
- **Trust level:** controlled_research
- **Threat model:** Researcher with access to public lists; risk of spontaneous recognition in small schools.
- **Legal context:** Scientific research (GDPR Art. 89) with safeguards; pseudonymisation and data minimisation expected.
- **Utility tasks:** EDU-U3, EDU-U5, EDU-U1
- **Suggested privacy targets:** k>=10 on quasi-identifiers or synthetic microdata with documented fidelity; no notes text.

## public_admin

### PUB-S1: Open data publication of citizen feedback

- **Recipient:** Public (open data portal, CC BY)
- **Purpose:** Publish requests with category, time, area, status and the text so residents and journalists can follow service quality.
- **Trust level:** public
- **Threat model:** Anyone: neighbours, forum users (public adversary: neighbourhood_forum_posts), permit registry (public).
- **Legal context:** Published data must be anonymous; free text needs redaction of all personal data including third parties.
- **Utility tasks:** PUB-U1, PUB-U2, PUB-U3, PUB-U4
- **Suggested privacy targets:** No direct identifiers in any column or text; locations coarsened (e.g. 250 m grid or street level without house numbers); time to the hour or day; no account ids.
- **Notes:** Several cities publish feedback like this. The text is where most of the value and most of the risk is.

### PUB-S2: Internal analytics team

- **Recipient:** Service centre's own analysts
- **Purpose:** Dashboards on workload, response times and repeat issues.
- **Trust level:** internal
- **Threat model:** Curious colleague with insider knowledge (private adversary).
- **Legal context:** Same controller; data minimisation and pseudonymisation still expected (GDPR Art. 5, 25).
- **Utility tasks:** PUB-U1, PUB-U2, PUB-U5, PUB-U6
- **Suggested privacy targets:** Keyed pseudonyms for reporters (stable, so repeat reporting can be analysed); no contact details; text redacted.

### PUB-S3: Research group studying service equity

- **Recipient:** University research group
- **Purpose:** Do response times differ between areas and languages?
- **Trust level:** controlled_research
- **Threat model:** Researchers with public data (forum, permits).
- **Legal context:** Research use (GDPR Art. 89) with a data use agreement.
- **Utility tasks:** PUB-U1, PUB-U2, PUB-U3
- **Suggested privacy targets:** k>=5 on (postcode, category, month, language); no text or redacted text; aggregated reporter activity.

## customer_service

### CS-S1: Transcripts to an external LLM analytics vendor

- **Recipient:** Cloud AI vendor (processor, outside the EU possible)
- **Purpose:** Topic mining, contact-reason trends and agent-quality insights on all channels.
- **Trust level:** contractual
- **Threat model:** Vendor staff and model logs see all text; insider can link with leaked_customer_list.csv (public) or breach dumps (private evaluation).
- **Legal context:** Processor under GDPR Art. 28; transfer safeguards if outside EEA. Pseudonymised text is still personal data; aim for no direct identifiers and no special-category data in text.
- **Utility tasks:** CS-U1, CS-U3, CS-U5, CS-U4
- **Suggested privacy targets:** No residual direct identifiers in text (recall ≥ 0.98 on NATIONAL_ID, PAYMENT_CARD, IBAN, SECRET); remove HEALTH mentions; consistent pseudonyms within a conversation; round timestamps to the hour.
- **Notes:** Keep the intent signal: do not delete whole utterances.

### CS-S2: Train an internal intent model / chatbot

- **Recipient:** Aallokko data science team (internal)
- **Purpose:** Train an intent classifier and response suggestions.
- **Trust level:** internal
- **Threat model:** Model memorisation: verbatim identifiers in training text can be regurgitated by a generative model.
- **Legal context:** Compatible further processing (Art. 6(4)); data minimisation (Art. 5(1)(c)).
- **Utility tasks:** CS-U1, CS-U2, CS-U5
- **Suggested privacy targets:** Replace identifiers with typed placeholders or realistic surrogates; no secrets or card numbers anywhere; free text k-anonymised for rare phrases optional.
- **Notes:** Surrogates (fake names) preserve fluency better than [REDACTED].

### CS-S3: Quality-audit samples to an outsourced BPO

- **Recipient:** Quality assurance partner
- **Purpose:** Score 500 conversations a month for compliance (identity verification done, card numbers refused).
- **Trust level:** contractual
- **Threat model:** Auditors are human readers; re-identification by recognising neighbours or public figures; linkage via customer_id and timestamps.
- **Legal context:** Processor; access limited to sample; retention 90 days.
- **Utility tasks:** CS-U4, CS-U6, CS-U7
- **Suggested privacy targets:** Mask identifiers but keep evidence that verification happened (e.g. '[NATIONAL_ID]' placeholder); drop customer_id; generalise started_ts to week.
- **Notes:** Auditor must still see that the agent stopped a card number being read out.
