# POLARIS v3 Implementation Plan — FINAL (v2)

**Date:** 2026-03-17
**Status:** DRAFT — Requires user approval before any code is written
**Based on:** 80+ architecture sources, v2 post-mortem (8 root causes), component audit (16 files), testing strategy research, 43 integration dependencies, 30+ failure modes analyzed

---

## 0. What Changed From Plan v1

| Gap Found | Impact | Fix in This Plan |
|-----------|--------|-----------------|
| Frontend coupled to node names (NODE_ORDER, USER_PHASE_MAP) | Dashboard shows nothing for v3 nodes | Added Milestone 6.5: Frontend compatibility layer |
| `report_assembled` trace event triggers UI completion | UI never completes without it | Added to Phase 5 trace contract |
| `__init__.py` bypasses v3 toggle | External callers always get v1 | Added DEP-3 fix to Milestone 6 |
| Result JSON schema must match v1 | 10 API endpoints read specific keys | Added result JSON compatibility contract |
| Checkpoint endpoints hard-import v1 | Checkpoint/rewind breaks for v3 runs | Added to known limitations (defer) |
| Memory systems (LTM/VWM) not mentioned | Memory degrades, priors lost | Added memory integration to Phase 1+2 |
| Document upload pipeline | Uploaded docs never enter v3 | Added to Phase 2 |
| Campaign system reads v1 result keys | Campaign snowball breaks silently | Covered by result JSON contract |
| Steer callback | Live steering silently disabled | Added to `build_and_run_v3()` signature |
| Search-outline loop oscillation | Pipeline runs forever (P0 risk) | Hard caps: 5 search rounds + 2 gap searches |
| State serialization OOM at ~1500 evidence | Process killed (P0 risk) | Evidence content stored OUTSIDE state |
| Critic miscalibration | 36 LLM calls per section (P0 risk) | Calibration test against PG_TEST_039 |
| Previous-section context overflow | Prompt exceeds budget (P1 risk) | Sliding window: 3 recent + summaries |
| Phase timeout distribution wrong | One phase steals all budget (P0 risk) | Configurable percentages via env vars |
| 20+ trace event action subtypes | Dashboard panels permanently empty | Full trace event contract specified |
| No beast mode (graceful degradation) | Hard timeout = zero output | Graceful exit produces partial report |
| Model routing not specified | All calls use expensive model | Explicit model-per-role env vars |

---

## 1. Architecture (Unchanged from v1 Plan)

```
SCOPE → SEARCH+EXPLORE (3-5 rounds) ↔ DYNAMIC OUTLINE → SYNTHESIZE (sequential+critic) → ASSEMBLE
```

See v1 plan for full diagram. The pipeline sequence is validated by 80+ sources.

---

## 2. Critical Contracts

### 2.1 `build_and_run_v3()` Signature (Must Match v1)

```python
async def build_and_run_v3(
    vector_id: str,
    query: str,
    application: str = "",
    region: str = "",
    stage: int = 1,
    max_iterations: int = 3,
    max_execution_minutes: int = 60,
    resume: bool = False,
    enable_dashboard: bool = True,
    document_ids: list[str] | None = None,
    steer_callback: Callable | None = None,
    research_brief: str = "",
) -> dict:
    """v3 entry point. Signature matches v1/v2 for live_server compatibility."""
```

**Test:** `test_build_and_run_v3_signature` — assert parameter names and types match v1.

### 2.2 Result JSON Schema (Must Match v1)

The output JSON MUST contain these keys (consumed by 10+ API endpoints):

```python
class V3ResultOutput(BaseModel):
    """Output JSON written to outputs/polaris_graph/{vector_id}.json.
    Must contain all fields that live_server.py endpoints read."""

    vector_id: str
    original_query: str
    status: str                        # "completed" | "partial" | "failed"
    final_report: str                  # Full markdown report
    bibliography: list[dict]           # [{citation_number, title, authors, url, ...}]
    quality_metrics: dict              # {faithfulness_pct, word_count, citation_count, ...}
    sections: list[dict]               # [{section_id, title, content, evidence_ids, ...}]
    evidence: list[dict]               # [{evidence_id, statement, source_url, direct_quote, ...}]
    claims: list[dict]                 # [{claim_id, evidence_ids, is_faithful, ...}]
    iteration_count: int
    timestamps: dict                   # {started, completed, duration_seconds}
    trace_summary: dict                # {total_events, node_durations, ...}

    # v3-specific fields (frontend ignores unknown keys)
    v3_metadata: dict                  # {sub_questions, outline_versions, reflections, ...}
```

