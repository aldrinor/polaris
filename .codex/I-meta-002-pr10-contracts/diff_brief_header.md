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
