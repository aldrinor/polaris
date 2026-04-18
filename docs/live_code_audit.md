# Live-code audit — 2026-04-18

Static import-closure analysis from 250 entry points (orchestrators + preflight + tests). Produced by `scripts/audit_live_code.py`.

- Total `.py` files under `src/` + `scripts/`: **463**
- Reachable from entry points (LIVE): **301**
- Not reachable (ORPHAN candidates): **162**
- Dynamic imports detected: **2** (listed in appendix — may make orphans live)

## Orphan candidates by subpackage

Files below are NOT reachable from any entry point via static import analysis. They may still be used via dynamic imports (see appendix) or as standalone scripts. Archive only after human review.

### `scripts/` — 61 orphan file(s)

| File | Size | Last commit | First docstring line |
|------|------|-------------|----------------------|
| `scripts/_lb_dump_claims.py` | 2K | never | Dump all claims from both pending requests for manual review. |
| `scripts/_lb_honest_audit.py` | 2K | never | Post-hoc honest audit of PG_LB_SA_02 VerificationBatch B (already consumed). |
| `scripts/_lb_process_pg_lb_sa_02.py` | 10K | never | Process PG_LB_SA_02 VerificationBatch B requests honestly. |
| `scripts/_lb_resp_14d24de92814.py` | 18K | never | One-shot script to produce loopback response resp_14d24de92814.json. |
| `scripts/_serve_batch_sources.py` | 10K | 2026-04-16 | Helper: write 7 SourceAnalysisBatch responses in one shot. |
| `scripts/_serve_batch_sources2.py` | 5K | 2026-04-16 | Round 2: 4 more SourceAnalysisBatch responses. |
| `scripts/_write_resp_ee70166cd34d.py` | 17K | never | One-shot writer for loopback response resp_ee70166cd34d.json (PG_LB_SA_02 round 4). |
| `scripts/_write_storm_r2.py` | 11K | never | Atomic writer for two StormAnswer R2 responses (Lindqvist + Adeyemi). |
| `scripts/apply_auth_history_patch.py` | 4K | 2026-03-16 | Insert the /api/auth/history endpoint into live_server.py. |
| `scripts/audit_layer0_provenance.py` | 0K | never | Layer 0: Ground truth provenance map. |
| `scripts/audit_layer1_contamination.py` | 4K | never | Layer 1: Operator contamination audit. |
| `scripts/check_trace_cost.py` | 1K | 2026-03-16 | Quick trace file cost analyzer. |
| `scripts/debug_api_check.py` | 0K | 2026-03-16 | Check if source-preview API works with the evidence IDs from result API. |
| `scripts/debug_citations_visible.py` | 2K | 2026-03-16 | Check if citations are visible after hydration fix. |
| `scripts/debug_consistency.py` | 1K | 2026-03-16 | Run 3 independent page loads to test consistency. |
| `scripts/debug_console_trace.py` | 1K | 2026-03-16 | Trace console messages during hydration to see post-hydration path. |
| `scripts/debug_endtime.py` | 1K | 2026-03-16 | Check state.endTime and feed timestamps at render time. |
| `scripts/debug_enhanced_popover.py` | 2K | 2026-03-16 | Test enhanced popover with quote + source context. |
| `scripts/debug_final_visual.py` | 2K | 2026-03-16 | Final visual verification: fresh load + citations + popover. |
| `scripts/debug_fresh_load.py` | 4K | 2026-03-16 | Debug fresh page load - why are citations empty? |
| `scripts/debug_full_visual.py` | 2K | 2026-03-16 | Full visual verification: fresh page load + citations + popover. |
| `scripts/debug_full_visual2.py` | 2K | 2026-03-16 | Full visual verification with cache bypass. |
| `scripts/debug_google_style.py` | 1K | 2026-03-16 | Test Google-style popover: real article HTML with highlighted citations. |
| `scripts/debug_hydration.py` | 6K | 2026-03-16 | Debug script: check hydration state and take screenshots. |
| `scripts/debug_hydration_check.py` | 2K | 2026-03-16 | Check hydration state after server restart. |
| `scripts/debug_hydration_deep.py` | 1K | 2026-03-16 | Deep debug: check hydration sequence and state at each stage. |
| `scripts/debug_multi_quote.py` | 2K | 2026-03-16 | Test multi-quote popover - shows all verified excerpts from source. |
| `scripts/debug_multi_quote2.py` | 3K | 2026-03-16 | Test multi-quote popover with proper timing and error capture. |
| `scripts/debug_phase_trace.py` | 2K | 2026-03-16 | Trace all setWorkspacePhase calls to find what resets it to idle. |
| `scripts/debug_phase_trace2.py` | 2K | 2026-03-16 | Trace setWorkspacePhase calls to find what's overriding report. |
| `scripts/debug_popover.py` | 4K | 2026-03-16 | Verify popover enrichment: bibliography entries should have evidence_ids + quotes after hydration. |
| `scripts/debug_popover2.py` | 1K | 2026-03-16 | Debug why bibliography is empty after hydration. |
| `scripts/debug_popover_errors.py` | 2K | 2026-03-16 | Check for JS errors when popover loads. |
| `scripts/debug_popover_final.py` | 6K | 2026-03-16 | Final visual popover verification - captures screenshots of popovers. |
| `scripts/debug_popover_hover.py` | 2K | 2026-03-16 | Test popovers by hovering multiple citation cards. |
| `scripts/debug_popover_more.py` | 2K | 2026-03-16 | Test more popovers - cards 5, 7, 10 for thorough coverage. |
| `scripts/debug_popover_multi.py` | 3K | 2026-03-16 | Test popovers on multiple citation cards to assess content quality. |
| `scripts/debug_popover_test.py` | 4K | 2026-03-16 | Test popover shows real content, not 'No cached content available'. |
| `scripts/debug_popover_trigger.py` | 4K | 2026-03-16 | Debug popover trigger mechanism. |
| `scripts/debug_popover_visual.py` | 7K | 2026-03-16 | Visually verify popover content after quote_text preference fix. |
| `scripts/debug_single_multi.py` | 1K | 2026-03-16 | Test both single-evidence and multi-evidence cards. |
| `scripts/debug_snapshot_api.py` | 1K | 2026-03-16 | Check what the snapshot and research status APIs return. |
| `scripts/debug_timing.py` | 1K | 2026-03-16 | Check timing of snapshot load and state changes. |
| `scripts/loopback_fix_all_quotes.py` | 20K | never | Fix all quotes below 400 chars by extending with source-adjacent context. |
| `scripts/loopback_serve_batch.py` | 55K | never | Serve 8 SourceAnalysisBatch loopback requests for POLARIS. |
| `scripts/pg_chain_validation.py` | 7K | never | Full chain validation: Evidence → Wiki → Citation Integrity → Compose Capacity. |
| `scripts/pg_micro_test_071_fixes.py` | 14K | 2026-03-27 | Tests for all 4 FIX-071 changes before TEST_072. |
| `scripts/pg_micro_test_deepener.py` | 19K | 2026-03-28 | Micro tests for evidence deepener module. |
| `scripts/pg_micro_test_deepener_e2e.py` | 15K | 2026-03-28 | End-to-end integration test for evidence deepener. |
| `scripts/pg_micro_test_edge_v2.py` | 15K | 2026-03-25 | Comprehensive edge case tests for all fixes. |
| `scripts/pg_micro_test_final.py` | 17K | 2026-03-26 | Final comprehensive mini test: Verify ALL issues found in TEST_063->TEST_067 |
| `scripts/pg_micro_test_gaps.py` | 14K | 2026-03-26 | Micro tests for Gap 1/2/4/Reasoning fixes before TEST_069. |
| `scripts/pg_micro_test_polish.py` | 14K | 2026-03-26 | Micro tests for polish pass, academic gate, and GRADE standardization. |
| `scripts/pg_micro_test_polish_scale.py` | 9K | 2026-03-26 | Scale tests: Polish pass on real 14K-word report + interaction with post-processing. |
| `scripts/pg_micro_test_risks.py` | 12K | 2026-03-25 | Risk tests: Verify 4 remaining uncertainties before TEST_068. |
| `scripts/pg_stress_test_wiki.py` | 10K | 2026-04-09 | Structural stress test: 300 evidence from 80 academic sources through wiki pipeline. |
| `scripts/test_right_panel.py` | 7K | 2026-03-16 | Playwright visual test: right panel in idle, running (simulated), and report states. |
| `scripts/test_right_panel_debug.py` | 2K | 2026-03-16 | Debug test: capture console errors and dark theme state. |
| `scripts/test_word_cap.py` | 5K | 2026-04-07 | Serious test of post-continuation word cap fix. |
| `scripts/write_missing_responses.py` | 8K | never | Write the two missing response files with explicit fsync. |
| `scripts/write_section2_response.py` | 9K | never | Write section 2 response and move request to done. |

