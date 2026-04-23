# M-52 + M-53 Code Audit — V29 Strategy β Cycle 1

**Verdict: READY / CONDITIONAL-no-blockers.**

No V29 launch-blocking defects found in commits `0ac24cb` (M-52) or `332265b` (M-53). Revisions #4-7 from the pass-1 plan review are applied in the code paths that matter for the V29 sweep.

## Scope Checked

- `src/polaris_graph/generator/multi_section_generator.py`
- `scripts/run_honest_sweep_r3.py`
- `tests/polaris_graph/test_m52_generator_corpus_injection.py`
- `tests/polaris_graph/test_m53_custody_telemetry.py`
- `tests/polaris_graph/test_m49_v28_preservation.py`

## Findings

No blockers.

No high-severity or medium-severity findings.

## M-52 Audit

1. **ev_id preservation logic: PASS.**
   `_m52_pull_from_live_corpus()` preserves a live-corpus `evidence_id` when it is a non-empty string and not already present in `evidence_pool`. Missing IDs or collisions with an existing pool ID fall back to `ev_from_corpus_{anchor_slug}` with `_n` suffix probing for uniqueness.

2. **Mutation contract: PASS.**
   Rows are skipped unless they have `direct_quote`, `tier`, and either `source_url` or `url`. Pulled rows are copied, assigned `evidence_id`, normalized to `source_url`, and receive a `title` fallback from `statement` or `source_title` when `title` is absent. That satisfies the stated Revision #5 contract for rows that reach `evidence_pool`.

3. **Canonical content-key behavior: PASS.**
   The function builds a content key independent of `evidence_id` using URL, title-like text, and the direct quote prefix. Same-content rows already in the pool are skipped, while same-ID/different-content rows are treated as collisions and assigned a fallback ID.

4. **Backwards compatibility: PASS.**
   `live_corpus=None` or empty and missing/empty `primary_trial_anchors` are no-ops. `generate_multi_section_report()` keeps `live_corpus` defaulted to `None`.

5. **M-44 telemetry integration: PASS.**
   Pulled rows are added to `m44_injection_log` with `action="injected_from_corpus"` and `section="<pool-level>"`, preserving visibility of the corpus-pull path without pretending it is a section-level injection.

## M-53 Audit

1. **9-field schema: PASS.**
   `v29_primary_custody_log` entries include `anchor`, `found_in_live_corpus`, `found_ev_id`, `selected_into_pool`, `injected_into_section`, `direct_quote_chars`, `direct_quote_adequate`, `cited_in_verified_prose`, and `citation_count`.

2. **`selected_into_pool` semantics: PASS.**
   The computation scans final `evidence_pool` rows with `_m42e_detect_primary_for_anchor()` rather than checking dict-key membership for the live-corpus ID.

3. **Final bibliography numbering: PASS.**
   `cited_in_verified_prose` is computed after global bibliography creation and after section verified text has been remapped to global `[N]` markers. It builds an `evidence_id -> num` map from finalized `global_biblio` and regex-counts those final markers across `section_results[].verified_text`.

4. **`injected_into_section` handling: PASS.**
   Section-level actions (`injected`, `already_present`, `swap_in_for_*`) populate the section name. Pool-level `injected_from_corpus` is recorded but leaves `injected_into_section=None`, which matches the requested semantics.

5. **Orchestrator persistence gate: PASS.**
   `scripts/run_honest_sweep_r3.py` passes `live_corpus=retrieval.evidence_rows` into the generator and writes `v29_primary_custody.json` for each run.

6. **M-49 extension: PASS.**
   `TestM53V29PrimaryCustody` asserts required schema and fails with per-anchor diagnostics when any custody entry has `cited_in_verified_prose=false`.

## Verification Run

- `python -m pytest tests/polaris_graph/test_m52_generator_corpus_injection.py tests/polaris_graph/test_m53_custody_telemetry.py -q` -> **24 passed**
- `python -m pytest tests/polaris_graph/test_m49_v28_preservation.py::TestM53V29PrimaryCustody -q` -> **2 skipped** because the current configured output root does not yet contain `v29_primary_custody.json`; this is expected before V29 sweep launch.
- `git diff --check 0ac24cb^..332265b -- ...` -> **clean**

## Notes

The audit observed one non-blocking residual edge case: M-53 chooses the first anchor-matched row in `evidence_pool` for citation counting. In a future hardening pass, counting citations for all anchor-matched pool ev_ids would make the telemetry more robust if duplicate primary rows for the same anchor coexist. This does not block V29 because M-44 also injects the first detected primary ev_id per anchor, so the current telemetry aligns with the current injection behavior.

Claude can proceed to V29 sweep launch (task #16).
