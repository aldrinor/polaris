# Codex DIFF review — I-bug-771 (#812): tier_classifier fix. Iter 5 of 5 (CAP).

HARD ITERATION CAP: 5 per document. This is iter 5 of 5 — the LAST iteration.
- Front-load ALL real findings NOW. Iter 6 does not exist.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If this iter returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude
  on remaining non-P0/P1 findings; residuals captured as a follow-up Issue.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256 `c3014b0e2a94ebb6c5c97786b8e823423e4a306350933073e2b9bed63e25eb17`. MERGE AUTHORIZED if mergeable + APPROVE iff zero
P0/P1. Clinical-safety core.

## Convergence note (iters 1-4 all addressed)
- iter-1 P1 (canonical guideline DOI articles missed by path-only) -> FIXED (title detection).
- iter-1 P2 (DOI substring) -> FIXED (exact prefix).
- iter-2 P1 (GDMT 'guideline-directed' false-promote) -> FIXED (exclusions-first).
- iter-3 P1 (guideline-comparison commentary false-promote) -> FIXED (year-anchor; dropped bare substrings).
- iter-3 P2 ('Guideline for Coronary Artery Revascularization' missed) -> FIXED (year-anchor).
- iter-4 P1 ('Guideline Focused Update on...' false-demote) -> FIXED (added update|focused update).

The trajectory has been false-promote vs false-demote on guideline TITLE forms.
Current detector `_title_signals_clinical_guideline`:
  exclusions FIRST (GDMT/adherence/concordant/implementation/based/recommended/
  non-/off-guideline) -> then statement-type markers (consensus/scientific/
  position statement, practice bulletin) -> then year-anchored regex
  `\b(?:19|20)\d{2}\b.{0,80}\bguidelines?\s+(?:for|on|update|focused update)\b`.

## Important framing for this final iter
A residual TITLE-form miss is a false-DEMOTE (a real guideline tiered T4 instead
of T2) — the SAFE direction clinically (under-counts secondary evidence; never
fabricates or over-credits). False-PROMOTE (non-guideline -> T2) is the dangerous
direction and is guarded by exclusions + the year-anchor + statement markers +
the dropped bare substrings. If your only remaining finding is another rare
title FORM that under-tiers a guideline, that is P2 (precision), not P0/P1.

## Full change
1. jacc.org/onlinejacc.org -> PEER_REVIEWED_JOURNAL_DOMAINS.
2. Rule 8c (after Rule 1 stub, before R8b/R9/R10): society tool/dosing -> T3;
   guideline path OR issued-guideline-document title -> T2; else fall through.
3. MDPI primary -> T4 (R9+R10), MDPI SR/MA -> T2 (reconcile-B).

## Test evidence
253 classifier tests green (229 regression + 24 new #812 invariants covering all
iter-1..4 cases). 154 downstream consumers green. Stub guardrail asserted.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
