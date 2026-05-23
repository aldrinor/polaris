# Codex DECISION request — I-bug-776 (#817, URGENT): clinical corpus_inadequate persists after #812+#815

You are the DECISION-MAKER (CHARTER §1). Decide the fix DIRECTION + guardrails +
verification. This is the THIRD and FINAL layer of the dominant benchmark abort
(corpus_inadequate, 5/13 vectors). Clinical-safety + a methodology dimension.

## Context: two layers already fixed (Codex-approved, PR'd)
- #812 classification (PR #816): jacc->T1, escardio guidelines->T2, mdpi->T4. Verified.
- #815 fetch (PR #818): PMC BioC full text (JACC 54-char stub -> 62647 chars). Verified.
- Combined #812+#815 afib re-run STILL aborts: **T1=0, T1+T2=1** (need T1>=3, T2>=2).

## Root cause (grounded, this is layer 3)
The clinical template (`config/v6_templates/clinical.json`) requires
`min_sources_per_tier {T1:3, T2:2}`. T1 = regulatory/registry/PubMed PRIMARY
(FDA/EMA/HealthCanada/ClinicalTrials.gov/PubMed); T2 = Cochrane/BMJ/JAMA/Lancet.
The afib question ("current clinical guidelines for oral anticoagulation in NVAF")
surfaces GUIDELINES + REVIEWS (T2/T4), not the primary RCTs that populate T1.

The infra to fix this EXISTS: `primary_trial_expander.py` (M-35) adds
`"{trial_name}" {question}` queries from `per_query_primary_trial_anchors[slug]`
in `config/scope_templates/clinical.yaml`, wired into run_honest_sweep_r3.py. It
WORKS for `clinical_tirzepatide_t2dm` (SURPASS-1..6). But **afib / dd_novo /
dd_lilly have NO anchors** -> expander returns empty -> the pivotal AF trials
(ARISTOTLE apixaban / ROCKET-AF rivaroxaban / RE-LY dabigatran / ENGAGE-AF
edoxaban) are never sought -> T1<3 -> abort.

## Options (decide DIRECTION)
- **(b1) Demo-scoped anchors:** add `per_query_primary_trial_anchors` for the
  curated clinical/dd demo vectors (afib, dd_novo, dd_lilly). Uses existing M-35,
  ships the demo vectors now. Con: manual per-question; doesn't generalize to
  arbitrary user questions.
- **(b2) Dynamic trial-anchor discovery:** first-pass retrieval extracts trial
  acronyms from the guidelines/reviews (or ClinicalTrials.gov), then M-35-expands.
  Generalizes to any question; more work; risk of off-topic acronym noise.
- **(a) Adequacy calibration:** for guideline/recommendation-type questions, weight
  T2 (guidelines/SRs) + T3 (regulatory) and don't demand T1>=3 primary RCTs.
  PRISMA/GRADE: a guideline synthesis IS a secondary-evidence task. Con: a generic
  T1 relaxation could let thin clinical corpora pass (safety risk) — must be
  question-type-gated, not blanket.
- combo (e.g. b1 now for the demo + b2 as the general follow-up; or a+b).

## Constraints
- Clinical-safety: do NOT blanket-relax T1>=3 (a real drug-safety question needs
  primary trials). Any adequacy flex must be question-type-scoped + defensible.
- A top-tier answer (ChatGPT/Gemini) for a "current guidelines" question cites
  BOTH the guidelines AND the pivotal RCTs — so surfacing the RCTs (b) is the
  faithful fix, not just relaxing the bar.
- Demo is curated vectors (Carney). General product is arbitrary questions.

## Decide
1. Direction (b1 / b2 / a / combo)? Why, on clinical-safety + faithfulness grounds?
2. If b1: which vectors + a guardrail so anchors stay on-topic.
3. If a: how to scope the calibration to question-type WITHOUT a safety hole.
4. Verification (re-run which vectors; pass bar T1>=3/T1+T2>=5 + no thin-corpus laundering).
5. Anything mis-diagnosed?
Return a decision, not a menu.

## Files I have ALSO checked and they're clean
- primary_trial_expander.py (M-35, template-driven, returns [] when slug absent).
- clinical.yaml: only clinical_tirzepatide_t2dm has per_query_primary_trial_anchors.
- clinical.json: min T1>=3, T2>=2; T1=regulatory/registry/PubMed.
- #812 (classifier) + #815 (BioC fetch) both verified working in the combined run.
