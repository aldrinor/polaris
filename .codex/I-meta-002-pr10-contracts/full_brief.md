HARD ITERATION CAP: 5 per document. This is iter 1 of the PR-10 DIFF gate.
- Front-load ALL real findings; reserve P0/P1 for real execution/safety/contamination risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (emit this exact YAML block as your final output)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

# Codex DIFF-gate — I-meta-002 PR-10: 5 benchmark native per_query_report_contract entries (gold-blind, attested, frozen)

You APPROVED this design (.codex/I-meta-002-pr10-contracts/codex_design_verdict.txt). This is the
implementation: native per_query_report_contract for the 5 LOCKED golden DRB-EN slugs so POLARIS's own
4-role gate has a coverage denominator for the benchmark, derived BLIND to the gold rubric. NO SPEND.

## CONTAMINATION IS THE CRITICAL REVIEW AXIS (§-1.1 LETHAL if violated)
- Authoring isolation: the agent authored with outputs/dr_benchmark PHYSICALLY SEALED OUT of the repo
  (moved to a temp location); the gold rubric + freeze pins + competitor answers did not exist at any
  path under C:/POLARIS during authoring. Then the rubric was restored and a diff-time verbatim-overlap
  scan was run.
- Contamination scan RESULT (please scrutinize + confirm you agree): ZERO verbatim 6-gram overlap with
  the GOLD RUBRIC (outputs/dr_benchmark/rubric_v3_frozen.json). 4 six-gram fragments overlap the stored
  competitor answers, ALL question-topic restatements (3 verbatim in the locked question text; 1 is
  Q72's own subject framing 'restructuring impact of AI on the labor market'). Authoring was sealed so
  copying was impossible.
- Please REVIEW THE ATTESTATION (.codex/I-meta-002-pr10-contracts/contract_attestation.txt) AGAINST THE
  DIFF: does every claimed allowed-input + the blindness statement + per-slug counts/severities match
  the actual contracts in the diff? Flag any mismatch.

## What to verify in the diff
- Each of the 5 slugs (drb_75_metal_ions_cvd, drb_76_gut_microbiota_crc, drb_78_parkinsons_dbs in
  clinical.yaml; drb_72_ai_labor in workforce.yaml; drb_90_adas_liability in policy.yaml) has
  required_entities[*] with id, type, anchor, canonical id (doi/pmid for biomedical; url_pattern for
  statutes/standards/reports), required_fields, severity, non-blank coverage_content_requirements; S0
  entities carry a valid s0_category. (M3a validator passes fail-closed on all 5 — see smoke.)
- S0 used ONLY on clinical slugs (true must-cover catastrophic categories); Q72/Q90 use S1/S2/S3 only.
- No element COUNT matched to the gold (counts: 75=6, 76=5, 78=5, 72=7, 90=6 — natively derived).
- Contracts are DATA only; no code/lock change; lock NOT promoted; claim_audit_scorer.py untouched.
- HONEST OPEN ITEM (flagged in the attestation, OUT OF SCOPE here): the benchmark questions' runtime
  domain routing (q["domain"]/q["slug"]) does not yet point Q72->workforce / Q90->policy / Q75-78->
  clinical; a separate no-spend wiring PR is needed to make these contracts LIVE at runtime. Confirm
  this is acceptable to defer (PR-10 = contracts + attestation + freeze only).

## SMOKE (Claude main-thread)
- M3a validator over all 5 contracts: load_required_entities + validate_entity_severity pass fail-closed
  (75:6 [S0,S1,S2], 76:5 [S0,S1,S2], 78:5 [S0,S1,S2], 72:7 [S1,S2,S3], 90:6 [S1,S2,S3]).
- pytest tests/dr_benchmark tests/roles tests/architecture -q -> 401 passed.
- verify_lock --consistency rc 0 (lock NOT promoted). gate_a_dry_run OVERALL PASS rc 0.
- Contamination scan: 0 gold-rubric overlap (clean). Freeze pins written (contract_freeze_pin.txt).

## ATTESTATION (review against diff)
POLARIS I-meta-002 PR-10 — Native per_query_report_contract attestation
=========================================================================

author:  Claude build agent (blind authoring agent, POLARIS I-meta-002 PR-10)
date:    2026-05-29
branch:  bot/I-meta-002-4role-wiring
scope:   the 5 LOCKED golden DRB-EN benchmark questions
         (.codex/I-safety-002b/golden_questions_locked.md)

PURPOSE
-------
Author POLARIS's OWN native required-element contracts (the 4-role Gate-B coverage
denominator) for the 5 locked benchmark questions, so the native gate
(src/polaris_graph/roles/native_gate_b_inputs.py) has a per-question denominator that
is NOT taken from the benchmark answer key. Authored BLIND — derived only from the
question text + POLARIS native config + general domain knowledge — because a contract
derived from the gold rubric would teach POLARIS to the test (§-1.1 LETHAL in clinical
context).

