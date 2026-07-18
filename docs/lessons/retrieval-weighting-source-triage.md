# Lessons: Retrieval, weighting & source triage (WEIGHT-not-FILTER)

Canonical home: CLAUDE.md §-1.3 + §-1.3.1; memory `feedback_pipeline_dna_weight_not_filter_2026_06_13.md`, `feedback_junk_deletion_carveout_2026_07_09.md`, `feedback_fetch_yield_is_first_forensic_number_hard_gate_2026_07_07.md`.

This hub covers the tier classifier (T1–T7) and authority_score as per-citation WEIGHTS surfaced to the user, consolidate-into-baskets, the junk-deletion carve-out, and the fetch-yield hard gate.

## WEIGHT, don't FILTER — never add a cap, target, thinner, or single global deadline to hit a breadth number

Carry every relevant source through to composition with a credibility weight. Do not hard-drop sources to hit a number. Anchor deadlines per-task at task start and scale workers with the candidate count. If you find yourself adding a knob to make a breadth number move, that knob is the bug.

Why: A cap or filter added to control cost or volume repeatedly lobotomized the pipeline while looking harmless. This is the operator-locked architecture DNA §-1.3.

Evidence: `logs/bug_log.md` BUG-035/037/041 (a global analyst cap of 5 restricted the ENTIRE output to 5 documents — the "Lobotomy Cap"); #1175 I-fetch-003 (a single submit-anchored deadline + unscaled workers timed out 85% of fetches before they ran, the P0 completeness root); BUG-P5 (evidence caps disproportionately cut academic sources); BUG-M-201 (gates certify a large corpus while generation only sees the first 20 rows).

Recurrence: Recurring — the dominant completeness lever across the whole beat-both era; codified as §-1.3.

## Do not gate a corpus on a tier or metadata COUNT — it is domain-blind

Replace a corpus-level tier-count material-deviation REFUSAL with PROCEED plus credibility-weighted disclosure; keep only the true zero-usable-source abort. Do not confuse a per-claim source-type veto (a clinical claim needs at least one independent clinical-tier source) with a corpus-level tier floor — they are different gates.

Why: On an economics question a rich 151-source corpus aborted `corpus_approval_denied` because ~50% were tier-4, yet tier-4 NBER working papers (Acemoglu/Restrepo) ARE legitimate primary econ sources. Removing a corpus-level metadata proxy does not enable fabrication, because each claim is still strict_verify'd against its cited span. "We shall not have a gate here, we shall weight the source."

Evidence: `credibility_weighted_sourcing_redesign_plan_2026_06_07.md` I-cred-006b (#1170, `weighted_corpus_gate.py`); `permanent_fix_migration_blueprint.md` gates 2/3; I-ready-017.

Recurrence: One-off with a broadly durable weight-not-count rule.

## Credible non-journals are GOOD at appropriate weight — only fake/predatory journals earn a low weight

WEF, Brookings, OECD, government agencies, BLS, major news, even reputable social media are good sources at an appropriate (often high) weight — keep and cite them. A high tier on them is correct weighting, not a bug. Only fake/predatory pay-to-publish journals masquerading as peer-reviewed earn a low weight, and even those are weighted-down and disclosed, never dropped.

Why: Calling a credible institution "mis-tiered junk to demote" is the filter mentality the DNA forbids; "not a peer-reviewed journal" does not mean low quality. When you catch yourself proposing to demote a credible source for being "not a journal," that is the overkill bug.

Evidence: `feedback_weight_not_filter_credible_nonjournals_2026_07_02.md` (operator flagged hard, twice).

Recurrence: Operator angry, flagged twice in a row.

## Fetch yield (N of M fetched) is the FIRST number in every forensic tick and a HARD pre-composition halt gate

Report fetch success-rate ("N of M fetched, X% success, K timeouts") as the first number in every live-run tick, before anything about flags or liveness. If success-rate falls below a floor (well under ~50%), the run HALTS before composition — never bank a starved corpus, never spend generator tokens writing over garbage. Build it as a real pre-composition gate, not a disclosed-gap footnote. Watch `parallel_fetch_timeout_count` specifically (mass timeouts = per-fetch timeout too low, throttle, no retry, or a single backend).

Why: A starved fetch is the dominant upstream root cause: with ~53 real sources the composer reaches for off-topic and chrome filler and rarely has a second source per claim (zero corroboration). A `--resume` run CANNOT undo it (no re-fetch); only a fresh front-half run can. A missed "fetched=53 failed=937" once let a whole run compose a deficient report.

Evidence: `feedback_fetch_yield_is_first_forensic_number_hard_gate_2026_07_07.md` (operator flagged hard 2026-07-07).

Recurrence: Operator flagged hard; a missed-signal that cost a night.
