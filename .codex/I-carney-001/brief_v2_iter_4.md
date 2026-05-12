HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# brief_v2 iter 4 — byte-exact schemas from your iter-3 citations

Read every file:line you cited. Below are the corrected resolutions.

## P1.2 — v30.1 contract exact shape

Per `report_contract.py:170` `_REQUIRED_ENTITY_KEYS = {"id", "type", "required_fields", "min_fields_for_completion", "rendering_slot"}` and `_REQUIRED_SLOT_KEYS = {"section", "subsection_title", "ordering"}`:

```python
# v30.1 contract emitted by synthesizer for query_slug `clinical_tirzepatide_t2dm`
contract = {
    "per_query_report_contract": {
        "clinical_tirzepatide_t2dm": {
            "schema_version": "v30.1",
            "required_entities": [
                {
                    "id": "tirzepatide",
                    "type": "drug",
                    "required_fields": ["rxcui", "drugbank_id", "atc_code"],
                    "min_fields_for_completion": 2,
                    "rendering_slot": "summary.intro",
                },
                {
                    "id": "type_2_diabetes",
                    "type": "condition",
                    "required_fields": ["icd_10", "snomed_ct"],
                    "min_fields_for_completion": 1,
                    "rendering_slot": "summary.intro",
                },
                # ... derived from frame_manifest by synthesizer
            ],
            "rendering_slots": [
                {"section": "summary", "subsection_title": "Introduction", "ordering": 1},
                {"section": "summary", "subsection_title": "Key findings", "ordering": 2},
                {"section": "efficacy", "subsection_title": "Primary endpoint", "ordering": 3},
                # ... derived from template frame_manifest mapping
            ],
        }
    }
}
```

Synthesizer module `src/polaris_graph/v30_contract_synthesizer.py:build(template_id, question, query_slug)`:
- Reads `config/v6_templates/<template_id>.json`
- For each frame in `frame_manifest`, derives 1-3 required entities + 1-2 rendering_slots
- Entities use `required_fields` (list of identifier-field NAMES per domain) + `min_fields_for_completion` (≤ len(required_fields))
- Identifier resolution: synthesizer ONLY emits field NAMES (e.g., `["rxcui", "drugbank_id"]`). Resolution to actual VALUES (e.g., `rxcui=2601723`) happens at retrieval/fetch time by domain-specific resolvers per Codex's frame_fetcher.py:861 path. If no resolver exists for a domain field, frame_fetcher's existing graceful-skip path handles it (`required_fields` may stay unresolved; coverage drops; ≥`min_fields_for_completion` is the threshold).
- DOI/PMID/URL regex patterns: NOT in contract shape per `_REQUIRED_*_KEYS`. Withdrew that from iter 3. Those patterns live in pipeline-A's existing source-discovery (run_honest_sweep_r3.py) and are domain-config not contract-shape.
- `schema_version: "v30.1"` literal string (verified at report_contract.py:170 `_KNOWN_SCHEMA_VERSIONS = frozenset({"v30.1"})`).

8 v6 templates synthesized → 8 golden fixtures (`tests/fixtures/v30_contracts/<template_id>.json`) loaded round-trip-clean by `load_report_contract_for_slug`. Codex-reviewed per fixture.

## P1.3 — AuditIR→slice-chain bridge with exact schemas

Reading scope_decision.py:127, evidence_pool.py:54+131, verified_report.py:386+410:

**ScopeDecision fields** (verified):
- `status: ScopeStatus`
- `scope_class: ScopeClassValue | None`
- `ambiguity_axes: list[AmbiguityAxis]`
- `clarifications_needed: list[str]`
- `provenance: dict[str, str]`
- NO `question`/`domain`/`verdict`/`reason` (I was wrong; withdrawn)

