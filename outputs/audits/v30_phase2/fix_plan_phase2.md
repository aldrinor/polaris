# V30 Phase-2 fix plan — M-58/M-59 generator integration

**Author**: Claude Opus 4.7 · 2026-04-23
**Cycle**: V30 Phase-2 (after Phase-1 live-run APPROVED + sealed
in `outputs/codex_findings/v30_sweep_integration_audit/phase1_live_run_evidence.md`)

**Codex pass-1 review**: CONDITIONAL (6 revisions required).
All 6 woven into this plan. Codex pass-2 review pending before
implementation begins.

**Stop condition (unchanged)**: BEAT-BOTH ChatGPT DR + Gemini 3.1 Pro
DR on 7 dimensions. Phase-1 didn't move dimensions; report.md
content was still legacy generator. Phase-2 is where V30 actually
replaces the generator with frame-driven prose and should move
dimensions.

## Root mechanism gap

Phase-1 sweep confirmed M-54..M-62 all work and V30 plumbing lands
in manifest + report.md. But `report.md` content is still produced
by `multi_section_generator.generate_multi_section_report(...)`
using its legacy LLM section prompts. The V30 contract is
information-rich (required_fields, min_fields_for_completion,
bound DOI / OA URL / abstract per entity) but Phase-1 doesn't
consume it to produce prose. The legacy generator runs blind to
the contract.

Phase-1 retrieval coverage was 14/15 entities retrieved. If the
legacy generator (which runs on the evidence pool, not the
contract) continues to choose off-frame evidence over contract
entities, V30's retrieved content never reaches report.md. Phase-2
fixes this by replacing the legacy per-section LLM call with
per-slot M-58 calls for entities with FrameRows; legacy LLM calls
remain ONLY for enrichment sections (Contradictions, Limitations)
that have no contract slots.

## V2 §5 schema fields

### M-63 — Integration contract for M-58 prose into multi_section_generator

**Causal stage**: `src/polaris_graph/generator/multi_section_generator.py::_run_section`
and `generate_multi_section_report` orchestration (lines 983 + 3110).

**Prior mechanism gap**: `_run_section` receives a `SectionPlan`
with `{title, focus, ev_ids}` pulled from the LLM-generated
outline. For slots bound to a contract entity, we want to bypass
the LLM section prompt and compose deterministic slot-prose from
M-58 instead.

**Fix** (Codex pass-1 revisions 1-4 woven in):

