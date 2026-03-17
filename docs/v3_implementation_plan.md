# POLARIS v3 Implementation Plan

**Date:** 2026-03-17
**Status:** DRAFT — Requires user approval before any code is written
**Based on:** 80+ sources (4 architecture surveys), v2 post-mortem (8 root causes), component audit (16 files), testing strategy research

---

## 0. Guiding Principles (Learned the Hard Way)

From v2's failure and 80+ sources of research:

1. **Test BEFORE code.** Write contract tests for each phase boundary first. If a test doesn't exist, the feature doesn't exist.
2. **Sequential writing is non-negotiable.** 4 of 8 v2 root causes were caused by parallel section writing. LangChain tested it and abandoned it. 95.6% of configs favor sequential.
3. **Verify DURING writing, not after.** Post-hoc verification caused 170 rewrites in v2. "From Fluent to Verifiable" (2025): post-hoc verification does not scale.
4. **Questions drive search, not the reverse.** Every production system decomposes queries BEFORE searching. Our current approach (questions at synthesize time) is architecturally backwards.
5. **The outline is a living document.** WebWeaver (ICLR 2026): interleave outline refinement with evidence acquisition. Neither search-then-outline nor outline-then-search.
6. **Reuse battle-tested code.** Only 2,615 LOC need rewriting (state.py + graph.py). 18,000+ LOC of proven search, extraction, verification, and citation code stays.
7. **Every design doc feature must have a test.** v2 specified "section boundaries, cross-references, narrative arc" in the Blueprint — none were implemented. Tests would have caught this on day 1.

---

## 1. Architecture Overview

### The 5-Phase Pipeline

```
Phase 1: SCOPE          Phase 2: SEARCH           Phase 3: OUTLINE
(1-2 LLM calls)         (parallel, 3-5 rounds)    (evolves with evidence)

  Decompose query    ┌──► Search per question  ◄──── Gap detected?
  into sub-questions │    Fetch + extract            │ yes → more search
  + perspectives     │    CRAG evaluate              │ no  → proceed
  + search queries   │    STORM interviews           │
                     │    Reflection distill     ───► Generate/refine outline
                     │    Convergence check           Map evidence to sections
                     └──  (repeat 3-5x)               Confidence per section


Phase 4: SYNTHESIZE                    Phase 5: ASSEMBLE
(sequential, critic loop)              (post-processing)

  For each section (in order):           Cross-section dedup
    Retrieve raw sources                 Grounded abstract
    Format evidence cards                Contradictions section
    Write with analytical prompt         Citation audit
    Inline verify each claim             Quality gates
    Critic evaluates depth               Format + output
    If deficient → revise
    Track used evidence
    → Next section
```

### Node-Level Specification

| Node | Input | Output | Model | Cost Est. |
|------|-------|--------|-------|-----------|
| `scope` | query, application, region | SubQuestions[], Perspectives[], SearchQueries[] | Cheap | $0.01 |
| `search` | SearchQueries[] | RawDocuments[], SearchResults[] | N/A (APIs) | $0 |
| `fetch_extract` | RawDocuments[] | FetchedContent[], EvidencePieces[] | Mid-tier | $0.10 |
| `crag_evaluate` | EvidencePieces[], FetchedContent[] | GradedEvidence[] (correct/ambiguous/incorrect) | Local NLI | $0 |
| `storm_interviews` | query, Perspectives[] | ConversationNotes[], AdditionalEvidence[] | Mid-tier | $0.15 |
| `outline` | SubQuestions[], GradedEvidence[], iteration_n | ReportOutline (living) | Expensive | $0.05 |
| `write_section` | SectionSpec, SectionEvidence[], PreviousSections[], Outline | SectionDraft (verified) | Expensive | $0.10/section |
| `critic` | SectionDraft, SectionEvidence[] | CriticVerdict (pass/revise + feedback) | Expensive | $0.03/section |
| `assemble` | SectionDrafts[], Outline, SourceRegistry | FinalReport | Cheap | $0.02 |

**Estimated total cost per report: $1.00-2.50** (vs v1's $4-8, v2's $2-3)

---

## 2. Phase Contracts (JSON Schemas)

Every phase boundary has an explicit contract. Tests validate these BEFORE implementation.

