HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001a iter 3 — call run_one_query directly + `status` backcompat

Iter 2 P2s all APPROVED (q-dict, UUID-scoped artifact_dir, RENAME COLUMN, single augment helper, 250 LOC). 1 novel P1 + 1 P2 remain.

## P1 from iter 2 — call run_one_query directly with full q shape

You wrote:
> "`build_and_run_v4` currently takes UI-style args (`vector_id`, `query`, etc.) at src/polaris_graph/graph_v4.py:187, not `q=`/`out_root=`. The actual q-dict API is `run_one_query(q, out_root)` in scripts/run_honest_sweep_r3.py:1107, and it requires `q['domain']`/`q['slug']`."

**Code-verified** at scripts/run_honest_sweep_r3.py:1107-1130:

```python
async def run_one_query(q: dict, out_root: Path) -> dict:
    ...
    run_dir = out_root / q["domain"] / q["slug"]
    ...
    run_id = f"SWEEP_{q['domain']}_{q['slug']}_{int(time.time())}"
    ...
    summary = {"slug": q["slug"], "domain": q["domain"], "question": q["question"], ...}
    ...
    scope = run_scope_gate(research_question=q["question"], run_dir=run_dir, run_id=run_id, domain=q["domain"])
```

Required q keys: `domain`, `slug`, `question`.

**Resolution**: actor calls `run_one_query` directly (not `build_and_run_v4`). q dict construction:

```python
# src/polaris_v6/queue/actors.py
import re

def _derive_slug(template_id: str, question: str) -> str:
    """Deterministic URL-safe slug for pipeline-A. Matches existing _SCOPE_LLM
    slug pattern in run_honest_sweep_r3.py."""
    base = f"{template_id}_{question[:60]}"
    return re.sub(r"[^a-z0-9_]+", "_", base.lower()).strip("_")[:120]

TEMPLATE_TO_SCOPE_DOMAIN = {
    "ai_sovereignty": "policy",
    "canada_us": "policy",
    "climate": "policy",
    "clinical": "clinical",
    "defense": "policy",
    "housing": "policy",
    "trade": "policy",
    "workforce": "policy",
}

@dramatiq.actor(...)
def enqueue_research_run(run_id, request_payload):
    if run_store.get_run(run_id) is None:
        return {"run_id": run_id, "status": "completed", "echo": request_payload}
    
    run_store.mark_in_progress(run_id)
    decision_id = str(uuid.uuid4())
    artifact_dir_root = Path(os.environ.get("POLARIS_V6_OUTPUT_ROOT", "outputs/v6_runs")) / run_id
    artifact_dir_root.mkdir(parents=True, exist_ok=True)
    
    template_id = request_payload["template"]
    question = request_payload["question"]
    domain = TEMPLATE_TO_SCOPE_DOMAIN.get(template_id, "policy")
    slug = _derive_slug(template_id, question)
    
    q = {
        # Pipeline-A required keys
        "domain": domain,
        "slug": slug,
        "question": question,
        # v6 extensions (read by augment_v6_manifest helper inside pipeline-A)
        "external_run_id": run_id,
        "decision_id": decision_id,
        "v6_mode": True,
        "out_root_override": str(artifact_dir_root),
    }
    
    try:
        from scripts.run_honest_sweep_r3 import run_one_query
        summary = asyncio.run(run_one_query(q, artifact_dir_root))
    except Exception as exc:
        run_store.mark_failed(run_id, f"pipeline_exception: {type(exc).__name__}: {exc}")
        raise
    
    # ... (rest of mark_completed/mark_aborted/mark_failed logic unchanged from iter 2)
```

Pipeline-A patches to honor v6 keys (per iter 2):
- `run_dir = Path(q["out_root_override"])` when `q.get("v6_mode")`, else existing `out_root / q["domain"] / q["slug"]`
- `if q.get("v6_mode"): manifest = augment_v6_manifest(manifest, external_run_id=q["external_run_id"], decision_id=q["decision_id"], query_slug=q["slug"], ...)` at all 7 manifest-write sites

