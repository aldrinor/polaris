HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001a iter 2 — code-grounded fixes for 4 P1s + 5 P2s

## P1 from iter 1 → resolutions

### P1.1 — Complete actor failure-mapping

You wrote:
> "actors.py failure mapping is underspecified. `error_unexpected`, missing/invalid manifest, or pipeline invocation exceptions must call `mark_failed(...)`."

**Resolution**: full status-mapping logic in actors.py:

```python
@dramatiq.actor(max_retries=ENQUEUE_MAX_RETRIES, time_limit=30 * 60 * 1000)
def enqueue_research_run(run_id, request_payload):
    # Stub-mode path (tests with no run_store row)
    if run_store.get_run(run_id) is None:
        return {"run_id": run_id, "status": "completed", "echo": request_payload}

    run_store.mark_in_progress(run_id)
    decision_id = str(uuid.uuid4())
    artifact_dir_root = Path(os.environ.get("POLARIS_V6_OUTPUT_ROOT", "outputs/v6_runs")) / run_id
    artifact_dir_root.mkdir(parents=True, exist_ok=True)
    
    # Build q dict (NO os.environ mutation per P1.2)
    q = {
        "external_run_id": run_id,
        "decision_id": decision_id,
        "v6_mode": True,
        "question": request_payload["question"],
        "template_id": request_payload["template"],
        "scope_domain": _map_template_to_scope_domain(request_payload["template"]),
        "out_root_override": str(artifact_dir_root),  # P1.3 fix
    }
    
    try:
        from src.polaris_graph.graph_v4 import build_and_run_v4
        result = asyncio.run(build_and_run_v4(q=q, out_root=artifact_dir_root))
    except Exception as exc:
        logger.exception("[actor] pipeline-A raised")
        run_store.mark_failed(run_id, f"pipeline_exception: {type(exc).__name__}: {exc}")
        raise  # Dramatiq retry/dlq machinery

    # Find the manifest pipeline-A wrote
    manifest_path = artifact_dir_root / "manifest.json"
    if not manifest_path.is_file():
        run_store.mark_failed(run_id, "manifest_missing: pipeline-A returned without writing manifest.json")
        return result
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        run_store.mark_failed(run_id, f"manifest_invalid: {exc}")
        return result
    
    pipeline_status = manifest.get("status") or manifest.get("pipeline_status") or "error_unexpected"
    query_slug = manifest.get("query_slug")
    manifest_run_id = manifest.get("run_id")
    cost_usd = float(manifest.get("cost_usd", 0.0))
    
    run_store.set_pipeline_meta(
        run_id=run_id,
        query_slug=query_slug,
        manifest_run_id=manifest_run_id,
        artifact_dir=str(artifact_dir_root),
        decision_id=decision_id,
    )
    
    if pipeline_status == "success" or pipeline_status.startswith("partial_"):
        run_store.mark_completed(run_id, result, pipeline_status=pipeline_status, cost_usd=cost_usd)
    elif pipeline_status.startswith("abort_"):
        run_store.mark_aborted(run_id, pipeline_status=pipeline_status, abort_reason=manifest.get("abort_reason", pipeline_status), cost_usd=cost_usd)
    elif pipeline_status.startswith("error_"):
        run_store.mark_failed(run_id, f"pipeline_error: {pipeline_status}: {manifest.get('error', '')}")
    else:
        run_store.mark_failed(run_id, f"unknown_pipeline_status: {pipeline_status!r}")
    
    return result
```

Tests `tests/polaris_v6/queue/test_actors_failure_mapping.py`:
- exception in pipeline-A → mark_failed called
- manifest missing → mark_failed
- manifest invalid JSON → mark_failed
- success → mark_completed
- partial_thin_corpus → mark_completed (still ran)
- abort_corpus_inadequate → mark_aborted
- error_unexpected → mark_failed
- unknown status string → mark_failed (loud)

### P1.2 — DROP os.environ mutation entirely; pass via q dict

You wrote:
> "Do not mutate `os.environ` globally for per-run IDs in a long-running Dramatiq worker."

