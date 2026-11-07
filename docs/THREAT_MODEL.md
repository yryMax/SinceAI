# Threat model: who could re-identify people, and what they know

Protection is only meaningful against a stated attacker. This package ships **attacker knowledge** as data, so your claims can be tested rather than asserted.

## The world

- **Population.** All datasets draw on one synthetic population of 100,000 residents living at synthetic addresses in real postcode areas of Southwest Finland.
- **Overlap.** The same people appear in several datasets: an ED patient may also ride the bus, bank at Saaristo Bank, work at Meridian Logistics and appear in a noise complaint.
- **Mosaic effect.** Because of this overlap, linking two weakly protected datasets can identify people that neither dataset identifies alone.

## Attackers shipped in the package (`adversary/`)

| File | Who it represents | What they know | Typical attack |
|---|---|---|---|
| `public_directory.csv` | Anyone | Name, street address, postcode, city, sometimes phone. About half of adults are listed, and some entries are out of date. | Link name and address to records with postcode, age and sex. |
| `news_clips_health.csv`, `social_posts_health.csv` | Journalist, neighbour, social media | Event date and place, sometimes a name or "a 34-year-old man from Raisio" | Find the ED visit. |
| `social_checkins.csv`, `fitness_app_leak.csv` | Social media, leaked app data | Times and places; run start points near home | Trajectory linkage to transit cards and bike trips. |
| `plate_sightings.csv` | Someone who saw a car | Plate, place, time | Link to ANPR parking events. |
| `vacation_posts.csv` | Social media | Holiday dates, sometimes a name | Spot the empty home in meter data (burglary risk). |
| `receipt_photos_ocr.csv` | Shared receipts | Card last 4 digits, time, merchant, amount | Link to card transactions. |
| `company_website_staff.csv` | OSINT | Employee names and titles | Reverse pseudonymised users, hostnames and hashed emails. |
| `sports_club_rosters.csv`, `graduation_lists.csv` | Clubs, local newspapers | Names, school, year | Identify students in small groups. |
| `neighbourhood_forum_posts.csv` | Local forum | Complaints described by neighbours | Link service requests to reporters. |
| `leaked_customer_list.csv` | An old marketing list | Names, emails, phones | Find customers in transcripts and redacted text. |

Each public attacker file has a truth file in `truth/adversary__<name>.csv`, so you can measure your own re-identification rate.

`pets-eval scorecard` runs the linkage attacks defined in `metadata/attack_specs.json`, and computes **trajectory unicity** for the mobility and smart-city tables. Unicity is the share of travel cards, bike accounts, devices or vehicles that a few known (place, hour) points single out. In the original taps, 4 points single out about 98 % of cards.

Two files are not scored automatically: `social_checkins.csv` (it needs a stop-name join) and `vacation_posts.csv` (an attribute-inference scenario: spot the empty home in the meter data). They are there for you to build your own attack demonstrations.

## The attacker you have not seen

The organisers hold a **second, stronger attacker set** for every domain. It includes:

- a data-broker profile file;
- HR knowledge about sick leave;
- a colleague's knowledge of commute times;
- a merchant's view of card numbers;
- insider knowledge at the municipality.

These files are not in the package. Overfitting to the public attacker does not help; protecting the quasi-identifiers properly does.

## Capabilities assumed

- The attacker knows the dataset's schema and your published method description (Kerckhoffs's principle). The attacker does not know your secret keys or random seeds.
- The attacker can hash candidate values (emails, HETUs, phones) and compare them with your output.
- The attacker can combine every public file in the package.
- The attacker cannot access the original data.

## What counts as a successful attack

1. **Re-identification.** A correct unique match from an attacker row to a protected record.
2. **Attribute inference.** Learning a sensitive value, such as a diagnosis, a union membership or an empty home, with confidence clearly above the base rate.
3. **Membership inference.** For synthetic data: telling with better than chance whether a person's record was used to train the generator.
4. **Residual identifiers.** Any direct identifier still present, including inside free text.
