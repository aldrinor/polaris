# 0012. Always release with labels; the verifier never holds or aborts a report

Status: accepted

Date: 2026-06-14

## Context

The empirical keystone: a fully-rendered drb_76 report with ZERO fabrication defects was BLOCKED (`abort_four_role_release_held`) while the exact contraindication safety fact was sitting on the page (I-perm-001..009, #1194, `permanent_fix_migration_blueprint.md` §1). A research engine that refuses to ship good grounded content is broken, and hiding the system's own uncertainty is worse than showing a weak-but-honest finding.

This decision overrides the earlier `abort_no_verified_sections` / `four_role_release_held` hold statuses. It was re-flagged (2026-06-20) because even a Codex APPROVE or a frontier "clinical abstention / fail-closed" recommendation will say "withhold on a safety gate" — and that is WRONG for POLARIS. Radical transparency (keep and label) is also the differentiator versus ChatGPT and Gemini.

## Decision

The faithfulness/verifier layer has NO power to hold, abort, or suppress a report. Always give the answer, grounded in true findings. A weak finding is shown labeled weak; a no-evidence claim is labeled "unsupported", never asserted as fact. `strict_verify` / 4-role / judge become per-claim labelers and weighters, never report-suppressing gates.

Report and aggregate-level gates (coverage below 0.70, S0-must-cover-missing, corpus tier-count adequacy, pending-rewrite) are RELOCATED from trap-doors to DISPLAYED labels and always release. Missing safety categories become PROMINENT top-of-report caveats. A non-VERIFIED claim can NEVER render in the "high" confidence bucket.

Only two hard blocks survive: the FABRICATED-occurrence latch (byte-unchanged, one-way) and true zero-grounding (which renders an honest "insufficient grounded evidence" report, not a hollow one).

## Consequences

- Clinical safety is preserved by HONEST LABELING, not by holding. A wrong dose or contraindication is caught by labeling the claim, not by hiding the whole report.
- On any change touching release policy or a hold/abort/withhold status, ask: does it HOLD? If yes, it is wrong — make it a LABEL. This is the standing self-check.
- This decision overrides outside advice, including a Codex APPROVE, when that advice recommends withholding on a safety gate. It is operator-locked and not delegable.
- The per-claim gates from ADR 0014 are untouched; only the report-level trap-doors are relocated to labels.
