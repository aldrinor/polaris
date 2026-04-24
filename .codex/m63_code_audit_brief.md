M-63 code audit — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh (project default).

## Scope

V30 Phase-2 M-63 Fix #1 (plus Fix #2 + #3 already committed).
Three commits reviewed together as one logical change:

- `efe4a92` — M-63 Fix #2 (body-only `render_slot_prose` w/ Title
  Cased labels) + Fix #3 (generalized citation-rewrite regex
  `[A-Za-z_][A-Za-z0-9_]*` replacing `ev_*`-only pattern).
- `66ed484` — M-63 Fix #1 (main surgery): SECTION-level dispatch
  via `ContractSectionPlanExt`, new `contract_section_runner.py`,
  `generate_multi_section_report` integration, sweep runner
  Phase-2 prep path, 5 new M-63 tests.

## Files

1. `src/polaris_graph/generator/contract_section_runner.py` (NEW, 332 lines)
2. `src/polaris_graph/generator/multi_section_generator.py` (+95 lines; dispatch in `_bounded_run`)
3. `src/polaris_graph/generator/slot_fill.py` (+18 lines; `render_slot_prose` rewrite)
4. `src/polaris_graph/generator/live_deepseek_generator.py` (regex generalization — in efe4a92)
5. `scripts/run_honest_sweep_r3.py` (+114 lines; Phase-2 prep block when `PG_V30_PHASE2_ENABLED=1`)
6. `tests/polaris_graph/test_m63_contract_section_runner.py` (NEW, 360 lines, 5 tests)
7. `tests/polaris_graph/test_m58_slot_fill.py` (3 assertions updated for Title Case)

All 321 V30+M-63 regression tests green.

## Plan context

The approved Phase-2 plan (pass-4, `848b5e7`) mandates:

- **Fix #1**: `ContractSectionPlanExt` dispatch type (distinct from
  M-57's `ContractSectionPlan`). SECTION-level `SectionResult`, NOT
  slot-level. Multi-entity slots render N blocks, each bound to its
  own entity_id.
- **Fix #2**: body-only `render_slot_prose` — no subsection heading
  inside the body; caller supplies `### {subsection_title}` above
  the block. Sentences in `Field: value [id].` format.
- **Fix #3**: GENERALIZE `_EV_MARKER_RE` (not alias) — picks up
  contract entity ids AND legacy `ev_*`. Register FrameRows into
  `evidence_pool` keyed by `entity_id` so strict_verify resolves.
- **No legacy overlap**: M-41c (under-framed trial sentences) is
  no-op by construction (no trial short-names in body format).
  M-44 (primary-citation validator) passes trivially (every
  sentence cites its bound ev_id). M-50 per-trial subsection
  generator is SKIPPED for entities whose anchor maps to a
  contract slot (integration layer enforces).
- **Hermetic gating**: Phase-2 path only active under
  `PG_V30_PHASE2_ENABLED=1`; default runs byte-identical to
  pre-M-63.

## Your pass-1 plan verdict context

Phase-2 plan pass-4 APPROVED (greenlight) after 4 passes resolving
citation-id mismatch, sentence format, output grain, M-41c
preservation, semantics marker, and M-65 gate strength.

## Questions

1. **Dispatch correctness** — `ContractSectionPlanExt` is a NEW
   dataclass (not subclass) that duck-types on `SectionPlan`'s
   public fields (title, focus, ev_ids). `is_contract_section` is
   an `isinstance` check used exactly once in `_bounded_run`. Is
   the duck-typing safe, or is there a risk the legacy assembly
   code reaches for `SectionPlan`-specific fields that
   `ContractSectionPlanExt` lacks? Trace the full path from
   `_bounded_run` → `run_contract_section` → `SectionResult`
   → downstream assembly.

2. **Evidence pool registration** — `register_frame_rows_into_evidence_pool`
   keys entries by `entity_id` (e.g., `surpass_2_primary`), carries
   `direct_quote`, `url`, `title`, `authors`, `journal`, `year`,
   `doi`, `pmid`, `provenance_class`. Does it risk clobbering a
   legitimate pre-existing `ev_*` pool entry if a curator happened
   to use `entity_id=ev_<uuid>`? Or is that collision impossible
   by M-57 construction?