**Source** (NOT `EvidenceSource`):
- `source_id: str`, `url: HttpUrl`, `domain: str`, `tier: SourceTier`, `title: str`, `publication_date: date | None`, `authors: list[str]`, `snippet: str`, `full_text_available: bool`, `full_text: str | None`, `fetched_at_utc: datetime`, `provenance: dict[str, Any]`, `retracted: bool`

**EvidencePool**:
- `pool_id`, `decision_id` (FK to ScopeDecision), `sources: list[Source]`, `adequacy: AdequacyVerdict`, `queries_executed`, `retrieval_started_at_utc`, `retrieval_finished_at_utc`, `latency_ms`, `cost_usd`

**VerifiedReport**:
- `report_id`, `pool_id` (FK to EvidencePool), `decision_id` (FK to ScopeDecision), `sections: list[Section]`, `overall_verify_pass_rate`, `pipeline_verdict`, `generator_model`, `evaluator_model`

Bridge:

```python
# src/polaris_v6/api/artifact_to_slice_chain.py
from datetime import datetime, timezone
from pathlib import Path
from polaris_graph.audit_ir.loader import load_audit_ir
from polaris_graph.scope.scope_decision import ScopeDecision, ScopeStatus, ScopeClassValue, AmbiguityAxis
from polaris_graph.retrieval2.evidence_pool import EvidencePool, Source, SourceTier, AdequacyVerdict
from polaris_graph.generator2.verified_report import VerifiedReport, Section, VerifiedSentence, PipelineVerdict, SectionStatus

def build_slice_chain(artifact_dir: Path) -> tuple[ScopeDecision, EvidencePool, VerifiedReport]:
    air = load_audit_ir(artifact_dir)
    
    # ScopeDecision — extract from manifest's scope block (verified at completed runs)
    decision = ScopeDecision(
        status=ScopeStatus.IN_SCOPE,
        scope_class=ScopeClassValue(air.manifest.scope.classification),  # if exists
        ambiguity_axes=[],  # no clarification needed for completed runs
        clarifications_needed=[],
        provenance={"classifier_layer": air.manifest.scope.classifier_layer or "auto", ...},
    )
    decision_id = decision.pool_id if hasattr(decision, "pool_id") else str(uuid.uuid4())
    # Note: ScopeDecision doesn't have an id field per current schema — emit via separate Pydantic extension or use a wrapper. Need clarification (Codex Q1).
    
    # EvidencePool — bibliography.json + sovereignty filter on Source.provenance.legal_cleared
    sources = []
    for entry in air.bibliography.entries:
        is_legal_cleared = entry.tier == "T1" or entry.legal_cleared_flag
        if not is_legal_cleared:
            continue  # exclude non-cleared from pool entirely (sovereignty_guard.py:17-26)
        sources.append(Source(
            source_id=entry.evidence_id,
            url=entry.url,
            domain=entry.domain,
            tier=SourceTier(entry.tier),
            title=entry.title,
            publication_date=entry.publication_date,
            authors=entry.authors or [],
            snippet=entry.snippet or "",
            full_text_available=bool(entry.full_text),
            full_text=entry.full_text,
            fetched_at_utc=entry.fetched_at_utc,
            provenance={"legal_cleared": True, "tier": entry.tier},
            retracted=entry.retracted,
        ))
    pool = EvidencePool(
        pool_id=str(uuid.uuid4()),
        decision_id=decision_id,
        sources=sources,
        adequacy=AdequacyVerdict.model_validate(air.manifest.adequacy_block),
        queries_executed=air.manifest.queries_executed or [],
        retrieval_started_at_utc=datetime.fromisoformat(air.manifest.retrieval_started_at),
        retrieval_finished_at_utc=datetime.fromisoformat(air.manifest.retrieval_finished_at),
        latency_ms=air.manifest.retrieval_latency_ms,
        cost_usd=air.manifest.retrieval_cost_usd,
    )
    
    # VerifiedReport — sections from report.md + verification_details.json
    sections = []
    for section_data in air.verification.sections:
        verified_sentences = [
            VerifiedSentence(...)  # from section_data.sentences
            for s in section_data.sentences
        ]
        sections.append(Section(
            section_id=section_data.section_id,
            section_title=section_data.section_title,
            verified_sentences=verified_sentences,
            section_verify_pass_rate=section_data.pass_rate,
            section_status=SectionStatus(section_data.status),
        ))
    report = VerifiedReport(
        report_id=air.manifest.run_id,  # pipeline-A SWEEP_xxx (internal)
        pool_id=pool.pool_id,
        decision_id=decision_id,
        sections=sections,
        overall_verify_pass_rate=air.verification.overall_pass_rate,
        pipeline_verdict=PipelineVerdict(air.manifest.pipeline_status),
        generator_model=air.manifest.generator_model,
        evaluator_model=air.manifest.evaluator_model,
    )
    
    return (decision, pool, report)
```