**Test:** `test_result_json_compat` — load a v1 result JSON (PG_TEST_039), validate against `V3ResultOutput`. Then generate a v3 result, validate same schema. Both must pass.

### 2.3 Trace Event Contract

v3 MUST emit these trace events for frontend compatibility:

```python
# REQUIRED events (frontend breaks without these)
REQUIRED_EVENTS = {
    "pipeline_start": ["query", "application", "region", "max_iterations", "budget_usd", "vector_id"],
    "pipeline_end": ["status", "total_words", "total_citations", "faithfulness_score", "total_cost_usd", "elapsed_seconds"],
    "node_start": ["node"],           # node name must be in NODE_ORDER
    "node_end": ["node", "duration_ms"],
}

# REQUIRED evidence actions (each populates a UI panel)
REQUIRED_EVIDENCE_ACTIONS = {
    "extracted": ["count", "gold", "silver", "bronze"],
    "accumulated": ["count"],
    "query_plan": ["queries"],
    "report_outline": ["sections"],
    "clustering": ["themes"],
    "citation_audit": ["mapping", "grounded"],
    "report_assembled": ["bibliography", "full_report", "section_titles", "count", "total_citations"],
    # ^ THIS ONE IS CRITICAL: triggers frontend completion
}

# REQUIRED llm_call types (populate section viewer)
REQUIRED_LLM_ACTIONS = {
    "section_write": ["section_id", "title", "content", "word_count", "evidence_count"],
}
```

**Test:** `test_trace_event_contract` — run v3 with VCR cassettes. Assert ALL required events emitted with ALL required fields.

### 2.4 Frontend Node Name Registry

v3 nodes must be added to `core.js` and `advanced_tabs.js`:

```javascript
// core.js NODE_ORDER — add v3 names
var NODE_ORDER = [
    // v1 nodes
    "plan","search","storm_interviews","analyze","verify","evaluate","synthesize","search_gaps",
    // v2 nodes
    "fetch_content","crag_analyze","plan_outline","blueprint","write_one_section","verify_one_section","assemble",
    // v3 nodes (NEW)
    "scope","v3_search","v3_storm","v3_outline","v3_write_section","v3_critic","v3_assemble"
];

// advanced_tabs.js USER_PHASE_MAP — add v3 mappings
"scope": { step: "search", text: "Decomposing research question...", pct: 5 },
"v3_search": { step: "search", text: "Searching {n} sources per question...", pct: 20 },
"v3_storm": { step: "interview", text: "Interviewing expert perspectives...", pct: 35 },
"v3_outline": { step: "verify", text: "Building dynamic outline...", pct: 50 },
"v3_write_section": { step: "synthesize", text: "Writing section {n}...", pct: 70 },
"v3_critic": { step: "synthesize", text: "Evaluating analytical depth...", pct: 80 },
"v3_assemble": { step: "synthesize", text: "Assembling final report...", pct: 95 },
```

**Why `v3_` prefix:** Prevents collision with v1 node names that have different semantics. `search` in v1 is broad; `v3_search` is sub-question-targeted.

---

## 3. State Architecture (Critical Change from v1 Plan)

### 3.1 Evidence Content OUTSIDE State

**P0 Risk (CC.7):** LangGraph serializes full state between every node. At 1500 evidence pieces × 25K chars = 37.5GB of serialization per transition. **Process will be killed by OOM.**

**Fix:** Evidence content stored in a side-channel dictionary, not in LangGraph state. State carries only evidence metadata (IDs, scores, tier, source_url — ~500 bytes per piece instead of ~25K).

```python
# In graph_v3.py — passed via config, not state
evidence_store: dict[str, EvidencePiece] = {}  # Full evidence objects keyed by ID

# In LangGraph state — lightweight references only
class V3State(TypedDict):
    evidence_ids: list[str]           # Just IDs, not full objects
    evidence_meta: dict[str, dict]    # {ev_id: {tier, score, source_url, word_count}}
    # ... other state fields
```

