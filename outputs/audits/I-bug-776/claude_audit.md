# Claude architect audit — I-bug-776 (#817) afib primary-trial anchors

## Root cause (3rd & final corpus_inadequate layer)
Combined #812 (classification) + #815 (fetch) afib re-run STILL aborted (T1=0):
a 'current clinical guidelines for NVAF anticoagulation' question surfaces
guidelines/reviews (T2/T4), not the primary RCTs (T1) the clinical template
demands (T1≥3, T2≥2). The M-35 primary_trial_expander (which surfaces pivotal
trials via per-slug anchors) had anchors ONLY for clinical_tirzepatide_t2dm; afib
had none → no pivotal AF trials sought → T1<3.

## Decision provenance (Codex = decision-maker)
`.codex/I-bug-776/decision_verdict.txt`: Codex decided b1 (per-slug anchors;
NO clinical.json relaxation; slug-scoped, no global fallback; molecule+indication-
specific; count T1 only if primary). Codex explicitly rejected a blanket adequacy
relaxation (safety hole).

## Implementation
Added to config/scope_templates/clinical.yaml:
- per_query_primary_trial_anchors[clinical_afib_anticoagulation]: ARISTOTLE,
  ROCKET-AF, RE-LY, ENGAGE-AF-TIMI-48 (the four NOAC-vs-warfarin pivotals).
- per_query_primary_trial_variants[...]: first-author+journal+drug hints.
Config-only; uses existing M-35 expander; tirzepatide anchors intact.

## Trial-fact accuracy (LAW II) — Codex fact-checked against NEJM DOIs
ARISTOTLE=apixaban/Granger/NEJM2011 (NEJMoa1107039); ROCKET-AF=rivaroxaban/Patel/
NEJM2011 (NEJMoa1009638); RE-LY=dabigatran/Connolly/NEJM2009 (NEJMoa0905561);
ENGAGE-AF-TIMI-48=edoxaban/Giugliano/NEJM2013 (NEJMoa1310907). All verified.

## Evidence
- Smoke: expand_primary_trial_queries(afib) → 8 queries (4 anchors × bare+variant);
  no-anchor slug → 0 (negative check); tirzepatide intact.
- Codex diff review: APPROVE iter-1 (zero P0/P1/P2, MERGE AUTHORIZED, trial facts
  verified against NEJM DOIs).

## Verdict
Code-correctness: APPROVE (Codex iter-1). **Remaining gate (LAW II empirical):**
combined #812+#815+#817 afib re-run must reach T1≥3 / T1+T2≥5 and ship (running).
This is the 3rd layer; the three together are the full clinical corpus_inadequate
fix. dd_novo (due_diligence domain) anchors are a follow-on; dd_lilly is a
separate template-mismatch (manufacturing question, no efficacy trials).
