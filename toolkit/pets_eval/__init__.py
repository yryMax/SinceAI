"""pets_eval — self-assessment toolkit for the TrustED PETs Transformer challenge.

Modules
- io         load the package: data tables, field catalog, PII spans, adversary files, truth, scenarios
- detect     score a field-classification (Detect step) against the field catalog
- text       score PII span detection and redaction leakage in free text
- privacy    k-anonymity, l-diversity, t-closeness, uniqueness, small cells, differencing, DCR/NNDR, MIA, unicity
- attacks    linkage (re-identification) attack, attribute inference, hash dictionary attack
- scorecard  one-command privacy + utility report (JSON + HTML)
- check      regex scan for residual direct identifiers in any folder
- parse      tolerant parsers for generalised values (age bands, rounded times, truncated postcodes)
- utility    per-domain utility tasks

Scores produced here are a SELF-ASSESSMENT aid, not the official judging score.
"""
__version__ = "1.0.0"
