# POLARIS Substrate Audit — what's actually built (2026-05-01)

**Purpose:** Stop planning as if greenfield. Map what's already built so the plan is "expose + fix + add what's missing" not "build from scratch."

## Headline numbers

- **270 Python files** in `src/`
- **134 scripts** in `scripts/`
- **47 audit_ir modules** (the V30 substrate)
- **123 HTTP routes** total (69 in `live_server.py` + 54 in `inspector_router.py`)
- **2 frontend templates** (`live_dashboard.html` 938 lines, `inspector_shell.html` 101 lines)
- **113 milestones marked complete**

## Existing substrate by capability

### Memory — built, partly UI-exposed
- `src/polaris_graph/memory/`: campaign_store, content_cache, cross_vector, evidence_hierarchy, **local_document_rag**, search_cache, session_feedback, source_content_store
- `src/memory/chroma_client.py` — ChromaDB client (initialized at server startup)
- `/api/memory/stats`, `/api/memory/search`, `/api/memory/items`, `DELETE /api/memory/items/{item_id}` — exposed
- M-21 "Retrieval-active workspace memory" — completed
- "Memory" nav button exists in dashboard
- **Missing in UI**: per-org shared memory view, memory as searchable corpus with previews, cross-session continuity surfacing

### Document upload + private corpus — built, no UI
- `src/polaris_graph/document_ingester.py`
- `src/polaris_graph/audit_ir/private_corpus_sync.py`
- `src/polaris_graph/audit_ir/workspace_store.py`
- `/api/documents/upload`, `/api/documents/parse`, `/api/documents/brief`, `/api/documents/list`, `/api/documents/{doc_id}`
- `/api/cloud/{provider}/authorize|callback|files|import|import-batch|disconnect`
- `/api/inspector/uploads/{upload_id}`, `/api/inspector/uploads/{upload_id}/chunks`
- `/api/inspector/private-corpus-sources` + `/{source_id}`
- M-11 "Bounded upload + workspace data model" — completed
- M-25 "Narrow private-corpus sync" — completed
- M-INT-10 "Drive connector v2 (narrow)" — completed
- **Missing in UI**: drag-and-drop upload zone, upload progress, doc preview after parse, doc-as-evidence in active query

### Knowledge snowballing / citation chasing — built
- `src/polaris_graph/agents/evidence_deepener.py` — the snowball orchestrator
- `src/polaris_graph/retrieval/primary_trial_expander.py`, `regulatory_expander.py`, `citation_normalizer.py`
- `src/polaris_graph/synthesis/cross_section_reflector.py`
- `src/polaris_graph/agents/cross_reference.py`
- `src/polaris_graph/agents/storm_interviews.py` (STORM-style multi-perspective expansion)
- `evidence_deepening_architecture.md` memory — explicit decision to build the deepening loop (named study extraction → S2 citation chasing → S2 recommendations → mechanism keyword search → PDF full-text fetch → re-analyze + merge)
- M-D8 "parallel retrieval substrate" — completed
- M-INT-1 "Parallel fetch into live_retriever" — completed
- **Missing in UI**: visualize the snowball as a graph, surface "new sources discovered via citation chasing," let user trigger more depth

### Citation system — built
- `src/polaris_graph/audit_ir/citation_health.py` — health checks
- `src/polaris_graph/audit_ir/freshness_monitor.py` + `freshness_aggregates.py` — freshness/retraction watch
- `src/polaris_graph/retrieval/citation_normalizer.py` — DOI/PMID normalization
- `src/polaris_graph/synthesis/citation_mapper.py` — span-to-claim mapping
- `src/polaris_graph/agents/citation_agent.py`
- M-17 "Citation health checks" + M-18 "Regression alerts" + M-D10 "Citation freshness monitoring" — all completed
- `/api/inspector/runs/{slug}/health` — exposed
- **Missing in UI**: hover-tooltip with quote, citation graph navigation, citation-style switcher (APA/Vancouver/Chicago), retraction alerts visible inline

### Generator + synthesis — built and rich
- 12 generator modules: `multi_section_generator`, `live_deepseek_generator`, `slot_fill`, `slot_validator`, `contract_section_runner`, `contradiction_hedging`, `cross_jurisdiction_synthesizer`, `cross_trial_synthesis`, `frame_manifest`, `provenance_generator`, `regulatory_synthesizer`
- 17 synthesis modules: `report_assembler`, `report_assembler_v2`, `synthesizer_v2`, `verifier_v2`, `section_writer`, `section_utils`, `evidence_explorer`, `evidence_router`, `peptide_flow`, `disulfide_bridge` (creative names but real code), `covalent_binder`, `ionic_rebalancer`, `citation_mapper`, `cross_section_reflector`, **`smart_art_generator`** (← chart generator!), `token_budget`, `token_accounting`
- M-69 (citation bindings repair), M-70 (regulatory_synthesizer), M-71 (contradiction-aware hedging), M-72 (cross-trial synthesis) — all completed
- **Missing in UI**: surface the multi-section structure visibly, contradiction-hedging language called out, cross-jurisdiction comparison view

