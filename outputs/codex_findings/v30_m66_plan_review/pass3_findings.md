# V30 M-66 fix plan v3 review (pass 3)

**Verdict**: CONDITIONAL-no-blockers

## Pass-2 issue resolution

1. Ship rule inconsistency (pass-2 Blocker): RESOLVED
   - v3 now defines one canonical ship gate and applies the run-3 `2 BB + 4 BO + 1 LB` projection to `PHASE2_CHECKPOINT`, not `BEAT_BOTH_SHIP` (`outputs/audits/v30_phase2/fix_plan_run3_v3.md:27-42,102-105,129-138`).
2. M-66b test seam (pass-2 Medium): RESOLVED
   - The new AccessBypass-backed path will sit outside the existing `httpx.Client` DI used by CrossRef / Unpaywall / PubMed, so stubbing `_fetch_url_pattern` is the correct unit seam. Existing AccessBypass tests already use module-level monkeypatching at the helper boundary rather than transport mocking (`src/polaris_graph/retrieval/frame_fetcher.py:698-899`, `tests/polaris_graph/test_fetch_access_bypass_wiring.py:57-206`).
3. Trial Summary real-content filter (pass-2 Partial): PARTIAL
   - The negative regression is now concrete and it would reject the observed bad rows in the current report (`outputs/full_scale_v30_phase2/clinical/clinical_tirzepatide_t2dm/report.md:47-58`).
   - But the prose points at the wrong implementation surface: the malformed rows are emitted by the deterministic M-42b builder after `_m42b_extract_from_quote` plus the 4-of-7 acceptance gate, not by an `_build_trial_summary` function (`src/polaris_graph/generator/multi_section_generator.py:1268-1271,1499-1537`).
   - The generic `result contains no digit` rule is broader than needed; safer is to reject rows whose `effect` is empty and whose rendered result is only the `at week N` fallback / placeholder, plus the specific comparator-fragment guard.
4. Structure projection (pass-2 Partial): RESOLVED
   - `PROBABLE BO` is acceptable as a forecast label because v3 no longer treats it as booked score and the actual ship/checkpoint logic still uses only BB/BO/LB (`outputs/audits/v30_phase2/fix_plan_run3_v3.md:87-105,129-138`).

## Answers

1. Strict ship gate application: Yes. The run-3 honest projection is correctly classified as `PHASE2_CHECKPOINT`, not `SHIP`. I do not see a remaining zero-LB contradiction in v3.
2. Test seam spec: `_fetch_url_pattern` is the right seam for M-56 unit tests. I would not rewrite the plan around AccessBypass constructor injection. `AccessBypass.__init__` only exposes config flags, not a pluggable fetch backend (`src/tools/access_bypass.py:334-340`), so constructor injection does not materially improve orchestration tests. If you want cleaner DI later, add an optional private `url_fetcher` kwarg in `frame_fetcher`; otherwise module-level monkeypatch of `_fetch_url_pattern` is fine.
3. Trial Summary patterns: Sufficient for the observed bad rows, but only partially safe as written. The specific comparator fragment `in adults with type` plus rejecting placeholder endpoint + `at week N` result will kill the current SURPASS-4 / SURMOUNT-2 junk rows (`outputs/full_scale_v30_phase2/clinical/clinical_tirzepatide_t2dm/report.md:47-58`). The unsafe part is the prose-level `result contains no digit` rule: keep it scoped to the builder's fallback result path, not as a blanket rule over any text cell. Also add one positive keep test for a valid glargine/placebo row with a numeric effect.
4. PROBABLE BO label utility: Useful if it remains forecast-only. It is meaningful shorthand for "expected but not booked." It becomes uncertainty-theatre only if it leaks into acceptance logic or post-run scoring.
5. New blockers: None.
6. Reason NOT to implement: No blocker. Implement v3 now, but carry the trial-summary surface fix and one positive keep test in the same change.

## Findings (new only)

- Medium: The trial-summary validator is attached to the wrong surface in the v3 prose. `outputs/audits/v30_phase2/fix_plan_run3_v3.md:63-81` names `multi_section_generator._build_trial_summary` / `tests/polaris_graph/test_m42_trial_summary_table.py`, but the malformed rows are produced by the deterministic M-42b builder in `src/polaris_graph/generator/multi_section_generator.py:1365-1537` and its current builder tests live in `tests/polaris_graph/test_m42ab_anaphoric_and_builder.py:176-416`. If the filter lands only on the old M-36 parser surface, it will not stop the observed bad rows in `outputs/full_scale_v30_phase2/clinical/clinical_tirzepatide_t2dm/report.md:47-58`.

## Next

On CONDITIONAL-no-blockers: Claude implements the M-66 bundle. While implementing, put the Trial Summary filter on the M-42b deterministic builder path, add the negative regression there, and add one positive keep case so the validator does not drift into over-rejection.
