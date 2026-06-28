HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW MODE: STATIC ONLY. Read the diff `.codex/I-deepfix-001/b11c1_fix.patch` and the changed regions. Do NOT run pytest / the pipeline / broad exploration. Emit the schema at the end.

# I-deepfix-001 B11 C1 REMOVAL (#1344) — the cert-run blocker: invalid OpenRouter provider keys → 400 on the sentinel

## What happened (empirically grounded — these are live facts, not claims)
The Phase-5 cert run (`run_gate_b.py --only drb_72_ai_labor`) CRASHED at `super_heavy_preflight` BEFORE any spend:
`GateError: verifier role 'sentinel' slug 'minimax/minimax-m2' is NOT alive in its production call shape (HTTPStatusError 400) after 6 attempts`.

I diagnosed it on the VM by building the EXACT production probe body (`_build_probe_request("sentinel", slug)`) and POSTing it to OpenRouter. The verbatim error:
```
{"error":{"message":"provider: Unrecognized keys: \"min_throughput\", \"max_latency\"","code":400}}
```
The sentinel body carried `provider: {... "min_throughput": 5.0, "max_latency": 30.0 ...}`. The mirror (glm-5.2) and judge (qwen) bodies do NOT carry those keys → both returned HTTP 200. I then re-POSTed the sentinel body with ONLY those two keys removed → HTTP 200 with a well-formed choices envelope. So the 400 is caused EXACTLY and ONLY by those two keys.

Root cause: B11 C1 (my own earlier #1344 commit) injects `provider.min_throughput` / `provider.max_latency` from the role config's `preferred_min_throughput` / `preferred_max_latency`. **These are NOT real OpenRouter provider fields.** With `require_parameters: true` (which every pinned role carries), OpenRouter strict-validates the provider block and 400s on the unrecognized keys. The C1 docstring even falsely asserted "OpenRouter honours provider.min_throughput / provider.max_latency" — a hallucinated-API claim (the §9.1.8 "read the API, don't guess" failure). super_heavy_preflight correctly caught it before spend.

## The fix (4 files — DELETE the bolt-on per §-1.3, do not re-express)
The "steer toward healthy/fast hosts" intent is ALREADY served two valid ways, so C1 is both INVALID and REDUNDANT:
1. the pinned `order` + `ignore` + `allow_fallbacks: false` chain (real OpenRouter fields, returns 200);
2. B11 **C2** (a SEPARATE mechanism in `openrouter_role_transport.py`: `role_min_tps()` reads `PG_ROLE_MIN_TPS`, `role_min_tps_rotation_enabled()` reads `PG_JUDGE_PROVIDER_ROTATE`, `_observed_tokens_per_second()` pure predicate) — measured-tokens/s post-response rotation. C2 is gated by DIFFERENT envs and does NOT read the config `preferred_*` keys, so it is fully independent of C1 and is left UNTOUCHED.

- `src/polaris_graph/roles/provider_routing.py`: DELETE `_provider_slo_enabled()` and `role_provider_slo()`; remove the `slo` merge branch from `apply_provider_routing` (now emits ONLY order/ignore/allow_fallbacks, all real OpenRouter fields); replace the C1 docstring + `_PROVIDER_SLO_ENV` constant with a removal note warning never to re-add the keys.
- `config/settings/openrouter_provider_routing.yaml`: remove the sentinel's `preferred_min_throughput: 5.0` / `preferred_max_latency: 30.0` (now inert) + replace the comment with the removal rationale.
- `scripts/dr_benchmark/run_gate_b.py`: remove the Phase-4 `os.environ["PG_OPENROUTER_PROVIDER_SLO"] = "1"` force-on line (the feature it armed is deleted).
- `tests/polaris_graph/test_deepfix_wave2_sweep_eval.py`: replace the 3 old C1 tests (which ASSERTED the invalid keys were injected) with 2 regression guards: (a) `apply_provider_routing` for the sentinel emits a valid pinned chain but NEVER `min_throughput`/`max_latency` even with the old env ON; (b) the C1 helper functions are deleted (`not hasattr`). The 4 C2 tests are unchanged.

## Offline evidence (already run, local)
- `py_compile` clean on both changed .py files.
- `apply_provider_routing({'require_parameters':True},'sentinel')` → keys == [allow_fallbacks, ignore, order, require_parameters]; no min_throughput/max_latency; helpers absent.
- `pytest -k b11` → 6 passed (2 new C1-removal guards + 4 untouched C2 tests).
- VM probe: sentinel body with the 2 keys stripped → HTTP 200, well-formed choices.
- CRLF preserved on the 3 CRLF-in-HEAD files (provider_routing.py, run_gate_b.py, the yaml); the test file stays LF. Verified zero lone-LF.

## VERIFY HARDEST (adversarial)
1. **Faithfulness engine UNTOUCHED.** This is a transport provider-routing change ONLY — strict_verify / NLI / 4-role / provenance / span-grounding are not touched. Confirm.
2. **C2 not broken.** Confirm the deleted symbols (`role_provider_slo`, `_provider_slo_enabled`, `_PROVIDER_SLO_ENV`, the config `preferred_*` keys, the `PG_OPENROUTER_PROVIDER_SLO` env) are NOT referenced anywhere else (especially not by C2 in `openrouter_role_transport.py`). If any live reference to a deleted symbol remains → NameError at runtime = P0.
3. **No other emitter of the invalid keys.** Confirm no OTHER code path writes `provider.min_throughput`/`provider.max_latency` into a request body (grep-level). If another path still emits them, the sentinel 400 returns under that path.
4. **Steering preserved.** Confirm `apply_provider_routing` still pins `order` + merges `ignore` + sets `allow_fallbacks: False` (the valid, 200-returning steering). The fix must not weaken healthy-host routing — only drop the invalid keys.
5. **§-1.3 compliance.** This DELETES a number-forcing transport bolt-on built on a hallucinated API; it does not add a cap/floor/thinner and does not relax any faithfulness gate. Confirm it is a delete, not a re-expression that could still 400.
6. **Test honesty.** Confirm the new tests actually assert the ABSENCE of the invalid keys (a real regression guard that would have caught the dead run), not a tautology.

## Output schema (REQUIRED, last lines)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
