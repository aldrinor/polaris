# Codex Diff Review Brief — I-phase0-005 (ITER 3)

**Iter:** 3 of N (no hard cap per CLAUDE.md §8.3.1)

## Iter-2 outcome (recap)

Verdict: `REQUEST_CHANGES`. One P1 + five P2.

- **P1-I2-001:** App import eagerly decorates `enqueue_research_run` via `api/runs.py` → `actors.py`, which calls `dramatiq.get_broker()` at decoration time. Dramatiq tries `RabbitmqBroker` (pika absent → ImportError fallback) then `RedisBroker` — which requires the `redis` package. `requirements.txt:143` declared `dramatiq>=2.1.0` core only, with no `redis`. In a clean web_ci-style environment `uvicorn polaris_v6.api.app:app` would `ImportError` at import time before `/health` responds. **Codex empirically reproduced via `BlockRedis` MetaPathFinder.**
- **P2-I2-001..005:** acknowledged as out-of-scope-for-this-Issue or already-acknowledged in claude_audit.md.

## Iter-3 fix

**One-line addition to `requirements.txt`:**

```diff
 dramatiq>=2.1.0  # actors, brokers, middleware base class
+redis>=4.0,<8.0  # I-phase0-005 P1-I2-001: dramatiq.get_broker() RabbitMQ->Redis fallback ImportErrors at app boot if absent
 opentelemetry-api>=1.36.0  # tracer + propagate APIs
```

Rationale: dramatiq's `get_broker()` fallback chain is RabbitmqBroker (`pika` absent) → RedisBroker (`redis` required). Phase 0 production already needs Redis (Task 0.3 Vast.ai dev cluster, Phase 4 OVH BHS H200). Declaring it directly closes Codex's empirical app-boot regression. `redis>=4.0,<8.0` matches dramatiq's `[redis]` extras pin.

## Empirical verification (Claude verified)

```
$ PYTHONPATH=src python -c "import polaris_v6.api.app; import dramatiq; print('broker_class=', type(dramatiq.get_broker()).__name__); print('app_import=ok')"
broker_class= RedisBroker
app_import=ok
```

Tests still 13/13 PASS:

```
$ PYTHONPATH=src python -m pytest tests/v6/acceptance/test_runs_db_integration.py tests/v6/acceptance/test_dramatiq_acceptance.py::test_scenario_1_enqueue_and_complete tests/v6/test_actors.py
============================= 13 passed in 2.29s ==============================
```

## P2 observations from iter-2 — Claude's classification

### P2-I2-001: LOC budget +314 net (now +315)

Codex iter-2 already wrote: "I accept this as disclosed substrate+integration-test overrun if the P1 is fixed." P1 is now fixed in iter-3. Iter-3 adds 1 line to `requirements.txt` for the fix → total `+348/-33 = +315 net`. Recommendation: hold the iter-2 P2-acceptance.

### P2-I2-002: POLARIS_V6_QUEUE_USE_STUB not honored at app import outside pytest

Codex iter-2 already classified as "out-of-scope-for-this-issue production/test harness architecture, not a P1 acceptance failure." Confirmed: brief acceptance #1-4 do not specify env-driven broker selection at app boot. Production deploys (Task 0.3, Phase 4) use real Redis by design. No code change.

### P2-I2-003: `init_db` doesn't wrap permission/open failures into RuntimeError

True observation. Brief's "adversarial inputs" section anticipated `RuntimeError → 503` in `api/runs.py:31-33` for **enqueue failures** (broker unavailable), not DB-permission failures. SQLite at `state/v6_runs.sqlite` is gitignored under repo control; permission failures are operator-config errors, not user-facing runtime failures. Adding broad permission→503 wrapping is scope-creep into "all DB I/O paths return 503 on permission" — a Phase 4 sovereign-migration concern (Postgres replaces SQLite). Classification: **P3 documentation accuracy** — iter-3 brief acknowledges the gap.

### P2-I2-004: `get_run` catches all `sqlite3.OperationalError` → None can mask real DB problems

True. Defensive masking preserves stub mode. The alternative is to whitelist only `"no such table"` in the error message — fragile string-match. Acceptable trade-off for Phase 0; Phase 4 Postgres migration eliminates the surface (Postgres tables exist before app import). Classification: **P3 acknowledged technical-debt**, not P1.

### P2-I2-005: POST inserts row before enqueue; enqueue failure leaves a `queued` row

True. Brief acceptance #3 specifies POST returns 202 + persists row + enqueues. Order is insert→enqueue (so race-free). On enqueue failure, the `RuntimeError → 503` path (already in `api/runs.py:31-33`) returns 503 to the caller; the orphan `queued` row is observable via GET — a follow-up Issue handles `mark_failed` reconciliation. Classification: **P3 follow-up Issue**, already in claude_audit.md "out of scope this Issue."

## Hard requirements for iter-3 output

1. **Static review only. Do NOT re-run pytest.** Codex iter-1 hit Windows TEMP `PermissionError`. The empirical pytest output is included above. The fix is verified locally.
2. **Emit the YAML schema block.** Verdict APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

3. **List ALL findings this iteration. No toothpaste-squeeze. Same quality bar.**

## Artifacts under review

- `.codex/I-phase0-005/brief.md` — Codex APPROVE'd iter-4 spec
- `.codex/I-phase0-005/codex_diff.patch` — canonical PR diff with `# canonical-diff-sha256: fbfa9aa18b02af6a94a55ab75015f2835f2e4a35ee7f138a4ce3096400cb6d25` trailer
- `.codex/I-phase0-005/codex_diff_audit_iter2.txt` — iter-2 verdict (REQUEST_CHANGES + P1-I2-001)
- `outputs/audits/I-phase0-005/claude_audit.md` — Claude's architect self-audit (updated for iter-3)

## Files in this diff (7 files, +348 / -33 = +315 net)

```
requirements.txt                                   MOD    +1 / -0   (NEW iter-3)
src/polaris_v6/queue/run_store.py                  NEW    +148
src/polaris_v6/queue/actors.py                     MOD    +15 / -1
src/polaris_v6/api/runs.py                         MOD    +44 / -33
src/polaris_v6/schemas/run_status.py               MOD    +3 / -0
tests/v6/acceptance/test_runs_db_integration.py    NEW    +151
tests/v6/acceptance/test_dramatiq_acceptance.py    MOD    +13 / -7
```

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

List ALL findings this iteration. Do NOT hold any back to drip-feed across iterations. Same quality bar regardless of iteration count. No hard cap on iterations.
