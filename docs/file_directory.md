# POLARIS File Directory

**Last Updated**: 2026-03-13 (Session 39 — FIX-B2 citation chain fix, playwright_interaction_audit.py added)
**Status**: 362 integration tests passing. 5 deprecated legacy test files deleted (48 failures eliminated). 153 dashboard tests. Live audit 118/120 PASS. PG_TEST_061 launched. 8 CSS + 16 JS modules. 58 interaction checks (IA-IH).

---

## Key Architecture Notes

- **TWO SYSTEMS**: `src/polaris_graph/` = PRODUCTION, `src/phases/` + `src/orchestration/` = LEGACY (kept for reference only)
- **Entry point**: `src/polaris_graph/graph.py::build_and_run()`
- **LLM**: All calls via OpenRouter -> Kimi K2.5 1T
- **Major cleanup 2026-02-23**: 13 dead `src/` dirs removed, 27 legacy scripts archived, 14 stale docs archived, 8.5GB duplicate checkpoints archived, empty output dirs removed, old logs archived

---

## 1. Root Level Files

| File | Purpose | Status |
|------|---------|--------|
| `CLAUDE.md` | AI agent operational directives and project laws | ACTIVE |
| `architecture.md` | Complete system architecture specification | ACTIVE |
| `ground_rules.md` | Engineering ground rules and conventions | ACTIVE |
| `README.md` | Project overview and quick start guide | ACTIVE |
| `requirements.txt` | Python dependencies (incl. fastapi, uvicorn, sse-starlette, slowapi, weasyprint) | ACTIVE |
| `pytest.ini` | Pytest configuration | ACTIVE |
| `.env` | Environment variables (API keys, feature flags, thresholds, 1540+ lines) | ACTIVE - SENSITIVE |
| `Dockerfile` | Python 3.11-slim container with WeasyPrint deps and health check | ACTIVE |
| `docker-compose.yml` | 4-service compose: web, chromadb, searxng (sovereign), vllm (sovereign) | ACTIVE |
| `.dockerignore` | Excludes logs/, outputs/, archive/, .env, __pycache__, tests/ | ACTIVE |

---

## 2. src/polaris_graph/ -- PRODUCTION System (Core Files)

