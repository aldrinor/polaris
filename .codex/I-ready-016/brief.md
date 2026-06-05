# Brief — I-ready-016 (#1086): reconcile the manifest-status taxonomy + repair 6 stale gates — ITER 2

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## iter-1 verdict was REQUEST_CHANGES (2 P1, 1 P2) — ALL incorporated. Thank you — both P1s were real and I missed them; verified against source below.

This is now scoped as a **manifest-status taxonomy reconciliation across all mirrors** + the 6 stale
gate repairs. The taxonomy has 3 mirror locations + several test gates that drifted apart.

## Part A — taxonomy reconciliation (the real contract gaps)

Source-of-truth = `scripts/run_honest_sweep_r3.py:UNIFIED_STATUS_VALUES`. Two real terminal manifest
statuses are written to `manifest.json` but absent from the taxonomy:

1. **`cancelled`** — `_abort_if_cancelled` (`run_honest_sweep_r3.py:1431`) writes `manifest.json`
   with `"status": "cancelled"`. Decision (yours, iter-1): **add_with_prefix_exception** — preserve
   the consumed value (v6 UI + SSE `run.completed` at line 1437 read it; renaming would break them).
2. **`abort_four_role_release_held`** — `_SUMMARY_TO_UNIFIED["four_role_held"]` (line 224); written to
   `manifest.status` via `unified_status` when `summary_status="four_role_held"` (lines 4931, 5059).
   Absent from `UNIFIED_STATUS_VALUES`. The abort-status REGEX never caught it (it appears only as a
   mapping value, never a `"status":"literal"`); you caught it by reading the mapping. Matches the
   `abort_` prefix, so no prefix-test exception needed.

**Mirror sync (all must agree):**
- `scripts/run_honest_sweep_r3.py:UNIFIED_STATUS_VALUES` — add `cancelled`, `abort_four_role_release_held`.
- `src/polaris_graph/audit_ir/regression_lab.py:_STATUS_TIERS` (line 589; `KNOWN_STATUS_VALUES =
  frozenset(_STATUS_TIERS)`) — currently MISSING `abort_verifier_degraded` (added to UNIFIED by #1071
  but never mirrored here → `test_saturation_phase4.py:888` and `test_md9_regression_lab.py:294`,
  which assert `KNOWN_STATUS_VALUES == UNIFIED_STATUS_VALUES`, are ALREADY RED). Add
  `abort_verifier_degraded` + `cancelled` + `abort_four_role_release_held` (all tier 2 — terminal,
  no report produced; `cancelled` is a user-cancel terminal, tier 2).