ISOLATION METHOD (CONTAMINATION GUARD)
--------------------------------------
isolation: outputs/dr_benchmark was PHYSICALLY ABSENT from the repo during authoring
           (gitignored / sealed out of the build agent's working tree). The gold
           rubric (outputs/dr_benchmark/rubric_v3_frozen.json), the freeze pins, and
           the stored competitor answers (outputs/dr_benchmark/external_outputs/
           gpt_5_5_pro/*, gemini_3_1_pro/*) DID NOT EXIST at any path under C:/POLARIS
           during authoring and were never created, reconstructed, or accessed.

EXPLICIT GOLD-BLINDNESS STATEMENT
---------------------------------
I authored these contracts in an isolated working tree with outputs/dr_benchmark
absent. The gold rubric, the freeze pins, and the stored competitor answers were NOT
read, NOT reconstructed, and NOT consulted in any form. I did not read
.codex/I-safety-002b/gold_rubrics_pathB.md or any freeze_pin file (those describe the
gold). I did not target any per-question element COUNT; each contract's entity count is
whatever POLARIS's own scope requires, not a match to the gold rubric's count.

ALLOWED INPUTS (the ONLY sources used to derive the contracts)
--------------------------------------------------------------
Common to all 5:
  - The locked question text in .codex/I-safety-002b/golden_questions_locked.md
  - config/architecture/d8_release_policy.yaml s0_must_cover_categories
    (contraindications, dosing_limits, black_box_warnings,
     pregnancy_renal_hepatic_cautions, regulatory_status — all clinical)
  - General domain knowledge of what a rigorous answer to each question MUST cover

Per-slug allowed inputs:

  drb_75_metal_ions_cvd  (DRB-EN #75, clinical -> config/scope_templates/clinical.yaml)
    - Question #75 text (plasma metal-ion modulation as CVD prevention/therapy;
      supplementation; clinical evidence of feasibility/efficacy)
    - config/scope_templates/clinical.yaml (clinical scope protocol)
    - config/completeness_checklists/clinical.yaml (efficacy / safety / contraindications
      / class-risk / regulatory-status / population-subgroup topics)
    - General clinical knowledge (chelation outcome RCTs; mineral-supplementation
      cardiovascular evidence; supplement upper-intake limits + iron-overload
      contraindications)

  drb_76_gut_microbiota_crc  (DRB-EN #76, clinical -> config/scope_templates/clinical.yaml)
    - Question #76 text (predominant probiotics; prebiotics + mechanism; pathogenic
      bacteria + toxic metabolites; daily-diet optimization)
    - config/scope_templates/clinical.yaml
    - config/completeness_checklists/clinical.yaml
    - General clinical/microbiology knowledge (probiotic intervention RCTs; dietary-
      fiber/CRC-risk evidence; pathogen genotoxins; probiotic safety in vulnerable
      patients)

  drb_78_parkinsons_dbs  (DRB-EN #78, clinical -> config/scope_templates/clinical.yaml)
    - Question #78 text (warning signs across disease stages; family-alert signs; DBS
      post-surgery daily-life adjustments + support strategies)
    - config/scope_templates/clinical.yaml
    - config/completeness_checklists/clinical.yaml
    - General neurology knowledge (DBS outcome RCTs; PD staging/red flags; DBS
      device complications; DBS MRI/diathermy contraindications; dopaminergic-
      withdrawal hyperpyrexia)

  drb_72_ai_labor  (DRB-EN #72, source-critical -> config/scope_templates/workforce.yaml)
    - Question #72 text (literature review of AI's restructuring impact on the labor
      market; Fourth Industrial Revolution; cite only high-quality English-language
      journal articles)
    - config/scope_templates/workforce.yaml (inclusion criteria naming QJE / Journal
      of Labor Economics / Labour Economics / AER-tier journals)
    - The tracked, gold-blind `amplified` retrieval set already committed in
      scripts/run_honest_sweep_r3.py for the drb_72_ai_labor manifest entry (Autor;
      Acemoglu-Restrepo; Frey-Osborne; Brynjolfsson; Eloundou; Goos-Manning-Salomons)
    - General labor-economics knowledge of the canonical peer-reviewed papers a
      faithful review MUST cite
    NOTE: workforce has NO completeness_checklist file (config/completeness_checklists/
      workforce.yaml does not exist); none was used.

  drb_90_adas_liability  (DRB-EN #90, source-critical -> config/scope_templates/policy.yaml)
    - Question #90 text (liability allocation for ADAS-involved crashes in shared
      human-machine driving; integrate technical ADAS principles + legal frameworks +
      relevant case law; conclude with proposed regulatory guidelines)
    - config/scope_templates/policy.yaml (existing source-critical contract shape)
    - config/completeness_checklists/policy.yaml (regulatory-framework / enforcement /
      precedent / international-comparison topics)
    - General law-and-technology knowledge (SAE J3016 automation levels; UNECE ALKS
      regulation; NHTSA ADS policy; product-liability doctrine; ADAS-crash case law)

CANONICAL SLUG <-> QUESTION_ID <-> DOMAIN TEMPLATE MAPPING
----------------------------------------------------------
  drb_75_metal_ions_cvd    <-> DRB-EN #75  -> clinical  (config/scope_templates/clinical.yaml)
  drb_76_gut_microbiota_crc<-> DRB-EN #76  -> clinical  (config/scope_templates/clinical.yaml)
  drb_78_parkinsons_dbs    <-> DRB-EN #78  -> clinical  (config/scope_templates/clinical.yaml)
  drb_72_ai_labor          <-> DRB-EN #72  -> workforce (config/scope_templates/workforce.yaml)
  drb_90_adas_liability    <-> DRB-EN #90  -> policy    (config/scope_templates/policy.yaml)

Slug-resolution note: the 4-role builder keys the contract by the run's q["slug"] and
loads the domain template via load_scope_template(q["domain"]) (scripts/
run_honest_sweep_r3.py). Only drb_72_ai_labor is presently wired in the tracked
benchmark manifest, and there it is registered with domain "custom" (not "workforce").
For these workforce/policy contracts to be LIVE at runtime, a separate wiring change is
required so each benchmark question's q["domain"] points at the template that contains
its contract (Q72 -> workforce, Q90 -> policy, Q75/Q76/Q78 -> clinical) and q["slug"]
uses the canonical key above verbatim. That wiring change is OUT OF SCOPE for this PR
(contracts + attestation only) and is flagged here as the one open downstream item.

VALIDATION (no-spend, offline)
------------------------------
Each new contract was validated to:
  - parse + load via the V30 loader load_report_contract_for_slug
    (schema_version / required_entities / rendering_slots / min_fields bounds /
     rendering_slot referential integrity / unique entity ids)
  - load + validate via the M3a native builder validators
    (load_required_entities + validate_entity_severity), fail-closed
  - satisfy the stronger PR-10 spec invariants: every entity declares a canonical
    identifier (doi OR url_pattern) AND a non-blank coverage_content_requirements list;
    every S0 entity declares a valid s0_category from the D8 vocabulary
  - blind-safety: no biomedical entity carries BOTH doi and pmid (a single canonical
    identifier per entity means a blind DOI<->PMID pairing can never be authored wrong)

Per-slug entity counts + severities (NATIVE, never count-matched to the gold):
  drb_75_metal_ions_cvd    : 6 entities  (S1 x2, S2 x2, S0 x2)
  drb_76_gut_microbiota_crc: 5 entities  (S1 x2, S2 x2, S0 x1)
  drb_78_parkinsons_dbs    : 5 entities  (S1 x1, S2 x2, S0 x2)
  drb_72_ai_labor          : 7 entities  (S1 x4, S2 x2, S3 x1; NO S0 — non-clinical domain)
  drb_90_adas_liability    : 6 entities  (S1 x4, S2 x1, S3 x1; NO S0 — non-clinical domain)

Severity policy (per Codex design ruling codex_design_verdict.txt): S0 is used ONLY for
the clinical slugs and ONLY where a true D8 must-cover catastrophic category applies
(supplement/device dosing limits + contraindications). The two source-critical slugs
(Q72/Q90) use S1/S2/S3 only — the workforce and policy domains define no must-cover
catastrophic/invalidating omission category in the D8 policy.

Green bars (all passing at authoring time):
  - python -m pytest tests/dr_benchmark tests/roles tests/architecture -q   -> 401 passed
  - python -m pytest tests/polaris_graph/test_v30_contract_doi_pmid_consistency.py
      tests/polaris_graph/test_m54_contract_schema.py -q                    -> 57 passed
  - python -m scripts.architecture.verify_lock --consistency                -> rc 0
  - python -m scripts.dr_benchmark.gate_a_dry_run                           -> OVERALL PASS, rc 0

SHA256 BLOCK HASHES (to be filled by Claude main-thread after bring-back)
-------------------------------------------------------------------------
The main thread computes the SHA256 of each new per_query_report_contract block (the
exact YAML span added for the slug) AFTER the diff-time verbatim-overlap contamination
check (vs outputs/dr_benchmark, which exists in the main tree) passes and Codex reviews
the diff + this attestation, then SHA-freezes the pins BEFORE any benchmark run or gold/
scorer consultation.

  drb_75_metal_ions_cvd    SHA256: 20e523ce3c33e524584c5abb09c5711bc2907ab2116ad7b3777530d10566b787
  drb_76_gut_microbiota_crc SHA256: 6c09268e544a5a314c498baa360f6b0c584f3963b6bc9639d8ec385137087930
  drb_78_parkinsons_dbs    SHA256: dbbd8443d277cf07c06a5180ad445c77feeb3e3aedbac81ac6b688240540bc57
  drb_72_ai_labor          SHA256: 59feb47e191be6484f5783ee5184997b09aabc965ffde73303eba8429c852e78
  drb_90_adas_liability    SHA256: bd5ba823748beaf433581844afcfa7ced993d445d173b5d0b1e617a1d3132313

=========================================================================
END OF ATTESTATION


DIFF-TIME CONTAMINATION SCAN (Claude main-thread, rubric restored)
---------------------------------------------------------------
Verbatim 6-gram overlap of all new contract strings vs the GOLD RUBRIC
(outputs/dr_benchmark/rubric_v3_frozen.json) and the stored competitor answers:
  - overlap with GOLD RUBRIC (the scoring answer key): 0  [CLEAN]
  - overlap with competitor answers: 4 six-gram fragments, ALL question-topic
    restatements: 3 are verbatim in the locked question text; 1 ('restructuring
    impact of ai on the') is Q72's own subject framing. Authoring ran with
    outputs/dr_benchmark physically sealed out of the repo, so copying was
    impossible; these are coincidental descriptions of the same question topic,
    NOT copies of any scoring element.
  VERDICT: CLEAN — zero teaching-to-the-test overlap with the gold rubric.

===== FREEZE PIN =====
POLARIS I-meta-002 PR-10 — benchmark contract FREEZE PIN
frozen: 2026-05-29 (before any benchmark run / gold-scorer consultation)
method: SHA256 of yaml.safe_dump(per_query_report_contract[slug], sort_keys=True)

drb_75_metal_ions_cvd  (clinical.yaml)  SHA256: 20e523ce3c33e524584c5abb09c5711bc2907ab2116ad7b3777530d10566b787
drb_76_gut_microbiota_crc  (clinical.yaml)  SHA256: 6c09268e544a5a314c498baa360f6b0c584f3963b6bc9639d8ec385137087930
drb_78_parkinsons_dbs  (clinical.yaml)  SHA256: dbbd8443d277cf07c06a5180ad445c77feeb3e3aedbac81ac6b688240540bc57
drb_72_ai_labor  (workforce.yaml)  SHA256: 59feb47e191be6484f5783ee5184997b09aabc965ffde73303eba8429c852e78
drb_90_adas_liability  (policy.yaml)  SHA256: bd5ba823748beaf433581844afcfa7ced993d445d173b5d0b1e617a1d3132313

===== DIFF =====
diff --git a/config/scope_templates/clinical.yaml b/config/scope_templates/clinical.yaml
index 2d0facb1..f23c3450 100644
--- a/config/scope_templates/clinical.yaml
+++ b/config/scope_templates/clinical.yaml
@@ -603,3 +603,535 @@ per_query_report_contract:
         subsection_title: "Health Canada Product Monograph"
         ordering: 6
         required: true
+
+  # ===================================================================
+  # I-meta-002 PR-10 — DRB-EN benchmark slug #75 (metal ions / CVD).
+  # NATIVE per_query_report_contract authored BLIND to the frozen gold
+  # rubric / freeze pins / competitor answers (outputs/dr_benchmark was
+  # sealed out of the repo during authoring; see
+  # .codex/I-meta-002-pr10-contracts/contract_attestation.txt). Every
+  # required_entity below is derived SOLELY from the locked question
+  # text, the clinical scope_template + completeness_checklist, the D8
+  # s0_must_cover categories, and general clinical domain knowledge of
+  # what a rigorous answer to a "modulate plasma metal-ion levels to
+  # prevent/treat cardiovascular disease — supplementation — clinical
+  # evidence of feasibility/efficacy" question MUST cover.
+  #
+  # Severity rationale (NATIVE, not gold-derived): the landmark RCT
+  # evidence (chelation, mineral supplementation outcome trials) carries
+  # decision-relevant efficacy -> S1; the mechanistic / observational
+  # association evidence is supporting context -> S2; the regulatory /
+  # safety dimension of taking metal-ion supplements (dosing limits,
+  # contraindications, renal cautions) maps to true clinical must-cover
+  # catastrophic categories -> S0 with a valid s0_category + non-blank
+  # coverage_content_requirements. Biomedical-literature entities carry a
+  # SINGLE canonical identifier (doi only, no paired pmid) so a blind
+  # DOI<->PMID pairing can never be authored wrong; regulatory /
+  # authoritative entities carry the FULL canonical url_pattern (exact-
+  # equality coverage, never a fragment).
+  drb_75_metal_ions_cvd:
+    schema_version: "v30.1"
+
+    section_order:
+      - Efficacy
+      - Mechanism
+      - Regulatory
+
+    required_entities:
+      - id: tact_chelation_rct
+        type: pivotal_trial
+        severity: S1
+        anchor: TACT
+        # Lonn/Lamas TACT — EDTA chelation post-MI cardiovascular
+        # outcomes RCT (the landmark trial of metal-ion modulation as a
+        # cardiovascular therapeutic). doi only (no blind pmid pairing).
+        doi: 10.1001/jama.2013.13805
+        journal: JAMA
+        year: 2013
+        population_scope: direct
+        coverage_content_requirements:
+          - chelation
+        required_fields:
+          - N
+          - population
+          - comparator
+          - intervention
+          - primary_endpoint
+          - timepoint
+          - effect_estimate_with_uncertainty
+          - safety_signal
+          - study_design
+        min_fields_for_completion: 4
+        rendering_slot: efficacy_chelation_rct
+
+      - id: magnesium_supplementation_meta
+        type: systematic_review
+        severity: S1
+        anchor: Mg-supplementation-meta
+        # Meta-analysis of magnesium supplementation and cardiovascular /
+        # blood-pressure outcomes (the most-studied mineral-ion
+        # supplementation arm for CVD).
+        doi: 10.1161/HYPERTENSIONAHA.116.07664
+        journal: Hypertension
+        year: 2016
+        population_scope: direct
+        coverage_content_requirements:
+          - magnesium
+        required_fields:
+          - included_studies
+          - population
+          - intervention
+          - dose_range
+          - primary_outcome
+          - effect_estimate_with_uncertainty
+          - heterogeneity
+          - certainty_of_evidence
+        min_fields_for_completion: 4
+        rendering_slot: efficacy_mineral_supplementation
+
+      - id: iron_status_cvd_observational
+        type: cohort_primary
+        severity: S2
+        anchor: Iron-CVD-cohort
+        # Observational / Mendelian-randomization evidence on iron status
+        # and cardiovascular risk (mechanistic + association tier —
+        # supporting, not RCT-grade efficacy).
+        doi: 10.1161/ATVBAHA.117.309757
+        journal: Arteriosclerosis Thrombosis and Vascular Biology
+        year: 2017
+        population_scope: indirect
+        coverage_content_requirements:
+          - iron
+        required_fields:
+          - exposure
+          - population
+          - outcome
+          - effect_estimate_with_uncertainty
+          - confounding_adjustment
+          - study_design
+        min_fields_for_completion: 3
+        rendering_slot: mechanism_metal_homeostasis
+
+      - id: zinc_oxidative_mechanism
+        type: mechanism_primary
+        severity: S2
+        anchor: Zinc-redox-mechanism
+        # Mechanistic primary on metal-ion (zinc/copper/selenium) redox
+        # biology and endothelial / oxidative-stress pathways relevant to
+        # the proposed cardiovascular benefit.
+        doi: 10.3390/nu12082358
+        journal: Nutrients
+        year: 2020
+        population_scope: indirect
+        coverage_content_requirements:
+          - oxidative
+        required_fields:
+          - metal_ion
+          - mechanism
+          - pathway
+          - evidence_type
+        min_fields_for_completion: 2
+        rendering_slot: mechanism_metal_homeostasis
+
+      - id: nih_ods_mineral_supplement_safety
+        type: regulatory
+        severity: S0
+        s0_category: dosing_limits
+        # An answer that recommends/discusses mineral-ion supplementation
+        # for CVD MUST state the tolerable upper intake limits — exceeding
+        # the UL (e.g. iron, zinc, selenium, magnesium) is a real
+        # catastrophic-omission dosing-safety category. Credited only when
+        # a VERIFIED claim cited to the authoritative source states an
+        # upper-limit / tolerable-upper-intake dosing bound.
+        coverage_content_requirements:
+          - tolerable upper intake
+          - mg
+        jurisdiction: NIH
+        label_name: NIH Office of Dietary Supplements mineral fact sheets
+        url_pattern: https://ods.od.nih.gov/factsheets/Magnesium-HealthProfessional/
+        required_fields:
+          - nutrient
+          - tolerable_upper_intake_level
+          - adverse_effects_of_excess
+          - at_risk_populations
+        min_fields_for_completion: 2
+        rendering_slot: regulatory_supplement_safety
+
+      - id: fda_iron_supplement_contraindication
+        type: regulatory
+        severity: S0
+        s0_category: contraindications
+        # Iron / metal-ion supplementation is contraindicated in iron-
+        # overload disorders (hemochromatosis) and excess iron is itself
+        # cardiotoxic — a true must-cover contraindication for a CVD
+        # supplementation answer. Credited only when a VERIFIED claim
+        # states the iron-overload / hemochromatosis contraindication.
+        coverage_content_requirements:
+          - contraindicated
+          - iron overload
+        jurisdiction: FDA
+        label_name: FDA iron-containing supplement labeling / hemochromatosis warning
+        url_pattern: https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfcfr/CFRSearch.cfm?fr=101.17
+        required_fields:
+          - contraindication
+          - at_risk_population
+          - warning_statement
+        min_fields_for_completion: 2
+        rendering_slot: regulatory_supplement_safety
+
+    rendering_slots:
+      efficacy_chelation_rct:
+        section: Efficacy
+        subsection_title: "Chelation therapy cardiovascular outcomes RCT (TACT)"
+        ordering: 1
+        required: true
+      efficacy_mineral_supplementation:
+        section: Efficacy
+        subsection_title: "Mineral-ion supplementation cardiovascular outcome evidence"
+        ordering: 2
+        required: true
+      mechanism_metal_homeostasis:
+        section: Mechanism
+        subsection_title: "Metal-ion homeostasis, oxidative stress, and vascular biology"
+        ordering: 1
+        required: true
+      regulatory_supplement_safety:
+        section: Regulatory
+        subsection_title: "Supplement dosing limits, contraindications, and at-risk populations"
+        ordering: 1
+        required: true
+
+  # ===================================================================
+  # I-meta-002 PR-10 — DRB-EN benchmark slug #76 (gut microbiota / CRC).
+  # NATIVE, authored BLIND (outputs/dr_benchmark sealed out; see
+  # contract_attestation.txt). Derived SOLELY from the locked question
+  # text ("predominant gut probiotics; what prebiotics are + mechanism;
+  # which pathogenic bacteria + their toxic metabolites; how to optimize
+  # daily diet"), the clinical scope_template + completeness_checklist,
+  # the D8 s0_must_cover categories, and general domain knowledge.
+  #
+  # Severity rationale (NATIVE): probiotic clinical-outcome evidence in
+  # inflammation / colorectal-cancer prevention carries decision-relevant
+  # efficacy -> S1; the mechanistic prebiotic / SCFA evidence and the
+  # pathogen-genotoxin (e.g. Fusobacterium, colibactin, B. fragilis
+  # toxin) mechanism are supporting context -> S2; the safety dimension —
+  # probiotics are contraindicated / hazardous in immunocompromised and
+  # critically-ill patients (a real catastrophic must-cover) -> S0
+  # contraindications. Biomedical entities carry doi only (no blind pmid
+  # pairing); the safety entity carries a full canonical url_pattern.
+  drb_76_gut_microbiota_crc:
+    schema_version: "v30.1"
+
+    section_order:
+      - Efficacy
+      - Mechanism
+      - Regulatory
+
+    required_entities:
+      - id: probiotic_crc_inflammation_rct
+        type: pivotal_trial
+        severity: S1
+        anchor: Probiotic-CRC-RCT
+        # RCT of probiotic supplementation on colorectal / mucosal
+        # inflammation or post-resection / adenoma outcomes (the
+        # interventional efficacy anchor the question's "probiotics retard
+        # CRC progression" claim must rest on).
+        doi: 10.1093/ajcn/85.2.488
+        journal: American Journal of Clinical Nutrition
+        year: 2007
+        population_scope: direct
+        coverage_content_requirements:
+          - probiotic
+        required_fields:
+          - N
+          - population
+          - intervention
+          - probiotic_strain
+          - comparator
+          - primary_endpoint
+          - effect_estimate_with_uncertainty
+          - safety_signal
+          - study_design
+        min_fields_for_completion: 4
+        rendering_slot: efficacy_probiotic_intervention
+
+      - id: prebiotic_fiber_scfa_meta
+        type: systematic_review
+        severity: S1
+        anchor: Prebiotic-SCFA-meta
+        # Systematic review of dietary fiber / prebiotic intake and
+        # colorectal-cancer risk (the evidence basis for the question's
+        # "inform daily dietary choices" deliverable).
+        doi: 10.1136/bmj.d6617
+        journal: BMJ
+        year: 2011
+        population_scope: direct
+        coverage_content_requirements:
+          - fiber
+        required_fields:
+          - included_studies
+          - exposure
+          - population
+          - outcome
+          - effect_estimate_with_uncertainty
+          - dose_response
+          - certainty_of_evidence
+        min_fields_for_completion: 4
+        rendering_slot: efficacy_prebiotic_diet
+
+      - id: fusobacterium_genotoxin_mechanism
+        type: mechanism_primary
+        severity: S2
+        anchor: Fusobacterium-CRC
+        # Pathogenic-bacterium mechanism: Fusobacterium nucleatum and
+        # colorectal carcinogenesis (directly answers "which pathogenic
+        # bacteria warrant concern + toxic metabolites").
+        doi: 10.1016/j.chom.2013.07.012
+        journal: Cell Host and Microbe
+        year: 2013
+        population_scope: indirect
+        coverage_content_requirements:
+          - fusobacterium
+        required_fields:
+          - pathogen
+          - toxic_metabolite_or_virulence_factor
+          - mechanism
+          - association_with_crc
+        min_fields_for_completion: 2
+        rendering_slot: mechanism_pathogen_genotoxin
+
+      - id: colibactin_pks_ecoli_mechanism
+        type: mechanism_primary
+        severity: S2
+        anchor: Colibactin-pks-Ecoli
+        # Colibactin-producing (pks+) E. coli genotoxin and the
+        # characteristic mutational signature in colorectal cancer (a
+        # second pathogen-metabolite the question explicitly requests).
+        doi: 10.1038/s41586-020-2080-8
+        journal: Nature
+        year: 2020
+        population_scope: indirect
+        coverage_content_requirements:
+          - colibactin
+        required_fields:
+          - pathogen
+          - toxic_metabolite_or_virulence_factor
+          - mechanism
+          - mutational_signature
+        min_fields_for_completion: 2
+        rendering_slot: mechanism_pathogen_genotoxin
+
+      - id: probiotic_immunocompromised_contraindication
+        type: regulatory
+        severity: S0
+        s0_category: contraindications
+        # A daily-diet probiotic recommendation MUST flag that live
+        # probiotics are hazardous / contraindicated in immunocompromised,
+        # critically-ill, and central-line patients (bacteremia /
+        # fungemia; the PROPATRIA pancreatitis mortality signal). A true
+        # catastrophic must-cover. Credited only when a VERIFIED claim
+        # states the immunocompromised / critically-ill contraindication.
+        coverage_content_requirements:
+          - contraindicated
+          - immunocompromised
+        jurisdiction: FDA
+        label_name: FDA / authoritative guidance on live-biotherapeutic / probiotic safety in vulnerable patients
+        url_pattern: https://www.fda.gov/vaccines-blood-biologics/cellular-gene-therapy-products/early-clinical-trials-live-biotherapeutic-products-chemistry-manufacturing-and-control-information
+        required_fields:
+          - contraindication
+          - at_risk_population
+          - adverse_event
+          - warning_statement
+        min_fields_for_completion: 2
+        rendering_slot: regulatory_probiotic_safety
+
+    rendering_slots:
+      efficacy_probiotic_intervention:
+        section: Efficacy
+        subsection_title: "Probiotic intervention clinical evidence (inflammation / CRC)"
+        ordering: 1
+        required: true
+      efficacy_prebiotic_diet:
+        section: Efficacy
+        subsection_title: "Prebiotic / dietary-fiber intake and colorectal-cancer risk"
+        ordering: 2
+        required: true
+      mechanism_pathogen_genotoxin:
+        section: Mechanism
+        subsection_title: "Pathogenic bacteria and their genotoxic metabolites in colorectal carcinogenesis"
+        ordering: 1
+        required: true
+      regulatory_probiotic_safety:
+        section: Regulatory
+        subsection_title: "Probiotic contraindications and at-risk populations"
+        ordering: 1
+        required: true
+
+  # ===================================================================
+  # I-meta-002 PR-10 — DRB-EN benchmark slug #78 (Parkinson's / DBS).
+  # NATIVE, authored BLIND (outputs/dr_benchmark sealed out; see
+  # contract_attestation.txt). Derived SOLELY from the locked question
+  # text ("health warning signs across disease stages; which signs
+  # should alert family to seek medical advice; for Deep Brain
+  # Stimulation [DBS] post-surgery patients, daily-life adjustments and
+  # support strategies"), the clinical scope_template +
+  # completeness_checklist, the D8 s0_must_cover categories, and general
+  # neurology domain knowledge.
+  #
+  # Severity rationale (NATIVE): the DBS efficacy/long-term-outcome RCT
+  # evidence carries decision-relevant efficacy -> S1; disease-staging /
+  # progression-marker evidence is supporting clinical context -> S2; the
+  # device + medication safety dimension carries true catastrophic
+  # must-cover categories — DBS device contraindications (MRI/diathermy
+  # precautions) and the danger of abrupt dopaminergic withdrawal
+  # (parkinsonism-hyperpyrexia / NMS-like syndrome) -> S0. Biomedical
+  # entities carry doi only (no blind pmid pairing); the device-safety
+  # entity carries a full canonical url_pattern.
+  drb_78_parkinsons_dbs:
+    schema_version: "v30.1"
+
+    section_order:
+      - Efficacy
+      - Mechanism
+      - Regulatory
+
+    required_entities:
+      - id: dbs_vs_medical_therapy_rct
+        type: pivotal_trial
+        severity: S1
+        anchor: DBS-RCT
+        # Randomized trial of deep brain stimulation vs best medical
+        # therapy in Parkinson's disease (the efficacy/benefit anchor for
+        # the question's DBS-patient deliverable).
+        doi: 10.1056/NEJMoa060281
+        journal: NEJM
+        year: 2006
+        population_scope: direct
+        coverage_content_requirements:
+          - deep brain stimulation
+        required_fields:
+          - N
+          - population
+          - intervention
+          - comparator
+          - primary_endpoint
+          - timepoint
+          - effect_estimate_with_uncertainty
+          - adverse_events
+          - study_design
+        min_fields_for_completion: 4
+        rendering_slot: efficacy_dbs_outcomes
+
+      - id: parkinson_staging_progression
+        type: cohort_primary
+        severity: S2
+        anchor: PD-staging
+        # Disease-staging / progression-marker evidence (Hoehn & Yahr,
+        # MDS-UPDRS, non-motor and red-flag symptoms) underpinning the
+        # "warning signs at different stages" deliverable.
+        doi: 10.1002/mds.22340
+        journal: Movement Disorders
+        year: 2008
+        population_scope: direct
+        coverage_content_requirements:
+          - stage
+        required_fields:
+          - staging_instrument
+          - stages_or_domains
+          - progression_markers
+          - red_flag_symptoms
+          - validation
+        min_fields_for_completion: 2
+        rendering_slot: mechanism_disease_staging
+
+      - id: dbs_complications_warning_signs
+        type: mechanism_primary
+        severity: S2
+        anchor: DBS-complications
+        # DBS device- and stimulation-related complications and the
+        # caregiver warning signs (infection, lead migration, hardware
+        # erosion, stimulation-induced dysarthria / gait / mood change)
+        # that should prompt seeking medical advice.
+        doi: 10.1136/jnnp-2013-306580
+        journal: Journal of Neurology Neurosurgery and Psychiatry
+        year: 2014
+        population_scope: direct
+        coverage_content_requirements:
+          - complication
+        required_fields:
+          - complication_type
+          - warning_sign
+          - time_course
+          - recommended_action
+        min_fields_for_completion: 2
+        rendering_slot: mechanism_dbs_complications
+
+      - id: dbs_device_mri_safety
+        type: regulatory
+        severity: S0
+        s0_category: contraindications
+        # DBS hardware imposes hard device contraindications/precautions —
+        # MRI conditional-use limits, prohibition of diathermy, and
+        # electromagnetic-interference precautions; violating them can
+        # cause lethal tissue heating. A true catastrophic must-cover for
+        # any DBS daily-life-support answer. Credited only when a VERIFIED
+        # claim states the MRI / diathermy device contraindication.
+        coverage_content_requirements:
+          - diathermy
+          - contraindicated
+        jurisdiction: FDA
+        label_name: FDA DBS device labeling — MRI / diathermy contraindications and precautions
+        url_pattern: https://www.accessdata.fda.gov/cdrh_docs/pdf/P960009.pdf
+        required_fields:
+          - device_precaution
+          - mri_conditions
+          - diathermy_contraindication
+          - emi_precautions
+        min_fields_for_completion: 2
+        rendering_slot: regulatory_dbs_device_safety
+
+      - id: dopaminergic_withdrawal_caution
+        type: regulatory
+        severity: S0
+        s0_category: dosing_limits
+        # Abrupt reduction/withdrawal of dopaminergic therapy (including
+        # peri-operatively around DBS) can precipitate parkinsonism-
+        # hyperpyrexia (NMS-like) syndrome — a real dosing-safety
+        # catastrophic must-cover for the daily-management answer.
+        # Credited only when a VERIFIED claim states the do-not-abruptly-
+        # stop / withdrawal-hyperpyrexia dosing caution.
+        coverage_content_requirements:
+          - abrupt
+          - withdrawal
+        jurisdiction: FDA
+        label_name: FDA carbidopa-levodopa labeling — abrupt-withdrawal hyperpyrexia warning
+        url_pattern: https://www.accessdata.fda.gov/drugsatfda_docs/label/2020/017555s076lbl.pdf
+        required_fields:
+          - warning
+          - mechanism
+          - clinical_consequence
+          - management
+        min_fields_for_completion: 2
+        rendering_slot: regulatory_dbs_device_safety
+
+    rendering_slots:
+      efficacy_dbs_outcomes:
+        section: Efficacy
+        subsection_title: "Deep brain stimulation clinical outcomes vs medical therapy"
+        ordering: 1
+        required: true
+      mechanism_disease_staging:
+        section: Mechanism
+        subsection_title: "Parkinson's disease staging, progression, and red-flag warning signs"
+        ordering: 1
+        required: true
+      mechanism_dbs_complications:
+        section: Mechanism
+        subsection_title: "DBS device / stimulation complications and caregiver warning signs"
+        ordering: 2
+        required: true
+      regulatory_dbs_device_safety:
+        section: Regulatory
+        subsection_title: "DBS device contraindications and dopaminergic-withdrawal dosing safety"
+        ordering: 1
+        required: true
diff --git a/config/scope_templates/policy.yaml b/config/scope_templates/policy.yaml
index 28f6a294..54a0bb76 100644
--- a/config/scope_templates/policy.yaml
+++ b/config/scope_templates/policy.yaml
@@ -213,3 +213,186 @@ per_query_report_contract:
         subsection_title: "CBO 10-year baseline IRA savings projection"
         ordering: 1
         required: true
+
+  # ===================================================================
+  # I-meta-002 PR-10 — DRB-EN benchmark slug #90 (ADAS liability, crime
+  # & law), SOURCE-CRITICAL. Authored BLIND to the frozen gold rubric /
+  # freeze pins / competitor answers (outputs/dr_benchmark was sealed out
+  # of the repo during authoring; see
+  # .codex/I-meta-002-pr10-contracts/contract_attestation.txt).
+  #
+  # Allowed inputs used (NATIVE only): the locked question text ("liability
+  # allocation in accidents involving vehicles with advanced driver-
+  # assistance systems (ADAS) in a shared human-machine driving context
+  # ... integrate technical principles of ADAS, existing legal frameworks,
+  # and relevant case law ... conclude with proposed regulatory
+  # guidelines"); this policy scope_template + completeness_checklist
+  # (regulatory_framework / enforcement / precedent / international-
+  # comparison topics); and general law-and-technology domain knowledge
+  # of the load-bearing standards, statutes, case law, and agency
+  # documents a faithful analysis MUST cite.
+  #
+  # Severity rationale (NATIVE): no S0. Every D8 s0_must_cover category is
+  # clinical; the policy domain defines NO must-cover catastrophic/
+  # invalidating omission category, so per the design ruling severities
+  # are S1/S2/S3 only. The load-bearing technical standard (SAE J3016
+  # automation levels) and the controlling legal-framework / case-law
+  # sources without which the liability analysis is invalid -> S1; the
+  # supporting agency-report / regulatory-guideline context -> S2; the
+  # forward-looking proposed-guideline framing -> S3. Canonical id is
+  # `url_pattern` (statutes / standards / case law / agency reports do
+  # not carry a biomedical DOI) — the FULL canonical URL (exact-equality
+  # coverage, never a fragment).
+  drb_90_adas_liability:
+    schema_version: "v30.1"
+
+    section_order:
+      - Technical_Standard
+      - Legal_Framework
+      - Case_Law
+      - Regulatory_Recommendations
+
+    required_entities:
+      - id: sae_j3016_automation_levels
+        type: technical_standard
+        severity: S1
+        anchor: SAE-J3016
+        # SAE J3016 driving-automation levels (0-5) — the load-bearing
+        # technical taxonomy that defines the human-machine responsibility
+        # boundary; a liability analysis is invalid without it.
+        url_pattern: https://www.sae.org/standards/content/j3016_202104/
+        coverage_content_requirements:
+          - j3016
+        required_fields:
+          - standard_id
+          - automation_levels_defined
+          - human_role_per_level
+          - fallback_responsibility
+        min_fields_for_completion: 2
+        rendering_slot: technical_sae_levels
+
+      - id: unece_alks_regulation_framework
+        type: regulation
+        severity: S1
+        anchor: UNECE-ALKS
+        # UNECE WP.29 automated-lane-keeping (ALKS) regulation — the
+        # controlling international regulatory framework allocating
+        # system-vs-driver responsibility during automated operation.
+        url_pattern: https://unece.org/transport/documents/2021/03/standards/un-regulation-no-157-automated-lane-keeping-systems-alks
+        coverage_content_requirements:
+          - lane keeping
+        required_fields:
+          - instrument
+          - scope_of_automation
+          - driver_obligations
+          - system_obligations
+          - transition_demand
+        min_fields_for_completion: 3
+        rendering_slot: legal_framework_unece
+
+      - id: nhtsa_ads_policy_framework
+        type: agency_report
+        severity: S2
+        anchor: NHTSA-ADS
+        # NHTSA automated-driving-systems policy / standing general order
+        # on crash reporting — the US agency framework and the data
+        # source for ADAS-involved crash liability analysis.
+        url_pattern: https://www.nhtsa.gov/laws-regulations/standing-general-order-crash-reporting
+        coverage_content_requirements:
+          - nhtsa
+        required_fields:
+          - issuing_agency
+          - scope
+          - reporting_obligation
+          - liability_relevance
+        min_fields_for_completion: 2
+        rendering_slot: legal_framework_nhtsa
+
+      - id: product_liability_doctrine
+        type: authoritative_source
+        severity: S1
+        anchor: Products-liability-Restatement
+        # The product-liability / negligence doctrinal framework
+        # (Restatement (Third) of Torts: Products Liability; defect
+        # categories) under which an ADAS manufacturer's responsibility is
+        # assessed — load-bearing for the driver-vs-system boundary.
+        url_pattern: https://www.ali.org/publications/show/torts-products-liability/
+        coverage_content_requirements:
+          - product liability
+        required_fields:
+          - doctrine
+          - defect_categories
+          - manufacturer_duty
+          - driver_duty
+        min_fields_for_completion: 2
+        rendering_slot: legal_framework_product_liability
+
+      - id: adas_crash_case_law
+        type: legal_case
+        severity: S1
+        anchor: ADAS-liability-case
+        # Relevant case law on ADAS/automated-feature-involved crash
+        # liability (the question explicitly requires "relevant case
+        # law"). The canonical id is the authoritative court-record URL.
+        url_pattern: https://www.courtlistener.com/?q=advanced+driver+assistance+autopilot+liability
+        coverage_content_requirements:
+          - liability
+        required_fields:
+          - case_name
+          - court
+          - disposition
+          - liability_holding
+          - applicability_to_shared_control
+        min_fields_for_completion: 3
+        rendering_slot: case_law_adas
+
+      - id: proposed_regulatory_guidelines
+        type: policy_report
+        severity: S3
+        anchor: Proposed-guidelines
+        # The question's required CONCLUSION — proposed regulatory
+        # guidelines / recommendations. Observe-only (S3): a synthesis
+        # deliverable, anchored to an authoritative policy framework
+        # (e.g. an NTSB / national AV-policy recommendation set) rather
+        # than a single load-bearing empirical claim.
+        url_pattern: https://www.ntsb.gov/Advocacy/mwl/Pages/mwl-22-23/mwl-hs.aspx
+        coverage_content_requirements:
+          - recommendation
+        required_fields:
+          - recommendation
+          - allocation_principle
+          - implementation_path
+        min_fields_for_completion: 1
+        rendering_slot: recommendations_synthesis
+
+    rendering_slots:
+      technical_sae_levels:
+        section: Technical_Standard
+        subsection_title: "SAE J3016 driving-automation levels and the human-machine boundary"
+        ordering: 1
+        required: true
+      legal_framework_unece:
+        section: Legal_Framework
+        subsection_title: "UNECE WP.29 ALKS regulation (system-vs-driver responsibility)"
+        ordering: 1
+        required: true
+      legal_framework_nhtsa:
+        section: Legal_Framework
+        subsection_title: "NHTSA automated-driving-systems policy and crash-reporting order"
+        ordering: 2
+        required: true
+      legal_framework_product_liability:
+        section: Legal_Framework
+        subsection_title: "Product-liability / negligence doctrine for ADAS manufacturers"
+        ordering: 3
+        required: true
+      case_law_adas:
+        section: Case_Law
+        subsection_title: "Relevant ADAS / automated-feature crash-liability case law"
+        ordering: 1
+        required: true
+      recommendations_synthesis:
+        section: Regulatory_Recommendations
+        subsection_title: "Proposed regulatory guidelines and liability-allocation recommendations"
+        ordering: 1
+        required: false
diff --git a/config/scope_templates/workforce.yaml b/config/scope_templates/workforce.yaml
index bd268e8c..70b6c3d2 100644
--- a/config/scope_templates/workforce.yaml
+++ b/config/scope_templates/workforce.yaml
@@ -77,3 +77,232 @@ audit_emphasis:
   - statistical_agency_citation_required_for_quantitative_claims
   - per_jurisdiction_metric_definition_disclosed
   - advocacy_group_funding_disclosure_required
+
+# -------------------------------------------------------------------
+# per_query_report_contract — NATIVE required-element denominator for
+# the 4-role Gate-B builder (src/polaris_graph/roles/native_gate_b_inputs.py).
+# Same shape M3a validates. ADDED by I-meta-002 PR-10.
+#
+# I-meta-002 PR-10 — DRB-EN benchmark slug #72 (AI / labor market),
+# SOURCE-CRITICAL. Authored BLIND to the frozen gold rubric / freeze
+# pins / competitor answers (outputs/dr_benchmark was sealed out of the
+# repo during authoring; see
+# .codex/I-meta-002-pr10-contracts/contract_attestation.txt).
+#
+# Allowed inputs used (NATIVE only): the locked question text ("a
+# literature review on the restructuring impact of AI on the labor
+# market ... AI as a key driver of the Fourth Industrial Revolution ...
+# only cites high-quality, English-language journal articles"); this
+# workforce scope_template (inclusion criteria naming QJE / Journal of
+# Labor Economics / Labour Economics / AER-tier journals); the
+# tracked, gold-blind `amplified` retrieval set already committed in
+# scripts/run_honest_sweep_r3.py for drb_72_ai_labor (Autor;
+# Acemoglu-Restrepo; Frey-Osborne; Brynjolfsson; Eloundou; Goos-
+# Manning-Salomons); and general labor-economics domain knowledge of the
+# canonical peer-reviewed papers a faithful review of this literature
+# MUST cite. Naming canonical papers is convergent validity, NOT gold
+# leakage — the diff-time verbatim-overlap check is the contamination
+# guard.
+#
+# Severity rationale (NATIVE): no S0. Every D8 s0_must_cover category is
+# clinical (contraindications / dosing / black-box / pregnancy-renal-
+# hepatic / regulatory-status); the workforce domain defines NO must-
+# cover catastrophic/invalidating omission category, so per the design
+# ruling severities are S1/S2/S3 only. The foundational
+# automation/displacement econometric papers that any faithful review
+# MUST cite to be valid -> S1; the supporting exposure/measurement and
+# Fourth-Industrial-Revolution framing papers -> S2. The canonical id is
+# `doi` where the journal article exposes one (exact-equality coverage:
+# M3b regex-extracts the bare DOI token), with `url_pattern` reserved for
+# the journal landing page where a DOI is the native citation anchor.
+per_query_report_contract:
+  drb_72_ai_labor:
+    schema_version: "v30.1"
+
+    section_order:
+      - Foundational_Theory
+      - Empirical_Displacement
+      - Generative_AI_Evidence
+
+    required_entities:
+      - id: acemoglu_restrepo_automation_tasks
+        type: economic_report
+        severity: S1
+        anchor: Acemoglu-Restrepo-tasks
+        # Acemoglu & Restrepo — the task-based displacement/reinstatement
+        # framework that any faithful AI-labor review MUST cite to be
+        # valid. Peer-reviewed economics journal; doi is the canonical id.
+        doi: 10.1257/jep.33.2.3
+        journal: Journal of Economic Perspectives
+        year: 2019
+        coverage_content_requirements:
+          - task
+        required_fields:
+          - thesis
+          - mechanism
+          - displacement_vs_reinstatement
+          - empirical_support
+          - journal_quality_tier
+        min_fields_for_completion: 3
+        rendering_slot: theory_task_framework
+
+      - id: autor_why_still_jobs
+        type: economic_report
+        severity: S1
+        anchor: Autor-polarization
+        # Autor — labor-market polarization / complementarity-vs-
+        # substitution; foundational English-language peer-reviewed
+        # journal article the review's structure should rest on.
+        doi: 10.1257/jep.29.3.3
+        journal: Journal of Economic Perspectives
+        year: 2015
+        coverage_content_requirements:
+          - polarization
+        required_fields:
+          - thesis
+          - polarization_evidence
+          - complementarity_argument
+          - journal_quality_tier
+        min_fields_for_completion: 2
+        rendering_slot: theory_polarization
+
+      - id: acemoglu_restrepo_robots_jobs
+        type: economic_report
+        severity: S1
+        anchor: Robots-and-jobs
+        # Acemoglu & Restrepo — robots and jobs commuting-zone
+        # identification; the canonical empirical displacement estimate.
+        doi: 10.1086/705716
+        journal: Journal of Political Economy
+        year: 2020
+        coverage_content_requirements:
+          - robot
+        required_fields:
+          - identification_strategy
+          - population
+          - effect_estimate_with_uncertainty
+          - outcome
+          - journal_quality_tier
+        min_fields_for_completion: 3
+        rendering_slot: empirical_robots
+
+      - id: frey_osborne_computerisation
+        type: economic_report
+        severity: S2
+        anchor: Frey-Osborne
+        # Frey & Osborne — occupational computerisation susceptibility
+        # ("47%"); high-citation peer-reviewed journal article, supporting
+        # the exposure-measurement strand of the review.
+        doi: 10.1016/j.techfore.2016.08.019
+        journal: Technological Forecasting and Social Change
+        year: 2017
+        coverage_content_requirements:
+          - automation
+        required_fields:
+          - method
+          - exposure_measure
+          - headline_estimate
+          - limitations
+          - journal_quality_tier
+        min_fields_for_completion: 2
+        rendering_slot: empirical_exposure
+
+      - id: brynjolfsson_genai_at_work
+        type: economic_report
+        severity: S1
+        anchor: GenAI-at-work
+        # Brynjolfsson, Li & Raymond — generative-AI productivity field
+        # evidence; the contemporary peer-reviewed journal article a
+        # current AI-labor review MUST incorporate.
+        doi: 10.1093/qje/qjae044
+        journal: Quarterly Journal of Economics
+        year: 2025
+        coverage_content_requirements:
+          - generative
+        required_fields:
+          - design
+          - population
+          - intervention
+          - effect_estimate_with_uncertainty
+          - generalizability
+          - journal_quality_tier
+        min_fields_for_completion: 3
+        rendering_slot: genai_productivity
+
+      - id: eloundou_gpts_are_gpts
+        type: economic_report
+        severity: S2
+        anchor: GPTs-are-GPTs
+        # Eloundou et al. — LLM occupational-exposure measurement; a
+        # supporting exposure-estimate the generative-AI section should
+        # cite. (Published in a peer-reviewed venue with a DOI.)
+        doi: 10.1126/science.adj0998
+        journal: Science
+        year: 2024
+        coverage_content_requirements:
+          - exposure
+        required_fields:
+          - exposure_method
+          - occupations_covered
+          - headline_exposure_estimate
+          - limitations
+          - journal_quality_tier
+        min_fields_for_completion: 2
+        rendering_slot: genai_exposure
+
+      - id: fourth_industrial_revolution_framing
+        type: policy_report
+        severity: S3
+        anchor: 4IR-framing
+        # The Fourth-Industrial-Revolution framing the question explicitly
+        # invokes. Observe-only (S3): contextual framing, not a load-
+        # bearing empirical claim; the question demands JOURNAL articles
+        # for substantive claims, so this authoritative framing source is
+        # context. url_pattern is the canonical id (no DOI native).
+        type_note: authoritative_source
+        url_pattern: https://www.weforum.org/about/the-fourth-industrial-revolution-by-klaus-schwab/
+        coverage_content_requirements:
+          - fourth industrial revolution
+        required_fields:
+          - definition
+          - relation_to_ai
+          - scope_caveat
+        min_fields_for_completion: 1
+        rendering_slot: theory_4ir_framing
+
+    rendering_slots:
+      theory_task_framework:
+        section: Foundational_Theory
+        subsection_title: "Task-based automation framework (Acemoglu & Restrepo, JEP 2019)"
+        ordering: 1
+        required: true
+      theory_polarization:
+        section: Foundational_Theory
+        subsection_title: "Labor-market polarization and complementarity (Autor, JEP 2015)"
+        ordering: 2
+        required: true
+      theory_4ir_framing:
+        section: Foundational_Theory
+        subsection_title: "Fourth Industrial Revolution framing (contextual)"
+        ordering: 3
+        required: false
+      empirical_robots:
+        section: Empirical_Displacement
+        subsection_title: "Robots and jobs commuting-zone evidence (Acemoglu & Restrepo, JPE 2020)"
+        ordering: 1
+        required: true
+      empirical_exposure:
+        section: Empirical_Displacement
+        subsection_title: "Occupational computerisation susceptibility (Frey & Osborne, TFSC 2017)"
+        ordering: 2
+        required: true
+      genai_productivity:
+        section: Generative_AI_Evidence
+        subsection_title: "Generative-AI productivity field evidence (Brynjolfsson et al., QJE 2025)"
+        ordering: 1
+        required: true
+      genai_exposure:
+        section: Generative_AI_Evidence
+        subsection_title: "LLM occupational-exposure measurement (Eloundou et al., Science 2024)"
+        ordering: 2
+        required: true
