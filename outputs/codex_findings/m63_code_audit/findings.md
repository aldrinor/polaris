# Codex M-63 audit

**Verdict**: REJECT

## Answers

1. Dispatch correctness: The duck-typed field set itself is sufficient; the generic plan-side code only reads `title`, `focus`, and `ev_ids`, and downstream assembly only reads `SectionResult`, not the plan object. The real break is earlier: once `primary_trial_anchors` are present, `_m44_inject_primaries_into_outline()` rebuilds every plan as a plain `SectionPlan`, so `_bounded_run()` no longer sees `ContractSectionPlanExt` and the contract dispatcher never fires on the normal clinical sweep path.

2. Evidence pool registration: Collision is possible; M-54/M-55 only require entity ids to be non-empty strings, not non-`ev_*` strings. Live retrieval already uses `ev_###`, and `register_frame_rows_into_evidence_pool()` overwrites existing keys in place, so a contract entity like `ev_001` would clobber a legacy pool row.

3. Citation rewrite generalization: The listed prose examples `[Figure 1]`, `[Table 2]`, and `[N=500]` do not match the new regex because spaces and `=` are excluded, so they survive unchanged. Identifier-shaped prose brackets such as `[FDA]` or `[Figure_1]` do match; `_rewrite_draft_with_spans()` leaves them verbatim when no pool row exists, but they still count as `unverifiable` and do not become provenance.

4. Slot-fill gap/failure handling: The current LLM-exception fallback is not a silent downgrade; it is broken. `_fill_one_slot()` routes non-gap rows into `compose_gap_payload()`, but that helper now hard-raises on non-gap provenance, so the section/report can fail outright. Also, the intended M-59 `FAIL_MIN_FIELDS` surface is not active in the sweep yet: `v30_contract_slot_payloads` is returned by the generator but not consumed by `run_honest_sweep_r3.py`.

5. SectionResult shape parity: It does not match legacy expectations. Legacy `_run_section()` resolves kept sentences to numbered citations and a populated `biblio_slice`; `run_contract_section()` returns raw `[#ev:...]` sentences and `biblio_slice=[]`. Downstream global bibliography/remap/M-44/report assembly all assume per-section bibliography slices, so contract citations never enter `multi.bibliography` and raw span tokens leak into `report.md`.

6. Body prose format / sentence splitter: The Title Case trick is not Unicode-robust. `render_slot_prose()` only uppercases the first codepoint, while `_SENTENCE_SPLIT_RE` only recognizes ASCII `[A-Z]`, so non-ASCII-leading labels are not guaranteed sentence boundaries. A local smoke run on the current code also showed overlap failures: the heading+`N` sentence and the `Population` / `Comparator` / `Timepoint` sentences were dropped by `strict_verify`.

7. M-41c / M-44 no-op proof: The docstring overstates this. On the true contract path, M-41c is skipped because `run_contract_section()` bypasses `_run_section()`, not because trial short-names are impossible; the raw draft still includes `### SURPASS-2` headings. M-44 does not pass trivially because its validator reads `[N]` markers through `biblio_slice`, and contract sections currently never produce that shape.

8. M-50 per-trial subsection skip: It is not enforced by the current integration. Sweep still passes `direct_trial_anchors` unconditionally, and M-50 gating is only anchor/bibliography based; there is no contract-slot-aware suppression. Any suppression today would be accidental fallout from the empty-bibliography bug, not the planned rule.

9. Sweep runner Phase-2 prep block: It is hermetic when `PG_V30_PHASE2_ENABLED` is unset, and prep-stage exceptions degrade cleanly to the legacy generator instead of crashing the sweep. But the successful path is still not launch-ready: it seeds `ContractSectionPlanExt.ev_ids` from only the first slot, and the later M-44 pass strips the contract type before dispatch.

10. Test coverage: It is too thin for launch. The five tests cover helper-level happy paths, but they miss the integration surfaces that currently fail: M-44 type erasure, non-gap LLM-exception fallback, contract `SectionResult` bibliography/remap parity, mixed legacy+contract runs, M-50 contract suppression, and id-collision/human-curated cases.

