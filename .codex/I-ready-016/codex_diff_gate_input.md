# Codex DIFF review — I-ready-016 (#1086) taxonomy reconcile + 6 stale gates — ITER 1

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

You APPROVED the brief at iter-2 (`.codex/I-ready-016/brief.md`). This is the DIFF implementing it.
Diff: `.codex/I-ready-016/codex_diff.patch` (vs base bot/I-ready-005, 333 lines).

## What the diff does (exactly as the approved brief specified)

**Part A — taxonomy reconciliation (3 mirrors):**
- `scripts/run_honest_sweep_r3.py` UNIFIED_STATUS_VALUES += `cancelled`, `abort_four_role_release_held`.
- `src/polaris_graph/audit_ir/regression_lab.py` _STATUS_TIERS += `abort_verifier_degraded` (mirror
  drift since #1071), `abort_four_role_release_held`, `cancelled` (all tier 2). KNOWN_STATUS_VALUES
  (= frozenset(_STATUS_TIERS)) now equals UNIFIED_STATUS_VALUES.
- `src/polaris_v6/schemas/run_status.py` PipelineStatus Literal += `partial_saturation`,
  `abort_budget_exceeded`, `abort_verifier_degraded`, `abort_four_role_release_held`, `cancelled`.

**Part B — 6 gate repairs:**
1. test_manifest_contract_exception_writes_error_manifest: select the top-level try whose source
   segment contains `error_unexpected` (the orchestration try), not the first try (the
   `except Exception: pass` synthesis-reset guard).
2. test_manifest_contract_abort_statuses_are_authoritative: allowlist tightened to
   `{started, abort_quota_exceeded}` (the latter written to sweep_quota_refusal.json, not a
   manifest). Feature telemetry `status` key renamed `status` -> `firing_status` everywhere
   (make_feature_telemetry L246, the 2 init kwargs L1520/1524, all `_storm_telemetry`/
   `_agentic_telemetry` `["status"]` writes + `.update`, feature_firing_warning, and the test file),
   so the manifest-status regex no longer matches feature firing-state — NO `error` allowlist.
3. test_manifest_contract_unified_taxonomy_defined: expected += the 3 new statuses.
4. test_manifest_contract_all_manifest_writes_have_status: idempotent re-stamp
   `manifest["status"] = unified_status` immediately before the SUCCESS write (the additive
   V30/depth/NLI blocks pushed the original assignment ~600 lines up, past the gate's 200-line
   window). NOT a window-widen; `unified_status` is unchanged.
5+6. test_b3 x2: re-anchor `methods_idx` from `PG_GENERATOR_MODEL` (now referenced early by
   STORM/agentic/quantified blocks, before the abort) to `PG_EVALUATOR_MODEL` (first ref at L4207,
   after the abort). The real abort-before-generation invariant is intact.

`cancelled` per your decision: add_with_prefix_exception — value preserved (v6 UI + SSE consume it),
one documented exception in test_manifest_contract_status_prefixes.

## Evidence
- 90/90 PASS: test_manifest_contract.py + test_b3_no_verified_sections.py +
  test_feature_firing_telemetry_iready005.py + retrieval/test_saturation_phase4.py +
  test_md9_regression_lab.py (the last two assert KNOWN_STATUS_VALUES == UNIFIED_STATUS_VALUES).
- Telemetry rename verified complete: zero residual `_storm_telemetry["status"]` /
  `_agentic_telemetry["status"]` / `make_feature_telemetry(... status=...)`.
- RIGOROUS regression check: a broad sweep (tests/polaris_graph + roles + dr_benchmark) had 46
  pre-existing failures. I stashed my diff and re-ran the deterministic suspicious subset on the
  base: the 6 entailment/verification failures (test_provenance_generator_entailment x4,
  test_verification_mode_phase0b, test_strict_verify) are BYTE-IDENTICAL on the base — pre-existing
  #1071 entailment/judge-model debt, NOT this diff. test_four_role_budget_cap + test_seam_parallel
  PASS in isolation (their sweep failures were test-pollution/order). test_generator + test_m49 are
  network/citation-count env tests. ⇒ this diff adds ZERO new failures.
  (Those 46 pre-existing failures are broader stack debt outside #1086's manifest-contract scope;
  flagged for the readiness audit, tracked separately — not silently absorbed.)

## Review focus
(1) Is the taxonomy reconciliation complete + correct (all 3 mirrors agree; no real manifest status
left out)? (2) Is the `cancelled` prefix exception + value-preservation correct (no consumer break)?
(3) Is the telemetry rename complete (no stray `status` key that still trips the regex)? (4) Is the
gate-4 re-stamp honest (idempotent, not a relaxation)? (5) Are the b3 + exception re-anchors sound?

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
