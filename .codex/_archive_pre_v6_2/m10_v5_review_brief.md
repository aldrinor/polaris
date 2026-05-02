M-10 v5 — final GREEN check round 3.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-10 v4 verdict: PARTIAL on single-alien slack:
- "tirzepatide for diabetes pleasingly" → routed 0.70
- "tirzepatide for diabetes printer" → routed 0.70
- "dulaglutide phase 3 trial outcomes for type 2 diabetes printer" → 0.95
- "empagliflozin ... heart failure printer" → 0.795
You said "alien <= 1 is still too permissive".

## What changed in v5

`template_classifier.py`:
- **_ROUTED_MAX_ALIEN_TOKENS = 0** (was 1). Tier A now strict —
  any unrecognized content token in the stopword-filtered query
  downgrades verdict to OPERATOR_REVIEW.
- Added clinical-context filler verbs to STOPWORDS: "use", "used",
  "using", "uses", "given", "taking", "received", "receiving".
  Did NOT add "alongside", "wherever", "whenever" — those remain
  alien so nonsense tails can't slip in.

`template_catalog.py`:
- medical_keywords expanded substantially. Includes all the
  vocabulary you suggested (renal, albuminuria, egfr,
  hospitalization, hfpef, hfref, polycystic ovary syndrome, pcos,
  adolescent, adolescents, triglyceride, triglycerides,
  apolipoprotein, apob) PLUS broader clinical-query vocabulary
  (profile, management, prevention, prophylaxis, screening,
  monitoring, diagnosis, prognosis, assessment, evaluation,
  comparison, comparative, combined, combination, maintenance,
  induction, chronic, acute, mild, moderate, severe, primary,
  secondary, onset, duration, guideline, evidence, remission,
  relapse, recurrence, kidney, dyslipidemia, arthritis,
  osteoarthritis, psoriasis, eczema, dermatitis, population,
  neonate, obese, diabetic, hypertensive). 80+ new entries.
- Added 2 new exemplars (renal outcomes + obesity management):
    "Empagliflozin renal outcomes in chronic kidney disease patients"
    "GLP-1 receptor agonists management of obesity in adults"

`tests/test_template_classifier.py`:
- 6 new v4 bypass regression cases.
- New invariant test: every scope_example in the catalog must
  self-route at confidence ≥ floor_high. This catches vocab gaps
  where an exemplar uses an unknown content token.

Tests: 62 → 69 in M-10 module. Phase B suite 206 → 213 green.

Verification:

Codex v4 bypasses (now blocked):
  pleasingly tail              → operator_review (0.433)
  printer tail                 → operator_review (0.433)
  long printer tail            → operator_review (0.450)
  cryptocurrency tail          → operator_review (0.438)
  wherever tail                → operator_review (0.450)

True positives still route:
  tirzepatide for diabetes              → routed (0.730)
  glp-1 cardiovascular                  → routed (0.730)
  metformin obesity                     → operator_review (0.425) — 2-token query is too underspecified for confident route, falls to review intentionally
  Renal outcomes empagliflozin CKD      → routed (0.936)
  Adolescent semaglutide use obesity    → routed (0.730)
  All 8 of the original exemplars + 2 new ones → routed (1.000) self-test passes

## Your job

Final verdict on M-10. GREEN / PARTIAL / DISAGREE.

Probe with:
- More single-alien-token bypasses (now strict alien=0; should
  catch all of them)
- Real-world clinical queries you can think of that should route
  but might trip the strict gate (vocab gaps)
- Adversarial queries with all-medical-vocab tokens but nonsense
  semantics
- Anything else

If GREEN, M-10 is locked and Phase B can proceed to M-11.

## Output

Write to `outputs/codex_findings/m10_v5_review/findings.md`:

```markdown
# Codex final review of M-10 v5

## Verdict
GREEN / PARTIAL / DISAGREE

## Strict alien-token gate
- [x/no] All 4 v4 single-alien bypasses now ≤ OPERATOR_REVIEW
- [x/no] Cannot find a meaningful new bypass
- [x/no] Vocabulary coverage adequate; legitimate queries still route

## Final word
GREEN to lock M-10 + proceed to M-11 / PARTIAL with edits.
```

Be terse. Under 60 lines.
