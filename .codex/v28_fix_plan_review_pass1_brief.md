You are Codex, step 6 of autoloop V2 — reviewing Claude's V28 fix plan.

## Context

V27 cross-reviewed deep content audit (you wrote step 2b at
`outputs/codex_findings/v27_deep_content_audit/findings.md`, Claude wrote
step 2a at `outputs/audits/v27/claude_deep_content_audit.md`) converged
on the following content-level scoreboard (line-by-line PRISMA/AMSTAR-2
pass):
- ChatGPT 4 topic wins (SURPASS-2, SURPASS-CVOT, SURPASS-4, Contradictions)
- V27 1 topic win (Regulatory)
- Gemini 1 topic win (Mechanism)

V27 is rigorously bound but materially incomplete for a clinical audience.
Root-cause diagnosis identifies 5 defects + 1 infra gap spanning retrieval,
selector activation, content acquisition, generator prompt, mechanism
extraction, and preservation guards.

## Your responsibility

Read Claude's draft plan at `outputs/audits/v27/fix_plan_v28.md`. Evaluate
each item against the V2 §5 schema:
- causal_stage populated and at earliest preventable point?
- prior_mechanism_gap evidence-backed?
- preservation_risks stated and mitigated?
- acceptance_criteria measurable?
- test_coverage real (not just "write tests")?
- classification `root_cause` vs `band_aid` justified?

Then specifically answer the 5 self-critical questions Claude surfaced in
the plan's "Questions for Codex plan review" section.

## Output format

Write your verdict to
`outputs/codex_findings/v28_fix_plan_review_pass1/findings.md`.

Structure:
- **Verdict**: APPROVED | CONDITIONAL | REJECT
- **Per-item verdicts**: table M-48 / M-46 / M-45 / M-44 / M-47 / M-49
  each with root_cause_approved | needs_revision | band_aid | reject
- **Specific revisions required** (if CONDITIONAL/REJECT): numbered,
  concrete, with suggested alternative language
- **Answers to Claude's 5 self-critical questions** (be direct)
- **Completeness review**: anything Claude missed that would block
  V28 from reaching 3-4 BEAT_BOTH? Candidates to consider:
  - Should we add a per-trial subsection outline generator for
    Structural depth's second BEAT_BOTH? (Claude deferred as V29.)
  - Should M-44 also add scorer-level primary-paper boost?
  - Any AMSTAR-2 / GRADE / PRISMA element V27 should have that neither
    competitor has and that V28 could ship (GRADE certainty rating per
    claim; PRISMA flow diagram; risk-of-bias table)?
- **Implementation order confirmation or revision**

Your input carries V2 step 6 weight. On APPROVED, Claude will
implement items in Codex-recommended order with per-item Codex code
audits (the established pattern from M-42e/a+b/c/d and M-43).

Codex pass-1 review should run ~15 min. Budget: unlimited review
passes up to §7 trigger #11 (>3 ping-pong halts the loop).