**Test:** `test_state_size_bounded` — create state with 1000 evidence IDs + metadata. Assert serialized size < 5MB (not 37GB).

### 3.2 Decomposed Sub-States

```python
class V3State(TypedDict):
    # Identity (immutable after init)
    vector_id: str
    original_query: str
    application: str
    region: str

    # Phase 1: Scope
    sub_questions: list[dict]
    perspectives: list[str]
    search_queries: list[dict]
    complexity: str

    # Phase 2: Search (accumulated across rounds)
    evidence_ids: list[str]           # IDs only, content in evidence_store
    evidence_meta: dict[str, dict]    # Lightweight metadata per evidence
    reflections: list[dict]           # Distilled insights per round
    search_round: int
    convergence_score: float
    sources_fetched: int

    # Phase 3: Outline (versioned)
    outline: dict                     # LiveOutline as dict
    outline_version: int
    gaps: list[dict]

    # Phase 4: Synthesize (accumulated per section)
    completed_sections: list[dict]    # VerifiedSectionDrafts
    used_evidence_ids: set[str]       # Cross-section tracking
    current_section_index: int

    # Phase 5: Assemble
    final_report: str
    bibliography: list[dict]
    quality_metrics: dict

    # Control
    status: str                       # "running" | "completed" | "partial" | "failed"
    iteration: int
    elapsed_seconds: float
    total_cost_usd: float
    phase_budgets: dict[str, float]   # Remaining time per phase
```

---

## 4. Failure Mode Mitigations (P0 Items)

### 4.1 Search-Outline Loop Oscillation (P0)

The #1 predicted failure. Every gap-fill search finds tangential evidence → new gaps → infinite loop.

```
HARD CAPS (non-negotiable):
- PG_V3_MAX_SEARCH_ROUNDS=5          (initial search, not counting gap fills)
- PG_V3_MAX_GAP_SEARCHES=2           (gap-triggered searches after outline)
- PG_V3_SEARCH_PHASE_BUDGET_PCT=35   (% of total time for Phase 2+3 combined)
- PG_V3_MAX_EVIDENCE=1000            (hard evidence cap)

CONVERGENCE LOGIC:
- Convergence score = 1 - (new_evidence_this_round / total_evidence)
- If convergence > 0.85 for 2 consecutive rounds → stop searching
- If convergence DECREASES for 2 consecutive rounds → stop (query space expanding)
- Minimum 2 rounds before convergence can trigger
```

**Tests:**
- `test_convergence_triggers` — mock declining new evidence. Assert convergence triggers after round 3.
- `test_gap_search_cap` — mock gap detection always finding gaps. Assert max 2 gap searches.
- `test_evidence_cap_stops_search` — mock 200 evidence per round. Assert search stops at round 5 (1000 cap).

### 4.2 Critic Miscalibration (P0)

```
CALIBRATION REQUIREMENT:
Before deploying v3, run the critic on PG_TEST_039's 15 sections.
If critic rejects >40% of sections → critic prompt is too strict.

SAFETY RAILS:
- Max 2 revisions per section (already in plan)
- After 2 rejections, accept the best-scoring draft
- Fast-pass: faithfulness >80% AND citations >5 → auto-pass critic
- Critic evaluates DEPTH not STYLE (compare/aggregate/challenge markers, not prose quality)
```

**Test:** `test_critic_calibration` — feed critic 5 real sections from PG_TEST_039 fixture. Assert >=3 pass.

### 4.3 State OOM Prevention (P0)

See §3.1 above. Evidence content OUTSIDE state.

### 4.4 Phase Timeout Distribution (P0)

```python
# Configurable via env vars
PHASE_BUDGETS = {
    "scope": float(os.getenv("PG_V3_SCOPE_BUDGET_PCT", "5")),      # 3 min of 60
    "search": float(os.getenv("PG_V3_SEARCH_BUDGET_PCT", "35")),    # 21 min
    "outline": float(os.getenv("PG_V3_OUTLINE_BUDGET_PCT", "10")),  # 6 min
    "synthesize": float(os.getenv("PG_V3_SYNTH_BUDGET_PCT", "40")), # 24 min
    "assemble": float(os.getenv("PG_V3_ASSEMBLE_BUDGET_PCT", "10")),# 6 min
}

# Soft timeout: phase exits gracefully at budget
# Hard timeout: asyncio.wait_for at graph level (last resort)
# On ANY timeout: proceed to Phase 5 with whatever exists → partial report
```