### Tools / Python execution — built
- `src/polaris_graph/tools/code_executor.py` — Python sandbox
- `src/polaris_graph/tools/data_analyzer.py`
- `src/polaris_graph/tools/analysis_notebook.py`
- `src/polaris_graph/tools/analysis_toolkit.py`
- `src/polaris_graph/tools/pdf_table_extractor.py`
- `src/polaris_graph/tools/evidence_database.py`
- `src/polaris_graph/tools/evidence_extractor.py`
- `src/polaris_graph/tools/openalex_client.py`
- `src/polaris_graph/tools/react_agent.py` — ReAct paradigm agent
- `src/polaris_graph/tools/package_installer.py` — runtime package install
- `src/polaris_graph/tools/tool_registry.py` — tool discovery
- `src/polaris_graph/synthesis/smart_art_generator.py` — visual generation
- **Missing in UI**: surface tool calls inline in report, render generated charts as Vega-Lite/PNG, tool-call audit trail

### Scope gate / refusal / disambiguation — built
- `src/polaris_graph/audit_ir/scope_classifier.py` + `scope_classifier_llm.py`
- `src/polaris_graph/retrieval/scope_query_validator.py`
- `src/polaris_graph/audit_ir/template_classifier.py`
- `src/polaris_graph/audit_ir/template_catalog.py`
- M-INT-4 "OpenRouter ScopeAffinityLLM in production" — completed
- M-INT-5 "Domain router into live retrieval flow" — completed
- M-D5 phase 2 "LLM-augmented ScopeEligibilityClassifier" — completed
- M-D6 phase 1 "cross-domain template substrate" — completed
- **Bug from BPEI**: scope gate accepts "What is BPEI?" by falling through to `domain=custom`. The substrate is built, the classifier is too permissive.
- **Missing**: ambiguity detector (cluster retrieval candidates by primary entity), refusal-with-explanation UI

### Job queue + SSE + checkpoints — built
- `src/polaris_graph/audit_ir/job_queue.py`, `job_runner.py`, `job_worker.py`
- `src/polaris_graph/audit_ir/progress_surfaces.py`
- `src/polaris_graph/checkpoint_manager.py`
- `/api/inspector/jobs`, `/jobs/{job_id}/cancel|pause|resume|stream|surfaces`
- `/api/research/checkpoints/{vector_id}`, `/api/research/checkpoint/{vector_id}/{checkpoint_id}`
- `/api/research/rewind/{vector_id}/{checkpoint_id}`
- M-8 "Job Queue infrastructure" + M-9 "V30 integration with job runner + checkpoints" + M-13 "Progressive in-run Inspector surfaces" — all completed
- **Missing in UI**: live progress consumer, queue depth visibility, checkpoint timeline visualization

### Audit bundle / export — built
- `src/polaris_graph/audit_ir/serializer.py`
- `src/polaris_graph/audit_ir/run_diff.py`
- `src/polaris_graph/audit_ir/slide_deck.py`
- `src/polaris_graph/audit_ir/parser_runner.py`
- `/api/inspector/runs/{slug}/audit-bundle.zip`, `/report.md`, `/health`, `/slide-deck`, `/slide-deck.html`
- `/api/inspector/runs/diff`, `/regression`
- M-16 "Audit bundle export + run diff" + M-22 "Cited slide deck export" — completed
- **Missing in UI**: download button, preview pane, comparison view for two runs side-by-side, slide-deck preview

### Operator review / human-in-loop — built
- `src/polaris_graph/audit_ir/review_store.py`
- `/api/inspector/reviews`, `/{review_id}`, `/claim|/decision|/diff|/transitions`
- M-23 "Human review queue + version diff" — completed
- **Missing in UI**: review queue page, claim-and-decide flow, diff visualization

### Dashboard / aggregates / observability — built
- `src/polaris_graph/audit_ir/decision_aggregates.py` + `freshness_aggregates.py` + `pin_trends.py`
- `src/polaris_graph/audit_ir/decision_telemetry.py`
- `src/polaris_graph/audit_ir/security_audit_log.py`
- `/api/inspector/dashboard/decision-aggregates|freshness-aggregates|pin-trends`
- `/api/inspector/metrics`
- M-LIVE-3 "Operator dashboard" + M-PROD-3 "Production observability" + M-D11 phase 2 v2 "trend analysis on pin replay" — completed
- **Missing in UI**: actual dashboard rendering these aggregates (currently API-only)