### `src/agents/` — 9 orphan file(s)

| File | Size | Last commit | First docstring line |
|------|------|-------------|----------------------|
| `src/agents/__init__.py` | 1K | 2026-03-16 | POLARIS v3 Agents Module (Legacy) |
| `src/agents/citefirst/__init__.py` | 0K | 2026-03-16 | POLARIS Cite-First Synthesizer Package (FIX-223) |
| `src/agents/citefirst/claim_processing.py` | 0K | 2026-03-16 | FIX-223 Stub: Claim Processing Module |
| `src/agents/citefirst/evidence_clustering.py` | 0K | 2026-03-16 | FIX-223 Stub: Evidence Clustering Module |
| `src/agents/citefirst/prose_generation.py` | 0K | 2026-03-16 | FIX-223 Stub: Prose Generation Module |
| `src/agents/citefirst/report_composition.py` | 0K | 2026-03-16 | FIX-223 Stub: Report Composition Module |
| `src/agents/citefirst/revision_loop.py` | 0K | 2026-03-16 | FIX-223 Stub: Revision Loop Module |
| `src/agents/citefirst/synthesizer.py` | 0K | 2026-03-16 | POLARIS Cite-First Synthesizer - Main Module (FIX-223) |
| `src/agents/clarification_agent.py` | 17K | 2026-03-16 | POLARIS v3 Clarification Agent |