### Contract 1: scope → search

```python
class ScopeOutput(BaseModel):
    """Output of Phase 1: SCOPE"""
    sub_questions: list[SubQuestion]  # 6-10 questions
    perspectives: list[str]          # 5-8 STORM perspectives
    search_queries: list[SearchQuery] # 3-5 queries per sub-question
    complexity: str                  # "simple" | "moderate" | "complex"
    estimated_depth: int             # target evidence count

class SubQuestion(BaseModel):
    id: str                          # "sq_01"
    question: str                    # "How effective is biochar..."
    analytical_focus: str            # "compare" | "aggregate" | "explain" | "tabulate" | "challenge"
    expected_depth: str              # "deep" | "moderate" | "brief"
    parent_id: str | None = None     # For DAG structure (Plan*RAG)

class SearchQuery(BaseModel):
    query: str
    sub_question_id: str             # Links back to SubQuestion
    perspective: str                 # Which perspective drives this
    source_preference: str           # "web" | "academic" | "both"
```

### Contract 2: search → outline

```python
class SearchRoundOutput(BaseModel):
    """Output of one search round"""
    evidence: list[EvidencePiece]     # Graded, deduped
    reflections: list[Reflection]    # Tavily-style distilled insights
    sources_fetched: int
    convergence_score: float         # 0-1, how much new info this round added
    gaps: list[str]                  # Identified knowledge gaps

class Reflection(BaseModel):
    """Tavily pattern: distilled insight from a search round"""
    insight: str                     # Key finding in 1-2 sentences
    sub_question_id: str             # Which question this answers
    evidence_ids: list[str]          # Supporting evidence
    confidence: float                # How well-supported (0-1)
```

### Contract 3: outline → synthesize

```python
class LiveOutline(BaseModel):
    """The living outline — evolves with each search round"""
    title: str
    abstract_draft: str              # Updated each round
    sections: list[OutlineSection]
    version: int                     # Increments on each refinement
    gaps: list[OutlineGap]           # Sections needing more evidence
    narrative_flow: str              # How sections connect

class OutlineSection(BaseModel):
    id: str
    title: str
    sub_question_id: str             # Which question this answers
    description: str
    analytical_focus: str            # From SubQuestion
    evidence_ids: list[str]          # Assigned evidence
    confidence: float                # Based on evidence depth
    target_words: int
    cross_refs: list[str]            # "References findings from section X"
    order: int

class OutlineGap(BaseModel):
    section_id: str
    description: str                 # What's missing
    suggested_queries: list[str]     # Targeted searches to fill gap
```

### Contract 4: synthesize → assemble

```python
class VerifiedSectionDraft(BaseModel):
    """Output of write + inline verify + critic"""
    section_id: str
    title: str
    content: str                     # Markdown with [CITE:ev_xxx]
    evidence_ids_used: list[str]     # What was actually cited
    claims_verified: int             # How many claims inline-verified
    claims_total: int
    faithfulness_score: float        # From inline verification
    critic_passed: bool              # Did the critic approve?
    critic_feedback: str | None      # If revision was needed
    revisions: int                   # How many critic rounds (max 2)
    word_count: int
    analytical_depth: dict           # Comparison/aggregation/challenge markers
```

---

## 3. Build Order (Test-First)

### Milestone 0: Foundation (Before ANY new code)

**Goal:** Establish testing infrastructure and validate reusable components still work.

| Task | What | Tests | Lines Est. |
|------|------|-------|-----------|
| 0.1 | Set up VCR cassette recording | Record one v1 pipeline run as fixtures | 50 |
| 0.2 | Write contract tests for all 4 phase boundaries | 20 Pydantic schema tests | 200 |
| 0.3 | Write node isolation test harness | Mock LLM, test each v1 node independently | 150 |
| 0.4 | Verify 6 REUSE components import + work | Import tests + basic function tests | 60 |
| 0.5 | Create golden dataset | 3 topics with v1-best outputs as baseline | 50 |

**Gate:** All Milestone 0 tests pass. No new code written yet. ~510 LOC of tests.

### Milestone 1: SCOPE Phase (New)

**Goal:** Sub-question decomposition + perspective discovery + query generation.

