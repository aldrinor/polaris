M-10 v8 — final GREEN check round 6.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-10 v7 verdict: PARTIAL on orthography normalization gaps.
Said "the hyphen split fix is correct" — only 4 orthography variants
remained:
- "Dulaglutide phase III trial outcomes for type 2 diabetes" → 0.45
- "Dulaglutide phase 3 trial outcomes for type II diabetes" → 0.45
- "GLP1 agonists for diabetes" → 0.35
- "DPP4 inhibitors for type 2 diabetes" → 0.40

## What changed in v8

`template_classifier.py`:
- Added Roman→Arabic normalization in tokenizer:
    ii→2, iii→3, iv→4, vi→6, vii→7, viii→8, ix→9
  Single-char Romans (i/v/x) deliberately excluded — "i" is the
  pronoun (stopword), "v"/"x" too ambiguous.
- Added compact-drug-class normalization in tokenizer:
    glp1 → [glp, 1]
    sglt2 → [sglt, 2]
    dpp4 → [dpp, 4]
  Without this, "GLP1" tokenizes as one token while "GLP-1"
  tokenizes as [glp, 1] (after v6 hyphen split). The multi-word
  kw "glp-1" matched only the latter. Normalization unifies the
  orthographies.

`template_catalog.py`:
- Removed redundant hyphen-less drug-class entries; tokenizer now
  normalizes them to the hyphenated forms.

`tests/test_template_classifier.py`:
- 4 new parametrized regression cases (your exact 4 + a IV-Roman
  case "Phase IV trial of empagliflozin in heart failure").

Phase B suite 222 → 227 green.

Verification on your exact v7 cases:
  Dulaglutide phase III trial outcomes for type 2 diabetes  → routed (1.00)
  Dulaglutide phase 3 trial outcomes for type II diabetes   → routed (1.00)
  GLP1 agonists for diabetes                                → routed (0.743)
  DPP4 inhibitors for type 2 diabetes                       → routed (0.719)
All previous bypasses (16 parametrized) still ≤ operator_review.
All true positives still route.

## Your job

Final verdict on M-10. GREEN / PARTIAL / DISAGREE.

Probe with anything you can think of. After 7 rounds the bypass +
true-positive surface should be tight. If you find something,
include the exact reproducer.

If GREEN, M-10 is locked and Phase B can proceed to M-11.

## Output

Write to `outputs/codex_findings/m10_v8_review/findings.md`:

```markdown
# Codex final review of M-10 v8

## Verdict
GREEN / PARTIAL / DISAGREE

## v7 orthography fix
- [x/no] Roman-numeral phase/type forms route correctly
- [x/no] Compact drug-class forms (GLP1/DPP4) route correctly
- [x/no] All previous bypasses still ≤ operator_review

## Final word
GREEN to lock M-10 + proceed to M-11 / PARTIAL with edits.
```

Be terse. Under 60 lines.
