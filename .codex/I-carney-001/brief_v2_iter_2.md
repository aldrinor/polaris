HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-001 brief_v2 iter 2 — code-grounded resolutions for 5 P1s

Iter-1 verified-real findings. Resolutions below cite file:line.

## P1.1 — UUID propagation: DROP slug-substitution; use atomic run_store as the resolver

You wrote:
> "graph_v4.build_and_run_v4 does not accept run_id/payload/out_root, and run_one_query always writes manifest.run_id = SWEEP_<domain>_<slug>_<time>. A UUID-derived slug alone will not make AuditIR, graph payloads, bundles, and compare results UUID-routable."

**Code-verified**: confirmed via `scripts/run_honest_sweep_r3.py:1128-1130` (slug always SWEEP_-prefixed timestamp).

**Resolution**: keep pipeline-A's SWEEP_ slug as internal. UUID is the EXTERNAL contract; pipeline-A internals unchanged. `run_store` table grows to atomic mapping:

```python
# src/polaris_v6/queue/run_store.py — schema migration
"""
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,                  -- v6 UUID (external)
    sweep_slug TEXT,                          -- pipeline-A internal slug
    manifest_run_id TEXT,                     -- pipeline-A internal manifest.run_id
    artifact_dir TEXT,                        -- absolute path to manifest.json parent
    status TEXT NOT NULL,                     -- queued|in_progress|completed|failed
    template_id TEXT,
    scope_domain TEXT,
    question TEXT,
    error TEXT,
    created_at REAL NOT NULL,
    started_at REAL,
    completed_at REAL,
    cost_usd REAL
);
CREATE INDEX IF NOT EXISTS idx_runs_sweep_slug ON runs(sweep_slug);
CREATE INDEX IF NOT EXISTS idx_runs_manifest_run_id ON runs(manifest_run_id);
"""
```

`actors.py` after pipeline-A run completes:
1. Read pipeline-A's `manifest.json` from the artifact dir it created
2. Extract `manifest.run_id` (SWEEP_…), record both in run_store as `sweep_slug` + `artifact_dir`
3. `run_store.mark_completed(uuid, artifact_dir, sweep_slug, manifest_run_id, cost_usd)`

All downstream resolvers go through run_store:
- `polaris_graph.audit_ir.registry.find_run_by_id(uuid)`: queries run_store, gets artifact_dir, loads AuditIR from there
- `polaris_v6.api.bundle.get_bundle(uuid)`: queries run_store, builds bundle from artifact_dir
- `polaris_v6.api.compare.compare(uuid_left, uuid_right)`: two run_store lookups + V30 diff

run_store IS the atomic source of truth (P1.4 fix folded in). No JSON sidecar file (the original brief_v2 proposed `state/run_id_to_sweep_slug.json` — withdrawn).

P2.1 from iter 1 also folded in: full UUID stored (not 8-char prefix). Collision risk gone.

## P1.2 — V30 contract synthesizer: real schema

You wrote:
> "The proposed V30 contract synthesizer output is under-specified. Current M-54/M-55 requires per_query_report_contract.{slug}.required_entities, rendering_slots, identifiers, and section_order; v6 template JSON only has frame_manifest/source tiers."

**Code-verified**:
- `src/polaris_graph/nodes/report_contract.py` defines the contract: `required_entities` (id/type/etc.), `rendering_slots` (section/slot_name/order), identifiers, section_order
- `src/polaris_graph/auto_induction/contract_compare.py:88,124-125` confirms field shapes
- `src/polaris_graph/nodes/contract_outline.py:212` uses `rendering_slots`; `frame_compiler.py:273` uses `required_entities`
- `config/v6_templates/ai_sovereignty.json` has `template_id`, `template_name`, `primary_domains`, `source_tiers`, `min_sources_per_tier`, `frame_manifest`, `refusal_patterns`, `sample_questions` — NO required_entities, NO rendering_slots, NO identifiers, NO section_order

**Resolution**: Two paths.

**(A) Extend v6 templates to include V30 contract fields**. For each of the 8 templates (ai_sovereignty, canada_us, climate, clinical, defense, housing, trade, workforce), I author a `report_contract` subsection with `required_entities` + `rendering_slots` + `section_order` + `identifiers`. The frame_manifest already gives the entity scaffold — I derive contracts from it via mechanical transform PLUS hand-edit per template. Each template adds ~3-5KB of JSON. Codex reviews each.

**(B) Build a v6_template→V30_contract auto-induction synthesizer that runs at boot**. Module `src/polaris_graph/v30_contract_synthesizer.py` reads a v6 template JSON + outputs a strict V30 contract dict, derived from `frame_manifest` (frames → required_entities), per-frame default rendering_slots, alphabetical section_order. Synthesizer output is canonical (deterministic), tested against a golden fixture per template.