| Task | What | Reuses | Tests First | Lines Est. |
|------|------|--------|------------|-----------|
| 1.1 | `ScopeOutput` schema | schemas.py (ADAPT) | Contract test: schema validates | 40 |
| 1.2 | `scope_node()` function | planner.py (REUSE) | Unit test: mock LLM → valid ScopeOutput | 120 |
| 1.3 | Perspective discovery prompt | storm_interviews.py (REUSE) | Unit test: returns 5-8 perspectives | 30 |
| 1.4 | Query generation per sub-question | planner.py (REUSE) | Unit test: 3-5 queries per question | 50 |
| 1.5 | Integration test: scope → search contract | N/A | Contract test: ScopeOutput → SearchQuery[] | 40 |

**Gate:** `scope_node()` takes a query string, returns valid `ScopeOutput` with mock LLM. VCR cassette recorded with real LLM. ~280 LOC.

### Milestone 2: SEARCH Phase (Adapted)

**Goal:** Sub-question-targeted search with CRAG evaluation and reflection loop.

| Task | What | Reuses | Tests First | Lines Est. |
|------|------|--------|------------|-----------|
| 2.1 | `search_round()` function | searcher.py (ADAPT) | Unit test: returns SearchRoundOutput | 200 |
| 2.2 | Per-sub-question search dispatch | searcher.py (ADAPT) | Unit test: queries tagged with sq_id | 80 |
| 2.3 | CRAG evaluation integration | crag_retriever.py (REUSE) | Unit test: correct/ambiguous/incorrect routing | 50 |
| 2.4 | Reflection distillation | NEW | Unit test: compresses round findings | 60 |
| 2.5 | Convergence detector | NEW | Unit test: detects saturation | 40 |
| 2.6 | Content quality gate integration | content_quality_gate.py (REUSE) | Already tested | 10 |
| 2.7 | Evidence card enrichment | analyzer.py (ADAPT) | Unit test: enrichment adds metadata | 30 |
| 2.8 | Integration test: search → outline contract | N/A | Contract test: SearchRoundOutput validates | 40 |

**Gate:** `search_round()` takes SearchQueries, returns SearchRoundOutput with evidence + reflections + convergence score. ~510 LOC.

### Milestone 3: OUTLINE Phase (New)

**Goal:** Dynamic outline that evolves with evidence and detects gaps.

| Task | What | Reuses | Tests First | Lines Est. |
|------|------|--------|------------|-----------|
| 3.1 | `LiveOutline` schema | schemas.py (ADAPT) | Contract test | 40 |
| 3.2 | `generate_outline()` from sub-questions + evidence | section_writer.py plan_report (ADAPT) | Unit test: valid outline from mock evidence | 120 |
| 3.3 | `refine_outline()` with new evidence | NEW | Unit test: outline version increments, sections update | 80 |
| 3.4 | Evidence-to-section assignment | section_writer.py _assign_evidence (REUSE) | Unit test: exclusive assignment | 30 |
| 3.5 | Gap detection | NEW | Unit test: sections with <3 evidence flagged | 40 |
| 3.6 | Gap → search query generation | planner.py (REUSE) | Unit test: gap produces targeted queries | 30 |
| 3.7 | Integration test: outline → synthesize contract | N/A | Contract test | 40 |

**Gate:** Outline generates from evidence, refines when new evidence arrives, detects gaps. ~380 LOC.

### Milestone 4: SYNTHESIZE Phase (Adapted — the critical path)

**Goal:** Sequential section writing with inline verification and critic loop.

| Task | What | Reuses | Tests First | Lines Est. |
|------|------|--------|------------|-----------|
| 4.1 | `VerifiedSectionDraft` schema | schemas.py | Contract test | 30 |
| 4.2 | `write_verified_section()` | section_writer.py (ADAPT) | Unit test: mock LLM → valid draft with citations | 150 |
| 4.3 | Inline claim verification | nli_verifier.py (REUSE) + verifier.py (ADAPT) | Unit test: claims checked during writing | 100 |
| 4.4 | `critic_evaluate()` function | NEW | Unit test: mock LLM → pass/revise verdict | 80 |
| 4.5 | Analytical depth scoring | synthesizer.py _evaluate_analytical_depth (REUSE) | Already tested | 10 |
| 4.6 | Used-evidence tracking (prevent cross-section duplication) | NEW | Unit test: evidence used in S1 deprioritized in S2 | 40 |
| 4.7 | Previous-section context injection | NEW | Unit test: S2 prompt includes S1 summary | 30 |
| 4.8 | Pre-formatted comparison tables | section_writer.py _build_comparison_tables (REUSE) | Already tested | 10 |
| 4.9 | Integration test: synthesize → assemble contract | N/A | Contract test | 40 |