3. **Citation rewrite generalization** — `_EV_MARKER_RE =
   r"\[([A-Za-z_][A-Za-z0-9_]*)\]"`. Does this introduce false
   positives on legitimate prose brackets (e.g., `[Figure 1]`,
   `[Table 2]`, `[N=500]`)? Trace through
   `_rewrite_draft_with_spans` and show whether non-evidence
   bracketed text survives intact.

4. **Slot-fill gap/failure handling** — `_fill_one_slot` has three
   paths: gap (skip LLM, `compose_gap_payload`), LLM exception
   (fall back to gap payload), parse exception (build manual
   all-`not_extractable` payload). Each path honors LAW II
   ("fail loudly, never return empty silently") differently.
   Is the LLM-exception → gap-payload fallback a silent
   downgrade? Or is M-59 FAIL_MIN_FIELDS the loud failure
   surface?

5. **SectionResult shape parity** — `run_contract_section` returns
   SectionResult with `biblio_slice=[]`, `regen_attempted=False`,
   `dropped_due_to_failure=(kept==0 and len(all_entity_ids)>0)`,
   `error="" if kept>0 else "no_sentences_verified"`. Does this
   match what legacy downstream assembly (`_assemble_report_body`
   or equivalent) expects? Is an empty biblio_slice OK given
   biblio is built globally?

6. **Body prose format → sentence splitter compatibility** —
   `render_slot_prose` emits `Field name: value [id].` with Title
   Cased labels specifically so strict_verify's sentence splitter
   (`. [A-Z\[]`) triggers a boundary. Is the Title Case transform
   robust to unicode field names (e.g., a field name with
   non-ASCII characters)? Is there a case where the resulting
   sentence fails strict_verify's content-word overlap check
   because the field label is too short?

7. **M-41c / M-44 no-op proof** — The docstring claims both
   validators are no-op by construction for contract sections.
   Verify by inspection: does M-41c key on trial short-names
   that literally cannot appear in `Field: value [id].` format?
   Does M-44 primary-citation validator pass trivially when
   every sentence cites the bound ev_id?

8. **M-50 per-trial subsection skip** — The plan says M-50 is
   skipped for contract-anchored entities. Is that actually
   enforced by the current integration, or does M-50 still run
   on `ev_ids_assigned` and generate stale sub-sections that
   conflict with contract output?

9. **Sweep runner Phase-2 prep block** — `run_honest_sweep_r3.py`
   adds 114 lines when `PG_V30_PHASE2_ENABLED=1`: compile_frame
   → fetch_compiled_frame → compose_outline_from_contract →
   build ContractSectionPlanExt per section → prepend contract
   evidence rows. Is this block fully hermetic (zero effect when
   env var unset)? Does the failure mode when a stage raises
   (e.g., fetch_compiled_frame 503) degrade gracefully or crash
   the whole sweep?

10. **Test coverage** — 5 M-63 tests (register_frame_rows,
    fill_one_slot gap, fill_one_slot LLM, run_contract_section
    end-to-end, dispatch). Fewer than peer layers (M-58=35,
    M-60=20, M-62=18). Is the coverage right-sized given M-63 is
    thin integration glue, or are there edge cases not covered
    (e.g., mixed legacy+contract sections, empty slots, M-61
    curator-completed rows)?

## Output

Write to `outputs/codex_findings/m63_code_audit/findings.md`.

Format:
```markdown
# Codex M-63 audit

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Answers

1. Dispatch correctness: ...
2. Evidence pool registration: ...
3. Citation rewrite generalization: ...
4. Slot-fill gap/failure handling: ...
5. SectionResult shape parity: ...
6. Body prose format / sentence splitter: ...
7. M-41c / M-44 no-op proof: ...
8. M-50 per-trial subsection skip: ...
9. Sweep runner Phase-2 prep block: ...
10. Test coverage: ...

## Findings

<blockers, mediums, nits with file:line>

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to
M-64 (validator promotion — real M-59 against actual
SlotFillPayloads, drop `phase1_retrieval_coverage_only` warning,
add `phase2_report_coverage` semantic marker) then M-65
(full-scale Phase-2 sweep + autoloop V2 audit, BEAT-BOTH
ChatGPT DR + Gemini DR on 7 dimensions).
```

Keep under 200 lines. Full xhigh reasoning budget. M-63 is the
generator-side integration layer; approval here unlocks
Phase-2 full-scale launch.
