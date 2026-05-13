HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001a DIFF REVIEW iter 2

Canonical diff SHA256: `f583b19656ddfa26724271569a3ca11fd83bd7c55f9ae257b5f59e9e189d5d2e`.
Patch: `.codex/I-arch-001a/codex_diff.patch` (1245 lines, 2 commits).

## Iter-1 findings → resolution

### P1-001 — Augment 7th manifest-write site (outer exception path)

**Resolved.** `scripts/run_honest_sweep_r3.py` outer `except Exception` block
at line ~2885 now routes `error_manifest` through `augment_v6_manifest`
before `json.dumps`:

```python
error_manifest = {"run_id": ..., "status": "error_unexpected", ...}
error_manifest = augment_v6_manifest(
    error_manifest,
    external_run_id=q.get("external_run_id"),
    decision_id=q.get("decision_id"),
    query_slug=q.get("slug"),
)
(run_dir / "manifest.json").write_text(json.dumps(error_manifest, ...))
```

Pipeline crashes now write a v6-augmented manifest with `external_run_id` /
`query_slug` / `scope.decision_id` intact. actors.py reads
`manifest.status == "error_unexpected"` → calls `mark_failed` (correct
terminal state). Non-v6 invocations remain byte-identical (augment helper
passthrough when external_run_id is None).

### P1-002 — Update tests/v6/acceptance for new schema + mocked pipeline-A

**Resolved.** `tests/v6/acceptance/test_runs_db_integration.py` updated:

- `test_init_db_creates_schema`: expected column set now includes
  `lifecycle_status` (renamed) + 6 new I-arch-001a columns (`query_slug`,
  `manifest_run_id`, `artifact_dir`, `pipeline_status`, `cost_usd`,
  `decision_id`). Old `status` column removed.
- `test_actor_marks_completed_after_pre_insert`: monkeypatches
  `scripts.run_honest_sweep_r3.run_one_query` with a synthetic async
  fixture that writes a minimal valid manifest + returns a summary dict.
  Asserts `lifecycle_status='completed'` + `pipeline_status='success'`
  + `record.status == 'completed'` (computed_field backcompat alias) +
  `query_slug`/`artifact_dir`/`cost_usd` all populated. Hermetic — no
  real OpenRouter call.
- `test_get_run_after_drain_returns_completed`: same monkeypatch
  pattern. Asserts `body["status"] == "completed"` (alias) +
  `body["lifecycle_status"] == "completed"` + `body["pipeline_status"]
  == "success"` + `body["cost_usd"] == 0.02`.

### P2-001 — Narrow OperationalError catch

**Resolved.** `run_store.get_run` now only catches "no such table" errors:

```python
except sqlite3.OperationalError as exc:
    if "no such table" in str(exc).lower():
        return None
    raise
```

Schema corruption / migration faults now surface instead of being masked
as missing-row.

## Smoke

`pytest tests/v6/acceptance/test_runs_db_integration.py
tests/polaris_v6/queue/test_run_store_i_arch_001a.py
tests/polaris_graph/audit_ir/test_manifest_augment.py`:
**16/16 passed in 3.44s.**

All 4 tests/v6/acceptance tests pass on the new schema + mocked
pipeline-A pattern. The previously-skipped acceptance smoke is now
green.

## Direct questions iter 2

1. Augment helper at the 7th (outer exception) manifest site — APPROVE'd?
2. tests/v6/acceptance update pattern (monkeypatch
   scripts.run_honest_sweep_r3.run_one_query + assert v6 fields) —
   APPROVE'd?
3. Narrowed OperationalError catch ("no such table" string match) —
   APPROVE'd, or want a more robust check (e.g., querying for table
   existence via sqlite_master)?
4. Any P0/P1 remaining? Anything iter-1 missed that surfaces now?

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