**Gate:** Sequential writing produces coherent sections with inline verification, critic approval, and no cross-section duplication. ~490 LOC.

### Milestone 5: ASSEMBLE Phase (Adapted)

**Goal:** Final report assembly with quality gates.

| Task | What | Reuses | Tests First | Lines Est. |
|------|------|--------|------------|-----------|
| 5.1 | Cross-section dedup | report_assembler.py detect_redundancy (REUSE) | Already tested | 10 |
| 5.2 | Citation resolution | citation_mapper.py (REUSE) | Already tested | 10 |
| 5.3 | Grounded abstract generation | report_assembler.py (ADAPT) | Unit test: abstract from actual content only | 40 |
| 5.4 | Contradictions section | synthesizer.py (REUSE) | Already tested | 10 |
| 5.5 | Quality gates (word count, citations, faithfulness, depth) | synthesizer.py + audit_v3_report.py (REUSE) | Already tested | 20 |
| 5.6 | Forensic audit integration | audit_v3_report.py (REUSE) | Already tested | 10 |

**Gate:** Full assembly pipeline produces report with bibliography, passing all quality gates. ~100 LOC.

### Milestone 6: GRAPH WIRING (Rewrite)

**Goal:** Wire all phases into a LangGraph StateGraph with the new topology.

| Task | What | Reuses | Tests First | Lines Est. |
|------|------|--------|------------|-----------|
| 6.1 | New `ResearchState` (decomposed sub-states) | state.py (REWRITE) | Schema tests for all sub-states | 200 |
| 6.2 | `build_v3_graph()` function | graph.py (REWRITE) | Graph compilation test (no execution) | 150 |
| 6.3 | Search↔Outline loop wiring | NEW | Integration test: gap triggers re-search | 50 |
| 6.4 | Timeout + budget enforcement | graph.py (REUSE pattern) | Unit test: timeout triggers graceful exit | 30 |
| 6.5 | `build_and_run_v3()` entry point | graph.py (ADAPT) | E2E test with VCR cassettes | 100 |
| 6.6 | Streaming + Rich dashboard | graph.py (REUSE) | Manual verification | 50 |

**Gate:** Full graph executes with VCR cassettes (no live API). All node transitions correct. ~580 LOC.

### Milestone 7: LIVE VALIDATION

**Goal:** Real API calls, forensic audit, head-to-head comparison.

| Task | What |
|------|------|
| 7.1 | Smoke test (16/16 existing tests pass with v3 graph) |
| 7.2 | V3_E2E_001: biochar query with real APIs |
| 7.3 | Forensic audit comparison vs PG_TEST_039 (v1 best) |
| 7.4 | Forensic audit comparison vs V2_E2E_007 (v2 baseline) |
| 7.5 | Second topic E2E to verify generalization |
| 7.6 | Cost analysis vs v1 and v2 |

---

## 4. Testing Strategy (4 Tiers)

### Tier 1: Blocks every change ($0, <10s)
- **20 schema contract tests** — Every Pydantic model validates + serializes
- **40 deterministic logic tests** — Citation normalization, dedup, tier scoring, content quality gate
- **10 property-based tests (Hypothesis)** — Citation normalization is idempotent, dedup is exhaustive
- **8 node isolation tests** — Each graph node with mock LLM input/output

### Tier 2: Blocks every change ($0, <30s)
- **5 VCR cassette tests** — Recorded real interactions replayed (pytest-recording)
- **10 behavioral contract tests** — Phase boundary validation, evidence ID format, content cap enforcement

### Tier 3: Main branch only ($1-2, ~5 min)
- **3 golden dataset regressions** — Known topics scored against baselines
- **1 LLM-as-judge quality gate** — Rubric-based evaluation

