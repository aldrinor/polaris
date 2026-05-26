# Codex — refusal/gap rendering DESIGN brief (recommended_path #4)

## §8.3.1 cap directive (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Where we are

- atom_extractor force-APPROVE'd at iter-5 cap (commit `0e634997`, 52/52 tests)
- format_refusal_for_missing_atom() exists (your APPROVE_DESIGN template wording)
- format_atom_catalog_for_prompt() exists (compact catalog renderer)
- Step 3 (V4 Pro `_call_section` integration) is NEXT after this design call settles refusal-first

Per your iter-1 design verdict: `step_3_integration_order.refusal_first: YES, reasoning: "build refusal/gap rendering BEFORE V4 Pro wiring so we know what the failure mode actually looks like before wiring the call."` Honoring that.

## What needs to be designed

V4 Pro will be told to cite `atom_NNN` for factual claims. Some claims will have no atom. The question: how do we handle that AT OUTPUT TIME?

Three approaches:

### Approach A: Prompt-side only

V4 Pro is INSTRUCTED in its system prompt:
> "For any factual quantitative claim where you cannot find a supporting atom_NNN in the ATOM CATALOG, write exactly: 'Insufficient verified atom-level evidence from the cited corpus to support a claim about [endpoint] [timepoint] for [entity].' Do NOT invent placeholder atom IDs. Do NOT use [ev_XXX] for factual claims."

No post-hoc enforcement. Trust V4 Pro.

Pros: Simplest. One prompt change. No new code.
Cons: V4 Pro has historically violated similar instructions ("don't fabricate sentences" was violated in baseline runs). High-stakes clinical context — instruction-following isn't a guarantee.

### Approach B: Post-hoc enforcement only

V4 Pro writes freely. We post-process EVERY sentence in EVERY section:
1. Detect quantitative-claim sentences (contains a number + an endpoint vocab term).
2. Check for `atom_NNN` citation in the sentence.
3. If no atom_id OR cited atom_id not in catalog OR atom_id doesn't match the claim's shape (endpoint/entity/timepoint/value), REPLACE the sentence with the refusal template.

Pros: Hard guarantee. False atoms cannot reach the report regardless of V4 Pro's behavior. The clinical safety property is preserved structurally.
Cons: Heavy post-processing. Replacing a sentence mid-paragraph may produce ugly text. Hard to scope-detect (is "patients showed improvement" a quantitative claim? It mentions "improvement" but no number).

### Approach C: Hybrid

Combine A + B:
1. Prompt-side: instruct V4 Pro on the refusal template + ban [ev_XXX] for factual claims.
2. Post-hoc: validate cited atom_NNN exists AND matches the sentence's quantitative core. On mismatch:
   - If atom_NNN doesn't exist → REPLACE sentence with refusal.
   - If atom_NNN exists but quantitative core differs (value/endpoint/entity/comparator mismatch) → log warning + emit telemetry, do NOT replace (V4 Pro may be paraphrasing — over-strict would gut the report).

Pros: Belt-and-suspenders. Most fabrications caught by either prompt or post-hoc. Allows V4 Pro creative paraphrasing while catching hard violations.
Cons: Two failure modes to debug. Need to define "quantitative core mismatch" carefully — too strict and reports get gutted, too loose and false atoms survive.

## My read (push back if wrong)

I prefer **Approach C with a STRICT layer** for the demo:
- Prompt-side: required, sets V4 Pro's expectations.
- Post-hoc: STRICT check for "is the cited atom_NNN actually in catalog?" — refuse on missing/invalid.
- Soft check: "does the cited atom's value appear in the sentence?" — log only, don't block. (Sentence "tirzepatide reduced HbA1c by 2.30 percentage points" cites atom_001 which has value=-2.30. Sign mismatch. Edge case — probably V4 Pro dropping the minus in narrative form. Log + carry on.)

The STRICT layer is non-negotiable for clinical safety. The soft layer surfaces issues for future tuning without breaking the demo's report aesthetics.

## Open design questions

### Q1: Refusal granularity

When V4 Pro fails to cite a valid atom, do we:
- **Sentence-level**: replace that single sentence with refusal template. Other sentences in paragraph untouched.
- **Paragraph-level**: if >50% of sentences in a paragraph refuse, replace the whole paragraph with one refusal block.
- **Section-level**: if >50% of sentences in a section refuse, replace the whole section.