Note: pipeline-A's internal `run_id` (SWEEP_<domain>_<slug>_<timestamp>) stays unchanged. v6's external UUID is stored as `manifest.external_run_id`. The bridge in I-arch-001d resolves UUID → artifact_dir via run_store.

## P2 from iter 2 — `status` alias backcompat for tests/v6/

You wrote:
> "If `/runs` response backcompat is still intended from iter 1, keep a deprecated `status` alias populated from `lifecycle_status`; current tests still assert body['status'] and record.status in tests/v6/test_api_health_and_runs.py and tests/v6/acceptance/*."

**Resolution**: Pydantic `computed_field` returning lifecycle_status:

```python
# src/polaris_v6/schemas/run_status.py
from pydantic import BaseModel, Field, computed_field

class RunStatusResponse(BaseModel):
    run_id: str
    lifecycle_status: LifecycleStatus
    # ... other fields ...
    
    @computed_field  # Serialized in JSON; readable on instances
    @property
    def status(self) -> LifecycleStatus:
        """Deprecated alias for lifecycle_status. Kept for v1 API backcompat.
        Will be removed post-Carney-demo once tests/v6/ migrate."""
        return self.lifecycle_status
```

Existing assertions `body['status']` continue to work; new code uses `lifecycle_status`.

run_store.get_run reads `lifecycle_status` column; constructs RunStatusResponse; the computed_field surfaces both.

Test `tests/polaris_v6/queue/test_run_status_backcompat.py`:
- get_run returns model where `.status == .lifecycle_status`
- JSON serialization includes BOTH `status` and `lifecycle_status` keys (computed_field is serialized by default)
- All existing tests/v6/ pass without modification

## Acceptance criteria (final)

1. ✅ run_store schema migration via RENAME COLUMN + ADD COLUMN (idempotent, value-preserving)
2. ✅ Single `augment_v6_manifest` helper at all 7 pipeline-A manifest-write sites
3. ✅ Full actor failure-mapping (pipeline_exception → mark_failed, manifest missing → mark_failed, success/partial_* → mark_completed, abort_* → mark_aborted with cost_usd, error_* → mark_failed)
4. ✅ q dict carries v6 fields with correct pipeline-A keys (`domain`, `slug`, `question`, `external_run_id`, `decision_id`, `v6_mode`, `out_root_override`)
5. ✅ UUID-scoped artifact_dir `outputs/v6_runs/{run_id}/`
6. ✅ run_store helpers: mark_failed, mark_aborted(with cost_usd), set_pipeline_meta, get_run with new fields
7. ✅ RunStatusResponse: Optional new fields + computed_field `status` alias for backcompat
8. ✅ PipelineStatus Literal: success, partial_thin_corpus, partial_incomplete_corpus, partial_outline_fallback, partial_qwen_advisory, partial_rule_check_warnings, abort_scope_rejected, abort_corpus_inadequate, abort_corpus_approval_denied, abort_no_verified_sections, abort_no_sources, abort_evaluator_critical, error_unexpected (NO abort_quota_exceeded)
9. ✅ NO os.environ mutation in actor (q-dict only)
10. ✅ Tests: schema migration, failure-mapping (all paths), artifact isolation, manifest augmentation, status backcompat alias, existing tests/v6/ updated where needed
11. LOC budget 250

## Direct questions iter 3

1. Direct `run_one_query` call with full q-dict (domain/slug/question/v6 fields) — APPROVE'd?
2. `_derive_slug` deterministic URL-safe pattern (template_id + question prefix, snake_case, 120-char cap) — APPROVE'd, or want a different slug scheme?
3. Pydantic `computed_field` for `status` alias — APPROVE'd?
4. TEMPLATE_TO_SCOPE_DOMAIN map (housing/trade/defense/climate/canada_us/ai_sovereignty/workforce → policy; clinical → clinical) — APPROVE'd as week-1 mapping?
5. Anything else blocking iter-3 APPROVE?

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
