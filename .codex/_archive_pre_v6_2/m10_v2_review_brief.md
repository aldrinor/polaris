M-10 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-10 v1 verdict: DISAGREE on 4 reproducible false positives:
- "Safety profile of ibuprofen for back pain" → routed 0.72
- "What is the efficacy of turmeric for arthritis?" → routed 0.75
- "FDA approval pathway for new supplements" → routed 0.85
- "Meta-analysis of psychotherapy in depression" → routed 0.69

Root causes you identified:
1. Raw-token Jaccard counted stopwords/scaffold tokens
2. Tier B auto-routed on exemplar overlap alone
3. Catalog mixed broad medical words with strong route signals
4. Test suite missed exemplar-shape bypass class
5. Unicode hyphen not normalized

All five integrated in v2.

## What changed in v2

`template_catalog.py`:
- **Two-class keyword split**: `drug_keywords` (specific regulated
  drugs + drug classes — the STRONG gate) and `medical_keywords`
  (broad medical/regulatory/trial/condition — review-only).
  `scope_keywords` kept as @property union for backwards compat.
- Removed "FDA approval pathway for new diabetes drugs" exemplar
  (too generic — no specific drug named).
- `scope_summary` extended to explicitly list OUT-of-scope:
  supplements, vitamins, homeopathy, psychotherapy, non-pharmaceutical
  treatments, etc.

`template_classifier.py`:
- **Unicode hyphen normalize** at tokenize-time: U+2010..U+2015 +
  U+2212 → ASCII `-`. So "GLP‑1" (NBH) tokenizes the same as
  "GLP-1" (ASCII).
- **Stopword filter** applied to Jaccard inputs only (keyword
  matching keeps raw tokens). Stopword list is small + conservative
  (English question scaffold + function words + "new"/"any"/"some").
- **New tier cascade — drug-anchored**:
    Tier A (ROUTED): n_drug ≥ 1 AND example_jaccard ≥ 0.30
                     → score = 0.55 + 0.45*jaccard
    Tier B (OR):     n_drug ≥ 1 (no jaccard requirement)
                     → score = 0.40 + 0.10*jaccard
    Tier C (OR):     n_medical ≥ 3 AND ex_jac ≥ 0.20
                     → score = 0.40
    Tier D (OR):     n_medical ≥ 1
                     → score = 0.30 or 0.35
    Tier E (UNSUP):  weak overlap → 0.20 or 0.0
  **Without ≥1 drug_keyword hit, verdict cannot rise to ROUTED.**
- `RoutingCandidate` adds `drug_hits` + `medical_hits` (keyword_hits
  kept as union for backwards compat). `/route` API surfaces them
  separately so the operator-review UI can show "no specific drug
  named — confirm or supply one".

`tests/test_template_classifier.py`:
- New parametrized test covering all 4 of your reported false
  positives PLUS 6 additional non-drug interventions/wellness
  queries (vitamin D, acupuncture, CBT, curcumin, Mediterranean
  diet, yoga). All assert verdict ≠ ROUTED.
- New `test_routed_requires_drug_keyword_hit`: invariant that ROUTED
  verdicts always have ≥1 drug_hit on the top candidate.
- New `test_drug_hit_alone_does_not_route_without_jaccard`:
  "tirzepatide weather forecast" → operator_review.
- New `test_unicode_hyphen_normalized_in_drug_class_match`: ASCII /
  NBSP / endash variants of "GLP-1" all return same verdict.
- New `test_stopword_filter_disables_scaffold_jaccard`: pure-scaffold
  query confidence < floor_high.

Tests: 36 → 50 in M-10 module. Phase B suite: 180 → 194 green.

Manual verification on your exact false positives:
  ibuprofen + back pain        → operator_review (0.30)  drug=[]
  turmeric + arthritis         → operator_review (0.30)  drug=[]
  FDA + supplements            → operator_review (0.35)  drug=[]
  psychotherapy + depression   → operator_review (0.35)  drug=[]
True positives still route at confidence 1.00:
  tirzepatide + diabetes       → routed (1.00)  drug=['tirzepatide']
  metformin + diabetes         → routed (1.00)  drug=['metformin']
  GLP-1 cardiovascular         → routed (1.00)  drug=['glp-1']

## Your job

Final verdict on M-10. GREEN / PARTIAL / DISAGREE.

Quick verification:
- Are the 4 reported false positives + 6 similar non-drug
  interventions all OPERATOR_REVIEW or UNSUPPORTED?
- Can you find a NEW false positive that mimics exemplar shape AND
  hits a drug_keyword unintentionally? (e.g. abuse of the drug-
  class umbrella terms "biologic", "biosimilar", "monoclonal
  antibody"?)
- Stopword list adequate? Any obvious omissions / over-inclusions?
- Unicode hyphen normalize covers the common Unicode variants?
- Tier cascade — any path that auto-routes off-scope?

If GREEN, M-10 is locked and Phase B can proceed to M-11 (bounded
upload + workspace data model).

## Output

Write to `outputs/codex_findings/m10_v2_review/findings.md`:

```markdown
# Codex re-review of M-10 v2

## Verdict
GREEN / PARTIAL / DISAGREE

## False-positive class fixed
- [x/no] All 4 v1 bypasses now ≤ OPERATOR_REVIEW
- [x/no] Drug-class umbrella terms not abusable as new bypass
- [x/no] Stopword filter / hyphen normalize / drug-anchored gate
  collectively close the bypass pattern

## New issues
none / list

## Final word
GREEN to lock M-10 + proceed to M-11 / PARTIAL with edits.
```

Be terse. Under 100 lines.