The production LangGraph research pipeline. Entry point: `graph.py::build_and_run()`.

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 33 | Module exports |
| `graph.py` | 1437 | Main LangGraph workflow definition (8-node: plan, search, storm_interviews, analyze, verify, evaluate, synthesize, search_gaps) |
| `state.py` | ~525 | Pipeline state TypedDict and env var management. Added memory_ltm_priors, uploaded_documents (Sprint 1), smart_art_diagrams (Sprint 2) |
| `document_ingester.py` | ~400 | Local document parser: 9 formats (PDF/DOCX/XLSX/PPTX/TXT/MD/CSV/HTML). Zero external API calls (A7.2) |
| `schemas.py` | 1355 | Pydantic models for pipeline state (EvidencePiece, ClusterPlan, SectionDraft, ReportOutline, etc.) |
| `tracing.py` | 228 | JSONL execution tracing (11 event types: +reasoning_capture, storm_transcript, iteration_decision) |
| `checkpoint_manager.py` | 595 | Checkpoint save/restore for pipeline resume. Extended Sprint 2: list_checkpoints(), get_checkpoint_state(), rewind_to_checkpoint() (A2) |
| `pipeline_definition.py` | ~310 | Pipeline schema (Sprint 4, A4.1): StageType enum (11 types), PipelineStage, MacroStage, PipelineDefinition Pydantic models. Dependency validation, cycle detection (Kahn's algorithm), topological sort execution ordering, YAML serialization, template loading |
| `dynamic_graph.py` | ~310 | Dynamic graph builder (Sprint 4, A4.2): builds LangGraph StateGraph from PipelineDefinition. Stage handler registry (11 types), macro sub-graph compilation, state pruning between MacroStages (A8.1), run_custom_pipeline() high-level API |
| `pipeline_wizard.py` | ~380 | Pipeline wizard engine (Sprint 4, A3): 6-stage conversational interview (problem→sources→analysis→verification→output→constraints). WizardSession class, heuristic-based pipeline generation from keyword responses, per-stage prompts + quick-reply chips |
| `batch_progress.py` | 101 | Batch progress tracking (SQLite-backed) |
| `dashboard.py` | 300 | Rich live dashboard display |
| `verify_subgraph.py` | 119 | Verification subgraph (ARCH-2, disabled) |

---

## 3. src/polaris_graph/agents/ -- Pipeline Agents

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 3 | Module exports |
| `synthesizer.py` | 2285 | Main synthesis orchestrator: map-reduce clustering, short-ID remapping, programmatic merge, evidence caps, fallback outline |
| `analyzer.py` | 2651 | Evidence analysis: extraction, per-piece BRONZE scoring, anti-embellishment prompt, quote validation |
| `searcher.py` | ~2263 | Search execution: Serper, Semantic Scholar, DuckDuckGo, Exa, Tavily, Jina Reader, Firecrawl, Crawl4AI, domain blocklist, authority scoring. A1.1: raw HTML capture + readability extraction |
| `verifier.py` | 1466 | Claim verification: NLI cascade (MiniCheck + LLM), incremental verify, auto-scale timeout, content cap alignment |
| `storm_interviews.py` | 1361 | STORM perspective interviews (8 perspectives) |
| `nli_verifier.py` | 832 | NLI verification: MiniCheck flan-t5-large on CUDA, quote context extraction, 96x faster than LLM |
| `planner.py` | 475 | Research planning: query generation, learned strategies from LTM, fallback planner. A7.4: human override retrieval + injection in plan_queries() and plan_seed_queries() |
| `cross_reference.py` | 332 | Cross-reference grouping and corroboration |
| `source_confidence.py` | 299 | Source confidence scoring: domain authority, peer-reviewed enforcement |
| `citation_agent.py` | 229 | Citation handling: S2 citation chasing, bibliography validation (ARCH-3) |
| `hallucination_detector.py` | 331 | NLI-based post-synthesis hallucination audit: MiniCheck claim-level verification, replaces LettuceDetect |

---

## 4. src/polaris_graph/synthesis/ -- Synthesis Pipeline

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 3 | Module exports |
| `section_writer.py` | 1822 | Section outline and content generation, LTM prior knowledge injection, expand thin sections |
| `report_assembler.py` | 1688 | Final report assembly: orphan citation fix, wire backfill, redundancy gate, grounded abstract |
| `citation_mapper.py` | 573 | Citation token resolution: [CITE:id] to [N] mapping, duplicate adjacent dedup, multi-citation split |
| `cross_section_reflector.py` | 459 | Cross-section reflection and revision: bond input, targeted revision, 130% upper bound |
| `peptide_flow.py` | 483 | Narrative flow optimization between sections (zero LLM cost, M-11) |
| `covalent_binder.py` | 319 | Claim-evidence binding verification (zero LLM cost, M-08) |
| `evidence_explorer.py` | 303 | Evidence exploration and embedding cosine similarity scoring |
| `disulfide_bridge.py` | 243 | Cross-section source consistency enforcement (zero LLM cost, M-10) |
| `ionic_rebalancer.py` | 195 | Evidence-section affinity rebalancing (zero LLM cost, M-09) |
| `section_utils.py` | 36 | Shared evidence_ids sync helper (M-01) |
| `smart_art_generator.py` | 597 | Smart art generation (A5): LLM-generated Mermaid.js diagrams. 7 types: process_flow, comparison_matrix, causal_chain, hierarchy, timeline, pros_cons, decision_tree |

---

## 4b. src/polaris_graph/export/ -- Report Export (Sprint 1, A8.4)

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 1 | Module marker |
| `docx_exporter.py` | 580 | Microsoft Word (.docx) export with corporate styling. Title page, TOC, bibliography, quality summary, audit certificate. |

---

## 5. src/polaris_graph/memory/ -- SQLite Caches

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 1 | Module marker |
| `evidence_hierarchy.py` | 358 | Evidence hierarchy cache (SQLite): tier tracking, cross-iteration persistence |
| `cross_vector.py` | 600 | Cross-vector memory (ChromaDB): shared findings across research vectors. Sprint 3: list_ltm_items(), delete_ltm_item(), store_human_override(), query_human_overrides() (A7.4 human correction collection) |
| `session_feedback.py` | 329 | Session feedback cache (SQLite): quality signals, iteration history |
| `content_cache.py` | ~250 | Content cache (SQLite): fetched URL content dedup. Extended with raw_html, readability_html columns, extract_readability_html() (A1.1) |
| `search_cache.py` | 145 | Search cache (SQLite): query result dedup |
| `campaign_store.py` | 364 | Campaign persistence (SQLite): CRUD for multi-query campaigns (Sprint 1, Task 1A.2) |
| `local_document_rag.py` | ~300 | Session-scoped ChromaDB RAG over uploaded documents (A7.2 + A8.1) |

---

## 6. src/polaris_graph/llm/ -- LLM Client

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 5 | Module exports |
| `openrouter_client.py` | ~1620 | OpenRouter API client: SSE streaming, generate/generate_structured/reason, CoT scrubbing, stub JSON detection, truncation repair, non-SSE fallback, OBS reasoning capture. A8.2: global concurrency semaphore via _call()→_call_impl() delegation |

---

## 7. src/ (Shared Utilities)

### src/search/ -- Search Infrastructure

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `engines.py` | Search engine implementations (Tavily, Serper, Academic) |
| `serper_client.py` | Serper.dev API client |
| `query_amplifier.py` | 10x query variants generation |
| `fan_out_executor.py` | Parallel search with circuit breaker |

### src/utils/ -- 35 Utility Modules

| File | Purpose |
|------|---------|
| `academic_fetcher.py` | Academic source fetching (CrossRef, S2, OpenAlex) |
| `academic_orchestrator.py` | Academic search orchestration |
| `atomic_decomposer.py` | LLM-based atomic fact decomposition |
| `circuit_breaker.py` | Circuit breaker for API resilience |
| `citation_chainer.py` | Citation chain following |
| `citation_registry.py` | Late-binding citation resolution |
| `claim_decomposer.py` | Claim decomposition Pydantic schemas |
| `content_deduplicator.py` | Content deduplication with MinHash |
| `cost_tracker.py` | API cost tracking and budgeting |
| `cot_post_filter.py` | Chain-of-thought post-filter |
| `cot_scrubber.py` | Chain-of-thought scrubber |
| `crossref_client.py` | CrossRef API client |
| `crossref_resolver.py` | CrossRef DOI resolution |
| `embedding_service.py` | Embedding generation (sentence-transformers) |
| `evaluation.py` | FactScore + G-Eval metrics |
| `fact_extractor.py` | LLM + regex fact extraction |
| `geographic_tagger.py` | Geographic metadata tagging |
| `hybrid_retrieval.py` | Hybrid retrieval (dense + BM25) |
| `ingest.py` | Content fetching and processing |
| `inline_verifier.py` | MiniCheck inline verification wrapper |
| `language_handler.py` | Multi-language support |
| `logging_config.py` | Logging configuration |
| `openalex_client.py` | OpenAlex API client |
| `quality_metrics.py` | Quality metrics calculation |
| `query_utils.py` | Query utilities |
| `question_classifier.py` | Question type classification |
| `ragas_evaluator.py` | RAGAS evaluation framework |
| `rate_limiter.py` | API rate limiting |
| `result_cache.py` | Search result caching |
| `safe_verifier.py` | SAFE verification loop |
| `self_refinement.py` | Self-refinement critique loop |
| `semantic_chunking.py` | Semantic text chunking |
| `semantic_scholar_client.py` | Semantic Scholar API client |
| `source_quality.py` | Source quality scoring (RCS Map) |
| `source_router.py` | Multi-source routing with RRF |
| `unpaywall_client.py` | Unpaywall API client |
| `url_blacklist.py` | URL/domain blacklist management |

### src/tools/ -- Agent Tools (11 files)

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `access_bypass.py` | Unpaywall, Archive.org, proxy access, nav boilerplate stripping |
| `agent_swarm_full.py` | Agent swarm orchestrator |
| `browser_automation.py` | Playwright JS rendering, SPA extraction |
| `file_analyzer.py` | Excel/CSV/PDF/JSON analysis + ChartGenerator |
| `long_form_generator.py` | 100K+ token document generation + CoherenceValidator |
| `pdf_parser.py` | PDF parsing with PyMuPDF |
| `streaming_reasoner.py` | Real-time reasoning token streaming |
| `user_feedback.py` | Mid-research user feedback/checkpoint |
| `vision_processor.py` | Vision processing (CLIP, OCR, Gemini fallback) |
| `vision_tool.py` | Gemini vision analysis |
| `visual_generator.py` | Visual output generation |

### src/auth/ -- Authentication & RBAC (Session 10)

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 1 | Module marker |
| `auth_manager.py` | 259 | AuthManager: Role enum, HMAC-SHA256 tokens, user CRUD, file-based user store |
| `auth_middleware.py` | 101 | FastAPI dependencies: get_current_user, require_role, require_action |
| `auth_routes.py` | 127 | 7 API endpoints at /api/auth/*: login, register, me, refresh, users, update, delete |
| `session_manager.py` | 170 | SessionManager: concurrent sessions, queue, history, MAX_CONCURRENT_RESEARCH |

### src/providers/ -- Provider Abstraction for Sovereign Mode (Session 10)

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 1 | Module marker |
| `llm_provider.py` | ~300 | LLM provider abstraction (A7.3 + A8.2): sovereign mode toggle, global concurrency semaphore, exponential backoff with jitter, GPU memory monitoring, provider factory |
| `search_provider.py` | 138 | Search provider factory: cloud (Serper+Exa+S2), searxng (self-hosted), internal (corpus) |
| `deployment_validator.py` | 151 | assert_sovereign_mode(), assert_not_sovereign(), validate_deployment_mode() -- sovereign/cloud mode validation with fail-loudly errors |

### src/memory/ -- ChromaDB Legacy Memory

| File | Purpose |
|------|---------|
| `__init__.py` | Module marker |
| `chroma_client.py` | VWM/LTM-Stage/LTM-Global ChromaDB management |

### src/state/ -- State Management

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `ledger.py` | Progress ledger management |
| `session.py` | Session state management |
| `orchestration.py` | Orchestration state utilities |
| `cost_ledger.json` | API cost tracking data |
| `last_pointer.json` | Last processed vector pointer |
| `progress_ledger.jsonl` | Append-only execution log |
| `ledger.lock` | Lock file for concurrent access |

### src/config/ -- Configuration Management

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `core.py` | Core configuration loading (PolarisConfig) |
| `thresholds.py` | Threshold dataclasses |

### src/audit/ -- Audit System

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `automated_deep_audit.py` | 10-dimension automated deep audit (D1-D10) |
| `benchmark_audit.py` | RAGAS + NLI benchmark evaluation |
| `collector.py` | Comprehensive audit data collection |
| `runner_audit.py` | Runner audit execution |
| `archive/deep_audit.py` | Deep audit (archived, kept for reference) |
| `archive/lightweight_audit.py` | Lightweight audit (archived) |
| `archive/phase_hooks.py` | Phase hooks (archived) |

### src/quality/ -- Quality Gates

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `gates.py` | Quality gate measurements |
| `bias_detector.py` | Bias detection and balanced viewpoints |
| `output_quality_gate.py` | CoT leakage, internal markers, near-duplicate, PDF noise detection |

### src/benchmarks/ -- SOTA Validation Framework

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `auditor_strict.py` | Strict auditor without gaming mechanisms |
| `hle_benchmark.py` | HLE benchmark runner |
| `hle_dataset.py` | HLE dataset handler |
| `metrics_strict.py` | Strict metrics with real atomic decomposition |
| `report_generator.py` | Publication-grade comparison reports |
| `stats_analysis.py` | Statistical tests (t-test, Wilcoxon, bootstrap CI) |

### src/llm/ -- LLM Clients (Legacy Track)

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `deberta_client.py` | DeBERTa NLI client (local inference) |
| `factory.py` | LLM factory |
| `gemini_client.py` | Gemini API client (fallback) |
| `kimi_client.py` | KIMI K2.5 via Fireworks AI |

### src/schemas/ -- Pydantic Data Models

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `api_query.py` | API query models |
| `decomposed_query.py` | SubQuery, DecomposedQuery models |
| `extracted_facts.py` | 8 fact type models |
| `phase_models.py` | Pydantic models for all phases |
| `question_types.py` | QuestionType enum and profiles |
| `validation_criteria.py` | 10 criterion types (DeCE-style) |

### src/agents/ -- Research Agents (Legacy Track)

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `analyst_agent.py` | Entity/fact/claim extraction with LLM |
| `auditor_agent.py` | Post-hoc verification and citation correction |
| `base_agent.py` | Abstract base class for all agents |
| `citation_enricher_agent.py` | Citation enrichment |
| `citefirst_synthesizer.py` | Cite-first synthesis (FIX-117) |
| `clarification_agent.py` | Pre-research query clarification |
| `critic_agent.py` | RAGAS-style quality evaluation |
| `planner_agent.py` | STORM-style query decomposition |
| `search_agent.py` | Multi-source search |
| `supervisor_agent.py` | Workflow coordination |
| `synthesizer_agent.py` | Report generation with [CITE:] tokens |
| `triage_agent.py` | Query complexity classification |
| `verifier_agent.py` | NLI claim verification |
| `citefirst/` | Cite-first sub-modules (claim_processing, evidence_clustering, prose_generation, report_composition, revision_loop, synthesizer) |

---

## 8. src/ (Legacy -- Kept for Reference)

These directories are from the original 13-phase CLI pipeline. They are NOT used by the production system (`src/polaris_graph/`).

### src/orchestration/ -- Legacy LangGraph State Machine

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `graph.py` | Legacy LangGraph workflow definition |
| `state.py` | Legacy ResearchState TypedDict |
| `iteration_manager.py` | ReAct loop iteration control |
| `persistence.py` | JSON state save/load |
| `dynamic_replanner.py` | Adaptive re-planning |
| `stopping_mechanism.py` | Coverage-based stopping |

### src/phases/ -- 14 Legacy CLI Phase Scripts

| File | Phase | Purpose |
|------|-------|---------|
| `p00_init.py` | P0 | VWM initialization |
| `p01_contextualization.py` | P1 | LTM query, strategic plan |
| `p02_query_generation.py` | P2 | STORM query generation |
| `p03_search.py` | P3 | Federated search |
| `p04_relevance_filter.py` | P4 | RCS Map + source quality |
| `p05_indexing.py` | P5 | Semantic chunking, VWM indexing |
| `p06_nli_integrity.py` | P6 | NLI verification |
| `p07_dual_rag.py` | P7 | Outline-first + thematic clustering |
| `p08_claim_verification.py` | P8 | FactScore atomic decomposition |
| `p09_adversarial_qa.py` | P9 | Adversarial QA |
| `p10_gating.py` | P10 | Gating decision matrix |
| `p11_knowledge_integration.py` | P11 | LTM promotion |
| `p12_research_packaging.py` | P12 | Self-refinement + SAFE |
| `p13_narrative_synthesis.py` | P13 | Cross-vector synthesis |
| `sota_classification.py` | -- | Question type classification |

### src/runner.py -- Legacy Pipeline Runner

Main pipeline orchestrator for P6-P13 execution. Not used by production system.

---

## 9. scripts/ -- Production Scripts (16 files)

| File | Lines | Purpose |
|------|-------|---------|
| `generate_dashboard.py` | 680 | JSONL trace -> self-contained HTML dashboard (ChatGPT Dark Mode, 10 collapsible sections) |
| `live_server.py` | ~3320 | FastAPI + SSE live server. CORS, auth, RBAC enforcement, rate limiting, security headers, health check, PDF/DOCX export, SSE streaming, research history, campaign management, document upload/parse, memory stats/search/items/delete, mind map API, overrides API. 45+ endpoints: /api/campaigns/* (5), /api/research/* (11 incl. mindmap, chain, checkpoints, rewind, overrides), /api/auth/* (8), /api/documents/* (5), /api/memory/* (4), /health, /api/events, /api/snapshot, /static/* |
| `docker_entrypoint.sh` | 48 | Docker entrypoint: 4 modes (serve, research, preflight, shell) |
| `live_monitor.py` | ~430 | Standalone backend anomaly detector. 9 categories, 40+ rules. Tails trace JSONL + polaris_graph.log. Outputs to logs/live_anomaly_log.jsonl + .md |
| `forensic_audit.py` | ~580 | Post-run exhaustive 11-section forensic analysis. Reads all trace + cost + result + report. Outputs outputs/forensic_report_{vid}.md + .json |
| `playwright_audit.py` | 280 | Automated headless browser audit of HTML dashboard (15 checks, screenshots, JSON report) |
| `pg_preflight_v2.py` | 1816 | Preflight v2: 40-test async validation (4 tiers: hard failures, config, integration, quality) |
| `pg_preflight_032.py` | 868 | Preflight for PG_TEST_032: 10-test real-API validation |
| `pg_preflight_047.py` | 425 | Preflight for PG_TEST_047 |
| `pg_sota_smoke_test.py` | 636 | 30-item SOTA smoke test automation |
| `pg_smoke_test.py` | 533 | 9-test polaris_graph smoke test |
| `pg_gemini_preflight.py` | 480 | Gemini Gap fire tests: Layer 1 (local, $0), Layer 2 (API, $0.20), Layer 3 (integration, $0.30) |
| `pg_component_verify.py` | 542 | Component-level verification |
| `full_cycle.py` | 585 | Full cycle pipeline execution |
| `pg_test_061.py` | -- | PG_TEST_061 test runner script |
| `run_audit.py` | 127 | Automated deep audit CLI (`python scripts/run_audit.py --result-file <path>`) |
| `run_s1v1_full.py` | 229 | Run S1V1 full pipeline (legacy) |
| `playwright_visual_overhaul.py` | ~850 | Closed-loop Playwright visual audit: 40 checks across 9 tabs, 3 breakpoints, screenshots + JSON audit report. Manages inject->server->browser lifecycle. |
| `deploy.sh` | ~1215 | **Sprint 5**: Production deployment script. Prerequisites check (Python/pip/CUDA/Docker/port), GPU detection (nvidia-smi/CUDA/VRAM), venv setup, .env validation + template generation, directory creation, health check (start server, poll /health, verify /api/system/info), Docker mode (compose build/up, GPU passthrough). CLI flags: --check-only, --docker, --gpu, --no-gpu, --port, --help. Colored output, trap cleanup, cross-platform venv paths. |
| `inject_test_trace.py` | ~600 | Synthetic JSONL trace generator for dashboard testing. Produces all event types: LLM calls, evidence, STORM, cross-ref, conflicts, verification batches, sections, quality gates. |
| `visual_qa_audit.py` | 2270 | **Session 31B**: Exhaustive visual QA audit (WCAG 2.2 AA + production-grade). Async Playwright. 12 sections (A-L): navigation uniqueness (15 states), axe-core WCAG (32 runs), focus audit, hover/active states, touch targets, cross-browser structural checks (3 engines), 7-viewport responsive + 320px reflow, print/PDF, CSS hardcoded scan, visual regression baselines, JSON+HTML report. `python scripts/visual_qa_audit.py --port 8766` |
| `playwright_interaction_audit.py` | 1757 | **Session 39**: Interaction audit — 58 checks across 8 categories (IA-IH): citation system (13), view switching & navigation (8), evidence browser (7), metrics & data display (8), export & action buttons (5), real-time indicators (5), workspace-specific (8), console errors & robustness (4). Async Playwright. JSON report output. |

### scripts/templates/ -- HTML Templates

| File | Lines | Purpose |
|------|-------|---------|
| `live_dashboard.html` | ~483 | Modular HTML shell (Sprint 1, A7.1). Loads 6 CSS files + 9 JS files from `/static/`. Contains only HTML body structure. |

### scripts/static/css/ -- Modular CSS (Sprint 1-2)

| File | Lines | Purpose |
|------|-------|---------|
| `base.css` | 294 | CSS variables (dark/light themes), reset, typography, scrollbar, accessibility (skip-link, focus-visible) |
| `layout.css` | 440 | App shell, header, nav bar, research view layout, responsive breakpoints, print styles |
| `components.css` | 460 | Buttons, badges, cards, toasts, modals, form controls, animations, auth UI, history, bookmarks |
| `report.css` | 661 | Report view, citations, TOC, STORM sidebar, quality banners, bibliography, section styles |
| `evidence.css` | 149 | Evidence view layout, evidence cards, graph area, tier badges, signal bars |
| `operator.css` | 1556 | Advanced tabs, STORM personas, operator panels, landing page, campaign management, trace cards |
| `citation_chain.css` | 290 | Citation chain-of-custody modal (A1): 4-tab layout, source preview iframe, reasoning chain, tier badges, responsive bottom sheet (Sprint 2) |

### scripts/static/js/ -- Modular JavaScript (Sprint 1-2)

| File | Lines | Purpose |
|------|-------|---------|
| `core.js` | ~390 | Constants, state object (incl. smartArtDiagrams), theme toggle (Mermaid re-render), view switching, stepper, utility functions |
| `event_processor.js` | ~375 | SSE event dispatch, event type handlers, updateMetrics. Calls fetchCheckpoints() on pipeline completion |
| `research_view.js` | 281 | Research view rendering, faith gauge, strength meter, funnel, Gantt, signal radar |
| `graph_viz.js` | 195 | Cross-ref graph, citation map, source network visualizations |
| `evidence_browser.js` | 330 | Evidence cards, tier filtering, sorting, detail panel, radar chart |
| `report_view.js` | ~570 | Report rendering, citation popovers, TOC, export (PDF/MD/DOCX/JSONL), Word export, _renderMermaidDiagrams() for smart art |
| `operator_console.js` | 264 | Cost breakdown, quality metrics, audit export, model info, operator panels |
| `sse_connection.js` | 377 | SSE connection/reconnect, BroadcastChannel, snapshot hydration, polling |
| `advanced_tabs.js` | ~1140 | Advanced sub-tabs, view mode, research submission (with document_ids), auth UI, campaigns, bookmarks, memory indicator, checkpoint init, DOMContentLoaded |
| `citation_chain.js` | 438 | Chain-of-custody modal (A1): 4-tab interface (Summary, Source Preview, Reasoning Chain, Metadata), sandboxed iframe with mark.js quote highlighting, tier badges, fallback to blockquote |
| `checkpoint_timeline.js` | 1107 | Checkpoint timeline (A2): horizontal dot timeline, state inspector drawer, rewind-to-checkpoint, metrics display, keyboard accessible |
| `document_upload.js` | 890 | Document upload (A7.2): drag-and-drop zone, file type validation, progress bars, delete support, auto-load from server |

| `mind_map.js` | 1358 | Radial mind map SVG renderer (Sprint 3): center→sections→findings→sources. 36 functions. Zoom/pan, click-to-highlight, cross-cutting halos, stats bar, info panel, tooltips. Performance: 150 findings cap, 100 sources cap, rAF debouncing |
| `memory_dashboard.js` | 1562 | Memory dashboard tab (Sprint 3): stats bar (tier counts, domain chart), knowledge cluster bubble chart (force-directed packing), search (debounced 300ms), item list (pagination, delete), timeline (sessions bar chart). 27 functions, 4 API integrations |

### scripts/static/js/ -- Sprint 4 Pipeline Files

| File | Lines | Purpose |
|------|-------|---------|
| `pipeline_editor.js` | 1379 | Pipeline DAG editor (Sprint 4): collapsible macro-stage SVG canvas, topological layout engine, expand/collapse macro groups, stage config panel (11 types, key-value editor), zoom/pan/fit, drag-and-drop stages between macros, template picker, saved pipeline CRUD, validation with inline errors, minimap, keyboard shortcuts (Del/Esc/Ctrl+S). 43 internal + 12 global functions |
| `pipeline_wizard.js` | 981 | Pipeline wizard chat UI (Sprint 4): 6-stage progress bar with animated fill, chat interface (user/bot bubbles, markdown, typing indicator), quick-reply chips, pipeline draft preview card ("Use This Pipeline"/"Edit Manually"), session management (start/chat/finalize API), error recovery with session expiry detection. ~30 functions |

### scripts/static/css/ -- Sprint 4 Pipeline Styles

| File | Lines | Purpose |
|------|-------|---------|
| `pipelines.css` | 753 | Pipeline-specific CSS (Sprint 4): 3-column layout, template/saved cards, DAG canvas, macro-box/stage-node styles, edges, config panel with field styles, wizard chat/progress/chips/draft, toolbar, minimap, drag-and-drop states, validation error overlays, responsive breakpoint at 1024px |

---

## 10. config/ -- Configuration Files

| File | Purpose |
|------|---------|
| `evaluation_strict.env` | Strict evaluation environment overrides |
| `sota_baselines.json` | SOTA comparison baselines |
| `vector_library.py` | 175 vector definitions |

### config/pipeline_templates/ -- Pipeline Templates (Sprint 4, A4.1)

| File | Nodes | Macros | Purpose |
|------|-------|--------|---------|
| `standard_research.yaml` | 8 | 5 | Default pipeline: plan→search→storm→analyze→verify→evaluate→synthesize→gap_search |
| `quick_scan.yaml` | 4 | 4 | Fast 15-min scan: plan→search→analyze→synthesize (no verify/STORM) |
| `academic_focus.yaml` | 8 | 5 | Academic research: citation chasing, S2 priority, 80% faithfulness, 15K words |
| `compliance_review.yaml` | 8 | 5 | Regulatory/legal: conflict detection, 85% faithfulness, strict verification |
| `multi_vector.yaml` | 14 | 5 | Deep C-POLAR 175-sub-question: 5 iterations, 180 min, STORM+citation chase+conflict detection, 20K words |

### config/settings/ -- YAML Configuration (11 files)

| File | Purpose |
|------|---------|
| `chunking.yaml` | Chunking parameters |
| `concurrency.yaml` | Concurrency limits |
| `extraction.yaml` | Extraction parameters |
| `geographic_regions.yaml` | Regional definitions |
| `models.yaml` | Model configurations |
| `quality_gates.yaml` | Quality gate thresholds |
| `retry.yaml` | Retry policy |
| `search.yaml` | Search parameters |
| `search_sources.yaml` | Search engine configs |
| `sota_parameters.yaml` | SOTA-aligned parameters |
| `thresholds.yaml` | Detailed thresholds |

---

## 11. tests/ -- Test Suite

### tests/unit/ -- 31 Unit Test Files

| File | Purpose |
|------|---------|
| `test_fix_048.py` | FIX-048: 4 root cause fix tests (quote substance, content pre-filter, corroboration, B2B detection) |
| `test_fix_045.py` | FIX-045: orphan citations, nav boilerplate, abstract metrics, citation renumbering |
| `test_agentic_search.py` | Agentic search depth, pages per round, content reasoning |
| `test_analyst_resilience.py` | Analyst agent resilience |
| `test_bias_detector.py` | Bias detection |
| `test_clarification_agent.py` | Pre-research clarification |
| `test_config_thresholds.py` | Configuration thresholds |
| `test_content_deduplicator.py` | Content deduplication with MinHash |
| `test_critical_fixes.py` | Critical fix verification |
| `test_cross_section_reflector.py` | Cross-section reflector (130% upper bound guard) |
| `test_depth_config.py` | Depth configuration |
| `test_domain_diversity.py` | Domain diversity checks |
| `test_evidence_explorer.py` | Evidence exploration |
| `test_exception_handling.py` | Exception handling |
| `test_feedback_collector.py` | Mid-research feedback |
| `test_gemini_fixes.py` | Gemini audit regression tests |
| `test_hle_benchmark.py` | HLE benchmark runner |
| `test_language_handler.py` | Multi-language support |
| `test_memory_cross_vector.py` | Cross-vector memory |
| `test_memory_evidence_hierarchy.py` | Evidence hierarchy cache |
| `test_memory_session_feedback.py` | Session feedback cache |
| `test_orchestration_state.py` | State management |
| `test_output_formatter.py` | Output format flexibility |
| `test_perspective_tracking.py` | STORM perspective health checks |
| `test_real_factscore.py` | Real FactScore via atomic decomposition |
| `test_return_handling.py` | Return value handling |
| `test_streaming_progress.py` | Streaming progress |
| `test_visual_generator.py` | Visual output generation |
| `test_live_monitor.py` | Live anomaly detector: 9 categories (CoT, stub, evidence, verification, synthesis, cost, gates, timing, log errors) + writer + state (42 tests) |
| `test_forensic_audit.py` | Forensic audit: helpers, 11 section builders, full run with fixtures, edge cases (45 tests) |
| `test_live_server.py` | Live server: TraceTailer JSONL tailing, async tail, discover_trace_file, 7 FastAPI endpoints incl. cost session_id filtering (19 tests) |

### tests/e2e/ -- End-to-End Tests (Sprint 5)

| File | Purpose |
|------|---------|
| `dashboard_tests.py` | **Sprint 5**: 153-test Playwright suite (195 assertions, 14 test classes). Covers: page load & structure, navigation & view switching, theme toggle, research input, report view, evidence view, pipelines view, memory view, advanced view, responsive (375/768/1440px), conflict modal, view mode toggle, research view internals, global JS functions. |
| `conftest_visual.py` | **Session 31/31B**: Visual regression test config — viewports (375/768/1024/1440), browser list, theme/nav helpers, dynamic counter freeze. **Updated 31B**: navigate_to_view uses operator mode + switchView() for reliable navigation. |
| `visual_regression_suite.py` | **Session 31/31B**: Playwright native visual regression (64 screenshots across 8 views x 4 viewports x 2 themes) + 11 interactive element tests (hover, focus, click, keyboard, scroll, modal, overflow). **Updated 31B**: _navigate_to_view_safe uses operator mode + switchView(). |

### tests/e2e/fixtures/ -- Visual Test Fixtures

| File | Purpose |
|------|---------|
| `visual_test_data.py` | **Session 31**: Deterministic mock data for visual tests — SSE events, report HTML, evidence cards, citation chain, API response, JS counter freeze |

### tests/fixtures/ -- Test Data

| File | Purpose |
|------|---------|
| `mindmap_test_result.json` | Real-schema mind map result fixture (3 sections, 8 evidence, 4 bibliography) |

### tests/integration/ -- 15 Integration Test Files

| File | Purpose |
|------|---------|
| `test_polaris_graph.py` | Core polaris_graph integration tests (56 tests) |
| `test_fix_043.py` | FIX-043 integration tests |
| `test_most_integration.py` | MoST bond module integration tests |
| `test_memory_integration.py` | Memory subsystem integration |
| `test_serper_sync.py` | Serper synchronization |
| `test_sota_compliance.py` | SOTA compliance |
| `test_sota_quality_sprint.py` | SOTA quality sprint tests |
| `test_document_pipeline_wiring.py` | Document upload → pipeline wiring (9 tests: ResearchRequest, DocumentIngester, analyzer GOLD chunking, planner context, API endpoint) |
| `test_citation_chain_integration.py` | Citation chain of custody API (12 tests: A-B-C-D chain logic, summary, tier breakdowns, API endpoints) |
| `test_checkpoint_rewind.py` | Checkpoint rewind/resume (22 tests: state summary extraction, list/get/rewind logic, state patching, auto-resume, API disabled endpoints, serialization, thread ID) |
| `test_mind_map_integration.py` | Mind map ASGI endpoint (19 tests: real httpx.ASGITransport, center/sections/findings/sources/edges/stats, cross-cutting, caps, edge cases, 404) — Session 29 REWRITE |
| `test_memory_search_integration.py` | LTM memory lifecycle (25 tests: promote with quality gates, stats, semantic search, pagination, deletion, full lifecycle, disk persistence with PersistentClient) — Session 29 expanded |
| `test_override_feedback_loop.py` | Human override feedback loop (17 tests: store/query/inject cycle, cross-vector semantic search, node filtering, planner prompt injection) |
| `test_campaign_persistence.py` | Campaign SQLite persistence (15 tests: CRUD, re-init persistence, concurrent creates, unicode, lifecycle) — Session 28 |
| `test_ltm_priors_injection.py` | LTM priors injection (22 tests: real ChromaDB embeddings, promote/query LTM, human overrides, planner prompt injection, relevance ordering, truncation caps) — Session 28 |
| `test_concurrency_cap.py` | Concurrency cap enforcement (15 tests: real asyncio.Semaphore, peak concurrent count, singleton, exception/timeout release, retry_with_backoff) — Session 28 |
| `test_docx_export.py` | DOCX export validation (19 tests: real python-docx generation/reading, title/TOC/body/bibliography/quality/audit certificate, large reports, special chars) — Session 28 |
| `test_pipeline_crud.py` | Pipeline CRUD API (22 tests: real ASGI endpoints, Pydantic validation, YAML templates, cycle detection, topological sort, round-trip) — Session 28 |
| `test_wizard_flow.py` | Pipeline wizard flow (15 tests: real PipelineWizard heuristic engine, 6-stage progression, keyword-based generation, concurrent sessions, API round-trip) — Session 28 |
| `test_performance_sla.py` | Performance SLA validation (13 tests: API <500ms, dashboard <2s, LTM <500ms, batch burst, health/templates/memory/system/history/status/snapshot/pipelines/campaigns/documents) — Session 29 |

---

## 12. docs/ -- Documentation

| File | Lines | Purpose |
|------|-------|---------|
| `todo_list.md` | ~447 | Active project definition (APD) -- 174-item prioritized task backlog |
| `file_directory.md` | ~610 | This file -- comprehensive file inventory |
| `ui_ux_design_prompt.md` | 1177 | UI/UX design brief for all 9 dashboard screens (Amendment A6). Standalone prompt for Figma-ready wireframe generation. Covers: design system, color palette, typography, 9 screen specs, interaction patterns, responsive behavior, component library. |
| `deployment_guide.md` | 1059 | Cloud, sovereign, air-gapped deployment guide with hardware specs and troubleshooting |
| `architecture_diagram.md` | 603 | System architecture diagrams: pipeline, data flow, security model, memory architecture |
| `landing_page.html` | 1879 | Static marketing landing page: hero, pipeline viz, comparison, pricing, demo form |
| `pitch_deck.md` | 271 | 10-slide pitch deck: problem, solution, moats, market, pricing, GTM, ask |
| `pitch_deck.html` | 335 | HTML presentation version: 10 slides, keyboard nav, responsive, print-ready |
| `feature_comparison.md` | 154 | 56-feature comparison: POLARIS vs Perplexity vs ChatGPT vs Gemini vs Claude |
| `benchmark_questions.md` | 304 | 10-question benchmark suite with scoring rubrics and evaluation protocol |
| `case_study_template.md` | ~200 | Reusable case study template: profile, challenge, solution, results, ROI |
| `partner_enablement.md` | ~200 | Partner program kit: overview, pricing/revenue share, technical requirements, differentiation, implementation timeline, sales playbook, demo script |

### docs/compliance_templates/ -- Compliance Export Templates (Session 10)

| File | Lines | Purpose |
|------|-------|---------|
| `eu_ai_act_article_11.md` | 317 | EU AI Act Article 11 conformity: risk classification, data governance, transparency |
| `soc2_evidence_mapping.md` | 196 | SOC 2 Type II: all 5 Trust Service Criteria mapped to POLARIS controls |
| `hipaa_audit_trail.md` | 320 | HIPAA Security Rule: access, audit, integrity, transmission safeguards |
| `fedramp_documentation.md` | 319 | FedRAMP: 17 control families, continuous monitoring, incident response |

### docs/compliance/ -- Additional Compliance Templates (Session 10)

| File | Lines | Purpose |
|------|-------|---------|
| `eu_ai_act_template.md` | 311 | EU AI Act with model inventory and conformity assessment |
| `soc2_evidence_map.md` | 186 | SOC 2 with evidence collection schedule and auditor guidance |
| `hipaa_audit_trail.md` | 414 | HIPAA with PHI detection controls and sovereign deployment advantages |

---

## 13. state/ -- State Persistence

| File/Dir | Purpose |
|----------|---------|
| `restart_instructions.md` | Resume instructions for session recovery |
| `cost_ledger.json` | API cost tracking |
| `pg_batch_progress.sqlite` | Batch progress tracking (SQLite) |
| `pg_checkpoints.sqlite` | Pipeline checkpoints (SQLite) |
| `pg_content_cache.sqlite` | Content cache (SQLite) |
| `pg_evidence_hierarchy.sqlite` | Evidence hierarchy cache (SQLite) |
| `pg_search_cache.sqlite` | Search cache (SQLite) |
| `pg_session_feedback.sqlite` | Session feedback cache (SQLite) |
| `feedback_checkpoints/` | Feedback checkpoint JSONs (ckpt_0000-0002) |

---

## 14. logs/ -- Active Logs

| File | Purpose |
|------|---------|
| `session_log.md` | Chronological session audit trail (APD component) |
| `bug_log.md` | Bug and issue registry |
| `polaris_graph.log` | Persistent pipeline log (dual console+file) |
| `serper_diag.log` | Serper API diagnostic log |
| `pg_cost_ledger.jsonl` | JSONL cost ledger |
| `pg_trace_PG_TEST_040.jsonl` | PG_TEST_040 trace |
| `pg_trace_PG_TEST_041.jsonl` | PG_TEST_041 trace |
| `pg_trace_PG_TEST_042.jsonl` | PG_TEST_042 trace |
| `pg_trace_PG_TEST_043.jsonl` | PG_TEST_043 trace |
| `pg_trace_PG_TEST_044.jsonl` | PG_TEST_044 trace |
| `pg_trace_PG_TEST_045.jsonl` | PG_TEST_045 trace |
| `pg_trace_PG_TEST_046.jsonl` | PG_TEST_046 trace |
| `pg_trace_PG_TEST_046_MOST.jsonl` | PG_TEST_046 MoST trace |
| `pg_trace_PG_TEST_047.jsonl` | PG_TEST_047 trace |

---

## 15. outputs/ -- Pipeline Outputs

| Directory | Purpose |
|-----------|---------|
| `polaris_graph/` | Production pipeline outputs (PG_TEST_040 through PG_TEST_047 JSON + reports) |
| `polaris_graph/audit_047/` | PG_TEST_047 audit artifacts (claims, evidence, sections, bibliography, clusters, report, metadata) |
| `audit/` | Legacy audit results (audit_pack_v4_fix61, SOTA readiness JSONs) |
| `archive/` | Archived S1V1 outputs |

---

## 16. archive/ -- Archived Files

| Directory | Contents |
|-----------|----------|
| `cleanup_20260223/` | **Major cleanup**: 13 dead src dirs, 27 scripts, 14 docs, 8.5GB ckpts, logs, config, docker, monitoring, tests, state, outputs |
| `cleanup_20260221/` | Pre-cleanup: exports, logs, outputs, scripts, state |
| `cleanup_20260129_sota_validation/` | Post-SOTA validation cleanup |
| `docs_historical_20260127/` | 14 historical docs |
| `ground_rules_original.txt` | Original ground rules |
| `logs_historical_20260127/` | Historical logs (Jan 27) |
| `logs_historical_20260131/` | Historical logs (Jan 27-28) |
| `POLARIS_APEX/` | Legacy v1 codebase |
| `state_history_20260131/` | Old test/validation run state |

### cleanup_20260223 Detail

| Subdirectory | What Was Archived |
|--------------|-------------------|
| `src_dead/` | 13 dead directories: api, budget, callbacks, cli, depth, evaluation, feedback, formatters, functions, graph, monitoring, reasoning, storage |
| `scripts/` | 27 legacy scripts: ablation, clean, diagnostics, resume, validation, evaluation scripts |
| `docs/` | 14 stale docs: benchmark_analysis, competitor_analysis, deployment plan, gemini audit, how_we_work, memory plan, runbook, SOTA reports, etc. |
| `ckpts_duplicate/` | 8.5GB duplicate model checkpoints (MiniCheck-Flan-T5-Large) |
| `chroma_db_legacy/` | Legacy ChromaDB SQLite database |
| `logs/` | 90+ historical run logs (s1v1, s1v6, s1v7, s1v9, run10-18, pg_test_016-039, snowball, etc.) |
| `config/` | Old thresholds.yaml |
| `docker/` | Dockerfile, docker-compose.yml |
| `monitoring/` | prometheus.yml |
| `tests/` | conftest.py, test_phases.py |
| `state/` | Old last_pointer.json, v3 state directory |
| `outputs/` | Empty (output dirs were already clean) |
| `root/` | Empty |

---

## 17. helm/polaris/ -- Kubernetes Helm Chart (Session 10)

| File | Purpose |
|------|---------|
| `Chart.yaml` | Helm chart metadata (name, version, description) |
| `values.yaml` | Default values: replicas, image, resources, ports, env vars, sovereign mode |
| `templates/_helpers.tpl` | Template helpers (labels, selector labels, fullname) |
| `templates/deployment.yaml` | Kubernetes Deployment: pod spec, volumes, health checks, resource limits |
| `templates/service.yaml` | Kubernetes Service: ClusterIP, port mapping |
| `templates/pvc.yaml` | PersistentVolumeClaim: output and model storage |
| `templates/ingress.yaml` | Optional Ingress: host routing, TLS |

---

## Other Directories

| Directory | Purpose |
|-----------|---------|
| `models/minicheck/` | MiniCheck-RoBERTa-Large model weights (HuggingFace cache) |
| `data/benchmarks/` | HLE dataset cache (`hle_dataset_cache.json`) |

---

## Naming Convention Compliance

Per CLAUDE.md LAW V:
- **All Python files**: snake_case (COMPLIANT)
- **All directories**: snake_case (COMPLIANT)
- **Generated artifacts**: UPPERCASE allowed (state files, test output JSONs)
- **Root docs**: PascalCase allowed (CLAUDE.md, README.md)