**Resolution**: NO os.environ mutation. All v6 fields flow through the `q` dict (pipeline-A's existing query-dict parameter). This is concurrency-safe by construction (q is per-call).

Pipeline-A patches (`scripts/run_honest_sweep_r3.py`):

```python
def run_one_query(q: dict, out_root: Path) -> dict:
    # NEW v6 fields read from q, not env
    v6_mode = q.get("v6_mode", False)
    external_run_id = q.get("external_run_id")  # UUID hex
    decision_id = q.get("decision_id")  # UUID hex; passed to ScopeDecision
    out_root_override = q.get("out_root_override")  # absolute artifact_dir
    
    if out_root_override:
        run_dir = Path(out_root_override)
    else:
        run_dir = out_root / domain / slug  # existing
    
    # ... pipeline body ...
    
    # At manifest write site(s): augment if v6_mode
    if v6_mode:
        manifest = augment_v6_manifest(
            manifest_base=manifest,
            external_run_id=external_run_id,
            decision_id=decision_id,
            query_slug=slug,  # pipeline-A's URL-safe slug
            retrieval_block=..., adequacy_block=..., models_block=...,
        )
```

`augment_v6_manifest` is the single helper for P2.1 (below).

No `os.environ` reads in pipeline-A code path. Zero concurrency risk. Argv-level CLI flag `--v6-mode` adds an alternative way to enable v6 fields when sweep is invoked from CLI (not actor) for testing.

### P1.3 — UUID-scoped artifact_dir; same-slug concurrency test

You wrote:
> "Artifact directories must be per-run unique. Pipeline-A currently writes `out_root/domain/slug`; repeated or concurrent same-slug runs can overwrite."

**Resolution**: q["out_root_override"] is set to `outputs/v6_runs/{run_id}/` by actors.py. UUID is the parent, so two concurrent runs of the same question/slug land in DIFFERENT directories.

Test `tests/polaris_v6/queue/test_actor_artifact_isolation.py`:
- Submit 2 runs with same question + template; assert artifact_dir1 != artifact_dir2
- Each artifact_dir has its own manifest.json with distinct external_run_id

### P1.4 — Value-preserving migration via RENAME COLUMN

You wrote:
> "The `status`→`lifecycle_status` migration must preserve existing values."

**Resolution**: SQLite 3.25+ supports `ALTER TABLE ... RENAME COLUMN`. Migration in init_db():

```python
def _migrate_schema(conn):
    """Idempotent schema migration. Safe to call on every init_db."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
    
    if "status" in cols and "lifecycle_status" not in cols:
        # Rename status -> lifecycle_status (value-preserving)
        conn.execute("ALTER TABLE runs RENAME COLUMN status TO lifecycle_status")
        cols.add("lifecycle_status")
        cols.discard("status")
    
    # Add new columns (each idempotent via column inspection)
    new_cols = {
        "query_slug": "TEXT",
        "manifest_run_id": "TEXT",
        "artifact_dir": "TEXT",
        "pipeline_status": "TEXT",
        "cost_usd": "REAL",
        "decision_id": "TEXT",
    }
    for col_name, col_type in new_cols.items():
        if col_name not in cols:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {col_name} {col_type}")
    
    # Indexes (CREATE INDEX IF NOT EXISTS is idempotent)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_query_slug ON runs(query_slug)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_manifest_run_id ON runs(manifest_run_id)")
```

Test `tests/polaris_v6/queue/test_run_store_migration.py`:
- Set up DB with old 9-column schema + 3 rows with status='completed'
- Run migration via init_db
- Assert rows preserved: status values now in lifecycle_status; new columns NULL
- Re-run migration: idempotent (no-op)

Python sqlite3 ships with SQLite 3.34+ on Python 3.11; RENAME COLUMN supported.

## P2 from iter 1 → resolutions

### P2.1 — Single manifest-augment helper for all 7 sites

```python
# src/polaris_graph/audit_ir/manifest_augment.py (NEW)
"""Single canonical helper for v6-mode manifest augmentation.

Pipeline-A's run_honest_sweep_r3.py writes manifest.json at 7 sites:
  1. Scope abort (line ~1331)
  2. Zero sources abort (~1453)
  3. Corpus inadequate abort
  4. Corpus approval denied abort
  5. No verified sections abort
  6. Success (final)
  7. Outer-exception error

All call this helper to merge in v6 fields when v6_mode=True. Non-v6
sweeps leave manifest byte-identical to today.
"""

from typing import Any

def augment_v6_manifest(
    manifest: dict[str, Any],
    *,
    external_run_id: str | None,
    decision_id: str | None,
    query_slug: str | None,
    retrieval_block: dict[str, Any] | None = None,
    adequacy_block: dict[str, Any] | None = None,
    models_block: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return augmented manifest dict (does not mutate input)."""
    if external_run_id is None:
        # Not v6 mode: passthrough
        return manifest
    
    augmented = dict(manifest)
    augmented["external_run_id"] = external_run_id
    augmented["query_slug"] = query_slug
    
    scope = dict(augmented.get("scope", {}))
    scope["decision_id"] = decision_id
    augmented["scope"] = scope
    
    if retrieval_block is not None:
        augmented["retrieval"] = retrieval_block
    if adequacy_block is not None:
        augmented["adequacy"] = adequacy_block
    if models_block is not None:
        augmented["models"] = models_block
    
    return augmented
```

All 7 manifest-write sites call this helper. Non-v6 invocations are byte-identical because helper returns input unchanged when external_run_id is None.

### P2.2 — mark_aborted persists cost_usd

Signature: `mark_aborted(run_id, pipeline_status, abort_reason, cost_usd)`. SQL UPDATE includes cost_usd column. Test covers a path where abort manifest has `cost_usd: 0.42` → after mark_aborted, get_run returns cost_usd=0.42.

### P2.3 — abort_quota_exceeded removed from PipelineStatus

It's sweep-level (`sweep_quota_refusal.json`), not per-run. Removed from PipelineStatus Literal. If actor encounters this (shouldn't), the else-branch maps to `mark_failed(unknown_pipeline_status)`.

