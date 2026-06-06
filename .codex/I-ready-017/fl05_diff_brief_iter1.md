# FL-05 (#1124) diff-gate — ITER 1 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope
Fail-loud no-silent-downgrade **backstop**. Flag-gated `PG_RUN_HEALTH_GATE` (default OFF =
byte-identical; benchmark slate forces ON). Does NOT block the rerun (CANARY-01 is the pre-spend
gate; FL-05 is the mid/post-run regression backstop). Diff: `.codex/I-ready-017/fl05_codex_diff.patch`
(vs FX-18 verified tip `27697b3e`).

## Bug — confirmed §-1.1 on the REAL held manifest
A FORCE-ENABLED discovery feature (STORM/agentic) can be ON but not fire (`firing_status in
{attempted_empty, error}`) — the run silently degrades to baseline yet records success. Held drb_72
manifest: `storm_query_expansion` enabled=True, **firing_status=attempted_empty, fired=False**, with
NO `discovery_llm_degraded` field and NO gate (advisory-only `run_log` warning). That run aborted for
an unrelated 4-role reason, but had it passed it would have shipped success with STORM silently dead.
Full §-1.1: `outputs/audits/I-ready-017/fl05_s11_audit.md`.

## Fix
1. Pure `compute_run_health_gate(discovery_telemetries, *, unified_status, gate_on)` (after
   `feature_firing_warning`): ALWAYS returns `discovery_llm_degraded: bool` +
   `discovery_rounds_on_fallback: int`; `override_status='abort_discovery_degraded'` IFF gate_on AND
   ≥1 force-enabled feature with firing_status in {attempted_empty, error} AND `unified_status ==
   'success'`.
2. Success manifest tail (`run_honest_sweep_r3.py` ~L5800, after the status re-stamp, before the
   manifest write): emit the two fields ALWAYS; when `override_status`, set
   summary_status/unified_status/manifest.status = abort_discovery_degraded BEFORE recording success.
   Abort control-flow elsewhere untouched.
3. Register `abort_discovery_degraded` (mirror `abort_verifier_degraded`): runner
   `UNIFIED_STATUS_VALUES`, `_SUMMARY_TO_UNIFIED`, `regression_lab` severity (tier 2), and the
   manifest-contract taxonomy guard. Prefix-compliant (`abort_`).

## Evidence
- **§-1.1 on REAL held manifest**: storm force-enabled + attempted_empty + no field/gate (above).
- **Offline smoke — `test_fl05_run_health_gate_iready017.py` → 7 passed**: registration +
  `KNOWN_STATUS_VALUES == UNIFIED_STATUS_VALUES` mirror invariant; the full gate decision matrix
  (degraded+gate-on+success → override; healthy → none; **gate-off → none but field still emitted**;
  non-success → never; disabled → not degraded).
- **Regression**: manifest_contract (13, taxonomy-drift guard updated) + m207 (11) + the broad
  status-registry/regression_lab suites — green.

## Decisions made (please confirm)
- **Gate set = {attempted_empty, error}** (per plan). `enabled_not_reached` is EXCLUDED — on a
  success path the discovery phase is always reached, so that state shouldn't persist; including it
  could false-abort. Acceptable, or include it?
- **Override only a would-be `success`** (partials already signal degradation; aborts/errors are
  more specific). Confirm.
- `discovery_rounds_on_fallback` = count of force-enabled discovery features that fell back (no
  per-round fallback counter exists). Acceptable proxy?

## Question
Is the gate correct + faithfulness-safe (flag-gated, default byte-identical, fail-closed on
degradation), the status registration complete across all 4 sites, and the abort control-flow
otherwise untouched? Anything blocking APPROVE?
