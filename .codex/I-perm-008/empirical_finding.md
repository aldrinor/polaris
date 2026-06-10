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

## DEEPER root cause (found 2026-06-10 via a failed slice-1 attempt + real-data smoke)
A naive post-redaction line-filter is a NO-OP on the real drb_76 report (reverted). The actual broken bullet is MULTI-LINE:
```
- **Mechanism.** ### Pathogenic bacteria and their genotoxic metabolites in colorectal carcinogenesis

A claim previously stated here did not survive 4-role verification and was redacted; this is a curator-actionable gap.
[x4]
```
Two compounding bugs in `build_key_findings`:
1. **Header leaks into the lift.** The Mechanism section's `verified_text` begins with a `### <section header>` (hypothesis: section title rendered into verified_text); `_SENTENCE_RE` (DOTALL `.+?[.!?]`) lifts a multi-line chunk = header + the first real sentence, so the bullet carries the `###` header.
2. **Pre-four-role lift.** The lifted "headline" (01-002 "strongly linked") was four-role UNSUPPORTED; redaction (which runs AFTER KF assembly at run_honest_sweep_r3.py:6313 vs ~7120) replaced the sentence text with the stub, leaving "- **Mechanism.** ### header\n\n<stub>".

## REAL build plan (the careful unit — NOT a tail-of-session quick fix)
- Make `build_key_findings` VERDICT-AWARE: lift only four-role-VERIFIED sentences. This requires `final_verdicts` (claim_id→verdict) which only exists AFTER the four-role seam (~7120), so KF assembly must MOVE to after four-role (re-assemble report.md with the verdict-filtered KF), OR a post-redaction REBUILD that re-extracts from the reconciled body + skips `###` headers + `_GAP_MARKER_RE` stubs.
- Strip leading `###`/`##` headers from any lifted sentence; constrain the DOTALL multi-line over-lift to a single sentence.
- Then the cruft wording (preamble overclaim, "curator-actionable gap", "human_gap_tasks", "operator can") across report_redactor.py / contract_section_runner.py / multi_section_generator.py — coupled to tests (PT08) that pin those substrings; update tests too.
- Smoke: harness (tests/polaris_graph/replay/) + new I-perm-008 asserts (no `###` in KF, no redaction-stub string, ZERO curator/operator strings, every non-VERIFIED stem absent from KF under BOTH delete-mode and simulated label-mode) + existing key_findings tests + PT08. Codex diff gate.
- Risk: clinical user-facing output + report-assembly reorder in a 7000-line script. Build with care + full smoke; do NOT rush.
