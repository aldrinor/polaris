HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001a DIFF REVIEW iter 3

Canonical diff SHA256: `fdfb67839d0130e5a175992d0ee2e7b28bb5fcdb24c1cb8ed742744d09ca7044`.
Patch: `.codex/I-arch-001a/codex_diff.patch` (3 commits, full series).

## Iter-2 findings → resolution

### P1-003 — `test_dramatiq_acceptance.py` scenario 1 hermetic

**Resolved.** `test_scenario_1_enqueue_and_complete` now monkeypatches
`scripts.run_honest_sweep_r3.run_one_query` with the same synthetic async
fixture used in `test_runs_db_integration.py`. Asserts `lifecycle_status
== "completed"`, `pipeline_status == "success"`, plus the computed_field
`status` backcompat alias.

### P2-002 — Legacy DB read-first-on-startup migration

**Resolved.** `run_store.get_run` now catches `"no such column"` as well
as `"no such table"`. On column-missing, it calls `init_db(path)` to run
the schema migration in-place, then retries the SELECT once. Means a
deployed legacy DB with `status` but no `lifecycle_status` migrates
transparently on the first read instead of returning 500.

## Smoke

`pytest tests/v6/acceptance/ tests/polaris_v6/queue/test_run_store_i_arch_001a.py
tests/polaris_graph/audit_ir/test_manifest_augment.py`:
**17 passed, 7 xfailed** (pre-existing xfails on scenarios 2-8 unrelated to this Issue).

## Direct questions iter 3

1. test_dramatiq_acceptance scenario 1 monkeypatch matches the
   test_runs_db_integration pattern — APPROVE'd?
2. Auto-migrate-on-read retry pattern (`get_run` catches "no such column",
   runs init_db, retries SELECT once) — APPROVE'd? Or want it bounded /
   logged differently?
3. Any P0/P1 remaining? Anything iter-1/iter-2 missed that surfaces now?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```
