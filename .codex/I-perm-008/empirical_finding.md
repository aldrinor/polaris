# I-perm-008 — empirical Key-Findings finding (verified on saved drb_76, 2026-06-10)

Verified with the I-perm-009 harness against `outputs/audits/beatboth8/drb_76/report.md` +
`manifest.four_role_evaluation.final_verdicts`. "Verify before fixing" (operator directive).

## What is NOT broken (do not "fix" a non-bug)
- **The ordering LEAK is closed under the current DELETE-redactor.** 0 of the 14 non-VERIFIED
  claim stems appear in the shipped Key Findings block — `reconcile_report_against_verdicts`
  (commit 0c64af25) redacts the KF block (first occurrence) along with the body. So a
  non-VERIFIED claim is NOT surfaced as a top-line "finding" today.

## What IS broken (the real I-perm-008 scope)
1. **KF carry-up cruft (B7).** The "Mechanism" Key-Finding bullet contains a section HEADER
   (`### Pathogenic bacteria and their genotoxic metabolites...`) AND four redaction stubs
   ("A claim previously stated here did not survive 4-role verification and was redacted; this
   is a curator-actionable gap.") instead of a clean verified sentence — because
   `build_key_findings` extracts the first sentence of `section.verified_text`, whose head is a
   header + redacted stubs after redaction.
2. **Preamble overclaim (B7).** "_Each finding below is a verbatim, span-verified statement_"
   while the block carries redaction stubs + headers.
3. **Curator wording (B5).** "curator-actionable gap" in autonomous output (no curator exists).

## The forward-looking R7 precondition (the ordering fix proper)
Under always-release (I-perm-001/005 label-not-delete), non-VERIFIED claims will no longer be
DELETED from `verified_text` — they will be LABELLED in place. At that point KF extracting from
`section.verified_text` would surface a labelled-but-non-VERIFIED claim as a "verified finding".
So I-perm-008 MUST verdict-FILTER Key Findings (build from `final_verdicts`, VERIFIED only) — this
is R7's "precondition for PG_ALWAYS_RELEASE".

## I-perm-008 build plan (when sequenced)
- Make `build_key_findings` consume `final_verdicts` (verdict-filter: only VERIFIED sentences;
  skip headers + redaction stubs + gap-disclosure boilerplate).
- Fix/soften the preamble to match what the block actually contains.
- Replace "curator-actionable gap" wording (factual self-contained gap disclosure).
- Harness asserts (blueprint §5): for every non-VERIFIED claim, its stem is absent from KF
  (holds under BOTH delete-mode AND simulated label-mode); KF contains no `###` header / no
  redaction-stub string; ZERO "curator"/"operator can" strings.
