# PII span annotation guidelines (all free-text fields)

Spans are character offsets `[start, end)` into the field text, with one label each. Labels never overlap.

| label | covers | examples |
|---|---|---|
| PERSON | names of any real-world person: customer, relative, agent, supervisor, staff; first name alone counts | "Aino Virtanen", "Tiina", "äitini Pirkko" → only "Pirkko" |
| NATIONAL_ID | Finnish personal identity code, whole or in parts, digits or spoken words | "210814A966S", "kaksi yksi, nolla kahdeksan, …, aa, …" |
| EMAIL | e-mail address, typed or spelled out | "aino.v@kotiposti.example", "aino piste v ät kotiposti piste example" |
| PHONE | phone numbers of persons, any format, also partial fragments when a number is split across turns | "040 344 1391", "nolla neljä nolla" |
| ADDRESS | street address incl. house number, staircase/apartment, and postcode+town when contiguous | "Koivukatu 12 B 14, 20100 Turku" |
| LOCATION | other places that locate a person: town of residence, travel destination, landmark where they are | "Raisio", "Thaimaassa" |
| DATE | calendar dates tied to the person (birth date, moving date, date of death, appointment) | "15.3.2025", "March 15" |
| AGE | stated age | "83" in "olen 83-vuotias" |
| IBAN | bank account numbers | "FI49 9123 4567 8901 23" |
| PAYMENT_CARD | card numbers, also last-4 digits when presented as a card reference | "4242 4242 4242 4242", "4242" |
| ACCOUNT_NUMBER | customer, contract, invoice and order numbers | "41234567" |
| IP_ADDRESS | IP address assigned to the person/their device (not generic gateways like 192.168.1.1) | "100.72.13.5" |
| LICENSE_PLATE | vehicle registration | "ABC-123" |
| ORG | organisation that reveals the person's affiliation (employer, bank, previous operator, care provider); not Aallokko itself | "Meridian Logistics Oy" |
| URL | URLs that are personal or malicious (tokens, emails in query strings, phishing links) | "https://oma.aallokko.example/reset?token=…" |
| USERNAME | login names | "ainov85" |
| SECRET | passwords, PINs, PUK codes, wifi keys | "Kesä2024" |
| HEALTH | health information about an identifiable person in non-clinical text | "minulla on kuulolaite" |
| DEVICE_ID | IMEI, SIM ICCID, device serials | "356938035643809" |
| PROPERTY_ID | Finnish property identifiers (kiinteistötunnus) | "445-412-3-77" |

Rules
1. Label the value only, not the cue word ("hetu on |210814A966S|").
2. Spoken numbers: the whole spoken sequence including separators between the digit words is one span.
3. A value split across turns gives one span per turn.
4. Lowercase or misspelled values are still labelled (ASR output, chat typos).
5. Prices, product names, generic times ("tomorrow at 4 pm"), Aallokko's own name, the bot name "Aava" and public
   service URLs without personal tokens are not labelled.
6. Common words that happen to be first names ("onneksi", "toivon", "lunta") are not PERSON.
