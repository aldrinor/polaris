HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-001 brief_v2 iter 3 — code-grounded fixes for 3 remaining P1s

Iter-2 narrowed to 3 P1s: (a) V30 synthesizer slug+identifiers, (b) AuditIR→slice-chain bundle bridge, (c) SSE durability+UUID-binding. All three resolved below with file:line citations.

## P1.2 — V30 contract synthesizer must emit `per_query_report_contract.{run_slug}` with resolvable identifiers

You wrote:
> "the V30 synthesizer must emit `per_query_report_contract.{run_slug}` for the actual pipeline-A slug, and must provide resolvable DOI/PMID/url_pattern identifiers. A frame_manifest-only baseline will either no-op at `v30_sweep_integration.py:273,287` or fail/gap at `frame_compiler.py:306` / `frame_fetcher.py:861`."

**Resolution: synthesizer is keyed by pipeline-A slug, not v6 UUID. Identifiers carry resolvable patterns.**

Synthesizer flow:

1. Actor receives v6 UUID + question + template_id
2. Actor calls `derive_pipeline_a_slug(template_id, question)` returning e.g. `clinical_tirzepatide_t2dm` (deterministic + URL-safe slug from `template_id` + a hash of question; collision-safe + 64-char max)
3. Actor calls `v30_contract_synthesizer.build(template_id, question, run_slug)` returning a `per_query_report_contract` dict KEYED by `run_slug`:

```python
{
    "per_query_report_contract": {
        "clinical_tirzepatide_t2dm": {
            "required_entities": [
                {"id": "tirzepatide", "type": "drug", "identifiers": {
                    "rxcui": "2601723",
                    "drugbank_id": "DB15171",
                    "atc_code": "A10BX16",
                    "url_pattern": "https://www.drugbank.ca/drugs/DB15171"
                }},
                {"id": "type_2_diabetes", "type": "condition", "identifiers": {
                    "icd_10": "E11",
                    "snomed_ct": "44054006",
                    "mesh_id": "D003924"
                }},
                # ... derived from template's frame_manifest + question entities
            ],
            "rendering_slots": [
                {"section": "summary", "slot_name": "intro", "order": 1},
                {"section": "summary", "slot_name": "key_findings", "order": 2},
                {"section": "efficacy", "slot_name": "primary_endpoint", "order": 3},
                # ... derived from template's frame_manifest mapping to sections
            ],
            "identifiers": {
                "doi_pattern": r"10\.\d{4,9}/[-._;()/:A-Z0-9]+",
                "pmid_pattern": r"PMID:\s*\d{1,8}",
                "url_pattern": r"https?://(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}/.*",
                "registry_patterns": {
                    "nct": r"NCT\d{8}",
                    "clinical_trial": r"https://clinicaltrials\.gov/study/NCT\d{8}",
                }
            },
            "section_order": ["summary", "efficacy", "safety", "regulatory_status", "limitations"],
        }
    }
}
```

Synthesizer module: `src/polaris_graph/v30_contract_synthesizer.py` (NEW).

Per-domain identifier extractors (entity resolver):
- `clinical`: rxcui (RxNorm API), drugbank_id, mesh_id, icd_10, snomed_ct, nct
- `housing`: stats_can_table_id, cmhc_market_code
- `defense`: nato_program_id, gao_report_id
- `climate`: ipcc_chapter_id, eccc_report_id
- `ai_sovereignty`: ised_program_id, bill_c27_section
- `trade`: hs_code, tariff_line, wto_dispute_id
- `canada_us`: cusma_chapter, fcc_proceeding_id
- `workforce`: stats_can_table_id, ilo_indicator_id

Each domain's resolver lives in `src/polaris_graph/entity_resolvers/<domain>.py`. Synthesizer dispatches by `scope_domain`. If no resolver exists yet for a domain (e.g., the 4 new policy domains), the synthesizer emits the entity with `identifiers: {}` and a `requires_resolution: true` flag; pipeline-A's `frame_fetcher.py:861` is patched (I-arch-001b) to skip resolution gracefully when this flag is set (vs failing) until resolvers ship.