**Test:** `test_phase_budget_enforcement` — set total=2 minutes. Assert Phase 2 exits at ~42s (35% of 120s).

### 4.5 Beast Mode (Graceful Degradation)

```
ON BUDGET/TIME EXHAUSTION:
- Mid-Phase 2: Stop searching. Proceed to outline with available evidence.
- Mid-Phase 3: Accept current outline version. Proceed to synthesis.
- Mid-Phase 4: Stop writing new sections. Assemble completed sections.
- Mid-Phase 5: Output whatever is assembled, even if quality gate fails.

NEVER produce zero output. A partial report is infinitely better than no report.

Result JSON status field:
- "completed": full pipeline finished, quality gate passed
- "partial": some phases truncated by budget/time
- "failed": fatal error (should never happen with beast mode)
```

**Test:** `test_beast_mode_mid_synthesis` — set time budget to expire at section 4 of 12. Assert output has 4 sections, status="partial".

---

## 5. Integration Points

### 5.1 live_server.py Routing

```python
# Replace the v1/v2 binary toggle with explicit version dispatch
graph_version = os.getenv("PG_GRAPH_VERSION", "v1")  # "v1" | "v2" | "v3"
if graph_version == "v3":
    from src.polaris_graph.graph_v3 import build_and_run
elif graph_version == "v2":
    from src.polaris_graph.graph_v2 import build_and_run
else:
    from src.polaris_graph.graph import build_and_run
```

### 5.2 `__init__.py` Public API

```python
# src/polaris_graph/__init__.py — route through same dispatch
async def run_research(...):
    graph_version = os.getenv("PG_GRAPH_VERSION", "v1")
    if graph_version == "v3":
        from src.polaris_graph.graph_v3 import build_and_run
    elif graph_version == "v2":
        from src.polaris_graph.graph_v2 import build_and_run
    else:
        from src.polaris_graph.graph import build_and_run
    return await build_and_run(...)
```

### 5.3 Memory Systems

```
Phase 1 (SCOPE):
- Query LTM cross-vector priors → inject into sub-question generation
- Query session feedback → adjust perspective weights

Phase 2 (SEARCH):
- Check content cache before fetching URLs
- Store fetched content in content cache
- Record session feedback on search strategies

Phase 4 (SYNTHESIZE):
- Record evidence hierarchy
- Record session feedback on synthesis quality

Phase 5 (ASSEMBLE):
- Store report in cross-vector LTM for future runs
```

### 5.4 Document Upload Pipeline

```
In build_and_run_v3():
if document_ids:
    from src.polaris_graph.document_ingester import DocumentIngester
    from src.polaris_graph.memory.local_document_rag import LocalDocumentRAG
    # Load documents → chunk → add to evidence_store as GOLD tier
    # Add document evidence IDs to state.evidence_ids
```

### 5.5 STORM Positioning

```
STORM runs ONCE between search round 1 and outline generation.
NOT every search round (too expensive).
NOT before any search (needs some evidence for context).

Sequence within Phase 2:
  Round 1: Search → CRAG evaluate → extract evidence
  STORM: Discover perspectives from round 1 evidence → interviews → additional evidence
  Round 2-5: Search (informed by STORM perspectives) → CRAG → extract
```

### 5.6 Model Routing

