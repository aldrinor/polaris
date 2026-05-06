M-10 v4 — final GREEN check round 2.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-10 v3 verdict: PARTIAL. New bypass: real drug + scaffold-
overlap + nonsense suffix still routed:
- "Dulaglutide phase 3 trial outcomes for video game addiction" → 0.75
- "Atorvastatin efficacy for engine lubrication" → 0.70
- "Empagliflozin cardiovascular outcomes meta-analysis in server uptime" → 0.78
- "Cardiovascular safety of GLP-1 receptor agonists for printer firmware" → 0.87

Root cause: jaccard didn't penalize unrecognized content tokens.

## What changed in v4

`template_classifier.py`:
- New `_alien_tokens()` helper computes
  (stopword-filtered query) − (tokens of matched drug+medical keywords).
- Tier A (ROUTED) now requires ALL THREE:
    (1) ≥1 drug_keyword hit
    (2) example_jaccard ≥ 0.30
    (3) alien_tokens count ≤ 1
- Tier B drug-only path caps at 0.45 when alien > 1 (the score
  doesn't drift toward floor_high for nonsense queries).
- Rationale message now surfaces alien-count when relevant
  ("query contains N unrecognized content tokens beyond what the
  catalog covers").

`template_catalog.py`:
- `medical_keywords` expanded substantially. Added pharmacological
  vocabulary (receptor/agonist/antagonist singular+plural,
  inhibitor, modulator, statin, ssri, ace inhibitor); outcome
  words (outcome/outcomes, endpoint/endpoints, result/results,
  rate/rates, ratio, response/responder); patient-population words
  (subject, participant, cohort, adult/child/infant/elderly/
  geriatric/pediatric); conditions (heart failure, atrial
  fibrillation, prediabetes, t2dm/t1dm, hypercholesterolemia, copd,
  asthma, ckd, esrd); trial-methodology variants (trials, review/
  reviews, analysis/analyses); broader words (long-term,
  short-term, effects, dose/dosage/dosing).

The vocab expansion is critical: legitimate queries should score
**0 alien tokens** so the slack-of-1 in the gate covers natural
phrasing variation, not gaps in catalog coverage.

Tests: 6 new regression cases for the v3 bypass class. Phase B suite
200 → 206 green.

Manual verification on your exact v3 bypasses:
  dulaglutide + video game addiction → operator_review (0.445)
  atorvastatin + engine lubrication  → operator_review (0.433)
  empagliflozin + server uptime      → operator_review (0.450)
  glp-1 + printer firmware           → operator_review (0.450)
True positives still route at confidence 1.00:
  tirzepatide + diabetes
  metformin + diabetes
  glp-1 + cardiovascular
  empagliflozin + heart failure
  liraglutide + obesity
  dulaglutide + diabetes
  atorvastatin + hypercholesterolemia

## Your job

Final verdict on M-10. GREEN / PARTIAL / DISAGREE.

Probe with:
- Single-alien-token bypasses (e.g. "tirzepatide for diabetes
  pleasingly" — 1 alien word, allowed by gate). Acceptable Phase B
  cost or new partial?
- Adversarial inputs: very long real-medical-vocab queries with a
  small alien tail; very short queries; queries with deliberate
  misspellings.
- Real-medical queries that might have unrecognized content that
  shouldn't be alien (i.e. our medical_keywords gaps). Drop me 3-5
  examples to add to the vocab if any.

If GREEN, M-10 is locked and Phase B can proceed to M-11 (bounded
upload + workspace data model).

## Output

Write to `outputs/codex_findings/m10_v4_review/findings.md`:

```markdown
# Codex final review of M-10 v4

## Verdict
GREEN / PARTIAL / DISAGREE

## Alien-token gate fix
- [x/no] All 4 v3 bypasses now ≤ OPERATOR_REVIEW
- [x/no] Cannot find a meaningful new exemplar-shape bypass
- [x/no] Vocabulary coverage adequate for legitimate queries

## Final word
GREEN to lock M-10 + proceed to M-11 / PARTIAL with edits.
```

Be terse. Under 60 lines.