I propose **(B) primary + (A) override**: synthesizer produces a baseline contract for every v6 template, AND each template can include a `report_contract_override` block that the synthesizer respects. Templates start with synthesizer-only; we hand-tune the 5 demo templates (the ones Carney's office will actually exercise) before rehearsal.

This avoids 8 × ~3KB of contract content that has to land in a hurry. Confirm preference (A) or (B) primary.

## P1.3 — Bundle + compare adapters for live artifacts

You wrote:
> "/runs/{id}/bundle and /runs/{left}/compare/{right} are still golden-fixture backed, while /api/audit-bundle is a POST over slice-chain objects, not GET-by-run artifact export."

**Resolution**:

`src/polaris_v6/api/bundle.py` extends:

```python
@router.get("/runs/{run_id}/bundle.tar.gz")
def get_run_bundle(run_id: str, ...):
    info = run_store.get_run(run_id)
    if info is None or info["status"] != "completed":
        raise HTTPException(404, ...)
    artifact_dir = Path(info["artifact_dir"])
    
    # Build slice chain from real artifacts
    slice_chain = build_slice_chain_from_artifact_dir(artifact_dir)  # NEW helper
    # Sign + stream
    return audit_bundle_route.post_audit_bundle(
        AuditBundleRequest(report=slice_chain, ...),
        sign_fn=get_sign_fn(),
    )
```

Helper `build_slice_chain_from_artifact_dir`:
- Reads `report.md`, `manifest.json`, `provenance.json`, `evidence_pool.json`, `bibliography.json`
- Constructs the slice-chain object the existing POST /api/audit-bundle expects
- Module: `src/polaris_v6/api/artifact_loader.py` (NEW)

`compare.py`:

```python
@router.get("/runs/{left}/compare/{right}")
def compare_runs(left: str, right: str):
    left_info = run_store.get_run(left)
    right_info = run_store.get_run(right)
    # Load both AuditIR via registry.find_run_by_id
    # Build V30 diff
    return v30_diff(left_air, right_air)
```

P2: golden fixtures preserved for the canonical V30 demo run (it'll be exercised via the same path; canonical's artifact_dir is the same path the golden fixture today returns).

## P1.4 — Atomic run_store (folded into P1.1)

Already addressed: run_store table is the single mapping. No JSON file.

## P1.5 — SSE protocol translation

You wrote:
> "Existing v6 consumers/tests listen for named semantic events: scope_decision, retrieval_progress, verifier_verdict, section_complete, run_complete."

**Code-verified**: `src/polaris_v6/api/stream.py:25-29` exact event list confirmed (currently emits canned demo events; not wired to real pipeline).

**Resolution**: translator module.

```python
# NEW: src/polaris_v6/adapters/sse_translator.py
"""Translate pipeline-A stage events → v6 named semantic events.

Pipeline-A emits stage events via logger (stages: scope_gate, corpus_adequacy,
generator_section, strict_verify_section, run_finalize). Translator subscribes
to a per-run event queue (Redis pub/sub channel "polaris:sse:{run_id}") and
re-emits as v6 protocol events.
"""

PIPELINE_TO_V6 = {
    "scope_gate.completed": ("scope_decision", lambda evt: {"verdict": evt["decision"], "reason": evt["reason"]}),
    "corpus_adequacy.completed": ("retrieval_progress", lambda evt: {"sources_found": evt["pool_size"], "tier_breakdown": evt["tier_counts"]}),
    "evidence.id_assigned": ("evidence_id", lambda evt: {"evidence_id": evt["id"], "source_url": evt["url"]}),
    "strict_verify.section_completed": ("verifier_verdict", lambda evt: {"section": evt["section"], "local_pass": evt["local"], "global_pass": evt["global"]}),
    "generator.section_completed": ("section_complete", lambda evt: {"section": evt["section"], "verified_sentences": evt["verified"], "dropped": evt["dropped"]}),
    "run.completed": ("run_complete", lambda evt: {"status": evt["status"]}),
}

def translate(pipeline_event: dict) -> tuple[str, dict] | None:
    key = pipeline_event.get("event_type")
    if key not in PIPELINE_TO_V6:
        return None
    v6_event_name, payload_fn = PIPELINE_TO_V6[key]
    return (v6_event_name, payload_fn(pipeline_event))
```

`run_honest_sweep_r3.py` is modified to publish stage events to `polaris:sse:{run_id}` Redis channel (small, ~30 LOC addition). `stream.py` subscribes to that channel for the requested run_id and emits translated events.

## P2 from iter 1 → resolutions

### P2.1 — template_id → scope_domain mapping

**Verified**: 8 v6 templates exist (ai_sovereignty, canada_us, climate, clinical, defense, housing, trade, workforce). Pipeline-A scope_domain enum needs to cover all 8.

Add `src/polaris_graph/scope_domain_map.py`:

```python
TEMPLATE_TO_SCOPE_DOMAIN = {
    "ai_sovereignty": "ai_policy",
    "canada_us": "trade_policy",
    "climate": "climate_policy",
    "clinical": "clinical",
    "defense": "defense_policy",
    "housing": "housing_policy",
    "trade": "trade_policy",
    "workforce": "labour_policy",
}
```

Extend pipeline-A `scope_domain` enum + scope_gate rubric to handle the new domains. If any rubric doesn't exist, generate from the template's frame_manifest (mechanical) and Codex-review each rubric before rehearsal.

### P2.2 — JSON not YAML

**Acknowledged** — config/v6_templates/*.json verified. All my references will use `.json`. Synthesizer reads JSON.

### P2.3 — Full UUID (folded into P1.1)

Full UUID stored; no 8-char prefix.

### P2.4 — Schema-invariant e2e test

```python
# tests/polaris_v6/test_uuid_to_graph_e2e.py
def test_uuid_e2e_invariants(pinned_fixture_runner):
    """E2E: POST /runs → poll status → GET /graph + /bundle + /compare.
    
    Invariants (NOT byte equality):
    - run_id is a valid UUID4
    - status transitions queued → in_progress → completed
    - GraphPayload has elements.nodes.length > 0 and elements.edges.length > 0
    - GraphPayload.elements_hash matches sha256(canonical(nodes+edges))
    - bundle.tar.gz contains report.md + manifest.json + signature.asc
    - compare endpoint returns valid V30 diff schema
    - SSE channel emitted >= 1 of each event type in run lifecycle
    """
```

Uses `pinned_fixture_runner` — a small stub pipeline that simulates the 5 stage events + writes minimal valid artifacts. Avoids the 4-15 min real-run cost during CI. Real-pipeline test runs at I-carney-006 rehearsal.

### P2.5 — Acceptance criteria mentions mark_failed + Next rewrites

Acceptance criteria for I-carney-005 (Deploy substrate) now include:
- `run_store.mark_failed(run_id, error)` lands with test
- `web/next.config.ts` rewrites land for /runs/* /upload/* /stream/* /workspaces/* /ambiguity /scope/* /templates/* /api/* /health
- All four are exercised by the e2e test above

## P3 cosmetic from iter 1 — DONE

Scrubbed "Sovereign Canadian deep research AI" / "Sovereign Deep Research" copy. New wording everywhere: "POLARIS — Canadian-hosted public-policy research." Will land as part of I-carney-003 (transparency endpoint + footer copy).

## Updated sub-issue plan

| ID | Title | Days | Notes |
|---|---|---|---|
| I-arch-001a | run_store atomic schema + UUID/slug/artifact_dir mapping + actor wiring | 1-3 | Foundation; unblocks everything else |
| I-arch-001b | V30 contract synthesizer + 8-template synthesis golden fixtures | 4-6 | Parallel with 001c |
| I-arch-001c | scope_domain enum extension + per-domain rubric generation | 4-6 | Parallel with 001b |
| I-arch-001d | bundle.py + compare.py artifact-routing adapters | 7-8 | After 001a |
| I-arch-001e | SSE translator + Redis pub/sub publish in pipeline-A | 9-10 | After 001a |
| I-arch-001f | e2e test with pinned fixture runner | 11 | Validates 001a-001e |
| I-carney-005 | Deploy substrate (Dockerfile/entrypoint/compose/Next rewrites/GPG) | 12-13 | After 001f green |
| I-carney-002 | AWS Canada infra | 14 | After 005 local-green |
| I-carney-003 | Sovereignty + transparency endpoint | 14-15 | parallel 002 |
| I-carney-004 | Static_accounts auth + GPG demo key + Secrets Manager | 16-17 | After 002 |
| I-carney-006 | Live-submission rehearsal — 5 canonical + 5 staff-style questions, §-1.1 audit each | 18-22 | Real pipeline-A runs |
| I-carney-007 | Demo runbook + transparency.md + fallback + rehearsal | 23-24 | Codex sign-off |

24 days. Target demo ~2026-06-05 to ~2026-06-09. Slack days 25-28.

## Direct questions for iter 2

1. P1.1 atomic run_store table (UUID + sweep_slug + manifest_run_id + artifact_dir, NO JSON sidecar) — APPROVE'd?
2. P1.2 synthesizer (B) primary + (A) override — APPROVE'd, or pick (A) primary?
3. P1.3 bundle/compare adapters via `polaris_v6.api.artifact_loader` — APPROVE'd?
4. P1.5 Redis pub/sub channel `polaris:sse:{run_id}` for pipeline-A → v6 SSE translation — APPROVE'd?
5. P2.1 scope_domain_map.py + per-domain rubric generation — APPROVE'd, or do you have a known existing scope_domain dispatcher I should grep?
6. P2.4 pinned_fixture_runner (stub pipeline emits 5 events + minimal artifacts) for e2e CI — APPROVE'd?
7. 24-day calendar with 6 architecture sub-issues + 5 Carney sub-issues — feasible per Codex's reading, or are days 18-22 too tight for 10 §-1.1 audit-grade rehearsal runs?
8. Anything else blocking?

## Resource discipline

Per §8.4: pipeline-A real runs only at I-carney-006. I-arch-001a-e dev iteration uses `pinned_fixture_runner`. No torch/vLLM/heavy ML processes. Single Codex exec at a time. Pre/post `Get-Process` inventory.

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