```python
# .env model configuration
PG_V3_MODEL_SCOPE=qwen/qwen3.5-9b           # Cheap: decomposition is simple
PG_V3_MODEL_SEARCH=qwen/qwen3.5-9b          # Cheap: query generation
PG_V3_MODEL_EXTRACT=qwen/qwen3.5-plus-02-15 # Mid: needs comprehension
PG_V3_MODEL_OUTLINE=qwen/qwen3.5-plus-02-15 # Expensive: high-leverage
PG_V3_MODEL_SYNTHESIZE=qwen/qwen3.5-plus-02-15  # Expensive: quality-critical
PG_V3_MODEL_CRITIC=qwen/qwen3.5-plus-02-15  # Expensive: judgment task
PG_V3_MODEL_ASSEMBLE=qwen/qwen3.5-9b        # Cheap: summarization

# Implementation: OpenRouterClient accepts model override per call
result = await client.generate_structured(
    prompt=prompt, schema=ScopeOutput,
    model=os.getenv("PG_V3_MODEL_SCOPE"),  # Override default
)
```

### 5.7 Previous-Section Context (Sliding Window)

```
Section N's prompt includes:
- Full text of sections N-1 and N-2 (recent context for coherence)
- 1-sentence summary of sections 1 through N-3 ("Earlier sections covered: ...")
- "Do NOT repeat" list: key stats already cited in previous sections

Hard token budget: 4000 tokens for previous-section context.
If exceeded: compress summaries further.
```

---

## 6. Updated Build Order

### Milestone 0: Foundation (1 session)

| Task | What | Tests | LOC |
|------|------|-------|-----|
| 0.1 | Install test dependencies (vcrpy, hypothesis) | N/A | 5 |
| 0.2 | Create `tests/v3/` directory structure | N/A | 10 |
| 0.3 | Write mock LLM factory (returns canned JSON per schema) | 5 tests | 80 |
| 0.4 | Write 4 phase boundary contract tests (scope→search, search→outline, outline→synth, synth→assemble) | 4 tests | 120 |
| 0.5 | Write result JSON compatibility test (validate PG_TEST_039 output against V3ResultOutput) | 1 test | 40 |
| 0.6 | Write trace event contract test (validate required events exist) | 1 test | 60 |
| 0.7 | Write `build_and_run_v3()` signature compatibility test | 1 test | 20 |
| 0.8 | Verify 6 REUSE components import cleanly | 6 tests | 30 |
| 0.9 | Create golden dataset fixture (3 topics from PG_TEST_039) | N/A | 50 |
| **Total** | | **18 tests** | **~415** |

**Gate:** All 18 tests pass. No implementation code exists yet. Tests define the contracts.

### Milestone 1: SCOPE Phase (1 session)

| Task | What | Reuses | LOC |
|------|------|--------|-----|
| 1.1 | `ScopeOutput` + `SubQuestion` schemas | schemas.py | 60 |
| 1.2 | `scope_node()` with LLM decomposition | planner.py | 120 |
| 1.3 | Perspective discovery (reuse STORM) | storm_interviews.py | 30 |
| 1.4 | Diversity gate (embedding-based dedup of sub-questions) | embedding_service | 40 |
| 1.5 | Fallback: template-based queries when LLM fails | planner._fallback_queries | 20 |
| 1.6 | LTM prior injection | memory.cross_vector | 20 |
| **Tests** | F1.1-F1.5 failure modes + contract | | 150 |
| **Total** | | | **~440** |

**Gate:** `scope_node()` produces valid ScopeOutput. All 5 failure mode tests pass. VCR cassette recorded.

### Milestone 2: SEARCH Phase (1-2 sessions)

| Task | What | Reuses | LOC |
|------|------|--------|-----|
| 2.1 | `search_round()` per sub-question dispatch | searcher.py | 150 |
| 2.2 | CRAG evaluation integration | crag_retriever.py | 30 |
| 2.3 | Content quality gate | content_quality_gate.py | 10 |
| 2.4 | Reflection distillation (compress round → insights) | NEW | 80 |
| 2.5 | Convergence detector (with hard caps) | NEW | 60 |
| 2.6 | STORM interview integration (after round 1) | storm_interviews.py | 40 |
| 2.7 | Evidence card enrichment | analyzer.py | 20 |
| 2.8 | Document upload injection | document_ingester | 30 |
| 2.9 | Evidence content → side-channel store (NOT state) | NEW | 40 |
| 2.10 | Content cache integration | memory.content_cache | 20 |
| **Tests** | F2.1-F2.8 failure modes + convergence + caps | | 200 |
| **Total** | | | **~680** |

**Gate:** Search produces evidence with convergence detection. Hard caps enforced. All 8 failure mode tests pass.