### `src/audit/` — 7 orphan file(s)

| File | Size | Last commit | First docstring line |
|------|------|-------------|----------------------|
| `src/audit/__init__.py` | 5K | 2026-03-16 | POLARIS Audit Module - Complete Quality Assurance |
| `src/audit/archive/deep_audit.py` | 35K | never | POLARIS Deep Audit System |
| `src/audit/archive/lightweight_audit.py` | 15K | never | Lightweight SOTA Audit System |
| `src/audit/archive/phase_hooks.py` | 10K | never | POLARIS Phase Audit Hooks |
| `src/audit/benchmark_audit.py` | 23K | 2026-03-16 | POLARIS SOTA Benchmark Audit System |
| `src/audit/collector.py` | 102K | 2026-03-16 | POLARIS Audit Collector - Complete Pipeline Quality Assurance |
| `src/audit/runner_audit.py` | 28K | 2026-03-16 | Runner Audit System - Comprehensive Pipeline Quality Assessment |

### `src/auth/` — 1 orphan file(s)

| File | Size | Last commit | First docstring line |
|------|------|-------------|----------------------|
| `src/auth/__init__.py` | 0K | 2026-03-16 | POLARIS Authentication and Authorization. |

### `src/benchmarks/` — 7 orphan file(s)

| File | Size | Last commit | First docstring line |
|------|------|-------------|----------------------|
| `src/benchmarks/__init__.py` | 1K | 2026-03-16 |  |
| `src/benchmarks/auditor_strict.py` | 15K | 2026-03-16 | POLARIS SOTA Validation Framework - Strict Auditor |
| `src/benchmarks/hle_benchmark.py` | 36K | 2026-03-16 | HLE (Humanity's Last Exam) Benchmark Runner for POLARIS |
| `src/benchmarks/hle_dataset.py` | 18K | 2026-03-16 | HLE (Humanity's Last Exam) Dataset Handler |
| `src/benchmarks/metrics_strict.py` | 18K | 2026-03-16 | POLARIS SOTA Validation Framework - Strict Metrics |
| `src/benchmarks/report_generator.py` | 14K | 2026-03-16 | POLARIS SOTA Validation Framework - Report Generator |
| `src/benchmarks/stats_analysis.py` | 16K | 2026-03-16 | POLARIS SOTA Validation Framework - Statistical Analysis |

### `src/llm/` — 3 orphan file(s)

| File | Size | Last commit | First docstring line |
|------|------|-------------|----------------------|
| `src/llm/__init__.py` | 1K | 2026-03-16 | POLARIS LLM Clients |
| `src/llm/deberta_client.py` | 7K | 2026-03-16 | POLARIS DeBERTa NLI Client |
| `src/llm/factory.py` | 6K | 2026-03-16 | POLARIS LLM Factory |

### `src/memory/` — 1 orphan file(s)

| File | Size | Last commit | First docstring line |
|------|------|-------------|----------------------|
| `src/memory/__init__.py` | 0K | 2026-03-16 |  |

### `src/orchestration/` — 1 orphan file(s)

| File | Size | Last commit | First docstring line |
|------|------|-------------|----------------------|
| `src/orchestration/__init__.py` | 2K | 2026-03-16 | POLARIS v3 Orchestration Module |

### `src/polaris_graph/` — 22 orphan file(s)

| File | Size | Last commit | First docstring line |
|------|------|-------------|----------------------|
| `src/polaris_graph/__init__.py` | 1K | 2026-03-17 | polaris graph — clean-room research pipeline. |
| `src/polaris_graph/agents/__init__.py` | 0K | 2026-03-16 | Agent nodes for polaris graph LangGraph workflow. |
| `src/polaris_graph/batch_progress.py` | 3K | 2026-03-16 | FIX-V10: Mid-node batch progress persistence. |
| `src/polaris_graph/dynamic_graph.py` | 15K | 2026-03-16 | Dynamic graph builder — creates LangGraph StateGraph from PipelineDefinition. |
| `src/polaris_graph/evaluator/__init__.py` | 0K | 2026-04-18 | POLARIS honest-rebuild external evaluator package (Phase 5). |
| `src/polaris_graph/export/__init__.py` | 0K | 2026-03-16 | Export package for polaris graph research reports. |
| `src/polaris_graph/generator/__init__.py` | 0K | 2026-04-18 | POLARIS honest-rebuild generator package (Phase 4). |
| `src/polaris_graph/llm/__init__.py` | 0K | 2026-03-17 | LLM client for polaris graph — OpenRouter gateway to Qwen 3.5 Plus. |
| `src/polaris_graph/memory/__init__.py` | 0K | 2026-03-16 | Memory system for polaris graph pipeline. |
| `src/polaris_graph/nodes/__init__.py` | 0K | 2026-03-17 | v3 pipeline nodes — one module per phase. |
| `src/polaris_graph/nodes/search.py` | 16K | 2026-03-17 | Phase 2: SEARCH — Sub-question-targeted search with convergence detection. |
| `src/polaris_graph/retrieval/__init__.py` | 2K | 2026-03-17 | CRAG Retrieval Pipeline (v2 Layer 1). |
| `src/polaris_graph/retrieval/fetch_limiter.py` | 5K | 2026-03-17 | Rate-Limited Fetch Helper (Fix R4-#4). |
| `src/polaris_graph/verify_subgraph.py` | 4K | 2026-03-16 | ARCH-2: Subgraph decomposition for verification with per-batch checkpointing. |
| `src/polaris_graph/wiki/mesh/api/__init__.py` | 0K | 2026-04-12 | Mesh REST API package. |
| `src/polaris_graph/wiki/mesh/api/server.py` | 8K | 2026-04-12 | Mesh REST API — FastAPI server exposing mesh operations. |
| `src/polaris_graph/wiki/mesh/cli/__init__.py` | 0K | 2026-04-12 | Mesh CLI package — thin presentation layer over mesh operations. |
| `src/polaris_graph/wiki/mesh/cli/main.py` | 11K | 2026-04-12 | Mesh CLI — thin presentation layer over mesh operations. |
| `src/polaris_graph/wiki/mesh/compose/__init__.py` | 0K | 2026-04-11 | Mesh compose package — answer composition + artifact rendering. |
| `src/polaris_graph/wiki/mesh/qa/__init__.py` | 0K | 2026-04-11 | Mesh Q&A package — ask orchestration + thread management. |
| `src/polaris_graph/wiki/mesh/retrieve/__init__.py` | 0K | 2026-04-11 | Mesh retrieval package — lethal retrieval + gap classification. |
| `src/polaris_graph/wiki/mesh/snapshot.py` | 3K | 2026-04-12 | Mesh snapshot — zstd-compressed database backup and restore. |

### `src/providers/` — 3 orphan file(s)

| File | Size | Last commit | First docstring line |
|------|------|-------------|----------------------|
| `src/providers/__init__.py` | 0K | 2026-03-16 | POLARIS Provider Abstraction — Swap between cloud and sovereign deployments. |
| `src/providers/deployment_validator.py` | 5K | 2026-03-16 | POLARIS Deployment Validator — Validates deployment mode configuration. |
| `src/providers/search_provider.py` | 4K | 2026-03-16 | Search Provider Abstraction — Cloud APIs (Serper/Exa/Tavily) or SearxNG (sovereign). |

### `src/schemas/` — 7 orphan file(s)

| File | Size | Last commit | First docstring line |
|------|------|-------------|----------------------|
| `src/schemas/__init__.py` | 1K | 2026-03-16 | POLARIS Schemas - The Law |
| `src/schemas/api_query.py` | 15K | 2026-03-16 | POLARIS API Query Schemas - SOTA Multi-Source Retrieval |
| `src/schemas/decomposed_query.py` | 11K | 2026-03-16 | POLARIS Decomposed Query Schema |
| `src/schemas/extracted_facts.py` | 17K | 2026-03-16 | POLARIS Extracted Facts Schema |
| `src/schemas/phase_models.py` | 32K | 2026-03-16 | POLARIS Phase Models - The Law |
| `src/schemas/question_types.py` | 17K | 2026-03-16 | POLARIS Question Type Classification Schema |
| `src/schemas/validation_criteria.py` | 17K | 2026-03-16 | POLARIS Validation Criteria Schema |

### `src/search/` — 3 orphan file(s)

| File | Size | Last commit | First docstring line |
|------|------|-------------|----------------------|
| `src/search/__init__.py` | 1K | 2026-03-16 | POLARIS Search Module |
| `src/search/engines.py` | 23K | 2026-03-16 | POLARIS Search Engines |
| `src/search/fan_out_executor.py` | 13K | 2026-03-16 | POLARIS Fan-Out Search Executor |

### `src/state/` — 4 orphan file(s)

| File | Size | Last commit | First docstring line |
|------|------|-------------|----------------------|
| `src/state/__init__.py` | 0K | never | POLARIS State Management |
| `src/state/ledger.py` | 12K | never | POLARIS Progress Ledger |
| `src/state/orchestration.py` | 52K | never | POLARIS Orchestration Layer |
| `src/state/session.py` | 21K | never | POLARIS Session Management |

### `src/tools/` — 9 orphan file(s)

| File | Size | Last commit | First docstring line |
|------|------|-------------|----------------------|
| `src/tools/agent_swarm_full.py` | 10K | 2026-03-16 | Full-Scale Agent Swarm (KIMI K2.5 Parity) |
| `src/tools/browser_automation.py` | 8K | 2026-03-16 | Browser Automation with JavaScript Rendering |
| `src/tools/file_analyzer.py` | 21K | 2026-03-16 | File Upload Analysis (OpenAI Parity) |
| `src/tools/long_form_generator.py` | 23K | 2026-03-16 | Long-Form Generation (KIMI K2.5 Parity) |
| `src/tools/pdf_parser.py` | 17K | 2026-03-16 | POLARIS v3 PDF Parser Tool |
| `src/tools/streaming_reasoner.py` | 7K | 2026-03-16 | Streaming Reasoning Tokens (OpenAI Parity) |
| `src/tools/user_feedback.py` | 10K | 2026-03-16 | User Feedback Loop (OpenAI Parity) |
| `src/tools/vision_processor.py` | 10K | 2026-03-16 | MoonViT-Style Vision Processor |
| `src/tools/vision_tool.py` | 20K | 2026-03-16 | POLARIS v3 Vision Tool |

### `src/utils/` — 24 orphan file(s)

| File | Size | Last commit | First docstring line |
|------|------|-------------|----------------------|
| `src/utils/academic_fetcher.py` | 21K | 2026-03-16 | POLARIS Academic Paper Fetcher |
| `src/utils/academic_orchestrator.py` | 22K | 2026-03-16 | POLARIS Academic Source Orchestrator |
| `src/utils/circuit_breaker.py` | 13K | 2026-03-16 | POLARIS Circuit Breaker |
| `src/utils/citation_chainer.py` | 21K | 2026-03-16 | Citation Chainer for POLARIS SOTA Retrieval. |
| `src/utils/claim_decomposer.py` | 18K | 2026-03-16 | POLARIS Claim Decomposer |
| `src/utils/crossref_client.py` | 17K | 2026-03-16 | CrossRef API Client for POLARIS SOTA Metadata Retrieval. |
| `src/utils/evaluation.py` | 23K | 2026-03-16 | POLARIS Evaluation Module (SOTA: FactScore + G-Eval) |
| `src/utils/fact_extractor.py` | 16K | 2026-03-16 | POLARIS Fact Extractor |
| `src/utils/geographic_tagger.py` | 17K | 2026-03-16 | POLARIS Geographic Tagger Module |
| `src/utils/hybrid_retrieval.py` | 16K | 2026-03-16 | POLARIS Hybrid Retrieval Module |
| `src/utils/logging_config.py` | 8K | 2026-03-16 | POLARIS v3 Logging Configuration |
| `src/utils/openalex_client.py` | 21K | 2026-03-16 | OpenAlex API Client for POLARIS SOTA Retrieval. |
| `src/utils/quality_metrics.py` | 11K | 2026-03-16 | POLARIS Quality Metrics Tracker |
| `src/utils/question_classifier.py` | 14K | 2026-03-16 | POLARIS Question Classifier Utility |
| `src/utils/ragas_evaluator.py` | 24K | 2026-03-16 | RAGAS-Style Evaluation Metrics for POLARIS. |
| `src/utils/result_cache.py` | 9K | 2026-03-16 | POLARIS Result Cache |
| `src/utils/safe_verifier.py` | 20K | 2026-03-16 | POLARIS SAFE (Search-Augmented Factual Evaluation) Verification Module |
| `src/utils/self_refinement.py` | 20K | 2026-03-16 | POLARIS Self-Refinement Critique Loop |
| `src/utils/semantic_chunking.py` | 16K | 2026-03-16 | POLARIS Semantic Chunking |
| `src/utils/semantic_scholar_client.py` | 23K | 2026-03-16 | Semantic Scholar API Client for POLARIS SOTA Retrieval. |
| `src/utils/source_quality.py` | 25K | 2026-03-16 | POLARIS Source Quality Scorer (SOTA: PaperQA2 RCS Map) |
| `src/utils/source_router.py` | 13K | 2026-03-16 | POLARIS Source Router and RRF Fusion |
| `src/utils/unpaywall_client.py` | 15K | 2026-03-16 | Unpaywall API Client for POLARIS Open Access PDF Retrieval. |
| `src/utils/url_blacklist.py` | 13K | 2026-03-16 | POLARIS URL Blacklist Module |

## Entry points used

- `scripts/anti_tunnel_view_test.py`
- `scripts/apply_dashboard_patches.py`
- `scripts/audit_brief.py`
- `scripts/audit_build_index.py`
- `scripts/audit_dashboard_rewrite.py`
- `scripts/audit_dashboard_visual.py`
- `scripts/audit_live_code.py`
- `scripts/audit_v3_report.py`
- `scripts/build_walkthrough_pdf.py`
- `scripts/codex_loop_parse.py`
- ... plus 240 test files under `tests/`

## Dynamic imports appendix

- `threading`
- `x`