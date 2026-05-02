M-10 v6 — final GREEN check round 4.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-10 v5 verdict: PARTIAL on two minor issues.

1. Vocab gap: "empagliflozin renal composite outcomes in chronic
   kidney disease patients" stayed operator_review at 0.45 because
   "composite" was alien.

2. Multi-word keyword cross-hit: "phase 2" matched a query that
   contained "phase 3" + "type 2 diabetes" via set-membership
   {phase, 2} ⊆ query tokens, even though those tokens weren't
   contiguous as the phrase "phase 2".

You said: bypasses appear closed; only these two leftovers prevented
GREEN.

## What changed in v6

`template_classifier.py`:
- Keyword matching is now arity-aware:
  * 1-token keyword: set membership (unchanged).
  * N-token keyword (N > 1): CONTIGUOUS subsequence match in the
    ordered query token list.
- New helpers: `_tokenize_raw_seq()` returns ordered list;
  `_contains_subseq()` is a textbook contiguous-subseq check;
  `_keyword_hits()` takes both set + seq and dispatches by arity.
- `_score_template` / `classify_query` updated to thread both
  representations through.

`template_catalog.py`:
- Added "composite", "composites", "individual", "individuals" to
  `medical_keywords`.

`tests/test_template_classifier.py`:
- New regression: composite query routes at high confidence.
- New regression: "phase 2" multi-word kw must NOT match
  "Phase 3 trial of monoclonal antibody for type 2 diabetes".
- New regression: "type 1 diabetes" must NOT match
  "Phase 1 trial of metformin for type 2 diabetes" even though
  type/1/diabetes are all individually present.

Tests: 69 → 72 in M-10 module. Phase B suite 213 → 216 green.

Verification:
  empagliflozin renal composite outcomes in CKD patients → routed (0.944)
  Phase 3 trial + type 2 diabetes → operator_review
    (drug=0; monoclonal antibody is medical, not drug)
  Phase 1 trial + type 2 diabetes → "phase 1" matched, "type 1
    diabetes" NOT matched
  All previous bypasses (10 parametrized) still ≤ operator_review.
  All true positives still route.

## Your job

Final verdict on M-10. GREEN / PARTIAL / DISAGREE.

Probe with:
- More multi-word kw cross-hit attempts you can think of
- Vocab gaps that remain
- Anything else

If GREEN, M-10 is locked and Phase B can proceed to M-11.

## Output

Write to `outputs/codex_findings/m10_v6_review/findings.md`:

```markdown
# Codex final review of M-10 v6

## Verdict
GREEN / PARTIAL / DISAGREE

## v5 leftover fixes
- [x/no] Vocab gap (composite/individual) closed
- [x/no] Multi-word kw cross-hit closed via contiguous subseq match

## Final word
GREEN to lock M-10 + proceed to M-11 / PARTIAL with edits.
```

Be terse. Under 60 lines.
