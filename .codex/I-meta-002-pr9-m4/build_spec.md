# M4 build spec — self-host served==pinned (I-meta-002 PR-9/M4) — NO SPEND, NO NETWORK

Codex-ordered no-spend item: prove at runtime that each self-host verifier box serves the EXACT
pinned model, by (a) consuming the M1 `_pathb_served` {endpoint, model} in the Path-B post-run
assertion, and (b) adding a self-host preflight branch for `serving_route: vast_self_host*` that
validates `PG_<ROLE>_BASE_URL` + served identity WITHOUT OpenRouter resolution. Generator stays
OpenRouter, unchanged.

## Locked constraints
- NO MONEY / NO NETWORK in this PR: all new logic exercised by tests with INJECTED/stub data; no
  real Vast endpoint hit, no OpenRouter call. (Live served==pinned check fires only during the
  later paid canary.)
- Frozen, no drift: claim_audit_scorer.py, runtime lock (do NOT promote), M1
  openai_compatible_transport.py logic, M2/M3a/M3b committed code (only EXTEND the gate).
- snake_case, explicit imports, named constants, no except:pass, no unittest.mock in src/scripts,
  no datetime.now in library code. Fail-closed.

## Grounding (READ FIRST)
- `scripts/dr_benchmark/pathB_run_gate.py`:
  - preflight that resolves ALL roles via OpenRouter (~217-237) + `resolve_role_provider` (~335-365,
    fails closed on empty) — these assume OpenRouter for every role.
  - `assert_post_run` (~481-493) fatals on missing `provider_name`.
  - `_assert_architecture_coverage` (~311-317) RAISES while lock status=codex_approved_pending_operator_signature.
- M1 `src/polaris_graph/roles/openai_compatible_transport.py`: the transport augments the captured
  raw with `raw['_pathb_served'] = {'endpoint': base_url, 'model': served_model}` and there is NO
  provider_name for vLLM self-host roles.
- `config/architecture/polaris_runtime_lock.yaml`: per-role `serving_route` (generator openrouter;
  mirror vast_self_host_bf16; sentinel vast_self_host; judge vast_self_host_fp8) + `model_slug`.
- `src/polaris_graph/benchmark/pathB_capture.py`: build_response_metadata surfaces `_pathb_served.endpoint`
  (M1, backward-compatible).

## Scope (acceptance criteria)
1. **Self-host preflight branch** in pathB_run_gate.py: for any role whose lock `serving_route`
   starts with `vast_self_host`, the preflight must NOT resolve it via OpenRouter. Instead validate:
   `PG_<ROLE>_BASE_URL` is set (fail-closed with a clear message if unset), and record the expected
   pinned `model_slug` for the post-run served==pinned check. The generator (serving_route openrouter)
   keeps the existing OpenRouter resolution path unchanged. Do NOT call any network in preflight for
   self-host roles (env presence + lock read only; the live /v1/models identity check is the M2 probe
   run during the canary, not here).
2. **assert_post_run consumes `_pathb_served`**: for self-host verifier roles, instead of fataling on
   missing `provider_name`, read `_pathb_served` from the captured metadata and assert: served `model`
   == the role's pinned `model_slug` AND served `endpoint` == the configured `PG_<ROLE>_BASE_URL`
   (normalized, trailing slash tolerant). Fail-closed (fatal) on missing `_pathb_served`, model
   mismatch, or endpoint mismatch — a self-host role that served the wrong model or wrong box must
   abort the gate. The generator path (provider_name present) is unchanged.
3. Keep `_assert_architecture_coverage` behavior intact (still raises while lock is pending operator
   signature — that's the spend gate; M4 does not promote the lock).
4. **Tests** (no network): self-host preflight passes when PG_<ROLE>_BASE_URL set, fails-closed when
   unset; assert_post_run passes when _pathb_served.model==slug and endpoint==base_url; fails-closed on
   missing _pathb_served, wrong model, wrong endpoint; generator (openrouter/provider_name) path
   unchanged + still passes. Use stub captured-metadata dicts; NO real endpoint.

## Verify
python -c "import scripts.dr_benchmark.pathB_run_gate" ;
python -m pytest tests/dr_benchmark tests/roles tests/architecture -q ;
python -m scripts.architecture.verify_lock --consistency ;
python -m scripts.dr_benchmark.gate_a_dry_run
Report files changed + results + confirm no network/spend. Do NOT commit.
