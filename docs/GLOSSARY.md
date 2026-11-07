# Glossary

**Aggregation**: Releasing totals, counts or means over groups instead of individual rows.

**Anonymous data**: Data from which a person can no longer be identified by any means reasonably likely to be used (GDPR Recital 26). GDPR does not apply to it. Pseudonymised data is *not* anonymous.

**Art. 9 special categories**: Health, genetic and biometric data, data on racial or ethnic origin, political opinions, religious beliefs, trade-union membership, sex life and sexual orientation. Stronger rules apply. Some fields in this package reveal them only *indirectly*, for example a union fee or a donation.

**Attribute inference**: Learning a sensitive value about a known person without necessarily finding their exact record.

**Binning / generalisation**: Replacing precise values with ranges or broader categories (age 37 becomes 30–39, postcode 20100 becomes 201**).

**Differencing attack**: Subtracting two overlapping published aggregates to reveal a hidden or small value.

**Differential privacy (DP)**: A mathematical guarantee that the output barely changes when any one person is added or removed. It is controlled by ε ("epsilon"): a smaller ε means more privacy and more noise.

**Direct identifier**: A value that identifies a person on its own: name, HETU, email, phone, IBAN, card number or plate.

**DCR (distance to closest record)**: For synthetic data, how close each synthetic row is to its nearest real row. Copies of real rows have a DCR of 0.

**HETU**: The Finnish personal identity code, `DDMMYYCNNNK`. It encodes birth date and sex (odd = male). This package uses only the 900–999 individual-number range. That range is reserved for temporary identifiers, so permanent identity codes never use it.

**k-anonymity**: Every combination of quasi-identifier values is shared by at least *k* records.

**l-diversity / t-closeness**: Extensions of k-anonymity. They require that each group also has varied sensitive values (l), or a distribution close to the overall one (t).

**Linkage attack**: Matching records across datasets on shared quasi-identifiers.

**Masking**: Hiding part of a value (`+358 40 *** **12`, `4111 11** **** 1111`).

**Membership inference**: Deciding whether a specific person's record was in the data used to train a model or generator.

**Mosaic effect**: Several individually harmless releases combine to identify people.

**Prefix-preserving IP anonymisation**: Pseudonymising IP addresses so that two addresses sharing a /24 prefix still share a pseudonymised prefix. Network structure survives; real addresses do not.

**Pseudonymisation**: Replacing identifiers with pseudonyms, so that re-identification needs additional information kept separately (GDPR Art. 4(5)). Keyed (HMAC) pseudonyms are reversible only with the key; unsalted hashes are reversible by anyone.

**Quasi-identifier**: An attribute that identifies in combination with others: birth date, postcode, sex, timestamps, places, employer, rare categories.

**Redaction**: Removing or replacing sensitive spans in free text, ideally with typed placeholders such as `[PERSON]`.

**Sharing scenario**: Who receives the data, why, under what contract, and what they could know. It decides which PETs are proportionate.

**Small-cell suppression**: Hiding table cells with counts below a threshold (for example 5), plus enough other cells that the hidden ones cannot be recomputed from totals.

**Suppression**: Removing a value, row or column entirely.

**Synthetic data**: Artificial records generated to reproduce the statistical properties of real data. It is useful, but not automatically private.

**Tokenisation**: Replacing a value with a random token, keeping the mapping in a secure vault. It is often format-preserving.

**Trajectory unicity**: The share of people uniquely identified by a few known points of their movement.

**Utility**: How well protected data still answers the questions it is shared for.