For Carney demo: prioritize resolvers for the 5 templates actually exercised (Codex picks which 5 in iter 4).

## P1.3 — AuditIR → slice-chain bundle bridge

You wrote:
> "canonical pipeline-A artifacts are `manifest.json`, `report.md`, `bibliography.json`, `contradictions.json`, `verification_details.json` (`audit_ir/loader.py:965-992`). Existing `/api/audit-bundle` requires `ScopeDecision`, `EvidencePool`, `VerifiedReport` (`audit_bundle_route.py:60-69`) plus legal-cleared pool sources (`sovereignty_guard.py:17-26`)."

**Resolution: NEW module `src/polaris_v6/api/artifact_to_slice_chain.py` builds slice-chain pydantic models from AuditIR artifact dir.**

```python
# src/polaris_v6/api/artifact_to_slice_chain.py (NEW)
"""Bridge AuditIR canonical artifacts → audit-bundle slice-chain models.

AuditIR (canonical pipeline-A output):
  manifest.json, report.md, bibliography.json, contradictions.json,
  verification_details.json  + optional protocol.json, corpus_approval.json,
  evaluator_rule_checks.json, qwen_judge_output.json

Slice-chain (audit-bundle POST shape):
  ScopeDecision (slice 001) + EvidencePool (slice 002) + VerifiedReport (slice 003)

Maps each field, sets provenance.legal_cleared per sovereignty_guard.py:17-26
requirements (legal_cleared=True for Tier-1 public + flagged-false otherwise).
"""

from pathlib import Path
from polaris_graph.retrieval2.evidence_pool import EvidencePool, EvidenceSource
from polaris_graph.intake_slice.scope_decision import ScopeDecision
from polaris_graph.verified_report.schemas import VerifiedReport
from polaris_graph.audit_ir.loader import load_audit_ir

def build_slice_chain(artifact_dir: Path) -> tuple[ScopeDecision, EvidencePool, VerifiedReport]:
    air = load_audit_ir(artifact_dir)
    
    # ScopeDecision from manifest.json.scope_block
    decision = ScopeDecision(
        question=air.manifest.question,
        domain=air.manifest.domain,
        verdict="accepted",  # only completed runs reach here
        reason=air.manifest.scope_decision.reason,
        # ... fields from manifest
    )
    
    # EvidencePool from bibliography.json + verification_details.json
    sources = []
    for entry in air.bibliography.entries:
        is_t1 = entry.tier == "T1"
        legal_cleared = is_t1 or entry.legal_status == "cleared"
        sources.append(EvidenceSource(
            source_id=entry.evidence_id,
            url=entry.url,
            tier=entry.tier,
            full_text=entry.snippet or "",
            provenance={
                "legal_cleared": legal_cleared,
                "tier": entry.tier,
                "publication_date": entry.publication_date,
            }
        ))
    pool = EvidencePool(question=air.manifest.question, sources=sources, ...)
    
    # VerifiedReport from report.md + verification_details.json + contradictions.json
    report = VerifiedReport(
        report_id=air.manifest.run_id,
        verdict="success",
        report_markdown=air.report_markdown,
        verified_sentences=air.verification.verified_sentences,
        dropped_sentences=air.verification.dropped_sentences,
        contradictions=air.contradictions.entries,
        ...
    )
    
    return (decision, pool, report)
```

`src/polaris_v6/api/bundle.py`:

```python
@router.get("/runs/{run_id}/bundle.tar.gz")
def get_run_bundle(run_id: str, sign_fn = Depends(get_sign_fn)):
    info = run_store.get_run(run_id)
    if info is None or info["status"] != "completed":
        raise HTTPException(404, ...)
    
    artifact_dir = Path(info["artifact_dir"])
    decision, pool, report = build_slice_chain(artifact_dir)
    
    # Pass to existing audit_bundle_route.post_audit_bundle (slice-chain shape)
    return post_audit_bundle(
        AuditBundleRequest(decision=decision, pool=pool, report=report),
        sign_fn=sign_fn,
    )
```

