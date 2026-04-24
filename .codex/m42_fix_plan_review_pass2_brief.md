You are Codex step 6 pass-2 of autoloop V2 — re-reviewing Claude's
revised V25→V26 fix plan after the pass-1 CONDITIONAL verdict.

## Your pass-1 verdict (what Claude had to address)

Pass-1 summary:
- M-42a APPROVED + minor group-ref tightening
- M-42d APPROVED + add preservation guard for FDA/EMA/NICE
- M-42e APPROVED + add cap / slot-accounting assertion
- **M-42b needs_revision**: pass-1 was "post-synthesis from verified
  prose" — still downstream. You required: revise to
  `evidence_selection + table_generation/rendering` that consumes
  selected primary trial evidence directly, add ≥6 pivotal-trial
  rows acceptance criterion, add a smoke for visible table.
- **M-42c needs_revision**: pass-1 was prompt-only. You required:
  add upstream evidence-selection/retrieval floor for mechanism
  content (PK / receptor / clamp / biomarker). Target 20-35 must
  be conditional on ≥4 mechanism rows.
- Completeness: Structural depth needs at least ONE additional
  artifact beyond the table (per-trial subsections OR timeline).
- Preservation: expand tests to prove M-42d/e don't reduce
  FDA/EMA/NICE presence, M-42e doesn't crowd out meta-analyses,
  Mechanism bloat doesn't create new under-framed claims.
- Order of operations: M-42e first; then M-42a + M-42b together;
  then M-42c evidence floor before prompt; M-42d independent.

## Pass-2 revisions (claimed)

Read `outputs/audits/v25/fix_plan.md`. All pass-1 requests should
be addressed:

1. **M-42b revised**: now `evidence_selection + generator/table`.
   Table builder consumes primary-trial evidence DIRECTLY from
   fetched source content (not prose). Also adds a **Trial Program
   Timeline** artifact as the 2nd structural element (addressing
   your completeness concern).
2. **M-42c revised**: two stages — (a) selector mechanism-evidence
   floor with explicit detection patterns (PK / receptor /
   half-life / clamp / isotope / affinity / signaling / biomarker
   / etc.), (b) CONDITIONAL section prompt target (20-35 if >=8
   mechanism ev_ids; 15-20 if 4-7; 10-15 if <4 with honest
   disclosure).
3. **M-42a**: group-ref tightening added — "SURPASS trials" must
   enumerate specific trials OR be a pooled/program-level claim
   with pooled N + pooled effect inline.
4. **M-42d**: jurisdiction preservation guard added — HC quota
   stays at 1 if FDA/EMA/NICE baseline counts drop.
5. **M-42e**: cap at 6 primary-floor slots; preservation guard if
   T2 meta-analysis count would drop below V25 baseline (3).
6. **Preservation regression tests**: new `test_m42_preservation.py`
   with 6 explicit tests (FDA>=7, EMA>=3, NICE>=4, biblio>=40,
   T2>=3, contradictions>=10).
7. **Structural depth scope**: table + timeline in M-42b; per-trial
   subsections deferred to M-43 if V26 still LOSE_BOTH on
   Structural depth (with explicit rationale).
8. **Implementation order** documented: M-42e → (M-42a + M-42b) →
   M-42c (floor before prompt) → M-42d independent.

## What to verify

1. Did pass-2 actually close each pass-1 required revision? For
   each of your 3 must-revise items + 4 must-add items, is there a
   corresponding concrete change in the plan, not just a renaming?

2. Is M-42b now truly at the earliest preventable stage? (The plan
   claims table builder consumes fetched source content, not prose.
   Is "fetched source content" specific enough? Could it still be
   downstream if the content doesn't have the structured data?)

3. Is M-42c's evidence floor actually earlier than pass-1's prompt-
   only fix? Does the conditional target text prevent LLM from
   padding when evidence is thin?

4. Does the preservation-test suite adequately protect the BEAT_ONE
   dims? Any missing preservation check?

5. Is Structural depth now adequately addressed with table +
   timeline, or does it still need per-trial subsections to hit
   BEAT_ONE against ChatGPT's trial architecture + charts + NNT +
   timeline?

6. Implementation order is Codex-recommended — is it still the
   right order after pass-2 revisions?

## Deliverable

Write `outputs/audits/v25/codex_plan_review_pass2.md` with:
- Overall plan verdict: APPROVED / CONDITIONAL / REJECT
- Per-item verdict for all 5 items
- For any still-CONDITIONAL item, exact revision needed
- Confirmation that each pass-1 required revision was closed
- Answer to verification questions 1-6 above

Keep under 1500 words. If APPROVED, implementation proceeds next
turn; if CONDITIONAL, Claude revises and resubmits for pass-3.
