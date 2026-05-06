M-20 v1 — first review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-20 begins Phase C catalog scaling. Per FINAL_PLAN.md the target
is 50+ curated templates. Phase B shipped a single template
(`v30_clinical`) plus the routing infrastructure (M-10). M-20 v1
adds the second and third templates AND the tie-detection
mechanism that the catalog growth makes necessary.

The router goal is unchanged: prevent off-scope queries from
silently routing to the wrong template (Risk #13). With multiple
templates that share the same drug (atorvastatin → both
v30_clinical and v30_clinical_cardio; statin → both), the new
failure mode is "routes to alphabetically first template instead
of the one that fits the query," which is just a different shape
of mis-routing.

## What changed in v1 (commit 211678b)

`src/polaris_graph/audit_ir/template_catalog.py`:
- `_V30_CLINICAL_ONCOLOGY` template added. drug_keywords cover:
  pembrolizumab/nivolumab/atezolizumab/durvalumab/ipilimumab,
  trastuzumab/pertuzumab, rituximab/obinutuzumab,
  bevacizumab/ramucirumab, cetuximab/panitumumab,
  imatinib/dasatinib/nilotinib, erlotinib/gefitinib/osimertinib,
  sorafenib/sunitinib, olaparib/rucaparib, venetoclax. Plus
  narrow class abbreviations (checkpoint inhibitor, PD-1/PD-L1,
  CAR-T, TKI, PARP, ADC). medical_keywords cover oncology-trial
  outcome vocabulary (ORR, PFS, OS, CR, PR), cancer types
  (NSCLC/SCLC/DLBCL/AML/CML/AML myeloid/lymphoid/lymphoblastic),
  and standard clinical-query content words.
- `_V30_CLINICAL_CARDIO` template added. drug_keywords cover:
  warfarin/apixaban/rivaroxaban/dabigatran/edoxaban,
  aspirin/clopidogrel/ticagrelor/prasugrel,
  lisinopril/enalapril/ramipril, valsartan/losartan/olmesartan,
  amlodipine/nifedipine, metoprolol/carvedilol/bisoprolol,
  furosemide/spironolactone, atorvastatin/rosuvastatin/simvastatin,
  ezetimibe, alirocumab/evolocumab, sacubitril/ivabradine,
  amiodarone/flecainide/sotalol. Class names: ACE inhibitor, ARB,
  beta blocker, CCB, statin, DOAC/NOAC, P2Y12, PCSK9, ARNI.
  medical_keywords cover cardiovascular outcomes/conditions
  (HFrEF/HFpEF/AFib/ASCVD/MACE/all-cause mortality/LDL/etc.).
- `TEMPLATE_CATALOG = (_V30_CLINICAL, _V30_CLINICAL_ONCOLOGY,
  _V30_CLINICAL_CARDIO)`.

`src/polaris_graph/audit_ir/template_classifier.py`:
- New constant `DEFAULT_TIE_MARGIN = 0.10`.
- `RouterConfig.tie_margin: float = DEFAULT_TIE_MARGIN` field.
- `RouterConfig.from_env()` reads `PG_TEMPLATE_ROUTER_TIE_MARGIN`
  (LAW VI) with garbage-fallback to default and clamp to [0, 1].
- In `classify_query` ROUTED branch (after sort by score desc):
  if `len(candidates) >= 2` and `top.score >= floor_high` and
  `top2.score >= floor_high` and `(top.score - top2.score) <
  tie_margin`, demote to `OPERATOR_REVIEW` with rationale that
  names both template_ids and their scores.

`tests/polaris_graph/test_template_classifier.py`:
- 6 new tests:
  * test_tie_detection_demotes_when_top_two_within_margin —
    synthetic two-template setup with identical exemplars; gap=0
    < tie_margin → operator_review with "Multiple templates" rationale.
  * test_tie_detection_does_not_fire_when_top2_below_floor_high —
    only top-1 above floor_high → ROUTED stays.
  * test_tie_detection_does_not_fire_when_gap_exceeds_margin —
    gap=~0.15, tie_margin=0.05 → ROUTED on top-1.
  * test_tie_margin_env_overridable — PG_TEMPLATE_ROUTER_TIE_MARGIN.
  * test_tie_margin_garbage_env_falls_back_to_default — error path.
  * test_real_catalog_has_no_unexpected_ties — every catalog
    template's scope_examples must NOT surface "Multiple templates"
    rationale in the live catalog.

Module: 71/71 classifier tests green; 27/27 run_diff tests green.

## Your job

Verdict on M-20 v1. GREEN / PARTIAL / DISAGREE.

I'm specifically asking you to look for:

1. **Bypass cases for the new templates.** Can a query that names
   an oncology drug AND has "diabetes" in it route to the wrong
   template? Or a non-clinical question with a checkpoint inhibitor
   name route via the new templates?
2. **Tie-detection holes.** Does the demotion fire on real-shape
   ambiguous queries? Does it accidentally over-fire on queries
   that should route cleanly? Are there queries where the right
   answer is template A but the router demotes because some
   irrelevant template B happens to score similarly?
3. **Self-routing invariant.** I added `test_real_catalog_has_no_
   unexpected_ties` — does that test catch the right failure mode,
   or is the assertion shape wrong?
4. **Catalog quality.** Are the new oncology/cardio templates
   sound? Drug coverage gaps? Wrong drug class assignments?
   medical_keywords too broad / too narrow?
5. **Anything else worth flagging before Phase C catalog growth
   continues to 50+ templates.**

If GREEN, M-20 locks (with a note that more templates will be added
in batches; each batch must keep test_real_catalog_has_no_
unexpected_ties green). Phase C proceeds to M-23.

## Output

Write to `outputs/codex_findings/m20_review/findings.md`:

```markdown
# Codex review of M-20 v1

## Verdict
GREEN / PARTIAL / DISAGREE

## Bypass cases tried
- [list 3-5 query strings tried and the router verdict]

## Tie-detection cases tried
- [list 2-3 ambiguous queries and verdicts]

## Catalog issues
- [drug coverage / keyword issues, or "none material"]

## Final word
GREEN to lock M-20 + proceed / PARTIAL with edits / DISAGREE.
```

Be terse. Under 120 lines.
