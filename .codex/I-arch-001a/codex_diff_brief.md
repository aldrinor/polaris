HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001a DIFF REVIEW iter 1

Branch `bot/I-arch-001a-run-store-schema`. Brief APPROVE iter 3 (zero findings).
Canonical diff SHA256: `77241528afe6982f42d3dbfe7029e78726a2555caf45ccbe3a51d88926d7a9f4`.
Patch: `.codex/I-arch-001a/codex_diff.patch` (1004 lines).

## Files

```
src/polaris_graph/audit_ir/manifest_augment.py     NEW  48 LOC
src/polaris_v6/schemas/run_status.py               MOD  +59 / -22 (lifecycle + pipeline + computed_field)
src/polaris_v6/queue/run_store.py                  MOD  +198 / -40 (schema migration + helpers + get_run)
src/polaris_v6/queue/actors.py                     MOD  +171 / -22 (full failure mapping, q-dict, UUID artifact_dir)
scripts/run_honest_sweep_r3.py                     MOD  +43 / -2  (v6 imports + run_dir override + 6 augment calls)
tests/polaris_graph/audit_ir/test_manifest_augment.py NEW  65 LOC
tests/polaris_v6/queue/test_run_store_i_arch_001a.py  NEW  131 LOC

7 files changed, 629 insertions(+), 86 deletions(-)
```

## Brief APPROVE iter-3 acceptance criteria → implementation

| Criterion | Implementation |
|---|---|
| RENAME COLUMN status→lifecycle_status (value-preserving) | `run_store.py:_migrate_schema` lines 48-93; test_migration_rename_preserves_values PASS |
| ADD COLUMN for 6 new fields, idempotent | same, with PRAGMA table_info inspection; test_migration_is_idempotent PASS |
| LifecycleStatus + PipelineStatus Literal types | `run_status.py:14-37` |
| RunStatusResponse new Optional fields + computed_field `status` alias | `run_status.py:44-77` |
| `mark_failed(run_id, error)` | `run_store.py:185-198`; sets lifecycle_status='failed', pipeline_status='error_unexpected' |
| `mark_aborted(run_id, pipeline_status, abort_reason, cost_usd)` | `run_store.py:163-183`; lifecycle_status='completed' (per CLAUDE.md §9.3 abort is pipeline verdict not error) |
| `set_pipeline_meta` with COALESCE | `run_store.py:130-155`; idempotent partial updates |
| TEMPLATE_TO_SCOPE_DOMAIN week-1 mapping | `actors.py:26-35` |
| `_derive_slug` deterministic | `actors.py:38-47` |
| q-dict v6 fields (NO os.environ mutation) | `actors.py:84-92` |
| UUID-scoped `outputs/v6_runs/{run_id}/` | `actors.py:74-76` |
| Direct `run_one_query(q, artifact_dir_root)` | `actors.py:101-103` |
| Full failure mapping | `actors.py:96-141` (try/except + manifest_missing + invalid_json + status dispatch) |
| augment_v6_manifest passthrough when non-v6 | `manifest_augment.py:21-22` (returns input unchanged) |
| augment_v6_manifest at all 6 manifest-write sites | `run_honest_sweep_r3.py` L1339-1345 / 1466-1472 / 1685-1691 / 1764-1770 / 2326-2332 / 2825-2831 |

## Smoke evidence

- `pytest tests/polaris_v6/ tests/v6/`: **418 passed in 29.71s**, zero regressions
- 12 new tests (5 manifest_augment + 7 run_store): **12/12 pass**
- Import smoke: `polaris_graph.audit_ir.manifest_augment` + `scripts.run_honest_sweep_r3` both load clean
- `status` computed_field alias backcompat verified by existing tests/v6/ assertions (asserts on body['status'] and record.status still pass)

## Out of scope (carried to downstream Issues per APPROVED brief)

- I-arch-001b (#464): V30 contract synthesizer
- I-arch-001c (#465): scope_domain template expansion
- I-arch-001d (#466): artifact_to_slice_chain bridge + 3 force-APPROVE residuals (verifier-span text, Pydantic Literal validity, VerifiedReport required fields)
- I-arch-001e (#467): SSE Redis Streams
- I-arch-001f (#468): full POST→graph→bundle→compare e2e

## Direct questions

1. Does the diff match the APPROVED brief iter-3 scope?
2. RENAME COLUMN approach safe across SQLite versions (Python 3.11 ships 3.34+; >= 3.25 required)?
3. mark_aborted using lifecycle_status='completed' (abort is pipeline verdict, not error) — APPROVE'd?
4. computed_field `status` alias breaks no existing serializer / consumer?
5. Pipeline-A 6-site augmentation pattern (call BEFORE json.dumps, when external_run_id is None it's passthrough) — APPROVE'd as byte-identical for legacy CLI sweep?
6. q-dict's `out_root_override` honored in run_one_query at line 1132 (run_dir resolution) — implementation matches intent?
7. Any P0/P1 blocking merge?

## LOC discussion

629 insertions / 86 deletions = 543 net. Above the brief's 250 LOC budget. Drivers:
- run_store.py +198/-40 = 158 net (schema migration + 5 new helpers + get_run rewrite with 9 new columns)
- actors.py +171/-22 = 149 net (full failure-mapping logic is more involved than brief preview suggested; 8 distinct status-mapping branches)
- Tests: 196 LOC (12 new tests covering migration, lifecycle, abort/fail, helper)

If LOC excess is a blocker, the split would be:
- PR1 (this diff but minus actors.py + run_honest_sweep_r3.py): run_store + run_status + manifest_augment + helper tests (~280 LOC)
- PR2: actors.py rewrite + pipeline-A patches + integration tests (~270 LOC)

But this split forces the helpers to ship without their first consumer, which means I-arch-001b can't depend on a working chain. Prefer landing as one PR given comprehensive test coverage demonstrates correctness.

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