### Milestone 3: OUTLINE Phase (1 session)

| Task | What | Reuses | LOC |
|------|------|--------|-----|
| 3.1 | `LiveOutline` schema | schemas.py | 50 |
| 3.2 | `generate_outline()` from sub-questions + reflections | section_writer.py (plan_report logic) | 120 |
| 3.3 | `refine_outline()` with new evidence | NEW | 80 |
| 3.4 | Evidence-to-section assignment (exclusive, embedding-based) | section_writer.py (_assign_evidence) | 30 |
| 3.5 | Gap detection + gap query generation | planner.py | 50 |
| 3.6 | Gap search loop with hard cap (max 2) | NEW | 30 |
| 3.7 | Keep-best strategy (don't adopt worse refinements) | NEW | 30 |
| **Tests** | F3.1-F3.6 failure modes + gap loop cap + oscillation | | 160 |
| **Total** | | | **~550** |

**Gate:** Outline generates, refines, detects gaps, and converges. Gap loop capped at 2. All 6 failure mode tests pass.

### Milestone 4: SYNTHESIZE Phase (2 sessions — critical path)

| Task | What | Reuses | LOC |
|------|------|--------|-----|
| 4.1 | `VerifiedSectionDraft` schema | schemas.py | 40 |
| 4.2 | `write_verified_section()` — single section write | section_writer.py (write_section) | 150 |
| 4.3 | Inline claim verification (NLI + LLM fallback) | nli_verifier.py, verifier.py | 80 |
| 4.4 | `critic_evaluate()` function | NEW | 100 |
| 4.5 | Critic calibration test against PG_TEST_039 | Fixture-based | 40 |
| 4.6 | Used-evidence tracking (de-prioritize, not exclude) | NEW | 40 |
| 4.7 | Sliding window previous-section context | NEW | 50 |
| 4.8 | Per-section timeout + beast mode | NEW | 30 |
| 4.9 | Analytical prompt injection (RC-2 from Sprint 1) | synthesis_prompts.py | 10 |
| 4.10 | Comparison tables injection (RC-6) | section_writer.py | 10 |
| 4.11 | Contradictions/corroboration injection (RC-5) | synthesizer.py | 10 |
| 4.12 | Raw source re-introduction from evidence_store | NEW | 20 |
| **Tests** | F4.1-F4.7 failure modes + critic calibration + context overflow | | 250 |
| **Total** | | | **~830** |

**Gate:** Sequential writing with inline verify + critic. All 7 failure mode tests pass. Critic accepts >=60% of PG_TEST_039 sections.

### Milestone 5: ASSEMBLE Phase (0.5 session)

| Task | What | Reuses | LOC |
|------|------|--------|-----|
| 5.1 | Cross-section dedup (numeric-aware) | report_assembler.py | 30 |
| 5.2 | Citation resolution | citation_mapper.py | 10 |
| 5.3 | Grounded abstract | report_assembler.py | 40 |
| 5.4 | Contradictions section | synthesizer.py | 10 |
| 5.5 | Quality gates + forensic audit | audit_v3_report.py | 20 |
| 5.6 | Result JSON output (v1-compatible format) | NEW | 60 |
| 5.7 | `report_assembled` trace event (CRITICAL for frontend) | tracing.py | 20 |
| **Tests** | F5.1-F5.4 + result JSON compat + trace event | | 100 |
| **Total** | | | **~290** |

**Gate:** Assembly produces v1-compatible result JSON. `report_assembled` trace event emitted. Quality audit runs.

### Milestone 6: GRAPH WIRING (1 session)

| Task | What | LOC |
|------|------|-----|
| 6.1 | `V3State` TypedDict (decomposed, lightweight) | 150 |
| 6.2 | `build_v3_graph()` — LangGraph StateGraph with 5 phases | 200 |
| 6.3 | Search↔Outline conditional edge (gap detection) | 30 |
| 6.4 | Phase budget enforcement (soft timeouts) | 40 |
| 6.5 | Beast mode handler (graceful exit on timeout) | 30 |
| 6.6 | `build_and_run_v3()` entry point (v1-compatible signature) | 100 |
| 6.7 | `__init__.py` dispatch fix (DEP-3) | 10 |
| 6.8 | live_server.py routing update (DEP-1) | 10 |
| 6.9 | Frontend NODE_ORDER + USER_PHASE_MAP additions | 30 |
| 6.10 | All required trace events wired (§2.3 contract) | 50 |
| 6.11 | Memory system integration (LTM, session feedback) | 30 |
| 6.12 | Document upload integration | 20 |
| 6.13 | Steer callback pass-through | 10 |
| 6.14 | Rich dashboard streaming (reuse v1 pattern) | 30 |
| **Tests** | Graph compilation + VCR full pipeline + signature compat | 200 |
| **Total** | | **~940** |

**Gate:** Full graph compiles. VCR cassette test passes (replay of recorded run). Frontend shows progress with v3 node names. Result JSON matches v1 format.

### Milestone 7: LIVE VALIDATION (1-2 sessions)

| Task | What |
|------|------|
| 7.1 | Smoke test (existing 16 tests + v3 graph compilation) |
| 7.2 | V3_E2E_001: biochar query with real APIs |
| 7.3 | Forensic audit vs PG_TEST_039 (v1 best) |
| 7.4 | Forensic audit vs V2_E2E_007 (v2 baseline) |
| 7.5 | Dashboard visual verification (all panels populated) |
| 7.6 | Second topic E2E (different domain to verify generalization) |
| 7.7 | Cost analysis (v3 vs v1 vs v2) |
| 7.8 | Phase timing analysis (actual vs budgeted, tune percentages) |

---

## 7. Testing Summary

### Counts by Tier

| Tier | Tests | Cost | Time | Blocks PR? |
|------|-------|------|------|-----------|
| Tier 1: Schema + logic | 60 | $0 | <10s | Yes |
| Tier 2: VCR + contracts | 15 | $0 | <30s | Yes |
| Tier 3: Golden dataset | 5 | <$2 | ~5min | Main only |
| Tier 4: Full E2E | 2 | ~$3 | ~60min | Manual |
| **Total** | **82** | | | |

### Failure Mode Coverage

| Phase | Failure Modes | Tests |
|-------|--------------|-------|
| Phase 1 | F1.1-F1.5 (5 modes) | 5 tests |
| Phase 2 | F2.1-F2.8 (8 modes) | 8 tests |
| Phase 3 | F3.1-F3.6 (6 modes) | 6 tests |
| Phase 4 | F4.1-F4.7 (7 modes) | 7 tests |
| Phase 5 | F5.1-F5.4 (4 modes) | 4 tests |
| Cross-cutting | CC.1-CC.12 (12 modes) | 12 tests |
| **Total** | **42 failure modes** | **42 tests** |

---

## 8. File Map (Updated)

### New Files

| File | Purpose | LOC |
|------|---------|-----|
| `src/polaris_graph/graph_v3.py` | v3 graph + build_and_run_v3 | 700 |
| `src/polaris_graph/state_v3.py` | Decomposed V3State | 200 |
| `src/polaris_graph/nodes/__init__.py` | Package | 5 |
| `src/polaris_graph/nodes/scope.py` | Phase 1 | 200 |
| `src/polaris_graph/nodes/search.py` | Phase 2 orchestrator | 300 |
| `src/polaris_graph/nodes/outline.py` | Phase 3 | 250 |
| `src/polaris_graph/nodes/synthesize.py` | Phase 4 | 350 |
| `src/polaris_graph/nodes/assemble.py` | Phase 5 | 200 |
| `tests/v3/conftest.py` | Fixtures + mock LLM | 150 |
| `tests/v3/test_contracts.py` | Phase boundary + result JSON | 200 |
| `tests/v3/test_scope.py` | Phase 1 unit + failure modes | 150 |
| `tests/v3/test_search.py` | Phase 2 unit + failure modes | 200 |
| `tests/v3/test_outline.py` | Phase 3 unit + failure modes | 160 |
| `tests/v3/test_synthesize.py` | Phase 4 unit + failure modes | 250 |
| `tests/v3/test_assemble.py` | Phase 5 unit + failure modes | 100 |
| `tests/v3/test_graph.py` | Graph wiring + VCR integration | 200 |
| `tests/v3/fixtures/` | Golden datasets + VCR cassettes | ~500 |
| **Total new** | | **~4,115** |

### Modified Files (Minimal Changes)

| File | Change | LOC |
|------|--------|-----|
| `scripts/live_server.py` | Add v3 routing (10 lines) | 10 |
| `scripts/static/js/core.js` | Add v3 to NODE_ORDER + labels | 20 |
| `scripts/static/js/advanced_tabs.js` | Add v3 to USER_PHASE_MAP | 15 |
| `src/polaris_graph/__init__.py` | Add v3 dispatch | 10 |
| `src/polaris_graph/llm/openrouter_client.py` | Accept model override per call | 15 |
| `src/polaris_graph/schemas.py` | Add v3 schemas (ScopeOutput, LiveOutline, etc.) | 150 |
| **Total modified** | | **~220** |

### NOT Modified (Zero Risk)

`graph.py`, `state.py`, `planner.py`, `crag_retriever.py`, `source_registry.py`, `content_quality_gate.py`, `nli_verifier.py`, `citation_mapper.py`, `section_writer.py` (core logic), `report_assembler.py` (core logic), `analyzer.py` (core logic), `searcher.py` (core logic), `storm_interviews.py` (core logic), `verifier.py` (core logic)

---

## 9. Known Limitations (Deferred)

| Item | Why Deferred | When to Address |
|------|-------------|-----------------|
| Checkpoint/rewind for v3 runs | Complex, v1 checkpoints work for v1 | After v3 is stable |
| Dynamic graph / pipeline editor for v3 | Low priority, power-user feature | After v3 is stable |
| Model routing to non-OpenRouter providers | Single provider works, multi-provider is optimization | After v3 validated |
| YAML config file integration | Env vars work, YAML is nice-to-have | After v3 validated |
| Concurrent pipeline runs (GPU contention) | Single-user mode works | After production deployment |

---

## 10. Success Criteria (Unchanged + Added)

### Quantitative

| Metric | v1 Best | v2 Broken | v3 Target | Gemini |
|--------|---------|-----------|-----------|--------|
| Duplicate sentences | 0% | 25.9% | 0% | 0% |
| Comparison markers | ~5 | ~2 | >= 20 | 30+ |
| Tables (clean) | 0 | 26 (garbled) | >= 3 | 2-4 |
| Key Findings | 0-1 | 15 | >= 4 | 4-6 |
| Citation density | 0.69 | 4.96 | > 2.0 | 2-4 |
| Cross-section refs | 0 | 0 | >= 5 | 5-10 |
| Faithfulness | 80.5% | N/A | >= 80% | ~85% |
| Cost | $1.31 | $2-3 | < $2.50 | N/A |

### Added Criteria

| Metric | Target |
|--------|--------|
| All 82 tests pass | 82/82 |
| Dashboard shows progress for all v3 nodes | Visual verification |
| Result JSON loads in all 10 API endpoints | No errors in server log |
| Beast mode produces partial output on timeout | status="partial" in result |
| Phase budgets within 20% of allocation | Logged and tunable |

---

## 11. Timeline (Honest)

| Milestone | Sessions | Cumulative | Gate |
|-----------|----------|------------|------|
| M0: Foundation | 1 | 1 | 18 tests pass, 0 code |
| M1: SCOPE | 1 | 2 | 23 tests pass |
| M2: SEARCH | 1-2 | 3-4 | 31 tests pass |
| M3: OUTLINE | 1 | 4-5 | 37 tests pass |
| M4: SYNTHESIZE | 2 | 6-7 | 44 tests pass + critic calibrated |
| M5: ASSEMBLE | 0.5 | 7 | 48 tests pass + result JSON compat |
| M6: GRAPH WIRING | 1 | 8 | 82 tests pass + dashboard works |
| M7: LIVE VALIDATION | 1-2 | 9-10 | Forensic audit ≥ v1 best |
| **Total** | **8-10** | | |

---

## 12. Rollback Strategy (Unchanged)

v1 `graph.py` is NEVER modified. v3 lives in `graph_v3.py`. Toggle via `PG_GRAPH_VERSION=v3`.

If v3 fails: set `PG_GRAPH_VERSION=v1`. Zero downtime. Zero regression.