My read: sentence-level for the demo. Refusal-block density in a section IS the data point that goes to the gap report.

### Q2: Gap report shape

Where does the per-claim, per-section refusal data go?
- Option I: Embedded INLINE in report.md (e.g., `[REFUSED: insufficient evidence for X]` markers)
- Option II: Separate JSON sidecar (`gaps.json` next to `report.md`)
- Option III: Both — markers in report + sidecar for machine analysis
- Option IV: Telemetry-only (in `manifest.json` + log lines, not surfaced in report)

My read: Option III. Inline markers preserve the human-readable refusal disclosure; JSON sidecar enables programmatic audit (Codex / line-by-line reviewer can sweep).

### Q3: "Quantitative claim" detection — what triggers atom-citation requirement?

Sentence types that need atom_NNN citation:
- A: Contains a number AND an endpoint vocab term (`-2.30 percentage points HbA1c reduction`)
- B: Just contains a number (`risk ratio 0.74`)
- C: Contains an endpoint vocab term even without a number (`HbA1c reduction was significant`) — but "significant" without a number is fluff, not a claim
- D: Any sentence in Efficacy / Safety / Dose Response sections (location-based)

My read: A AND B. C without a number is acceptable as narrative; D is too broad (would force atom citation on mechanism-of-action sentences).

### Q4: What about narrative / mechanism / synthesis sentences?

Per your APPROVE_DESIGN: `narrative_sentences_allowed: WITH_LIMITS`. Where exactly is the line?

Allowed without atom (narrative):
- Mechanism: "Tirzepatide acts via dual GIP/GLP-1 receptor agonism."
- Trial-design summary: "SURPASS-2 was an open-label phase 3 trial."
- Cross-trial synthesis without numbers: "These outcomes were consistent across the SURPASS program."
- Hedge/limitation: "Long-term safety data beyond 40 weeks remain limited."

Required (atom_NNN cite or refuse):
- Effect-size claims: "HbA1c fell by X."
- Comparative claims: "Tirzepatide showed greater reduction than semaglutide."
- Safety incidence: "Adverse events occurred in X% of patients."
- Dose-response: "Higher doses produced greater HbA1c reductions."

Is this the right line?

### Q5: Multi-atom sentences

A sentence may cite MULTIPLE atoms: "Tirzepatide 5/10/15 mg reduced HbA1c by atom_001/atom_002/atom_003 compared with -1.86 atom_004 with semaglutide."

Should the validator:
- Require ALL cited atoms exist in catalog (any missing → refuse)
- Allow partial coverage (some cited, some not — log only)
- Demand 1-to-1 mapping between number tokens and atom_id tokens

My read: require ALL cited exist. Partial-coverage tolerant on per-number basis seems risky.

## Output schema

```yaml
verdict: APPROVE_DESIGN | REQUEST_CHANGES

approach_choice: A_prompt_only | B_posthoc_only | C_hybrid
  if_c_hybrid:
    strict_layer: |
      (specific bullet list of what gets enforced)
    soft_layer: |
      (specific bullet list of what gets logged-only)

refusal_granularity: sentence | paragraph | section
  reasoning: |
    (one sentence)

gap_report_shape: I_inline_only | II_sidecar_only | III_both | IV_telemetry_only
  if_iii_both:
    inline_marker_format: |
      (e.g. "[REFUSED: ...]" or different wording)
    sidecar_filename: gaps.json | refusals.json | other_name
    sidecar_schema: |
      (proposed JSON shape)

quantitative_claim_detector:
  trigger_a_number_plus_endpoint: YES | NO
  trigger_b_number_alone: YES | NO
  trigger_c_endpoint_alone: YES | NO
  trigger_d_section_location: YES | NO
  additional_triggers: |
    (anything I missed)

narrative_allowance_line:
  allowed_categories: |
    (list)
  required_categories: |
    (list)

multi_atom_sentence_strictness: ALL_REQUIRED | PARTIAL_TOLERANT | OTHER
  if_other: |
    (proposed rule)

implementation_location:
  new_module: src/polaris_graph/generator/atom_refusal_validator.py
  consumer: src/polaris_graph/generator/multi_section_generator.py
  hook_point: |
    (specific function name to call from)

p0_or_p1_concerns: [...]

ready_to_implement: YES | NO
  if_no: |
    (specific blocker)
```

EMIT YAML ONLY. This is a design call, not a code review.