### P2.4 — RunStatusResponse fields Optional

```python
class RunStatusResponse(BaseModel):
    run_id: str
    lifecycle_status: LifecycleStatus
    pipeline_status: PipelineStatus | None = None  # NULL while queued/in_progress
    template: str
    question: str
    queued_at: str
    started_at: str | None = None
    finished_at: str | None = None
    query_slug: str | None = None
    manifest_run_id: str | None = None
    artifact_dir: str | None = None
    cost_usd: float | None = None
    decision_id: str | None = None
    result_json: str | None = None
    error_json: str | None = None
```

All new fields default None. POST /runs response (queued row) validates clean.

### P2.5 — Update existing tests/v6/ tests

I will grep `tests/v6/` for tests asserting old `status` column or old 9-column schema and update them in this same PR. Specifically:
- `tests/v6/test_run_store_*.py` (assertion of `status` column or `RunStatus` 9-value enum)
- `tests/v6/test_actors_*.py` (echo actor completion patterns)

The update is mechanical: `status` → `lifecycle_status`; expand expected Literal values; verify both new + existing tests pass on the new schema.

## Acceptance criteria (updated)

1. `run_store` schema migration (RENAME COLUMN + ADD COLUMN) — idempotent, value-preserving
2. Single `augment_v6_manifest` helper applied at all 7 pipeline-A manifest-write sites
3. Full actors.py failure-mapping (exception / manifest missing / manifest invalid / unknown status → mark_failed)
4. `q` dict carries v6 fields (NO os.environ mutation)
5. UUID-scoped artifact_dir (`outputs/v6_runs/{run_id}/`)
6. mark_failed, mark_aborted (with cost_usd), set_pipeline_meta helpers
7. RunStatusResponse fields Optional for queued/in_progress states
8. PipelineStatus Literal: success, partial_thin_corpus, partial_incomplete_corpus, partial_outline_fallback, partial_qwen_advisory, partial_rule_check_warnings, abort_scope_rejected, abort_corpus_inadequate, abort_corpus_approval_denied, abort_no_verified_sections, abort_no_sources, abort_evaluator_critical, error_unexpected (NO abort_quota_exceeded — sweep-level)
9. LOC budget 250 (raised from 200 to fit additional failure-mapping + migration code) — confirm acceptable
10. Tests cover: schema migration round-trip; all failure-mapping paths; artifact isolation; manifest augmentation (v6-mode on vs off byte-identical); existing tests/v6/ updated

## Direct questions iter 2

1. q-dict instead of os.environ — APPROVE'd as the concurrency-safe path?
2. UUID-scoped `outputs/v6_runs/{run_id}/` artifact_dir — APPROVE'd?
3. RENAME COLUMN migration — APPROVE'd (Python 3.11+ ships SQLite 3.34+)?
4. Single `augment_v6_manifest` helper at all 7 sites — APPROVE'd?
5. LOC budget raise 200→250 — APPROVE'd?
6. Anything else blocking?

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
