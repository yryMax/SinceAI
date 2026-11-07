# PET playbook: which technique for which kind of data

This is a field guide, not an answer key. The right protection depends on **who receives the data and why** (see `SCENARIOS.md`). The same column can need tokenisation in one scenario and deletion in another.

## The four questions to ask for every column

1. **Can it identify someone on its own?** These are direct identifiers: name, HETU, email, phone, IBAN, card number or plate. If yes, remove it or replace it.
2. **Can it identify someone in combination?** These are quasi-identifiers: birth date, postcode, sex, timestamps, coordinates, employer, rare categories. If yes, coarsen these columns together until the combinations are no longer unique.
3. **Is it the sensitive fact itself?** Examples are a diagnosis, union fee, special support level or income. If yes, keep it if the scenario needs it, but break the link back to the person.
4. **Does the analysis need it, and at what resolution?** Never protect more than the purpose requires. Never keep more than it requires either.

## Techniques by data type

| Data type | Typical techniques | Keeps | Common mistake |
|---|---|---|---|
| Names, emails, phones | Suppression; keyed pseudonym (HMAC-SHA-256 with a secret key) when records must stay linkable | Joins across tables | **Unsalted hash** (`sha256(email)`) is reversible by hashing a list of candidates. Try `pets-eval` dictionary attack. |
| National ID (HETU) | Suppress; keyed pseudonym; derive only what is needed (age band, sex) | Linkage, demographics | Forgetting that HETU *encodes* birth date and sex, and that partial HETUs (`DDMMYY-`) still identify. |
| Card numbers, IBANs | Tokenisation (format-preserving token vault), keep BIN/first6 only if needed | Format, joins, issuer | Keeping first6 + last4 + time + amount: a merchant can re-link. |
| Technical IDs (IP, MAC, hostname, device ID) | Prefix-preserving IP anonymisation (Crypto-PAn style); keyed pseudonyms; truncate to /24 or /16 | Subnet structure, joins | Random per-row tokens break every detection that needs joins; hostnames like `LT-AINVIR-0423` contain names. |
| Birth dates, ages | Generalise to year or bands (5/10 y); top-code very old ages (90+) | Age structure | Keeping exact date "only" with postcode and sex: often unique. |
| Postcodes, municipalities | Truncate (3 digits); merge small areas; population thresholds | Regional patterns | Rural postcodes with few residents identify on their own. |
| Coordinates, trajectories | Snap to grid (250 m–1 km), remove or perturb trip ends near home or work, drop rare trips | Flows, density | Rounding the middle of a trip but not its ends: home and work remain visible. |
| Timestamps | Round (15 min / hour / day); shift per person with a secret offset; keep order where needed | Seasonality, sequences | Exact timestamps link to news reports, social posts and receipts. |
| Free text | NER-based redaction with typed placeholders (`[PERSON]`, `[PHONE]`); rule + model hybrid; post-check with validators | Meaning, intent, topic | Spoken numbers ("neljä viisi..."), spelled emails, names in lower case, third parties' names, passwords typed into chat. |
| Rare categories | Merge into "other", suppress small groups, add noise | Main categories | One rare diagnosis in a small municipality is a name tag. |
| Numerical measures | Top/bottom coding, rounding, noise; binning | Distributions | Extreme incomes and ages are outliers that identify. |
| Aggregate tables | Small-cell suppression (e.g. n < 5) with secondary suppression; **differential privacy** for released counts and means | Totals, trends | Publishing two overlapping tables: differencing reveals the suppressed cell. |
| Whole tables | Synthetic data generation (marginals + correlations, copulas, Bayesian networks, deep generators); evaluate distance-to-closest-record and membership inference | Statistical properties | Overfitted generators copy real rows. Synthetic data is not automatically anonymous. |
| Joins across datasets | Different keys per recipient; per-dataset pseudonym domains | Prevent cross-dataset linkage | One global pseudonym for everyone: the mosaic effect re-identifies. |

## Differential privacy in one paragraph

A mechanism is ε-differentially private if adding or removing one person changes the probability of any output by at most a factor e^ε. For counts, add Laplace noise with scale Δ/ε, where Δ is the most one person can change the answer (often 1, but **one person with many visits contributes many rows**, so bound contributions per person first). The ε of several releases adds up. Saying "DP" without a stated mechanism, ε (and δ if any), the contribution bound and the unit of privacy (visit or person) is not a privacy claim.

## Evidence the jury will look for

- A field inventory with roles and reasons (demo item 1).
- A PET per field, tied to the scenario (item 2).
- The protected output, not just screenshots (item 3).
- Utility before and after, measured on the tasks the scenario needs (item 4). `pets-eval scorecard` produces this.
- Residual risk, stated honestly: which attacks still work, at what rate (item 5).

## References

- Sweeney, L. (2000). *Simple Demographics Often Identify People Uniquely.* ZIP code, birth date and sex identify about 87 % of the US population.
- de Montjoye, Y.-A. et al. (2013). *Unique in the Crowd: The privacy bounds of human mobility.* Scientific Reports 3:1376. Four spatio-temporal points identify 95 % of individuals.
- Narayanan, A. & Shmatikov, V. (2008). *Robust De-anonymization of Large Sparse Datasets* (Netflix Prize).
- Machanavajjhala, A. et al. (2007). *l-Diversity*; Li, N. et al. (2007). *t-Closeness*.
- Dwork, C., McSherry, F., Nissim, K., Smith, A. (2006). *Calibrating Noise to Sensitivity in Private Data Analysis.*
- Xu, J. et al. (2002). *Prefix-preserving IP address anonymization* (Crypto-PAn).
- Article 29 Working Party (2014). *Opinion 05/2014 on Anonymisation Techniques.*
- ENISA (2019, 2021). Reports on pseudonymisation techniques and best practices.
- GDPR: Art. 4(5) pseudonymisation, Art. 9 special categories, Art. 89 research safeguards, Recital 26 anonymous data.