**Direct Q1 for you**: `ScopeDecision` per the verified schema doesn't have a primary-key field. `EvidencePool.decision_id` and `VerifiedReport.decision_id` reference one. The slice-001 ScopeDecision must have an ID somewhere — either it's elsewhere in the pydantic model (not shown in my grep window) or the slice-chain FK contract is implicit (audit-bundle re-emits decision/pool/report in same payload). Verify which file/line carries the ScopeDecision identifier, OR confirm that decision_id is a manually-set UUID by the caller per call (and audit-bundle re-validates equality).

Sovereignty filter: drop non-cleared sources BEFORE constructing the pool (sovereignty_guard.py:17-26 fails if ANY source in pool.sources is not legal_cleared). The Inspector UI still shows non-cleared sources via a separate read-only registry view (no bundle redistribution).

## P1.5 — async Redis Streams + Last-Event-ID header + terminal events

Per Codex P1.5 iter 3:
> "The proposed async SSE loop uses blocking sync Redis xread inside an async generator and only reads a query param for replay instead of also honoring the standard Last-Event-ID header."

**Resolution**:

```python
# src/polaris_v6/queue/run_events.py
import redis.asyncio as aredis  # nonblocking async client
from fastapi import Header

async def stream_events_for(
    run_id: str,
    last_event_id_header: str | None = Header(None, alias="Last-Event-ID"),
    last_event_id_qs: str = "0",
) -> AsyncIterator[str]:
    """SSE stream of v6 named events for a given external UUID.
    
    Replay: honors HTTP Last-Event-ID header first, falls back to ?last_event_id=
    query string. Standard EventSource browsers send Last-Event-ID automatically
    on reconnect.
    
    Terminal events emitted on all success/abort/error paths:
        - run_complete (status=success|partial_*|abort_*|error_*)
    """
    last_id = last_event_id_header or last_event_id_qs or "0"
    redis_client = aredis.from_url(os.environ["POLARIS_V6_REDIS_URL"])
    key = f"polaris:events:{run_id}"
    
    try:
        while True:
            # block=5000ms; non-blocking on event loop because aredis is async
            events = await redis_client.xread({key: last_id}, count=100, block=5000)
            if not events:
                yield ": keepalive\n\n"
                continue
            for stream, entries in events:
                for entry_id, fields in entries:
                    last_id = entry_id
                    pa_event = {"event_type": fields[b"event_type"].decode(),
                                **json.loads(fields[b"payload"])}
                    v6_event = translate(pa_event)
                    if v6_event is None:
                        continue
                    v6_name, v6_payload = v6_event
                    yield f"id: {entry_id.decode()}\nevent: {v6_name}\ndata: {json.dumps(v6_payload)}\n\n"
                    if v6_name == "run_complete":
                        return  # terminal
    finally:
        await redis_client.aclose()
```

Pipeline-A `emit_event` for terminal events:
- `run.completed` with `status=success` (normal completion)
- `run.aborted` with `status=abort_scope_rejected|abort_corpus_inadequate|abort_corpus_approval_denied|abort_no_verified_sections|abort_budget_exceeded`
- `run.failed` with `status=error_<kind>`

