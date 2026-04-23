# V29 → V30 Fix Plan — Report Contract Architecture (Path A+B)

**User decision (2026-04-23)**: Path A + Path B per
`outputs/audits/v29/true_root_cause_cross_review.md`. Build
Report Contract Architecture AND hybrid human/licensed completion
interface. Goal: true-quality autonomous with honest
field-not-extractable gap-reporting.

## Root cause (both auditors converged)

V28 + V29 landed identical 3 BB + 0 BO + 4 LB cross-reviewed
outcomes. Custody bundle (M-51/52/53) was Codex-verified READY
but dimensional tier didn't move. That falsifies "custody" as
root cause.

True root cause (Codex's framing): **POLARIS has no mandatory
content model**. Report emerges from corpus, not instantiated
from schema. Retrieval failure silently becomes content absence
rather than explicit "field not extractable" language.

## Non-band-aid fix: 5-layer Report Contract Architecture

```
Layer 1: Report contract YAML (M-54)
Layer 2: Deterministic frame retrieval (M-56) + frame compiler (M-55)
Layer 3: Schema-instantiated outline (M-57)
Layer 4: Slot-bound generation (M-58) + slot-completion validator (M-59)
Layer 5: Enrichment (existing POLARIS M-42 bundle preserved)
```

Plus:
- **M-60**: explicit gap reporting in report.md + manifest
- **M-61**: hybrid human/licensed completion interface (Path B)
- **M-62**: non-clinical slug regression (prove generalization)

Existing POLARIS machinery (M-42 bundle + M-44/45/47/50/51/52/53)
runs ATOP the frame-bound skeleton as ENRICHMENT, preserving
transparency + regulatory + contradiction wins.

## Dimension-preservation statement (whole plan)

- **Dim 2 Regulatory BEAT_BOTH**: preserved. Frame contract adds
  regulatory slots; enrichment layer keeps existing regulatory_expander.
- **Dim 3 Jurisdictional BEAT_BOTH**: preserved. Same as Dim 2.
- **Dim 6 Contradictions BEAT_BOTH**: preserved. Contradiction
  detector unchanged. Tier disclosure unchanged.
- **Per-sentence [ev_id] provenance**: preserved. `strict_verify`
  is explicitly NOT relaxed. Both auditors rejected relaxation.
- **M-48 population-scope labels**: preserved. Frame labels inherit
  from per_query_trial_population_scope.

## Items (Codex-recommended implementation order)

### [1st] M-54 — Report contract YAML schema + loader

**Causal stage**: `config/scope_templates/clinical.yaml` +
`src/polaris_graph/nodes/scope_gate.py` (template loader).

**What it adds**: New `frame:` section in the YAML:

```yaml
frame:
  required_entities:
    - id: surpass_2_primary
      type: pivotal_trial
      anchor: SURPASS-2
      doi: 10.1056/NEJMoa2107519
      pmid: 34010531
      journal: NEJM
      publication_year: 2021
      required_fields:
        - N
        - population
        - comparator
        - baseline_hba1c
        - primary_endpoint
        - timepoint
        - etd_with_uncertainty
        - safety_signal
        - sponsor
        - study_design  # open-label / double-blind
      rendering_slot: efficacy_subsection_surpass_2
      min_fields_for_completion: 5
      population_scope: direct  # re-uses M-48 labels
    - id: surpass_4_primary
      type: pivotal_trial
      anchor: SURPASS-4
      doi: 10.1016/S0140-6736(21)01443-4
      ...
    - id: thomas_clamp
      type: mechanism_primary
      doi: 10.1016/S2213-8587(22)00041-1
      required_fields: [m_value_pct, insulin_secretion_rate, half_life, participant_n]
      rendering_slot: mechanism_clamp_subsection
      min_fields_for_completion: 3
    - id: fda_mounjaro_label
      type: regulatory
      jurisdiction: FDA
      url_pattern: accessdata.fda.gov
      required_fields: [boxed_warning, indications, contraindications]
      rendering_slot: regulatory_fda_paragraph
  rendering_slots:
    efficacy_subsection_surpass_2:
      section: Efficacy
      subsection_title: "SURPASS-2 (Frías et al., NEJM 2021)"
      ordering: 1
      required: true
    mechanism_clamp_subsection:
      section: Mechanism
      subsection_title: "Human pharmacodynamic findings"
      ordering: 2
      required: true
    ...
```

**Preservation risks**:
- Template authoring cost: ~1 day per research question.
  Mitigation: domain-template inheritance so clinical template
  provides default required_fields.
- Schema drift if not version-controlled. Mitigation: frame schema
  validator raises on load-time malformation; schema version field
  tracks template revisions.

**Acceptance**: `load_scope_template("clinical")` returns a
`ReportContract` object with resolved required_entities + fields +
slots. Malformed contract raises `ContractSchemaError` with
precise path to the offending field.

**Test coverage**: `tests/polaris_graph/test_m54_contract_schema.py`
— (a) well-formed contract loads, (b) missing required field
raises, (c) unknown entity type raises, (d) domain-inheritance
works.

**Classification**: `root_cause`. Layer 1 of the architecture.

### [2nd] M-55 — Frame compiler (query → instantiated contract)

**Causal stage**: `src/polaris_graph/nodes/frame_compiler.py`
(new module).

**Prior mechanism gap**: The YAML contract is static. For a given
research question + slug, the compiler resolves the contract into
an IN-MEMORY ReportContract object with final entity list, slot
assignments, and binding specs.

**Fix**: Pure function `compile_frame(research_question, template,
slug) -> ReportContract`. Resolves:
- Per-slug entity list (inheriting from template.frame)
- Required-field defaults (domain-level fallback)
- Rendering slot ordering
- Evidence-binding spec (which DOIs/hosts map to which entity)

**Preservation risks**: Compiler logic must be deterministic
(same input → same contract). Needed so regression tests stable.

**Acceptance**: `compile_frame(...)` returns ReportContract
instance with all 11 tirzepatide pivotal trials + 1 mechanism +
4 regulatory jurisdictions resolved. Bijective with YAML.

**Test coverage**: `test_m55_frame_compiler.py` — 8 tests covering
single-slug, domain-inheritance, missing-slug-returns-empty,
DOI-validation, schema-version-check, deterministic ordering.

**Classification**: `root_cause`. Layer 2a.

### [3rd] M-56 — Deterministic DOI/PMID/Unpaywall retriever

**Causal stage**: new module
`src/polaris_graph/retrieval/frame_fetcher.py`.

**Prior mechanism gap**: V28/V29 showed that Serper/S2 keyword
retrieval is non-deterministic — the same M-48 variant queries
landed different primary sets across runs. Root fix: bypass
keyword retrieval for known-DOI entities.

**Fix**: new `fetch_frame_entity(entity_spec) -> FrameRow | None`:
1. **CrossRef** `/works/{doi}` → metadata (title, authors, abstract,
   year). Always-free, never paywalled. Deterministic.
2. **Unpaywall** `/v2/{doi}` → OA PDF URL if OA version exists. Fetch
   via existing AccessBypass + Crawl4AI for full-text if OA.
3. **PubMed efetch** (pmid → abstract XML) → deterministic abstract
   text when full-text paywalled. Abstract carries headline ETDs
   for most primaries.
4. Construct FrameRow with `frame_role`, `provenance_class`
   (open_access / abstract_only / metadata_only /
   frame_gap_unrecoverable), and `direct_quote` (best available
   content in precedence order: OA full-text > abstract >
   metadata).

All steps have fixed retries + timeouts. On complete failure,
emit `frame_gap_unrecoverable=True` + failure_reason (e.g.
"paywalled_no_oa_no_abstract"). Explicit, never silent.

**Preservation risks**:
- CrossRef / Unpaywall / PubMed rate limits. Mitigation:
  conservative 1 rps + retries; 11 primaries per sweep ≈ trivial.
- Retrieval cost near zero ($0 for these APIs).

**Acceptance**: `fetch_frame_entity` is deterministic (same DOI →
same FrameRow). For the tirzepatide/T2D contract, ≥8 of 11
pivotal-trial primaries land with provenance_class ∈
{open_access, abstract_only} (not gap_unrecoverable). Remaining
≤3 emit explicit gap + failure_reason.

**Test coverage**: `test_m56_frame_fetcher.py` — 10 tests:
mocked CrossRef + Unpaywall + PubMed responses; OA-found path;
paywall-then-abstract fallback; all-fail-emit-gap; rate-limit
retry; deterministic-output invariant.

**Classification**: `root_cause`. Layer 2b. Eliminates Defect A
(retrieval non-determinism) by design.

### [4th] M-57 — Planner frame-slot integration

**Causal stage**:
`src/polaris_graph/generator/multi_section_generator.py`
`_compose_outline` function.

**Prior mechanism gap**: Current outline planner asks the LLM
"what sections and what ev_ids per section". In frame-driven
mode, outline structure is CONTRACT-DETERMINED, not LLM-emergent.

**Fix**: new `compose_outline_from_contract(contract, ...)` that
returns `[SectionPlan, ...]` directly from contract:
- Efficacy section with per-entity subsections for
  `pivotal_trial` entities
- Safety section with per-entity subsections where safety frame
  specified
- Mechanism section with slot for `mechanism_primary`
- Regulatory section with per-jurisdiction paragraphs
- Contradictions + Limitations (enrichment)

Each section's ev_ids list starts with the contract-bound
frame row(s) for that slot. Non-frame rows from enrichment
retrieval (existing selector output) fill remaining capacity.

**Preservation risks**:
- Existing LLM-outline planner still runs for enrichment sections
  (Contradictions, Limitations) that don't have frame slots.
- Outline fallback path (M-203) preserved when contract incomplete.

**Acceptance**: Given a ReportContract for tirzepatide, the outline
contains exactly one subsection per pivotal_trial slot that the
retrieval resolved. frame_gap_unrecoverable slots still appear as
subsections but carry the gap content (M-60).

**Test coverage**: `test_m57_planner_frame.py` — 8 tests:
outline composition for tirzepatide contract; enrichment outline
for sections without frame; empty frame path (falls back to LLM
planner); outline ordering honors contract.ordering.

**Classification**: `root_cause`. Layer 3.

### [5th] M-58 — Slot-bound generator prompts

**Causal stage**: `_call_section` prompt construction in
multi_section_generator.

**Prior mechanism gap**: Current section prompts give the LLM an
evidence subset and section focus; LLM picks relevance-best rows
to cite. V29 proved this is the cite-rejection bug.

**Fix**: new per-slot prompt template when section is
frame-bound:

```python
SLOT_BOUND_SYSTEM_PROMPT = """
You are filling a SPECIFIC SLOT in a structured clinical report.

SLOT: {slot.subsection_title}
BOUND EVIDENCE: [{bound_ev_id}]
DIRECT QUOTE: {direct_quote}

REQUIRED FIELDS (you MUST report each by extracting from direct_quote):
{required_fields_list}

CONTRACT:
- Every factual claim MUST cite [{bound_ev_id}].
- For each required field, extract from the direct_quote and
  report inline.
- If a field cannot be extracted from direct_quote, write the
  verbatim phrase: "field not extractable from available primary
  content" — never omit the field silently.
- Do NOT add content beyond the required fields.
- Do NOT cite other rows; this subsection is bound to one source.

Output format: one prose paragraph covering all required fields
in order.
"""
```

The generator prompt no longer offers a subset to choose from.
It binds to ONE row and instructs required-field extraction.

**Preservation risks**: Some slots will have thin abstracts
(PubMed efetch produces 200-400 words, may not contain every
required field). `min_fields_for_completion` governs whether the
slot is considered "filled" vs "gap".

**Acceptance**: For each retrieved frame entity with
provenance_class ∈ {open_access, abstract_only}, generator
produces a paragraph covering ≥min_fields with [ev_X] citations.

**Test coverage**: `test_m58_slot_bound_prompts.py` — 6 tests:
prompt construction for pivotal_trial slot; mechanism slot;
regulatory slot; field-not-extractable language enforcement
(mocked LLM response); min_fields threshold.

**Classification**: `root_cause`. Layer 4a. Eliminates Defect B
(cite-rejection) by design.

### [6th] M-59 — Slot-completion validator (replaces M-44 soft injection)

**Causal stage**:
`src/polaris_graph/generator/multi_section_generator.py` post-
section validation.

**Prior mechanism gap**: V29 M-44 validator fired on TRIAL-NAME
mention in prose; LLM never mentioned → validator empty → silent
failure. Correct validator must fire on SLOT CREATION.

**Fix**: new `_m59_validate_slot_completion(contract, sections)`:
- For each contract.rendering_slot:
  - slot was RENDERED (subsection exists in sections output) →
    check if slot has ≥min_fields_for_completion + the bound
    ev_id cited ≥1 time. If yes: PASS.
  - slot was NOT rendered → FAIL. Record as
    `m59_violation_missing_slot`.
  - slot was rendered but lacks bound ev_id citation → FAIL.
    Record as `m59_violation_unbound_slot`.
  - slot is frame_gap_unrecoverable → PASS iff the M-60 gap
    language is present in the subsection.

Fail the V30 build if any required slot fails validation. No
silent fallback.

**Preservation risks**: Tight coupling of validator to contract
schema. Mitigation: validator takes ReportContract + sections
as arg; schema mismatches raise precise errors.

**Acceptance**: For tirzepatide contract with 11 pivotal_trial
slots + 1 mechanism + 4 regulatory, validator reports per-slot
status. Build succeeds iff all non-gap slots are fully populated.

**Test coverage**: `test_m59_slot_validator.py` — 7 tests:
all-slots-pass; missing-slot-detected; unbound-slot-detected;
gap-slot-with-M60-language-passes; gap-slot-without-M60-language-
fails; partial-fields-within-min-threshold-fails;
partial-fields-above-threshold-passes.

**Classification**: `root_cause`. Layer 4b. Replaces M-44 soft-
injection semantics.

### [7th] M-60 — Explicit gap reporting in report.md + manifest

**Causal stage**: report assembly in run_honest_sweep_r3.py.

**Prior mechanism gap**: Today when a primary doesn't land, the
associated trial is silently omitted. User (clinician) can't tell
from the report whether the trial doesn't exist or was dropped.

**Fix**:
1. For each contract slot with `frame_gap_unrecoverable=True`,
   emit a subsection with the exact verbatim text:
   > **SURPASS-4 primary publication**: The Del Prato Lancet 2021
   > primary publication was not retrievable from accessible
   > sources (paywall; no OA version; no PubMed abstract). This
   > subsection is limited to: [whatever CAN be extracted, e.g.
   > design metadata from CrossRef / trial registry].
2. Manifest.json gets new field
   `frame_coverage_report: {...}` enumerating every contract
   slot with its final status (filled / partial /
   gap_unrecoverable + reason).
3. Tier disclosure in Methods section adds
   `frame_gap_count = N` so reader knows how many slots weren't
   fully populated.

**Preservation risks**: None. Strict content-honesty upgrade.

**Acceptance**: For tirzepatide run, report.md contains gap
language for each frame_gap_unrecoverable slot (if any).
manifest.json has frame_coverage_report.

**Test coverage**: `test_m60_gap_reporting.py` — 4 tests:
gap subsection rendering; manifest field schema;
tier disclosure frame_gap_count; backward-compat when no gaps.

**Classification**: `root_cause`. Layer 4c.

### [8th] M-61 — Hybrid human/licensed completion interface (Path B)

**Causal stage**: new module
`src/polaris_graph/retrieval/human_gap_completion.py` +
orchestrator integration.

**Prior mechanism gap**: Even with M-56 deterministic retrieval,
paywalled primaries without OA + abstract will fail. Path B is
user-provided completion for these gaps.

**Fix**:
1. After M-56 runs, for each entity with
   `frame_gap_unrecoverable=True`, emit a structured task file
   `outputs/.../human_gap_tasks.json`:
   ```json
   [
     {
       "entity_id": "surpass_4_primary",
       "doi": "10.1016/S0140-6736(21)01443-4",
       "required_fields": ["N", "ETDs_with_CI", ...],
       "failure_reason": "paywalled_no_oa_no_abstract_access",
       "needs": "operator to provide direct_quote from licensed copy"
     }
   ]
   ```
2. Accept operator completion file
   `human_gap_completions.json`:
   ```json
   [
     {
       "entity_id": "surpass_4_primary",
       "direct_quote": "In SURPASS-4 (Del Prato et al., Lancet 2021), 1,995 adults with type 2 diabetes and established or increased cardiovascular risk (87% with prior CVD)...",
       "source_type": "licensed_institutional_access",
       "provenance_class": "human_curated",
       "consent_proof": "operator-certified; original PDF retained on operator's licensed Lancet account; quote verbatim from pp.1811-1824",
       "curator_id": "operator@institution"
     }
   ]
   ```
3. Loader validates completion file schema; refuses entries
   without consent_proof or with non-matching DOI.
4. Completed entities enter evidence_pool with
   `provenance_class=human_curated` flag. strict_verify still
   applies.
5. Tier disclosure in Methods section counts human-curated rows
   separately from retrieved rows: "46 retrieved + 3 human-
   curated from licensed sources".

**Preservation risks**:
- Fraud/fabrication risk: if operator enters false quote, it
  passes strict_verify (matches the provided "source"). Mitigation:
  `provenance_class=human_curated` is a PERMANENT flag on the
  evidence row; all downstream citations carry visible marker;
  operator consent_proof is audit-logged.
- Legal: operator must have licensed access to the source. The
  completion file schema requires `consent_proof` field.

**Acceptance**: Given a human_gap_completions.json with 3 entries
for SURPASS-4 / SURPASS-CVOT / Thomas clamp, pipeline integrates
them; generator's slot-bound prompt uses them; report.md cites
[ev_X] correctly; Methods section discloses 3 human-curated rows;
strict_verify passes on the curated content.

**Test coverage**: `test_m61_human_completion.py` — 6 tests:
gap task file emission; completion file schema validation;
consent_proof required; DOI matching enforced;
provenance_class flag propagates; tier disclosure counting.

**Classification**: `root_cause` (Path B). Layer 4d.

### [9th] M-62 — Non-clinical slug regression

**Causal stage**: new scope template
`config/scope_templates/technical.yaml` OR existing `policy`
template extended with a frame.

**Prior mechanism gap**: Architectural change must be
domain-agnostic. Codex explicitly flagged risk of
"tirzepatide-specific hardcoding masquerading as architecture".

**Fix**:
1. Author a non-clinical scope template with a frame (e.g. a
   materials chemistry review on lithium-ion battery electrolyte
   additives: required entities = 4-5 pivotal experimental papers
   + 2 review papers).
2. Run V30 pipeline on this template.
3. Verify: slot-completion discipline works identically; DOI
   fetcher works on non-biomedical DOIs; gap reporting renders.
4. Acceptance: materials report has comparable slot coverage +
   per-sentence provenance to tirzepatide report, proving
   architecture generalizes.

**Preservation risks**: Sourcing a materials template from scratch
is 1-2 days research effort. Alternative: policy template +
pivotal-legislation frame.

**Acceptance**: V30 sweep on non-clinical slug completes without
requiring code changes specific to clinical domain.

**Test coverage**: `test_m62_non_clinical_regression.py` — fixture
materials template + end-to-end contract compilation + outline
from contract.

**Classification**: `preservation_guard`. Architectural-
generalization validator. Codex's original V32 idea, moved
forward.

## Per-item summary table

| Item | Stage | Addresses | Classification | V30 scope |
|---|---|---|---|---|
| M-54 | YAML schema + loader | Contract foundation | root_cause | in |
| M-55 | Frame compiler | Query → resolved contract | root_cause | in |
| M-56 | DOI/PMID/Unpaywall retriever | Defect A (retrieval non-determinism) | root_cause | in |
| M-57 | Planner frame integration | Outline schema-driven | root_cause | in |
| M-58 | Slot-bound prompts | Defect B (cite-rejection) | root_cause | in |
| M-59 | Slot-completion validator | Replaces M-44 soft injection | root_cause | in |
| M-60 | Explicit gap reporting | Honesty-under-failure | root_cause | in |
| M-61 | Human gap completion | Path B hybrid | root_cause | in |
| M-62 | Non-clinical regression | Architecture generalization | preservation_guard | in |

## Implementation order (Codex-recommended)

Bottom-up, schema-first:

1. **M-54** YAML schema + loader (foundation)
2. **M-55** Frame compiler (consumes schema)
3. **M-56** DOI/PMID/Unpaywall retriever (uses compiled contract)
4. **M-57** Planner frame integration (uses retrieved frame rows)
5. **M-58** Slot-bound prompts (per-slot binding)
6. **M-59** Slot-completion validator (gates on M-58 output)
7. **M-60** Explicit gap reporting (renders M-56 + M-59 outputs)
8. **M-61** Human gap completion (optional parallel; can ship in
   V30.5 cycle if V30 timeline tight)
9. **M-62** Non-clinical regression (after 1-7 ship)
10. V30 launcher + sweep + audit

Each item: implement → unit tests → Codex code audit before moving to
next. Per V2 protocol.

## Expected V30 outcome

| Dim | V29 | V30 projection | Rationale |
|---|:-:|:-:|---|
| 1. Citations | LB | **BEAT_ONE or BEAT_BOTH** | Frame entities guaranteed in bibliography via M-56 deterministic retrieval |
| 2. Regulatory | BB | BB | Preserved (enrichment layer) |
| 3. Jurisdictional | BB | BB | Preserved |
| 4. Claim frames | LB | **BEAT_ONE or BEAT_BOTH** | Slot-bound generation (M-58) guarantees per-slot PICO + ETDs extracted |
| 5. Structural depth | LB | **BEAT_ONE or BEAT_BOTH** | Per-trial subsections from contract (M-57); ChatGPT-style trial table extracted from slots |
| 6. Contradictions | BB | BB | Preserved |
| 7. Narrative depth | LB | **BEAT_ONE or LOSE_BOTH** | Mechanism slot extracts what's retrievable; paywalled Thomas clamp may hit gap (honest) unless Path B human completion fills it |

**Projected aggregate**:
- Path A alone: **5-6 BB + 1-2 BO + 0 LB** (8-10 days effort)
- Path A + B completed: **6-7 BB + 0-1 BO + 0 LB** (12-16 days + operator completion)
- Path A + B with licensed-operator filling all 11+1 gaps: 7/7 BB achievable

Codex's honest caveat stands: 7/7 requires licensed access. A+B
makes that access possible via M-61 operator interface.

## Plan review ping-pong budget

V2 §7 trigger #11 allows up to 3 plan-review passes. V30 = pass-1.
Budget intact.

## Questions for Codex plan review

1. **Is M-54 + M-55 + M-56 ordering correct**, or should M-56
   come FIRST (prove DOI fetch works before designing schema
   around it)?
2. **M-58 slot-bound prompt**: I've specified "bound to ONE row".
   Should it be ONE PRIMARY ROW per slot, with permission to
   reference enrichment rows (e.g. a meta-analysis confirming the
   primary's effect size)? Or strict one-row-one-slot?
3. **M-61 human completion fraud risk**: `consent_proof` string
   is all that prevents a bad actor from entering fabricated
   quotes. Is that sufficient? Should we require a structured
   hash or the operator to attach the primary's PDF hash?
4. **M-62 non-clinical template**: which domain gives highest-
   value regression? Materials chemistry vs policy vs ML
   benchmarking. I lean materials (tight scope, non-paywalled
   primaries — ChemRxiv is open).
5. **Frame-element cap**: contract for tirzepatide has ~16 entities
   (11 pivotal + 1 mechanism + 4 regulatory). Any concern about
   cost/time for 16 deterministic fetches + 16 slot-bound
   generator calls per sweep?

## Next step per V2 runbook

Submit this plan to Codex for step 6 pass-1 review at
`.codex/v30_fix_plan_review_pass1_brief.md`.

On APPROVED or CONDITIONAL-no-blockers: begin M-54 implementation.
