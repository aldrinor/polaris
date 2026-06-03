# I-run11-002 L1 — multi-fixture LIVE discrimination smoke (granite + non-inverted)

Ran the REAL production path (build_sentinel_request in noninverted mode -> _normalize_messages ->
live OpenRouter ibm-granite/granite-4.1-8b -> parse_sentinel_grounded_token), 2x per fixture,
temp 0, against the autor_why_still_jobs polarization document (outputs/q1_run11/evidence_pool.json).
Script: scripts/diagnostics/sentinel_multifixture_smoke.py.

| fixture | expect | run 1 | run 2 | result |
|---|---|---|---|---|
| 1 grounded verbatim (first 28 words of the doc) | GROUNDED | grounded | grounded | PASS |
| 2 fabricated numeric ("AI raised US median wages by exactly 14 percent in 2024") | UNGROUNDED | ungrounded | ungrounded | PASS |
| 3 qualitative negation ("the study found NO polarization of the labor market") | UNGROUNDED | ungrounded | ungrounded | PASS |
| 4 true paraphrase ("wage gains concentrated at top and bottom, not the middle") | GROUNDED | grounded | grounded | PASS |

VERDICT: granite + non-inverted DISCRIMINATES ROBUSTLY on ALL 4 fixtures, 2x stable — including the
hardest qualitative-negation case (#3, the regex-escape class per feedback_qualitative_negation).
The model returns a clean single-word GROUNDED/UNGROUNDED, parsed_ok=True every time. This is far
stronger than the n=1 probe and validates the L1 fix: KEEP granite (4-role lock), non-inverted
prompt+parser, NO polarity flip, NO false-accept (fabricated + negation both correctly UNGROUNDED).
