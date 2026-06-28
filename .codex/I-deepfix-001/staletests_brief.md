HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Gate iter 2: I-deepfix-001 (#1344) — STALE-TEST fixes for the winners-only PURITY build

## What changed since iter 1 (you returned REQUEST_CHANGES with 1 P1 + 1 P2)
Both of your findings are addressed. Re-review the fresh diff at `.codex/I-deepfix-001/purity_staletests.patch` (8 modified `tests/dr_benchmark/*.py`). Read the repo read-only as needed. Confirm the fixes are correct and introduced no regression.

### FIX for your P1 (env snapshot/restore not leak-safe)
You found: in `test_benchmark_stack_activation_meta007.py` and `test_verified_only_surface_iready013.py`, the manual `env_snapshot = dict(os.environ)` / `finally: os.environ.clear(); os.environ.update(env_snapshot)` was defeated because `monkeypatch.setenv(...)` inside the snapshot region captured POST-slate values, and pytest's monkeypatch teardown runs AFTER the `finally`, re-injecting them.

FIX applied: each `finally` now calls `monkeypatch.undo()` BEFORE the snapshot restore.
- `test_benchmark_stack_activation_meta007.py` finally: `monkeypatch.undo()` then `os.environ.clear()` / `os.environ.update(env_snapshot)`.
- `test_verified_only_surface_iready013.py` finally: `set_max_cost_per_run(old_cap)` then `monkeypatch.undo()` then the snapshot restore.

Rationale to verify: `monkeypatch.undo()` reverts the monkeypatch-tracked env+attr changes (so pytest's later teardown is a no-op — undo is idempotent), and THEN the snapshot restore overwrites os.environ to the pre-test state — which also covers the slate's DIRECT os.environ mutations that monkeypatch never tracked. Confirm: (a) ordering is correct (undo before snapshot restore so the snapshot is the final word on os.environ); (b) calling `monkeypatch.undo()` here, with pytest later calling it again at fixture teardown, is safe (idempotent); (c) no monkeypatch.setattr that must survive the test is wrongly undone (the only setattr is `orc.PG_MAX_COST_PER_RUN` in meta007, which SHOULD be reverted at test end); (d) the result is genuinely leak-safe — no slate value (PG_SWEEP_FETCH_CAP, PG_CLINICAL_PDF_EXTRACTOR=mineru25, the claim-workers value, etc.) survives into sibling tests.

### FIX for your P2 (broad pytest.raises without match)
You found: `test_evidence_to_generation_cap_iready001.py` and `test_section_timeout_token_sizing_iarch004.py` used `pytest.raises(RuntimeError)` without `match`. FIX applied — each now binds to the production message (env-var name appears in the message; verified against run_gate_b.py):
- evidence-to-generation throttle (`PG_LIVE_MAX_EV_TO_GEN=20`) → `match="PG_LIVE_MAX_EV_TO_GEN"` (extra-env floor msg, run_gate_b.py:2572-2575 includes `{name}`).
- section wall-clock (`PG_SECTION_WALLCLOCK_SECONDS=600`) → `match="PG_SECTION_WALLCLOCK_SECONDS"` (timeout-hierarchy check fires first since 6500<600 is false; its message at run_gate_b.py:2555-2560 contains the flag name).
- section tokens (`PG_SECTION_MAX_TOKENS=16384`) → `match="PG_SECTION_MAX_TOKENS"` (extra-env floor < 64000).
- frozen live generator timeout (`set_generator_timeout_seconds(600)`) → `match="GENERATOR_TIMEOUT_SECONDS"` (live-constant check at run_gate_b.py:2541-2546 fires first, message contains `GENERATOR_TIMEOUT_SECONDS`).

Verify each `match` string actually appears in the message the perturbation triggers AND that the intended check fires BEFORE any other (NO-LOSER, etc.) — i.e. the test still proves its specific protection, and the `match` cannot accidentally bind to the wrong raise.

## Evidence (for your context, not a substitute for your review)
All 4 edited files + the durable section test were run TOGETHER in one process (order-independence, the exact leak class your P1 named): `52 passed in 5.93s`, offline/zero-spend.

## Out of scope (do not flag — unchanged from iter 1)
- The 23 PRE-EXISTING dr_benchmark failures (20 all-GLM same-family `validate_role_families`; 2 `test_verify_serving_identity` glm-5.1→5.2 serving-config drift; 1 known `test_preflight_fails_when_floor_disabled`). They fail on unmodified HEAD; logged as separate tech-debt.
- The production gates + section test (already APPROVE'd in prior gates).
- `_cred_alive()` returning `z-ai/glm-5.1` (pre-existing serving-identity drift).
- The original purity retargeting you already reviewed in iter 1 and did NOT flag (the loser kills, the offline param usage, STORM-min neutralization, the K5 deletions, out_root→tmp_path). Only re-flag if the iter-2 changes broke one of them.

## Output schema (REQUIRED — loose prose is rejected)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
Static review only — do NOT run pytest. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