### Tier 4: Manual trigger ($2-5, ~60 min)
- **Full E2E** with live APIs
- **Forensic audit** comparison

### Test Infrastructure Needed BEFORE Code
1. `pytest` + `pytest-asyncio` (already installed)
2. `vcrpy` + `pytest-recording` (new dependency — record/replay HTTP)
3. `hypothesis` (new dependency — property-based testing)
4. Test fixtures directory: `tests/v3/fixtures/` with golden datasets
5. Mock LLM factory: returns canned JSON for each schema type

---

## 5. Risk Mitigation

### Risks from v2 Post-Mortem

| v2 Failure | v3 Mitigation | Test That Catches It |
|---|---|---|
| Parallel writing → 25.9% dupes | Sequential writing with used-evidence set | Contract test: no evidence_id appears in 2 sections |
| Blueprint coordination never built | Outline has cross_refs + narrative_flow | Schema test: OutlineSection.cross_refs required |
| Verifier runaway (170 rewrites) | Inline verify + critic with max 2 revisions | Unit test: critic_evaluate respects max_revisions |
| Zero cross-section coherence | Previous-section context in each write prompt | Integration test: section N prompt contains section N-1 summary |
| No cross-section dedup in assembly | Embedding-based dedup pass (existing code) | Integration test: duplicate sentences removed |
| Citation concentration (top 3 = 41%) | Used-evidence tracking + per-source cap | Unit test: no source cited >5x across full report |
| Stats bug (pre/post transform order) | Metrics captured before citation resolution | Unit test: metrics computed before resolve_citations |
| Design doc features never built | Every feature has a test BEFORE implementation | Milestone gates block progress without passing tests |

### New Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Scope phase produces bad sub-questions | Medium | Search is unfocused | Fallback: existing planner.py query generation |
| Outline refinement oscillates (never converges) | Medium | Infinite loop | Max 3 refinements + convergence threshold |
| Critic is too strict (rejects everything) | Medium | Pipeline stalls | Max 2 revisions per section + pass-through on 3rd |
| Reflection distillation loses critical details | Medium | Poor synthesis | Raw sources re-introduced at write time (Tavily pattern) |
| LangGraph state grows too large | High | OOM / slow | Decomposed sub-states + aggressive pruning between phases |
| VCR cassettes become stale | Low | Tests pass but real API fails | Re-record cassettes monthly |
| Qwen 3.5 Plus can't produce analytical output | Medium | Prompt changes don't help | Model switch for synthesis calls only |

---

## 6. What Gets Deleted

| File | Action | Reason |
|------|--------|--------|
| `graph_v2.py` | DELETE | v2 graph superseded by v3 |
| `synthesizer_v2.py` | DELETE | Parallel writer superseded by sequential |
| `verifier_v2.py` | DELETE | Post-hoc verifier superseded by inline |
| `report_assembler_v2.py` | DELETE | v2 assembler superseded |
| `section_blueprint.py` | DELETE | Blueprint replaced by LiveOutline |

These are already dead code (v2 gated behind `PG_V2_ENABLED=1` which is off). Deleting reduces confusion.

---

## 7. File Map: What Gets Created/Modified

### New Files
| File | Purpose | Lines Est. |
|------|---------|-----------|
| `src/polaris_graph/graph_v3.py` | New 5-phase LangGraph graph | 600 |
| `src/polaris_graph/state_v3.py` | Decomposed sub-states (Pydantic) | 300 |
| `src/polaris_graph/nodes/scope.py` | Phase 1: query decomposition | 150 |
| `src/polaris_graph/nodes/search.py` | Phase 2: targeted search orchestrator | 250 |
| `src/polaris_graph/nodes/outline.py` | Phase 3: dynamic outline | 200 |
| `src/polaris_graph/nodes/synthesize.py` | Phase 4: sequential write + verify + critic | 300 |
| `src/polaris_graph/nodes/assemble.py` | Phase 5: assembly + audit | 150 |
| `tests/v3/test_contracts.py` | Phase boundary contract tests | 200 |
| `tests/v3/test_nodes.py` | Individual node tests with mock LLM | 300 |
| `tests/v3/test_integration.py` | VCR-based integration tests | 150 |
| `tests/v3/conftest.py` | Fixtures, mock LLM factory, VCR config | 100 |
| **Total new** | | **~2,700** |

