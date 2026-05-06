# Codex Diff Review Brief — I-phase0-005

**Iter:** 1 of N (no hard cap per CLAUDE.md §8.3.1)

This is the SECOND of two Codex review gates for Issue I-phase0-005 per plan §7.A LOCKED A2 + §3.0 5-artifact contract:

1. ✅ **Brief review** (Codex APPROVE iter 4): see `.codex/I-phase0-005/codex_brief_verdict.txt`. Acceptance criteria correct.
2. ⏳ **Diff review** (this brief): Red-Team checklist on the actual code change.

## Artifacts under review

- `.codex/I-phase0-005/brief.md` — the Codex-APPROVE'd iter-4 spec
- `.codex/I-phase0-005/codex_diff.patch` — the canonical PR diff with `# canonical-diff-sha256: a363def93a144c23a72766c5f325a7ff3bc8eb850bb1c9b16b95b26908c94b3c` trailer
- `outputs/audits/I-phase0-005/claude_audit.md` — Claude's architect self-audit (includes LOC overrun disclosure)

## Files in this diff (6 files, +347 / -33 = +314 net)

```
src/polaris_v6/queue/run_store.py        NEW    +148
src/polaris_v6/queue/actors.py           MOD    +15 / -1
src/polaris_v6/api/runs.py               MOD    +44 / -33
src/polaris_v6/schemas/run_status.py     MOD    +3 / -0
tests/v6/acceptance/test_runs_db_integration.py    NEW    +151
tests/v6/acceptance/test_dramatiq_acceptance.py    MOD    +13 / -7
```

## Empirical test result (Claude verified before submission)

`PYTHONPATH=src pytest tests/v6/acceptance/test_runs_db_integration.py tests/v6/acceptance/test_dramatiq_acceptance.py::test_scenario_1_enqueue_and_complete tests/v6/test_actors.py` → **13/13 PASS in 2.62s.**

- All 4 new integration tests pass.
- Strengthened scenario 1 passes (now asserts DB transition, not just "drained").
- All 8 existing `test_actors.py` tests pass with zero modification (stub-mode preserved by `get_run` defensive `OperationalError → None`).

## Specific risks for Codex Red-Team

1. **CHARTER §3 LOC cap.** Brief budgeted 200; diff is 314 net (47% over). claude_audit.md §"LOC honesty disclosure" lists the trimming options I considered. Codex iter-1 of this diff has final say: strict-cap (require trimming) OR accept-the-overrun (with documented rationale). If strict, I will trim toward 275 (still over) by inlining helpers + removing one combined test; reaching 200 strictly would drop acceptance #2 or #4. Recommend accept-the-overrun.

2. **Stub-mode "row missing → noop"** contract verification:
   - `actors.py:54` checks `if run_store.get_run(run_id) is not None:` before any DB write.
   - `run_store.py:124-130` catches `sqlite3.OperationalError` → returns `None`. This handles the `tests/v6/test_actors.py` path where `init_db` was never called and the table doesn't exist.
   - Question: does this defensive behavior mask real bugs in production (e.g., DB file deleted under a running worker)? Risk-vs-mitigation: in production, `init_db` is called by `insert_run` (idempotent CREATE TABLE IF NOT EXISTS) on every POST /runs handler invocation, so a running worker post-DB-rotation would re-create the table next POST. Worker-only execution without a POST first is an edge case (cancellation? re-delivery?) — acknowledged risk, not handled this Issue.

3. **POST /runs IntegrityError → 409 path.** uuid4 collision is theoretically impossible (122 bits of entropy). Code path exists for defense; not test-covered (would require uuid mocking). Acceptable per brief?

4. **`canonical-diff-sha256` trailer correctness.** Trailer is appended AFTER the patch body. Workflow's `grep -E '^# canonical-diff-sha256: [a-f0-9]{64}$' | tail -1 | awk '{print $3}'` extracts the hash. Verify: open the patch file, locate the trailer at line 477-ish, confirm 64-hex value matches what `git diff base...head -- ":(exclude).codex/I-phase0-005/" ":(exclude)outputs/audits/I-phase0-005/"` would produce on the actual PR.

5. **Test isolation against session-shared StubBroker.** New test file's `isolated_db` fixture calls `broker.flush_all()` before AND after each test. Verify: the fixture is `@pytest.fixture` not `@pytest.fixture(autouse=True)` — it's referenced explicitly by each test parameter (`def test_X(isolated_db):`). This is intentional per brief P2-I4-002: explicit param ensures the env-set runs BEFORE the test body imports anything from `polaris_v6.queue`.

6. **Scenario 1 strengthening.** Old assertion was `assert True`. New assertion is `record.status == "completed"`. This is a stricter check. Verify the existing scenario 1 passes WITHOUT modification to anything else (just the test body update). I tested this: PASS.

7. **`document_ids: []` echo correctness.** `RunRequest.model_dump()` includes the default empty list per `src/polaris_v6/schemas/run_request.py:32`. Test #2 + test #4 both assert the echo includes `document_ids: []`. Verify the actor's noop return value matches.

8. **Pydantic forward-compat.** Adding `result_json: str | None = None` to `RunStatusResponse` is additive. Existing JSON deserializers using `RunStatusResponse(**dict)` won't break because the field has a default. Existing JSON serializers that called `.model_dump()` will now include `result_json: null` in the output — a benign payload change. Question: does any web/UI client reject unknown JSON keys? `web/lib/api.ts` types are TypeScript permissive (extra fields ignored). Acceptable.

9. **Brief follow-up Issue id naming (P2-I4-001).** Brief mentioned `I-phase0-005-followup` which would collide with the canonical issue-id regex on the gate. claude_audit.md acknowledges; deferred to PR-E follow-up time. Not a code-change risk in this Issue.

## Output schema

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
