M-10 v7 — final GREEN check round 5.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-10 v6 verdict: PARTIAL on hyphen-joined compound modifiers
falling to operator_review:
- "Dulaglutide phase-3 trial outcomes for type 2 diabetes" → 0.45
- "Dulaglutide phase 3 trial outcomes for type-2 diabetes" → 0.45
- "Empagliflozin renal composite outcomes in chronic-kidney
   disease patients" → 0.45

Root cause: tokenizer kept hyphens within tokens, so "phase-3"
tokenized as one token and didn't match the multi-word kw "phase 3"
([phase, 3]) via contiguous subseq.

## What changed in v7

`template_classifier.py`:
- Tokenizer regex changed from `[a-z0-9][a-z0-9-]*` to `[a-z0-9]+`.
  Hyphens are now token boundaries.
- Drug class entries "glp-1", "sglt-2", "dpp-4" still work — they
  tokenize to multi-word kw_seqs and the query forms (which split
  the same way) match contiguously.
- Multi-word entries "double-blind", "meta-analysis", "long-term",
  "post-marketing", "placebo-controlled", "dose-response" all
  become multi-word contiguous matches; query forms with or
  without hyphen match identically.
- Unicode hyphen normalize (U+2010..U+2015, U+2212 → ASCII -)
  still runs first.

`tests/test_template_classifier.py`:
- 6 new parametrized regression cases for compound-modifier
  orthography (phase-3, type-2, chronic-kidney, GLP-1, etc.).

Phase B suite 216 → 222 green.

Verification:
  Dulaglutide phase-3 trial outcomes for type 2 diabetes        → routed (1.000)
  Dulaglutide phase 3 trial outcomes for type-2 diabetes        → routed (1.000)
  Empagliflozin renal composite outcomes in chronic-kidney      → routed (0.944)
    disease patients
  GLP-1 agonists for diabetes                                   → routed (0.743)
All previous bypasses (10 parametrized cases) still ≤ operator_review.
All true positives still route.

## Your job

Final verdict on M-10. GREEN / PARTIAL / DISAGREE.

Probe with anything you can think of. After 6 rounds of fix-test-
review the bypass surface should be tight. If you find something
new, please be specific about the example so we can fix it.

If GREEN, M-10 is locked and Phase B can proceed to M-11.

## Output

Write to `outputs/codex_findings/m10_v7_review/findings.md`:

```markdown
# Codex final review of M-10 v7

## Verdict
GREEN / PARTIAL / DISAGREE

## v6 hyphen-orthography fix
- [x/no] phase-3 / type-2 / chronic-kidney now route correctly
- [x/no] All previous bypasses still ≤ operator_review

## Final word
GREEN to lock M-10 + proceed to M-11 / PARTIAL with edits.
```

Be terse. Under 60 lines.