### Modified Files (Interface Adaptations)
| File | Change |
|------|--------|
| `openrouter_client.py` | Add model routing (accept model override per call) |
| `searcher.py` | Accept SearchQuery[] instead of ResearchState |
| `analyzer.py` | Accept FetchedContent[] instead of ResearchState |
| `storm_interviews.py` | Accept explicit params instead of ResearchState |
| `section_writer.py` | Remove plan_report (moved to outline node), keep write_section |
| `schemas.py` | Add v3 schemas (ScopeOutput, LiveOutline, etc.) |

### Unchanged Files (Direct Reuse)
`planner.py`, `crag_retriever.py`, `source_registry.py`, `content_quality_gate.py`, `nli_verifier.py`, `citation_mapper.py`

---

## 8. Success Criteria

### Quantitative (Measured by audit_v3_report.py)

| Metric | v1 Best (PG_039) | v2 (Broken) | v3 Target | Gemini |
|--------|-------------------|-------------|-----------|--------|
| Duplicate sentences | 0% | 25.9% | 0% | 0% |
| Comparison markers | ~5 | ~2 | >= 20 | 30+ |
| Tables | 0 | 26 (garbled) | >= 3 (clean) | 2-4 |
| Key Findings sections | 0-1 | 15 | >= 4 | 4-6 |
| Citation density/100w | 0.69 | 4.96 | > 2.0 | 2-4 |
| Filler phrases | 23-59 | 3 | < 5 | < 3 |
| Contradictions noted | 0 | 0 | >= 3 | 2-5 |
| Cross-section refs | 0 | 0 | >= 5 | 5-10 |
| Garbled text | 0 | 38 | 0 | 0 |
| Faithfulness (NLI) | 80.5% | N/A | >= 80% | ~85% |
| Cost per report | $1.31 | $2-3 | < $2.50 | N/A |

### Qualitative
- Report reads as a unified analysis, not a dump of findings
- A domain expert would consider it useful, not just impressive-looking
- Each section answers a specific question, not just covers a topic
- Contradictions and limitations are honestly surfaced
- Tables contain multi-source comparison data with citations

### Testing
- Tier 1 + 2: 93 tests, all passing, <30 seconds, $0
- Tier 3: 4 tests, all passing, ~5 minutes, <$2
- Tier 4: 1 full E2E, forensic audit grades B+ or higher

---

## 9. Timeline (Honest)

| Milestone | Est. Sessions | Dependencies | Gate |
|-----------|--------------|--------------|------|
| M0: Foundation (tests + fixtures) | 1 | None | All tests pass |
| M1: SCOPE phase | 1 | M0 | scope_node mock + VCR test pass |
| M2: SEARCH phase | 1-2 | M1 | search_round mock + VCR test pass |
| M3: OUTLINE phase | 1 | M2 | outline generates + refines + gaps detect |
| M4: SYNTHESIZE phase | 2 | M3 | Sequential write + verify + critic pass |
| M5: ASSEMBLE phase | 0.5 | M4 | Assembly pipeline produces valid report |
| M6: GRAPH WIRING | 1 | M1-M5 | Full graph runs with VCR cassettes |
| M7: LIVE VALIDATION | 1-2 | M6 | Forensic audit meets targets |
| **Total** | **8-10 sessions** | | |

This is conservative. The v2 rewrite took 1 session and failed. This takes 8-10 and succeeds.

---

## 10. Rollback Strategy

If v3 fails at any milestone:
- **M1-M5 failure:** Fix the failing phase. No other code is affected (phases are independent).
- **M6 failure (wiring):** Fall back to v1 graph (still works, never modified).
- **M7 failure (quality):** v1 graph remains the production path. v3 graph lives behind `PG_V3_GRAPH_ENABLED=1` flag. Diagnose via forensic audit, fix specific phase, re-test.

**The v1 graph is NEVER modified or deleted.** v3 is a NEW graph file (`graph_v3.py`). Toggle via env var. Zero risk to existing functionality.