### Auth + RBAC + billing — built
- `src/polaris_graph/audit_ir/auth_middleware.py` + `auth_store.py`
- `src/polaris_graph/audit_ir/billing_quota_store.py`
- `src/auth/auth_manager.py` + `auth_routes.py` + `session_manager.py`
- `/api/auth/login|me|history|...` (7 routes)
- M-15a/b "Auth + RBAC" + M-NEW "Billing + quotas" + M-INT-7 "billing/quota gating in production" — completed
- **Missing in UI**: org switcher, role management, API key panel, billing/usage view

### Templates — built (3 active, scaling-stub)
- `template_catalog.py` — registry
- `template_classifier.py` — query routing
- `domain_router.py` — domain routing
- M-10 "Curated template router with confidence gating" + M-20 "Template router scaling 50-100 templates" — completed
- **Reality check**: only 3 templates active (`v30_clinical`, `v30_clinical_oncology`, `v30_clinical_cardio`). M-20 was scaffolding for scaling, not actual scaling. **Not 50 templates ready.**

### Pin replay / reproducibility / regression — built
- `src/polaris_graph/audit_ir/pin_replay.py` + `pin_trends.py` + `model_pin.py`
- `src/polaris_graph/audit_ir/regression_alerts.py` + `regression_lab.py`
- M-D11 phase 1 + 2 + 2-v2 + M-D9 + M-D9 phase 2 + M-LIVE-4 — all completed
- **Missing in UI**: pin replay UI, "what changed" diff, regression alerts inline

### Contract drafting / support tickets — built
- `src/polaris_graph/audit_ir/contract_draft_store.py`
- `src/polaris_graph/audit_ir/support_ticket_store.py`
- `/api/inspector/contract-drafts`, `/{draft_id}`
- `/api/inspector/support-tickets`, `/{ticket_id}`
- M-26 "Semi-automated contract drafting" + M-24 "Customer support flow" — completed
- **Missing in UI**: both API-only

### Cache / freshness — built
- `src/polaris_graph/audit_ir/cache_warming.py`, `retrieval_cache.py`
- M-D7 phase 1 + 2 "Aggressive caching layer + cache warming substrate" — completed
- M-D10 phase 1 + 2 "Citation freshness monitoring" — completed

### LangGraph variants — built (3 generations)
- `graph.py`, `graph_v2.py`, `graph_v3.py`, `graph_v4.py`
- `state.py`, `state_v3.py`
- `pipeline_definition.py`, `pipeline_wizard.py`
- The pipeline wizard was deferred but substrate exists

### Two-family evaluator — built
- `src/polaris_graph/llm/openrouter_client.py` (per CLAUDE.md, has `check_family_segregation`)
- `src/polaris_graph/evaluator/` (Qwen judge, external evaluator)
- Working invariant: generator + evaluator must be different lineages

### Audit IR loader — built
- `src/polaris_graph/audit_ir/loader.py`
- `src/polaris_graph/audit_ir/registry.py`
- M-1 "Audit Graph IR loader" — completed

### Provenance / verification — built (the core moat)
- `src/polaris_graph/audit_ir/provenance.py`
- `src/polaris_graph/agents/nli_verifier.py` + `hallucination_detector.py` + `verifier.py` + `source_confidence.py`
- `src/polaris_graph/synthesis/verifier_v2.py`
- strict_verify per CLAUDE.md §9.1 invariants
- **The crown jewel substrate is intact.**

## What's genuinely missing (real new builds)

After this audit, the genuinely-missing engineering is much smaller than I had been planning:

1. **Modern frontend (Next.js 15 + React 19 + shadcn/ui)** that actually surfaces all the existing endpoints. Current `live_dashboard.html` is research-grade; we need product-grade.
2. **Sovereign vLLM cluster** running DeepSeek V4 (replace OpenRouter cognition path).
3. **Ambiguity detector** for BPEI-class queries (substrate exists for retrieval clustering; needs the disambiguation modal logic).
4. **Anti-sycophancy CI suite** (paired-prompt evaluation; new test infra).
5. **Evidence Contract Gate** — a formalized JSON schema for the run artifact (substrate produces all this data; needs a single canonical schema doc + validator).
6. **Live citation overlay** (Perplexity-grade hover-tooltip with quote + tier — frontend work on top of existing provenance data).
7. **Inline visual rendering** in the report body (Vega-Lite consuming output of `smart_art_generator.py`).
8. **Conversational follow-up** on completed reports (substrate has session memory; needs the follow-up agent + UI).
9. **Side-by-side compare two reports** (substrate has run_diff; needs different UI than pin-replay).
10. **5 new templates** (defense, climate, AI sovereignty, Canada-US, workforce) — content work, not engineering.

## What was wrong with my previous planning

I was scoping every capability as "build from scratch" when ~80% of the substrate exists. The honest plan is **"expose, fix, swap cognition layer, add 5-8 small genuinely-new pieces"** — not "build a frontier deep research product from zero."

This collapses timeline and budget significantly. Real plan = ~10-14 weeks for full feature surfacing, not 22-26 weeks for "build everything."