- `src/polaris_v6/schemas/run_status.py:PipelineStatus` (Literal, line 26) — stale: MISSING
  `partial_saturation` (#988), `abort_budget_exceeded` (#1015), `abort_verifier_degraded` (#1071),
  `abort_four_role_release_held`. Real runtime risk: a run that yields any of these would fail
  `RunStatusResponse` Pydantic validation (500 on the status API). Add all four PLUS `cancelled`:
  `_abort_if_cancelled` writes `manifest.status="cancelled"`, and the v6 actor loads manifest.status
  into `pipeline_status`, so a cancelled run's `pipeline_status` can be `"cancelled"` — including it
  in `PipelineStatus` is the safe superset (no harm if never set; prevents a 500 if it is). Net:
  PipelineStatus gains `partial_saturation, abort_budget_exceeded, abort_verifier_degraded,
  abort_four_role_release_held, cancelled`.

## Part B — the 6 stale gate repairs

1. `test_manifest_contract_exception_writes_error_manifest` (TEST): selector grabs the first
   top-level try = the I-bug-111 synthesis-reset guard (`except Exception: pass`), not the outer
   orchestration try. Fix: select the top-level try whose source segment contains
   `"error_unexpected"`. Strengthens, not relaxes.
2. `test_manifest_contract_abort_statuses_are_authoritative` (TEST + Part-A): after Part A,
   `cancelled` + `abort_four_role_release_held` are in the taxonomy. Residual non-taxonomy literals:
   - `abort_quota_exceeded` — NON-manifest: `run_honest_sweep_r3.py:5682` writes it to
     `sweep_quota_refusal.json` in `main_async`, never a run manifest. Add to the test's
     `allowed_non_manifest` allowlist with that justification (a sweep-level refusal, not a manifest).
   - `fired` / `not_enabled` (+ `enabled_not_reached`, `attempted_empty`, `error`) — feature-firing
     telemetry `status` field. **Per your P2 (avoid a broad allowlist incl. `error`): RENAME the
     telemetry key `status` -> `firing_status`** in `make_feature_telemetry` (line 246) + the 2 update
     sites (2169, 2680) + `feature_firing_warning` + `test_feature_firing_telemetry_iready005.py`.
     This is #1076's brand-new telemetry (stacked, unmerged, NO consumers yet), so the rename is
     safe and ELIMINATES the firing vocabulary from the regex entirely — no `error` allowlist needed.
     After the rename the allowlist needs only `abort_quota_exceeded`.
3. `test_manifest_contract_unified_taxonomy_defined` (TEST): add `cancelled`,
   `abort_four_role_release_held` to the test's `expected` frozenset (mirrors Part A).
4. `test_manifest_contract_all_manifest_writes_have_status` (SOURCE, honest): the SUCCESS manifest's
   `"status": unified_status` is at ~4775 but written at ~5370 (595 lines later; V30/depth/NLI
   additive blocks inserted between), past the test's 200-line window → false positive. Fix: re-stamp
   `manifest["status"] = unified_status` immediately before the success write (idempotent no-op;
   documents the invariant at the write site, keeps the literal in-window). NOT a window-widen.
5+6. `test_b3_orchestrator_uses_extracted_helpers` / `test_b3_manifest_records_zero_verified` (TEST):
   anchor `methods_idx = src.find("PG_GENERATOR_MODEL")` now hits line 1883 (STORM/early generation)
   instead of post-abort generation, inverting `0 < abort_idx < methods_idx`. The real invariant
   holds (abort@4150 writes its zero-verified manifest@4203 BEFORE success-path generation@4207). Fix:
   re-anchor `methods_idx` to `src.find("PG_EVALUATOR_MODEL")` (first occurrence 4207, only in the
   success generation/manifest block, never before the abort).

## `cancelled` prefix-test
`test_manifest_contract_status_prefixes` requires every status match success/partial_/abort_/error_.
`cancelled` does not. Add a single documented exception for the terminal `cancelled` (preserve value
per your decision). `abort_four_role_release_held` matches `abort_` — no exception needed.

## Files I have ALSO checked
- `to_unified_status` / `_SUMMARY_TO_UNIFIED` already map `four_role_held -> abort_four_role_release_held`
  and `abort_verifier_degraded` — only the membership SETS (UNIFIED, _STATUS_TIERS, PipelineStatus)
  and the test `expected` sets are stale.
- The ~20 `inspect.getsource(run_one_query)` introspection gates (test_b2, m201/202/203/205/206,
  scope_gate, research_planner, four_role_budget_cap) are GREEN post-#1076 — untouched here.
- Renaming the telemetry field touches only #1076's unmerged code + its own test; no other consumer
  reads `manifest['storm_query_expansion']['status']` (grep clean).

## Acceptance criteria
- [ ] `UNIFIED_STATUS_VALUES`, `_STATUS_TIERS` (==), and `PipelineStatus` reconciled; all real
      manifest statuses (incl. `cancelled`, `abort_four_role_release_held`) present.
- [ ] 6 stale gates green; each fix labeled gate-staleness vs real-contract-fix.
- [ ] gate-2 allowlist is `abort_quota_exceeded` ONLY (telemetry renamed to `firing_status`); no
      generic `error` allowlist.
- [ ] `cancelled` consumed value preserved (no UI/SSE/API breakage); prefix-test exception documented.
- [ ] Full `test_manifest_contract.py`, `test_b3_no_verified_sections.py`, `test_saturation_phase4.py`,
      `test_md9_regression_lab.py`, `test_feature_firing_telemetry_iready005.py`, and a broad
      regression sweep green. v6 RunStatusResponse validates all pipeline statuses.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
