# Codex gate — broad-DR domain-general re-structure plan: code claims real, frontier quotes real, fix sound?

ADVERSARIAL §-1.1 auditor. The operator caught a prior doc using a METADATA artifact ("Gemini zero citations") — a
banned pattern. This redo (docs/broad_dr_domain_general_plan.md — READ IT FULLY) reads the BROAD frontier outputs
line-by-line and audits POLARIS's code line-by-line to find where it goes sub-par on a broad (non-clinical) Carney
question. Sub-agents may have erred — RE-VERIFY the file:line code claims and the competitor quotes yourself. This
commits to docs/ + GH #981 on APPROVE. Output YAML verdict FIRST. 5-cap; iter 1.

```yaml
verdict: APPROVE | REQUEST_CHANGES
fabricated_or_wrong_code_refs: [...]   # do the file:line claims (Gaps A-F) actually exist + say what's claimed?
fabricated_competitor_quotes: [...]    # spot-check several quoted frontier spans against the real files
overstated_or_wrong_diagnoses: [...]   # is any "clinical-locked" claim actually false (e.g. already domain-general)?
the_capability_gap_real: <true|false>  # is the "no quantified trade-off / cost-model" gap (§4, §6) a real POLARIS limitation?
fix_plan_sound: <true|false>           # are Steps 1-5 correctly targeted + open-weight-only + keep the faithfulness wedge?
the_one_correction: "<or none>"
honest_one_line: "<for the operator>"
```

## The 6 GAPS to verify (file:line — confirm each exists and says what's claimed)
- GAP A: pipeline_a_ui_adapter.py:112-122 substring _infer_domain ("ai"→tech, "pharma"→clinical); BUT the 3 sweep
  slugs hardcode domain (run_honest_sweep_r3.py:516,573,593) so it bites the UI/typed path NOT the frozen-slug sweep.
  VERIFY this nuance — it's the self-correction of the upstream framing.
- GAP B: domain_backends.py:443-455 no custom/ai_sovereignty/canada_us/workforce branch; _POLICY_SITE_FILTERS
  (:150-161) US-only, zero Canadian hosts.
- GAP C: tier_classifier.py:136-159 REGULATORY_DOMAINS are drug-regulators; grep claim = ZERO statcan/bankofcanada/
  osfi/cmhc/pbo/cdhowe/irpp in the file → Canadian economic authorities mis-tier UNKNOWN/T4. (deferred GH#406,
  corpus_adequacy_gate.py:124-128). VERIFY the grep claim yourself.
- GAP D: scope_gate.py:452-457 clinical_pico_unscoped→abort fires only when domain==clinical; corpus_adequacy_gate.py:
  71-78 min_t1_count=3 RCTs.
- GAP E: multi_section_generator.py:59-68 _ALLOWED_SECTIONS clinical; :259 "do not invent titles"; :371-372 off-list
  dropped; :450 fallback ["Efficacy","Safety","Comparative"]; :712-815 SURPASS/HbA1c claim-frame rules.
- GAP F: provenance_generator.py:957-964 no-token drop; :1032-1076 every-decimal-must-appear; :813-815,1137-1144
  >=2 content-word overlap; :1183-1291 entailment fail-closed on NEUTRAL → policy synthesis-prose mass-dropped →
  abort_no_verified_sections (run_honest_sweep_r3.py:2840-2851).

## Competitor quotes to spot-check (real spans?)
- ChatGPT q1 "beats AWS on-demand H100 pricing once utilization is above roughly 32%" (compare_chatgpt_q1.md:38);
  "512-GPU sovereign core ... US$61 million over 5 years vs ~US$123 million ... AWS" (:73); "modeling assumptions,
  not quoted federal procurement prices" (:36).
- Gemini q1 unhedged "60,000 ... GPUs / $9 billion injection / ALPHA-01 ... 504 ... B200 / 3.6 million units
  backordered" (compare_gemini_q1.md:7). Gemini dr.txt SURPASS-CVOT [30]→pubmed 41406444 with exact "12.2% (801) vs
  13.1% (862), HR 0.92; 95.3% CI 0.83-1.01".

## The decisive checks
1. Are the 6 gaps REAL (file:line exists + says what's claimed)? Any fabricated/wrong ref = fail (last doc had one).
2. Are the competitor quotes REAL spans (not invented)?
3. Is the §4/§6 "biggest risk = POLARIS has NO quantified-trade-off/cost-model capability, contract models trial
   entities not cost curves" a TRUE and important limitation, or overstated?
4. Is the fix plan (Steps 1-5: routing→backends→tiering→section-model→verification-synthesis-path) correctly targeted,
   open-weight-only (no model swap), and does it KEEP the faithfulness wedge (no-token-drop + numeric-match retained)?
5. Is the honest position (wins: verifiable sourcing/refusal; parity: prose/coverage; loses-first: source reach +
   quantified trade-off) fair?

## Your ruling
APPROVE iff all 6 code gaps verify real, competitor quotes real, capability-gap honest, fix sound + open-weight +
keeps the wedge. REQUEST_CHANGES with the specific fix otherwise. The single most important correction. One-liner.