Translator (`PIPELINE_TO_V6` table from iter 2) extended:
- `run.aborted` → `run_complete` event with `payload.status = abort_xxx`
- `run.failed` → `run_complete` event with `payload.status = error_xxx`

All terminal cases emit a `run_complete` v6 event → SSE consumer always gets a close signal. No hangs.

## P2.1 — status enum unified

Per Codex iter-3 P2.1: pipeline-A statuses are `success/partial_*/abort_*/error_unexpected` (run_honest_sweep_r3.py:165); v6 RunStatus is `queued/in_progress/completed/failed + abort subset` (src/polaris_v6/schemas/run_status.py:9).

**Resolution**: TWO orthogonal status fields in run_store:

```python
# src/polaris_v6/queue/run_store.py — schema
"""
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,                            -- v6 UUID
    query_slug TEXT,                                    -- pipeline-A URL-safe (e.g., clinical_tirzepatide_t2dm)
    manifest_run_id TEXT,                               -- pipeline-A SWEEP_xxx
    artifact_dir TEXT,                                  -- absolute path
    lifecycle_status TEXT NOT NULL,                     -- queued|in_progress|completed|failed
    pipeline_status TEXT,                               -- success|partial_*|abort_*|error_*  (NULL until manifest written)
    template_id TEXT,
    scope_domain TEXT,
    question TEXT,
    error TEXT,
    queued_at TEXT NOT NULL,                            -- ISO 8601 UTC
    started_at TEXT,
    completed_at TEXT,
    cost_usd REAL
);
"""
```

`lifecycle_status` is the v6 API contract (queued/in_progress/completed/failed). `pipeline_status` is the pipeline-A manifest status (preserves full taxonomy). The v6 API returns BOTH so frontend can show "Completed (abort_no_verified_sections)" with proper UX.

## P2.2 — graph_v4 domain mapping

graph_v4.py:92 + 112 + scope_gate.py:69 are the touch points. I'll grep them in I-arch-001c brief #1 and either:
- Add 4 new domains (housing/trade/defense/climate) to `SUPPORTED_DOMAINS` + write 4 minimal scope_template YAMLs that mirror existing policy template, OR
- Map all 4 to existing `policy` at the actor boundary (`actors.py` translates template_id → scope_domain before invoking pipeline-A)

For week-1: option B (map to policy). Per-domain template authoring is post-demo.

## Updated calendar (24 days, unchanged)

Same as iter 2 brief. I-arch-001a..f + I-carney-002..007. Days 1-11 architecture, 12-24 deploy + rehearsal.

## Direct questions iter 4

1. P1.2 v30.1 contract shape with `schema_version: "v30.1"` + `required_fields/min_fields_for_completion/rendering_slot` per entity + `section/subsection_title/ordering` per slot — exact match per report_contract.py:170-220 — APPROVE'd?
2. P1.3 slice-chain bridge with verified `Source` (not EvidenceSource) + `ScopeStatus.IN_SCOPE` + `AdequacyVerdict.model_validate(manifest.adequacy_block)` etc. — APPROVE'd?
3. P1.3 Direct Q1: where does the `ScopeDecision` ID/`decision_id` come from? Manual caller-supplied UUID? A field I missed in my grep window? Please cite file:line.
4. P1.5 async aredis + Last-Event-ID header + terminal events on success/abort/error — APPROVE'd?
5. P2.1 dual lifecycle_status + pipeline_status columns — APPROVE'd?
6. P2.2 template_id → "policy" map for week-1 (housing/trade/defense/climate) — APPROVE'd?

If APPROVE on this iter, I open sub-issues + start I-arch-001a. If REQUEST_CHANGES on iter 4, iter 5 force-APPROVE per §8.3.1, residuals captured as follow-up.

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