The `legal_cleared` provenance flag: Tier-1 public sources are legally re-distributable (gov-published, public-policy reports). Tier-2/3 sources default to `legal_cleared=False` and are dropped at sovereignty_guard.py:17-26. If any Tier-2/3 source is essential for a question, manual operator review marks it cleared in a per-source allowlist; non-cleared sources are excluded from the bundle but visible in the on-screen Inspector (which doesn't redistribute).

Bundle download for the canonical Q1-Q5 demo runs is preserved (they all use Tier-1 government sources).

## P1.5 — SSE: durable replayable event log keyed by external UUID

You wrote:
> "Redis pub/sub alone is lossy and the channel key is underspecified. Pipeline-A still creates internal `SWEEP_*` IDs at `run_honest_sweep_r3.py:1130`; v6 streams need the external UUID. Use an explicit UUID context/env plus a durable replayable event log, not bare pub/sub."

**Resolution: Redis Streams (durable, replayable) + UUID context injection.**

```python
# src/polaris_v6/queue/run_events.py (NEW)
"""Durable replayable event log per run.

Pipeline-A pushes events to Redis Stream key `polaris:events:{external_uuid}`.
v6 stream.py reads from the stream (with XREAD/XADD) so disconnect-replay
works without loss. Stream is trimmed at run_complete + 24h.
"""

import os
import redis
import json
import uuid as uuid_mod

# Pipeline-A side (called from run_honest_sweep_r3.py):
def emit_event(event_type: str, payload: dict) -> None:
    """Emit a stage event to the durable log for the current run.
    
    External UUID resolved from env POLARIS_V6_EXTERNAL_RUN_ID (set by actor
    before invoking pipeline-A).
    """
    external_uuid = os.environ.get("POLARIS_V6_EXTERNAL_RUN_ID")
    if not external_uuid:
        return  # CLI-mode pipeline-A invocation: no UUID, no v6 stream
    
    redis_client = _get_redis_client()  # POLARIS_V6_REDIS_URL
    key = f"polaris:events:{external_uuid}"
    redis_client.xadd(
        key,
        {"event_type": event_type, "payload": json.dumps(payload)},
        maxlen=10000,  # cap stream size; we don't expect >10k events per run
    )

# v6 stream.py side:
async def stream_events_for(run_id: str, request) -> AsyncIterator[str]:
    """SSE stream of named v6 events for a given external UUID.
    
    Reads from Redis Stream + translates pipeline-A event_types to v6 protocol.
    Resumes from last_event_id query param for disconnect-replay.
    """
    redis_client = _get_redis_client()
    key = f"polaris:events:{run_id}"
    last_id = request.query_params.get("last_event_id", "0")  # 0 = from beginning
    
    while True:
        events = redis_client.xread({key: last_id}, count=100, block=5000)
        if not events:
            # No events for 5s; emit keepalive, then loop
            yield "event: ping\ndata: {}\n\n"
            continue
        for stream, entries in events:
            for entry_id, fields in entries:
                last_id = entry_id
                pa_event = {"event_type": fields[b"event_type"].decode(),
                            **json.loads(fields[b"payload"])}
                v6_event = translate(pa_event)  # P1.5 translator from iter 2 brief
                if v6_event is None:
                    continue
                v6_name, v6_payload = v6_event
                yield f"id: {entry_id.decode()}\nevent: {v6_name}\ndata: {json.dumps(v6_payload)}\n\n"
                if v6_name == "run_complete":
                    return
```

Actor sets the env before invoking pipeline-A:

```python
# src/polaris_v6/queue/actors.py
import os
os.environ["POLARIS_V6_EXTERNAL_RUN_ID"] = run_id  # UUID
result = asyncio.run(build_and_run_v4(...))
```

`run_honest_sweep_r3.py` patched (~5 LOC) to call `run_events.emit_event(...)` at each stage transition.

Durability: Redis Stream persists events (with AOF enabled on the Redis container) for 24h after run_complete; trimmed via cron. Disconnected SSE clients reconnect with `last_event_id` and replay missed events.

## P2 from iter 2 → resolutions

### P2.1 — run_store migration must preserve API shape/status semantics

**Acknowledged**. Existing v6 status schema (verified via grep — actually src/polaris_v6/api/run_status.py doesn't exist as a separate file; status enum is in api/runs.py or queue/run_store.py with abort_* statuses + ISO timestamps). I will:
- Grep ALL existing run_status consumers
- Keep the status enum: `queued | in_progress | completed | failed | abort_scope_rejected | abort_corpus_inadequate | abort_corpus_approval_denied | abort_no_verified_sections | abort_budget_exceeded` (matches POLARIS §9.3 manifest statuses)
- Keep ISO timestamps for queued_at/started_at/completed_at (not REAL/epoch). Will use TEXT column with ISO 8601 strings.
- Migration script atomically adds columns to existing runs table; existing rows backfilled from manifest.json scans.

### P2.2 — scope_domain mapping uses existing dispatcher

**Acknowledged + verified grep target**. Existing:
- `src/polaris_graph/nodes/scope_gate.py:69` SUPPORTED_DOMAINS
- `src/polaris_graph/nodes/scope_gate.py:192-210` load_scope_template
- `src/polaris_graph/run_honest_sweep_r3.py:773` _SCOPE_LLM_SUPPORTED_DOMAINS

The 4 new policy domains (housing/trade/defense/climate) MAY already be supported or default to `policy`. I-arch-001c brief will grep these exact files and either:
- Add the 4 new domains to SUPPORTED_DOMAINS + write 4 scope template YAMLs (`config/scope_templates/<domain>.yaml`)
- OR map all 4 to existing `policy` domain (faster; less per-domain rigor)

Codex iter-4 picks. For week-1 I propose: map to `policy` for the 4 new domains; per-domain rigor in I-arch-001c phase 2 (post-demo).

### P2.3 — Pinned fixture runner writes minimal AuditIR-loadable artifacts

**Acknowledged**. `tests/fixtures/v6_e2e_pinned/` will contain:
- `manifest.json` (real schema, deterministic content)
- `report.md` (3 sentences, real provenance tokens)
- `bibliography.json` (2 sources, Tier-1 legal_cleared=True)
- `contradictions.json` ([])
- `verification_details.json` (2 verified sentences, 1 dropped)

The pinned runner is a stub that simulates pipeline-A emitting events + writing these files. NOT a parallel fake schema — uses the real AuditIR shape. Test asserts `load_audit_ir(fixture_dir)` succeeds + `build_slice_chain` produces valid pydantic models + `audit_bundle` returns signed tar.gz + compare endpoint works.

### P2.4 — 24-day plan post-P1-close

**Acknowledged**. Plan stands if iter-3 P1s close. Days 18-22 rehearsal: 10 questions × 4-15 min each = 40-150 min compute time only, but each needs §-1.1 line-by-line audit which IS the time sink (3-6 hrs per question for first-pass audit). 10 questions × 4-hr audit = 40 hrs across 5 days = doable for full focus. If rehearsal-iter churn surfaces fixes, slack days 25-28 absorb.

### P3 cosmetic — sweep_slug ambiguity

**Acknowledged**. run_store columns split:
- `query_slug` — pipeline-A's URL-safe query identifier (e.g., `clinical_tirzepatide_t2dm`); stable, human-readable
- `manifest_run_id` — pipeline-A's `SWEEP_<timestamp>_<...>` (e.g., `SWEEP_20260512T1430_clinical_tirzepatide`); unique-per-execution
- `artifact_dir` — absolute path

External UUID is the API contract; query_slug + manifest_run_id are internal-only.

## Direct questions iter 3

1. P1.2 synthesizer keyed by query_slug + per-domain identifier resolvers (clinical first, others incremental) — APPROVE'd?
2. P1.3 AuditIR→slice-chain bridge in `src/polaris_v6/api/artifact_to_slice_chain.py` mapping the 5 canonical artifact files — APPROVE'd?
3. P1.5 Redis Streams (durable XADD/XREAD) keyed by external UUID + 5s blocking read + last_event_id replay — APPROVE'd?
4. P2.1 status enum preserves abort_* + ISO timestamps — APPROVE'd or want different shape?
5. P2.2 map 4 new policy domains to existing `policy` for week-1, per-domain rigor in I-arch-001c phase 2 — APPROVE'd?
6. Any remaining blockers before iter 4?

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