## Findings

- Blocker: M-44 outline injection erases `ContractSectionPlanExt` by rebuilding every plan as a plain `SectionPlan`, so contract sections fall off the `_bounded_run()` contract path whenever primary-trial anchors are active. This is live on the clinical tirzepatide sweep path. `src/polaris_graph/generator/multi_section_generator.py:3126-3129`, `src/polaris_graph/generator/multi_section_generator.py:2420-2483`, `src/polaris_graph/generator/multi_section_generator.py:3195-3207`

- Blocker: `_fill_one_slot()`'s non-gap LLM-exception fallback is internally inconsistent with M-58 guardrails. It routes a non-gap row into `compose_gap_payload()`, which now raises `ValueError` on non-gap provenance, turning a planned honest fallback into a hard failure. `src/polaris_graph/generator/contract_section_runner.py:158-169`, `src/polaris_graph/generator/slot_fill.py:464-470`

- Blocker: `run_contract_section()` does not produce legacy-compatible section output. It concatenates headings into sentence text, runs `strict_verify()`, then returns raw `[#ev:...]` prose with `biblio_slice=[]` instead of resolving numbered citations. Downstream M-44/global bibliography/remap/report assembly all assume the legacy `[N]` + `biblio_slice` shape. `src/polaris_graph/generator/contract_section_runner.py:240-315`, `src/polaris_graph/generator/multi_section_generator.py:1910-1968`, `src/polaris_graph/generator/multi_section_generator.py:3235-3244`, `scripts/run_honest_sweep_r3.py:1196-1226`, `scripts/run_honest_sweep_r3.py:1510-1520`

- Medium: Sweep prep builds `ContractSectionPlanExt.ev_ids` from only the first slot in each section. That does not reflect the section's true entity set and makes any pre-dispatch logic using `plan.ev_ids` incomplete. `scripts/run_honest_sweep_r3.py:1097-1105`

- Medium: The promised contract-aware M-50 skip is absent. Sweep still passes direct anchors, and M-50 selection has no notion of “anchor mapped to a contract slot.” `scripts/run_honest_sweep_r3.py:1167-1175`, `src/polaris_graph/generator/multi_section_generator.py:1752-1812`, `src/polaris_graph/generator/multi_section_generator.py:3637-3650`

- Medium: Evidence-pool namespace collisions are possible. Contract ids are only required to be non-empty strings, live retrieval uses `ev_###`, and `register_frame_rows_into_evidence_pool()` overwrites existing keys in place. `src/polaris_graph/nodes/report_contract.py:250-262`, `src/polaris_graph/retrieval/live_retriever.py:1308-1310`, `src/polaris_graph/generator/contract_section_runner.py:116-131`

- Medium: Sentence-splitter compatibility is ASCII-only. `render_slot_prose()` uppercases only the first codepoint, while `_SENTENCE_SPLIT_RE` looks for `[A-Z]`; non-ASCII-leading labels are not guaranteed boundaries, and short boilerplate labels can fail overlap checks. `src/polaris_graph/generator/slot_fill.py:558-579`, `src/polaris_graph/generator/provenance_generator.py:703-719`, `src/polaris_graph/generator/provenance_generator.py:765-785`

## Next

Do not proceed to M-64 or M-65 yet.

Fix order:
1. Preserve `ContractSectionPlanExt` through M-44 or make M-44 a true no-op for contract plans without downcasting.
2. Repair the non-gap LLM-exception path in `_fill_one_slot()` and add the missing regression test.
3. Make `run_contract_section()` emit true legacy-compatible `SectionResult` output: safe heading handling, numbered citations, and non-empty `biblio_slice`.
4. Seed `ev_ids` from all section slots and enforce the contract-aware M-50 skip explicitly.
5. Add a real `generate_multi_section_report(..., v30_contract_plans=...)` integration test before rerunning the audit.
