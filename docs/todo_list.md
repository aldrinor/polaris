# POLARIS Todo List — v6.2 Carney Delivery

**Last Updated:** 2026-05-01 (v6.2 plan Codex GREEN; previous full_online_plan_FINAL superseded)

**Canonical plan:** `docs/carney_delivery_plan_FINAL.md` (v6.2 — substrate-aware, frontier-comparable)
**Codex Red-Team Checklist:** `.codex/codex_red_team_checklist.md`
**Per-task acceptance matrix:** `docs/task_acceptance_matrix.yaml`
**Substrate audit:** `docs/substrate_audit_2026-05-01.md`
**Triangle loop protocol:** `memory/autoloop_v2_audit_cross_review.md`

## Mission

Deliver sovereign Canadian deep research AI to Mark Carney as a gift. Match or beat ChatGPT 5.5 Pro DR + Gemini 3.1 Pro DR on every user-facing function. Substrate is ~80% built (270 Python files, 47 audit_ir modules, 113 prior milestones); the build is "expose + fix + sovereign migrate + 10 genuinely-new pieces."

**Timeline**: 18 weeks (May 1 → Sep 6).
**Budget**: $32-70k external cash ceiling.

## Active: Phase 0 — Foundation (May 1-12, 2026, 8 business days)

All 10 tasks must GREEN before Phase 1 starts.

- [ ] **0.1** Blocker decisions written + paid sample evaluator sourcing initiated (mandatory; for Phase 3 benchmark legitimacy)
- [ ] **0.2** Architecture pattern adoption doc (no MiroThinker fork) + license scan
- [ ] **0.3** Vast.ai US 4× H100 dev cluster operational (V4 Flash via SGLang/vLLM)
- [ ] **0.4** Frontend scaffold (Next.js 15 + React 19 + shadcn/ui MIT + Tailwind v4 + TypeScript 5)
- [ ] **0.5** Backend modernization (FastAPI 0.136.x + Pydantic v2 + Dramatiq queue acceptance test)
- [ ] **0.6** DeepSeek V4 hardware Path A/B/C decision committed (default Path C V4 Flash only)
- [ ] **0.7** SGLang vs vLLM bakeoff → one engine frozen for entire build
- [ ] **0.8** Gemma 4 31B verification (model card + license + serving recipe)
- [ ] **0.9** OVH Canada BHS H200 verification (HARD GATE) or backup procurement initiated
- [ ] **0.10** OpenTelemetry wired (`OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_dev`, semconv 1.30.0-dev pinned)

## Phase 1 — BPEI spine + Evidence Contract Gate (May 13-31, 3 weeks)

- [ ] **1.1** F1 scope discovery panel in Next.js frontend
- [ ] **1.2** F2 ambiguity detector backend (HDBSCAN clustering on candidate embeddings) + disambiguation modal UI
- [ ] **1.3** F3a backend wiring of document_ids into graph_v4 evidence pool (the biggest hidden work)
- [ ] **1.4** **Evidence Contract Gate** — canonical JSON schema + golden corpus + sample artifact
- [ ] **1.5** F3b drag-drop upload UI + parse status + chunk preview + sovereignty router
- [ ] **1.6** F15 audit bundle export with embedded source spans (legal review in parallel)
- [ ] **1.7** Sycophancy + refusal CI suite (paired prompts neutral/leading/opposite-frame)
- [ ] **1.8** End-of-Phase 1 walkthrough (3 evaluators)

## Phase 2A — Core inspection (June 1-21, 3 weeks)

- [ ] **2A.1** F4 live audit run UI consuming SSE (5 user-question affordances)
- [ ] **2A.2** F5 generalized Inspector view 1 (click-to-evidence for ANY user-submitted run)
- [ ] **2A.3** F7 frame coverage panel above-the-fold
- [ ] **2A.4** F8 contradiction navigation (badges + side pane + T1-vs-T1 handling)
- [ ] **2A.5** F9 two-family disagreement signal surfacing
- [ ] **2A.6** Templates 4-5 added (defense, climate) — content + eval set + smoke test
- [ ] **2A.7** End-of-Phase 2A walkthrough

## Phase 2B — Visualization + memory + replay (June 22 - July 12, 3 weeks)

- [ ] **2B.1** F6 live citation overlay (basic hover-card MVP — Perplexity-grade lifted to v2.5)
- [ ] **2B.2** F10a Vega-Lite renderer (forest plot + comparison table + timeline = 3 chart types)
- [ ] **2B.3** F10b chart provenance schema + click-through-to-source-data
- [ ] **2B.4** F10c executive-summary infographic
- [ ] **2B.5** F13 pin replay UI + "what changed" diff
- [ ] **2B.6** F14 auditable research memory (workspace_memory → Chroma migration + memory controls UI)
- [ ] **2B.7** End-of-Phase 2B walkthrough

## Phase 2C — UI polish + integration (July 13-19, 1 week)

- [ ] **2C.1** Cross-feature integration testing
- [ ] **2C.2** Visual regression baseline established
- [ ] **2C.3** Cross-browser (Chromium/Firefox/WebKit) verification
- [ ] **2C.4** Performance optimization (long-report hover-latency <100ms target)
- [ ] **2C.5** Accessibility audit (WCAG-AA pass)
- [ ] **2C.6** End-of-Phase 2C walkthrough on full feature set

## Phase 3 — Follow-up + benchmark (July 20 - Aug 9, 3 weeks)

- [ ] **3.1** F11 report-scoped auditable follow-up agent
- [ ] **3.2** F12 side-by-side compare two reports
- [ ] **3.3** Templates 6-8 added (AI sovereignty, Canada-US, workforce)
- [ ] **3.4** Benchmark suite design (50 questions × 8 templates × 4 systems × 6 dimensions)
- [ ] **3.5** Run benchmark + paid sample evaluator scoring (mandatory)
- [ ] **3.6** Sycophancy stress-test report
- [ ] **3.7** Industry benchmark suite run (BrowseComp, GAIA, DeepResearch Bench)
- [ ] **3.8** Proof package PDF for Carney's office

## Phase 4 — Sovereign migration (Aug 10-23, 2 weeks)

- [ ] **4.1** Provision Canadian sovereign cluster per Phase 0 hardware decision
- [ ] **4.2** Migrate vLLM/SGLang serving + DeepSeek V4 weights + Gemma 4 evaluator
- [ ] **4.3** Wire auto-scale: warm pool + spin-up via API on queue depth ≥3
- [ ] **4.4** Re-run benchmark on sovereign cluster (no regression)
- [ ] **4.5** Handover package documentation

## Phase 4.5 — Buffer (Aug 24-30, 1 week)

- [ ] **4.5.1** Address Phase 4 walkthrough findings

## Phase 5 — Carney handover (Aug 31 - Sep 6, 1 week)

- [ ] **5.1** Final user walkthrough with full corpus, recorded
- [ ] **5.2** Final Codex sweep all 10 crown jewels + all flows
- [ ] **5.3** Carney handover package (one-pager + 5-min video + URL + bundle)
- [ ] **5.4** Schedule + execute handover with Carney's office

## Superseded by v6 (no longer pending)
- ~~Phase D: Top-tier — auto-induction + faster audit + governance~~ (replaced by v6 phase plan)
- ~~M-PROD-2: First paying pilot customer~~ (replaced by Carney handover; no commercial pilot)
