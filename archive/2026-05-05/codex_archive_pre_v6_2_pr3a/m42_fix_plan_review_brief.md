You are Codex step 6 of autoloop V2 — reviewing Claude's V25→V26
fix plan for band-aid-vs-root-cause classification.

## Your responsibility

Per V2 runbook §6, evaluate each fix item against the §5 schema:

- Every field populated (causal_stage, prior_mechanism_gap,
  preservation_risks, acceptance_criteria, test_coverage,
  classification)?
- Classification correct (root_cause claims actually address the
  earliest preventable stage)?
- Preservation risks honestly enumerated, not hand-waved?
- Acceptance criteria testable?
- Test coverage ties to the ACTUAL V25 failure, not hypothetical?

Plan RED if any item is band_aid, or any root_cause item misses
the earliest preventable stage, or the dimension-preservation
statement is vague/missing.

## Plan to review

Read `outputs/audits/v25/fix_plan.md`. Five items:

- **M-42a** — anaphoric / group claim-frame rule extension
- **M-42b** — deterministic trial-table reconstruction (supersedes
  M-36 LLM extraction with regex-based extraction)
- **M-42c** — Mechanism-section minimum content target
- **M-42d** — Health Canada retrieval + selector quota expansion
- **M-42e** — SURPASS primary-paper biblio floor in evidence
  selector

## Context

V25 cross-reviewed verdict: 1 BEAT_BOTH + 4 BEAT_ONE + 2 LOSE_BOTH
(Claim frames, Structural depth). Full cross-review at
`outputs/audits/v25/cross_review.md`.

Prior verdicts:
- V23: 1 BEAT_BOTH + 2 BEAT_ONE + 4 LOSE_BOTH
- V24: 1 BEAT_BOTH + 1 BEAT_ONE + 5 LOSE_BOTH (REGRESSED)
- V25: 1 + 4 + 2 (best yet)

## Reference material

- `outputs/audits/v25/claude_audit.md`
- `outputs/audits/v25/codex_audit.md` (your prior output audit)
- `outputs/audits/v25/cross_review.md`
- `outputs/audits/v25/gate_verdict.md`
- `state/autoloop_v2_runbook.md` (§5 plan schema, §6 your role)

## Specific questions Claude asked in the plan

Claude flagged 3 self-critical questions in the plan:
1. Is M-42b truly root-cause or does it just shift the band-aid
   from M-41b to a new deterministic-guardrail position?
2. Is M-42a's "antecedent framing context" rule precise enough
   that the LLM can follow it?
3. Is M-42c's 20-35 sentence target achievable given Mechanism-
   section evidence pool sizes in real corpora?

Please answer these.

## Additional questions worth your judgment

4. **Is M-42 complete?** Are there LOSE_BOTH-dimension gaps not
   addressed by M-42? (V25 has 2 LOSE_BOTH: Claim frames +
   Structural depth. M-42a+b target Claim frames; M-42b targets
   Structural depth via table. Does M-42 adequately address
   Structural depth's OTHER gaps (forest chart, NNT, timeline,
   per-trial subsections)?
5. **Dimension preservation**: is the preservation statement
   honest? Any risk that M-42 items could trade off an existing
   BEAT_ONE?
6. **Scope**: M-42 is 5 items — is this too much for one V26 cycle
   or appropriately tight?
7. **Order of operations**: should any M-42 item be prerequisite
   for another? E.g., M-42a might need to land before M-42b
   because M-42b's table construction depends on framed prose
   from M-42a.

## Deliverable

Write `outputs/audits/v25/codex_plan_review.md` with:

- Per-item verdict: root_cause_approved / guardrail_only /
  band_aid / needs_revision
- Overall plan verdict: APPROVED / CONDITIONAL / REJECT
- For any CONDITIONAL item, the exact revision Claude must make
- Answer to Claude's 3 self-critical questions
- Answer to additional questions 4-7
- Completeness check: are Structural depth gaps adequately
  addressed?

Keep under 2000 words.