1. **Output grain decision (Codex rev #3)**: SECTION-level
   `SectionResult`, not slot-level. `_run_contract_section`
   aggregates all slots in the section into one
   `SectionResult`. This preserves the existing assembly loop
   which prints `### {sr.title}` per SectionResult.
   `ContractSlotPlan.subsection_title` is surfaced as an `###`
   subheading INSIDE the section result's rendered prose.
   Final report.md structure:
   ```
   ## Efficacy
   ### SURPASS-1 (Rosenstock et al., Lancet 2021)
   <M-58 prose for surpass_1_primary>
   ### SURPASS-2 (Frías et al., NEJM 2021)
   <M-58 prose for surpass_2_primary>
   ...
   ## Mechanism
   ### Human hyperinsulinemic-euglycemic clamp (Thomas et al., ...)
   <M-58 prose for thomas_clamp_2022>
   ## Regulatory
   ...
   ```

2. **New async `_run_contract_section(section_plan_ext,
   frame_rows_by_entity, contract_entities, evidence_pool,
   gen_model, section_temp, slot_max_tokens) -> SectionResult`**:
   - Iterates every slot in section_plan_ext.slots (sorted by
     slot.ordering).
   - For each slot, iterates every entity_id in
     slot.entity_ids (multi-entity slots supported per Codex
     rev #3 Q3: render N blocks, each with its own ev_id).
   - If `frame_row.provenance_class ==
     FRAME_GAP_UNRECOVERABLE`: use
     `compose_gap_payload(slot, frame_row, required_fields)`.
     No LLM call.
   - Else: one LLM call per entity via
     `build_slot_fill_prompt(slot, frame_row, required_fields,
     research_question)`, then
     `parse_slot_fill_response(...)` (raises on fabrication).
   - Concatenates: `### {slot.subsection_title}\n\n{rendered
     prose}\n\n` per slot, with one prose block per entity
     when the slot has multi-entity. Combined into a single
     `SectionResult.verified_text`.
   - Returns `SectionResult(title=section.section,
     focus=aggregated focus, ev_ids_assigned=all entity_ids
     in section, verified_text=...)`.

3. **Citation rewrite (Codex rev #1 + pass-2 + pass-3
   committed path)**: M-58's `render_slot_prose` uses
   `[bound_ev_id]` where bound_ev_id is the raw contract
   entity id like `surpass_2_primary`.
   `_rewrite_draft_with_spans` currently only handles
   `[ev_xxx]`. **GENERALIZE the regex** (not alias). The
   current pattern at
   `src/polaris_graph/generator/live_deepseek_generator.py:56`
   matches `ev_*` tokens. Phase-2 changes it to
   `[A-Za-z_][A-Za-z0-9_]*` so any identifier matching Python
   identifier grammar (including both legacy `ev_xxx` AND
   contract entity ids like `surpass_2_primary`,
   `thomas_clamp_2022`, etc.) is accepted. FrameRows are
   registered into evidence_pool keyed by entity_id so the
   rewriter's `evidence_pool.get(id)` lookup succeeds on
   either kind of key. NO alias layer. This is the one
   committed path. Acceptance test (M-63 test #A): direct
   `strict_verify` call on a rendered M-58 slot produces
   zero dropped sentences. Plus a direct regex unit test on
   `surpass_2_primary` marker to lock in the pattern change.

4. **Sentence format fix (Codex rev #2 blocker fix)**: M-58's
   `render_slot_prose` currently emits:
     `N: N=1879. [surpass_2_primary]`
   where `split_into_sentences` breaks on `. [` and the
   `[surpass_2_primary]` lands in the NEXT sentence, losing
   its binding. Phase-2 fix: patch `render_slot_prose` to
   emit citation INSIDE the sentence:
     `N: N=1879 [surpass_2_primary].`
   Period moves AFTER the citation. This also mirrors the
   legacy generator's existing convention (citations precede
   terminal punctuation). The gap-phrase template updates
   similarly. Acceptance test (M-63 test #B): rendered M-58
   prose with 5 fields all passes `strict_verify` with
   `total_kept == total_in`.

5. **Outline dispatch (Codex rev #2 Q2)**: new dataclass
   `ContractSectionPlanExt(SectionPlan)` with added fields
   `slots: tuple[ContractSlotPlan, ...]`,
   `frame_rows_by_entity: dict[str, FrameRow]`,
   `contract_entities_by_id: dict[str, RequiredEntity]`. The
   sweep integration layer constructs these from the already-
   compiled ContractOutline + M-56 FrameRows. The
   orchestration loop at line 3123 checks `isinstance(plan,
   ContractSectionPlanExt)` and dispatches to
   `_run_contract_section` vs legacy `_run_section`.

6. **M-41c preservation (Codex rev #4)**: NOT a blanket skip.
   Render trial-short-names ONLY in the slot's `### subsection_title`
   heading — NOT in body sentence text. Body sentences emit
   `"N: N=1879 [surpass_2_primary]."` without the trial name.
   M-41c's filter operates on body sentences; under this
   format the body doesn't mention trial names, so M-41c is
   essentially a no-op on M-58 slots by construction (not by
   bypass). When Phase-2 wiring also needs to carry population-
   scope / timepoint context in body sentences, those context
   tokens are parameterized into the slot heading.

7. `generate_multi_section_report` gains an opt-in parameter
   bundle `v30_phase2: V30Phase2Inputs | None = None` with
   fields `(contract: ReportContract, contract_outline:
   ContractOutline, frame_rows: tuple[FrameRow, ...])`. When
   non-None, runs hybrid pipeline; otherwise falls back to
   legacy.

8. Sweep integration (`v30_sweep_integration.py`): when
   PG_V30_ENABLED=1 AND PG_V30_PHASE2_ENABLED=1, passes the
   compiled contract+outline+rows into the generator. Phase-2
   env flag is a SEPARATE gate from Phase-1 so we can toggle
   generator replacement independently of coverage reporting.

**Preservation risks**:

- Existing M-44 validator fires on named-trial mention. After
  M-58 integration, trial-section prose is schema-driven and
  always cites `[bound_ev_id]` deterministically, which satisfies
  the M-44 check by construction. Risk: M-44 telemetry format
  changes. Mitigation: keep M-44 as-is; if it fires on M-58
  output, it will PASS because every sentence carries a citation.

- M-41c under-framed-sentence filter keys on trial SHORT-NAME
  tokens in body sentences (per Codex pass-2 review of
  multi_section_generator.py:823-924). Under M-63 fix #6, trial
  short-names ONLY appear in the `### subsection_title`
  heading — body sentences carry `field:value [entity_id]`
  format with no trial name. M-41c is therefore a no-op on
  body prose by construction. Residual risk: a required_field
  VALUE that happens to contain a trial short-name (e.g. a
  study_design field value "versus SURPASS-2 comparator"). The
  contract template's `required_fields` list avoids naming
  other trials inside values; the prompt's
  anti-fabrication contract rejects values not verbatim in
  direct_quote anyway. No code-level M-41c skip; no sentinel.

- `strict_verify` expects `[ev:id:start-end]` span tokens.
  M-58 currently renders `[bound_ev_id]` without spans.
  Codex pass-1 rev #1 + pass-2: GENERALIZE rewrite pattern
  (not alias). `_rewrite_draft_with_spans`'s regex is hard-
  coded to `ev_*` in
  `src/polaris_graph/generator/live_deepseek_generator.py`
  (lines 56 + 317-363). Phase-2 patches that regex to
  `[A-Za-z_][A-Za-z0-9_]*` so it accepts contract entity ids
  like `surpass_2_primary`. FrameRows are registered into
  evidence_pool keyed by entity_id so the rewriter's
  `evidence_pool.get(id)` lookup succeeds. Acceptance test
  required: `test_strict_verify_passes_on_m58_prose`.

- `_m42b_extract_from_quote` / M-50 per-trial subsection
  generator might duplicate M-58 trial subsections. Mitigation:
  when Phase-2 is active AND the trial anchor matches a
  contract entity with a SlotFillPayload, skip the M-50
  candidate for that trial. Check happens in M-50's
  `_m50_select_candidate_trials`.

**Acceptance** (Codex pass-2 rev #3 correction):

- For `clinical_tirzepatide_t2dm` with PG_V30_PHASE2_ENABLED=1,
  the generator produces:
  - 1 SectionResult per CONTRACT SECTION (3 for clinical:
    Efficacy, Mechanism, Regulatory). NOT one per slot.
  - Each SectionResult.verified_text contains ONE
    `### {slot.subsection_title}` heading per slot, followed
    by that slot's M-58 prose body (one prose block per
    entity in multi-entity slots).
  - Non-gap slot prose includes every required_field line
    with `[bound_ev_id]` citation ATTACHED to the sentence
    (before terminal punctuation: `value [id].`).
  - Gap slot prose uses the updated M-58 `_GAP_PHRASE` with
    citation INSIDE the sentence.
  - strict_verify passes on all deterministically-rendered
    prose (acceptance test required).
  - Legacy enrichment sections (Contradictions, Limitations)
    still run via legacy LLM path and are appended to the
    report as additional SectionResults.

- `render_slot_prose` change (Codex pass-2 new issue #1):
  the function is modified to return body-only prose (no
  inline `{subsection_title}: ` prefix). Subsection titles
  become responsibility of `_run_contract_section` which emits
  the `###` heading separately. This avoids duplicate heading
  emission and keeps body sentences free of trial short-names.

- Manifest `frame_coverage_report.by_status.pass` reflects
  REPORT coverage, not retrieval — Phase-2 validation replaces
  the synth with real M-59 `validate_slot_completion` against
  actual SlotFillPayloads. `coverage_semantics` field changes
  from `phase1_retrieval_coverage` to `phase2_report_coverage`
  (Codex pass-2 rev #5: shorter enum values).

**Test coverage**: `test_m58_generator_integration.py` — 10
tests:
1. per-slot prose rendering from a stub LLM response;
2. gap slot skips LLM and uses compose_gap_payload;
3. mixed contract + enrichment outline produces both
   ContractSectionPlanExt and legacy SectionPlan results;
4. PG_V30_PHASE2_ENABLED=0 falls back to legacy
   (backwards compat);
5. **strict_verify passes on M-58 prose (Codex pass-1 rev #1 +
   #2 acceptance test)** — uses the generalized entity-id
   regex + `value [id].` format;
6. citation rewrite: `[surpass_2_primary]` → `[#ev:...]`
   verified via direct `_rewrite_draft_with_spans` call;
7. M-44 validator passes trivially on M-58 prose (every
   sentence cites the bound ev_id);
8. M-50 per-trial subsection skipped for contract entities;
9. coverage_semantics enum flips phase1→phase2 under env gate;
10. full regression of M-54..M-62 + Phase-1 integration suite
    stays green (316/316).

ADDITIONAL tests in `tests/polaris_graph/test_m58_slot_fill.py`
(not a new file — updates to existing 44-test suite):
- All `render_slot_prose` fixtures/assertions updated from
  `value. [id]` to `value [id].` format.
- Subsection-title prefix removed from body assertions (M-58
  renderer no longer prepends it).
- Matching updates to `tests/polaris_graph/test_m59_slot_validator.py`
  helper that constructs prose from payloads.

**Classification**: `root_cause` (eliminates the remaining gap
between Phase-1 plumbing and actual report-level V30 coverage).

### M-64 — M-59 validator replaces Phase-1 synth

**Causal stage**: `v30_sweep_integration._synthesize_phase1_validation`.

**Prior mechanism gap**: Phase-1 synth is a retrieval-only
placeholder. Phase-2 has real SlotFillPayloads (from M-58) so
we can run real M-59 `validate_slot_completion`.

**Fix** (Codex pass-1 rev #5 woven in):
1. Thread the M-58 SlotFillPayloads from the generator back
   through the sweep integration call.
2. When all payloads present: run `validate_slot_completion(
   outline, contract, payloads_by_entity_id,
   rendered_prose_by_slot_id)`.
3. When PG_V30_PHASE2_ENABLED=0: keep Phase-1 synth (backwards
   compat).
4. **Transition semantics marker (Codex rev #5 + pass-2 rev +
   pass-3 canonical enum)**: keep manifest key
   `frame_coverage_report` (don't break Phase-1 consumers).
   Replace the removed `phase1_retrieval_coverage_only`
   warning with a POSITIVE semantic marker at the top of the
   coverage report block:
   `frame_coverage_report.coverage_semantics = "phase2_report_coverage"`
   (Phase-1 value was `"phase1_retrieval_coverage"`). These
   are the CANONICAL enum values used everywhere in Phase-2
   code + tests + manifest. Readers can branch on this value.
   Also add a one-cycle informational `v30_phase2_transition`
   warning for the first few sweeps so downstream consumers
   see the semantic shift.

**Acceptance**:
- `frame_coverage_report.coverage_semantics == "phase2_report_coverage"`
  under Phase-2 (shortened enum).
- `manifest.v30_warnings` contains `v30_phase2_transition`
  (informational, NOT a problem warning) instead of
  `phase1_retrieval_coverage_only`.
- Disclosure preamble changes from "not yet report-coverage" to
  "Report coverage via M-58 slot-bound generator + M-59
  structured validator".
- `frame_coverage_report.entries[*].status` values now reflect
  real per-field completion vs retrieval-only.

**Test coverage**: `test_m59_phase2_integration.py` — 4 tests:
warning drop; disclosure preamble change; real vs synth verdict
divergence on a degraded extraction case; back-compat when
Phase-2 disabled.

**Classification**: `root_cause`.

### M-65 — Phase-2 full-scale sweep + autoloop V2 BEAT-BOTH

**Causal stage**: sweep launcher + autoloop V2 protocol.

**Prior mechanism gap**: V28+V29 landed 3 BB + 0 BO + 4 LB
identically. V30 Phase-1 didn't touch the report.md content so
couldn't change that. Phase-2 replaces the generator → fresh
dimensional movement expected.

**Fix**:
1. Launch `run_honest_sweep_r3.py --only clinical_tirzepatide_t2dm
   --out-root outputs/full_scale_v30_phase2/` with
   PG_V30_PHASE2_ENABLED=1.
2. Run Claude audit + Codex audit in parallel against
   `state/compare_chatgpt_dr.txt` + `state/compare_gemini_dr.txt`
   per autoloop V2 protocol.
3. Cross-review; compute BB/BO/LB matrix.
4. If BEAT_BOTH count > V29's 3: write Phase-2 APPROVED gate
   verdict.
5. If BEAT_BOTH count ≤ 3: §7 #9 fires (repeated root cause).
   Escalate to user for re-scope.

**Acceptance** (Codex pass-1 rev #6 strengthened):
1. BEAT_BOTH count on 7 dimensions ≥ 4 (strict improvement over
   V29).
2. No regression on 3 baseline BB dimensions (Regulatory,
   Jurisdictional, Contradictions).
3. **TARGET-DIMENSION REQUIREMENT**: at least ONE of {Claim
   Frames, Structural Depth} must move OFF LOSE_BOTH into at
   least BEAT_ONE. These two dimensions are the ones Phase-2
   is designed to improve (M-58 structured field extraction
   directly addresses claim-frame density; contract-driven
   outline directly addresses structural depth). If neither
   moves, the architectural investment hasn't paid off and
   §7 #9 fires (repeated root cause).

**Classification**: `validation_cycle`.

## Implementation order

1. M-63 — generator integration (this is the bulk; ~1-2d)
2. M-64 — validator promotion (~0.5d; depends on M-63 payloads)
3. M-65 — sweep + audit (~0.5d eng + autoloop wall clock)

## Self-critical questions (all five CLOSED per Codex pass-1 Q&A)

Codex pass-1 answered these five in the CONDITIONAL verdict.
Claude accepted all five answers as-authored; restated here for
audit traceability only:

1. **M-41c for contract slots (CLOSED)**: NOT a blanket skip.
   Trial short-names appear ONLY in `### subsection_title`
   heading; body sentences use `field:value [entity_id].`
   format with no trial names. M-41c becomes a no-op
   by-construction on body prose (not by code bypass). See
   preservation_risks bullet 2.

2. **Outline dispatch (CLOSED)**: dedicated
   `ContractSectionPlanExt` dataclass subclassing legacy
   `SectionPlan`, NOT a `slot_id` sentinel. Preserves contract
   invariants (subsection_title, entity_ids, is_gap,
   is_partial). See Fix #5.

3. **Multi-entity slots (CLOSED)**: render N blocks per slot,
   each with its own citation id. Merging weakens M-59
   per-entity validation + obscures failure attribution. See
   Fix #2.

4. **Phase-2 env flag vs CLI arg (CLOSED)**: env flag
   `PG_V30_PHASE2_ENABLED`, matching `PG_V30_ENABLED`.
   Separate gate from Phase-1 for independent toggling. See
   Fix #8.

5. **Manifest field naming (CLOSED)**: keep
   `frame_coverage_report` key. Add
   `coverage_semantics` enum field with shortened values
   `phase1_retrieval_coverage` (legacy) or
   `phase2_report_coverage` (new) per Codex pass-2 rev #5.
   Plus one-cycle informational `v30_phase2_transition`
   warning. See M-64 Fix #4.

## Codex pass-1 revisions — response summary

| Rev | Codex finding | Fix applied |
|---|---|---|
| #1 | `_rewrite_draft_with_spans` only handles `[ev_*]`; M-58 emits `[surpass_2_primary]` — strict_verify will drop every M-58 sentence | M-63 fix #3 (pass-2 committed path): **GENERALIZE the regex** in `src/polaris_graph/generator/live_deepseek_generator.py:56,317-363` from `ev_*` to `[A-Za-z_][A-Za-z0-9_]*`. Register FrameRows into evidence_pool keyed by entity_id. NOT an alias layer. Acceptance test: `test_strict_verify_passes_on_m58_prose` plus direct regex test on `surpass_2_primary` marker. |
| #2 | M-58 renders `value. [id]` — sentence splitter drops the citation | M-63 fix #4: patch render_slot_prose to emit `value [id].` (period AFTER citation). Gap phrase template updates too. Update all `render_slot_prose` assertions in `tests/polaris_graph/test_m58_slot_fill.py:689-744` + M-59 helper prose constructor at `tests/polaris_graph/test_m59_slot_validator.py:195,375`. |
| #3 | Output grain ambiguous (section vs slot SectionResult) | M-63 fix #1: SECTION-level SectionResult. Slots aggregate into section result. Subsection titles become `###` headings inside the section prose. Acceptance updated: 1 SectionResult per CONTRACT SECTION (3 for clinical). |
| #4 | M-41c blanket skip unsafe | M-63 fix #6 (pass-2 clarified): render trial short-names ONLY in `### subsection_title` heading; body sentences use field:value format with no trial name. M-41c is no-op-by-construction, NOT a code-level bypass. No sentinel needed. |
| #5 | Silent warning removal hides semantic shift | M-64 fix #4 (pass-2 shorter enum values): add `frame_coverage_report.coverage_semantics` field with `phase1_retrieval_coverage` / `phase2_report_coverage` values. Plus one-cycle informational `v30_phase2_transition` warning. |
| #6 | BEAT_BOTH ≥ 4 too weak | M-65 acceptance #3: target-dimension requirement — at least one of {Claim Frames, Structural Depth} must move OFF LOSE_BOTH. |

Codex pass-2 additional fix: `render_slot_prose` returns
BODY-ONLY prose (drops inline `{subsection_title}: ` prefix).
Subsection titles become `_run_contract_section`'s
responsibility via `###` emission. Prevents duplicate-heading
emission and keeps body free of trial short-names.

Codex pass-1 Q&A accepted as-authored (Claude plan answers
already matched):
- Q1: trial names in headings only, not blanket skip
- Q2: tagged contract dispatch type (ContractSectionPlanExt)
- Q3: N blocks per slot with own ev_ids (multi-entity slots)
- Q4: env flag (PG_V30_PHASE2_ENABLED) for Phase-2 gating
- Q5: keep `frame_coverage_report` key + semantic marker

## Scope not in Phase-2

- Non-clinical slug generator integration (policy / materials /
  etc.): deferred to Phase-3. Phase-2 validates the clinical
  architecture; Phase-3 generalizes.

- M-61 operator completions actually flowing through the
  generator: the Phase-2 plan treats human-curated FrameRows
  identically to M-56-retrieved rows, so this should Just Work,
  but we don't explicitly exercise it until M-65 sweep.
