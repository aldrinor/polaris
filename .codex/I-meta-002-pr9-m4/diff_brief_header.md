HARD ITERATION CAP: 5 per document. This is iter 1 of the M4 DIFF gate.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Reserve P0/P1 for real execution/safety risks; classify the rest P2/P3.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (emit this exact YAML block as your final output)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

# Codex DIFF-gate — I-meta-002 PR-9/M4: self-host served==pinned

M4 makes the Path-B gate verify that each self-hosted verifier box serves the EXACT pinned model.
Part of the no-spend 4-role readiness sequence (M1 transport, M2 serving config + identity probe,
M3a/M3b builder + seam — all committed + Codex-APPROVE'd). NO MONEY / NO NETWORK in this PR.

## HARD CONSTRAINTS (operator-locked)
- NO SPEND / NO NETWORK: self-host preflight is env + lock read only (no network); assert_post_run
  uses captured/stub metadata; generator-path unit tests run offline=True. The live served==pinned
  check fires only during the later paid canary. No real Vast/OpenRouter call in any tested path.
- Frozen, no drift: claim_audit_scorer.py, runtime lock (NOT promoted — status stays
  codex_approved_pending_operator_signature), M1 openai_compatible_transport.py, pathB_capture.py,
  pathB_runner.py logic. M4 only EXTENDS pathB_run_gate.py.
- D8 remains the single binding gate. _assert_architecture_coverage must still raise while the lock
  is pending operator signature (M4 must NOT relax it).

## What to verify in the diff
1. **Self-host preflight branch**: roles whose lock serving_route starts with `vast_self_host` SKIP
   OpenRouter canonical-slug + provider resolution; instead the gate validates `PG_<ROLE>_BASE_URL`
   is set (fail-closed GateError naming the env var if unset) and pins base_url (trailing-slash
   stripped) + serving_route on the RolePin. Generator (serving_route openrouter) UNCHANGED. This
   branch must be independent of `offline` (env + lock read only — production runs offline=False).
   `_role_serving_routes()` degrades to {} on missing/unreadable lock so unknown roles keep the
   OpenRouter path (confirm this degradation can't silently bypass a self-host check for a real role).
2. **assert_post_run self-host branch**: self-host roles read served `model` + `endpoint` from the
   captured metadata (NOTE: build_response_metadata FLATTENS _pathb_served to top-level `model` +
   `endpoint` keys; there is no literal `_pathb_served` key in response_metadata — confirm the gate
   reads the right keys). Fail-closed (fatal GateError) on: missing endpoint/model, served model !=
   pinned model_slug, served endpoint != pinned base_url (trailing-slash tolerant). Compares against
   the value pinned at preflight. Generator path (provider_name present) UNCHANGED.
3. **_assert_architecture_coverage UNTOUCHED** — still raises while lock pending operator signature.
   Confirm M4 did not replicate/relax that freeze.
4. **Backward-compat**: pathB_gate_pin.json gains 2 additive fields (serving_route, base_url); all
   consumers read role_pins by key with .get(); no additionalProperties:false validator. Confirm safe.
5. Fail-closed everywhere; no silent fallback; a self-host role serving the WRONG model or WRONG box
   must ABORT the gate (this is the served==pinned safety invariant M4 exists to enforce).

## SMOKE (build agent, this session)
- python -c "import scripts.dr_benchmark.pathB_run_gate" — OK
- pytest tests/dr_benchmark tests/roles tests/architecture -q — 389 passed (+9 new M4 gate tests; 2
  pathB_runner fixtures updated to the self-host contract).
- verify_lock --consistency — exit 0 (lock NOT promoted).
- gate_a_dry_run — OVERALL PASS, exit 0.
- tests/polaris_graph not re-run here (M4 touches only pathB_run_gate.py + dr_benchmark tests; the
  49 tests/polaris_graph failures are PRE-EXISTING per the M3b stash-comparison, unrelated to M4).
- No network / no spend in any tested path; frozen files unchanged (git diff verified).

## DIFF (follows)
