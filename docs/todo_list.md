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

- [x] **0.1** Blocker decisions written + paid sample evaluator sourcing initiated → `docs/blockers.md`
- [x] **0.2** Architecture pattern adoption doc (no MiroThinker fork) + license scan → `docs/agent_architecture.md`
- [ ] **0.3** Vast.ai US 4× H100 dev cluster operational — needs user $ commitment ($1.8-3.2k); auto-loop CAN spin instances on confirm
- [x] **0.4** Frontend scaffold (Next.js 16 + React 19 + shadcn 4.6 MIT + Tailwind v4 + TypeScript 5 + ESLint 9 + Prettier) → `web/`; 4/4 CI gates green; 2 screenshots verified
- [~] **0.5** Backend modernization → 43 v6 tests PASSING (BPEI ambiguity 5, /ambiguity API 4, /health+runs 6, /bundle 4, OTEL 4, schemas 5, evidence contract gate 10, sycophancy 5). Acceptance scenarios 2-8 xfailed pending Task 0.3 cluster.
- [ ] **0.6** DeepSeek V4 hardware Path A/B/C decision committed (default Path C V4 Flash only) — needs Task 0.7 bakeoff data
- [ ] **0.7** SGLang vs vLLM bakeoff → one engine frozen for entire build — needs Task 0.3 cluster
- [~] **0.8** Gemma 4 31B verification → `docs/gemma_4_verification.md` (Errata E-1: Apache 2.0 + Gemma Use Policy, LOW severity); smoke test pending Task 0.3
- [ ] **0.9** OVH Canada BHS H200 procurement (HARD GATE for Phase 4 sovereign) — user must engage OVH Sales by 2026-05-12
- [~] **0.10** OpenTelemetry → `docs/opentelemetry_genai.md` (Errata E-2: `gen_ai_latest_experimental`, semconv 1.36.0+) + code (`src/polaris_v6/observability/otel_init.py` with fail-loudly contract + 4 contract tests)

## Phase 1 — BPEI spine + Evidence Contract Gate (May 13-31, 3 weeks)

- [x] **1.1** F1 scope discovery panel — `src/polaris_v6/scope/decision.py` + `api/scope.py` + dashboard inline panel + 5 tests; LLM-augment swap deferred to cluster
- [x] **1.2** F2 ambiguity detector — `src/polaris_v6/bpei/ambiguity_detector.py` + `api/ambiguity.py` + dashboard modal + 9 tests; HDBSCAN swap deferred to cluster
- [x] **1.3** F3a evidence pool merger (graph_v4.py:149 fix) — `src/polaris_v6/adapters/evidence_pool_merger.py` + 6 tests; production-path wire-in deferred to cluster (graph_v4 imports forbidden by LAW VII)
- [x] **1.4** Evidence Contract Gate — Pydantic v2 schema + 6 golden fixtures + 13 Gate tests GREEN
- [x] **1.5** F3b drag-drop upload — `src/polaris_v6/api/upload.py` + frontend dropzone wired into createRun document_ids + 7 tests; sovereignty router (CAN_REAL on-Canada-only) deferred to cluster
- [x] **1.6** F15 audit bundle export — `src/polaris_v6/api/bundle.py` + 4 tests + frontend Export-bundle + downloadBundleAsJson client; verbatim-spans IP review pending counsel
- [x] **1.7** Sycophancy + refusal CI suite — `src/polaris_v6/sycophancy/` + 12 paired-prompt fixtures + 21 tests (5 scorer + 16 fixtures); live LLM hookup deferred to cluster
- [ ] **1.8** End-of-Phase 1 walkthrough (3 evaluators) — needs user

## Phase 2A — Core inspection (June 1-21, 3 weeks)

- [x] **2A.1** F4 live audit run UI — `web/app/runs/[runId]/page.tsx` SSE subscription + 5 affordances panel (Open Inspector / Export bundle / Cancel / Follow-up / Pin)
- [x] **2A.2** F5 generalized Inspector view — `web/app/inspector/[runId]/page.tsx` 5-tab Inspector (Verified / Frames / Contradictions / Pool / Charts) + 2 live screenshots
- [x] **2A.3** F7 frame coverage panel — Inspector "Frames" tab with progress bars
- [x] **2A.4** F8 contradiction navigation — Contradictions tab + linking badges in Verified Sentences
- [x] **2A.5** F9 two-family disagreement — Inspector top KPI card with PASS/FAIL styling + destructive banner on invariant violation
- [x] **2A.6** Templates 4-5 (defense, climate) — `config/v6_templates/` 8 of 8 (clinical, trade, housing, defense, climate, ai_sovereignty, canada_us, workforce) + 13 tests
- [ ] **2A.7** End-of-Phase 2A walkthrough — needs user

## Phase 2B — Visualization + memory + replay (June 22 - July 12, 3 weeks)

- [x] **2B.1** F6 live citation overlay — `web/components/ui/evidence-tooltip.tsx` (base-ui Tooltip, hover preview of source span)
- [x] **2B.2** F10a Vega-Lite renderer — `src/polaris_v6/charts/spec_builder.py` + `from_bundle.py` + `api/charts.py` + `web/components/ui/vega-chart.tsx` (vega-embed v5) + Inspector Charts tab + live screenshot
- [x] **2B.3** F10b chart provenance schema — `polaris_provenance.evidence_ids` extension on every spec + click-through-to-source via VegaChart onPointClick
- [ ] **2B.4** F10c executive-summary infographic — composed from 3 chart types; UI glue remaining
- [x] **2B.5** F13 pin replay + diff — `src/polaris_v6/replay/{schema,differ}.py` + `regression_lab/runner.py` + 14 tests
- [x] **2B.6** F14 workspace memory — `src/polaris_v6/memory/{schema,store}.py` + `api/memory.py` (5 endpoints, 14 tests); Chroma swap deferred to cluster
- [ ] **2B.7** End-of-Phase 2B walkthrough — needs user

## Phase 2C — UI polish + integration (July 13-19, 1 week)

- [ ] **2C.1** Cross-feature integration testing
- [ ] **2C.2** Visual regression baseline established
- [ ] **2C.3** Cross-browser (Chromium/Firefox/WebKit) verification
- [ ] **2C.4** Performance optimization (long-report hover-latency <100ms target)
- [ ] **2C.5** Accessibility audit (WCAG-AA pass)
- [ ] **2C.6** End-of-Phase 2C walkthrough on full feature set

## Phase 3 — Follow-up + benchmark (July 20 - Aug 9, 3 weeks)

- [x] **3.1** F11 follow-up agent — `src/polaris_v6/followup/{schema,agent}.py` + `api/followup.py` + 8 endpoint tests (out-of-scope refusal verified)
- [x] **3.2** F12 side-by-side compare — `src/polaris_v6/compare/differ.py` + `api/compare.py` + 11 tests (7 lib + 4 API)
- [x] **3.3** Templates 6-8 (AI sov, Canada-US, workforce) — JSON files in `config/v6_templates/`
- [x] **3.4** Benchmark suite design schema — `src/polaris_v6/benchmark/schema.py` + 6 tests
- [ ] **3.5** Run benchmark + paid sample evaluator — needs evaluator retainer (user $) + cluster
- [ ] **3.6** Sycophancy stress-test report — needs LLM cluster to drive paired-prompt fixtures
- [x] **3.7** Industry benchmark adapters — `src/polaris_v6/benchmark/industry_adapters.py` (BrowseComp + GAIA + DeepResearch Bench) + `scripts/v6/run_benchmark.py` CLI + 13 tests
- [ ] **3.8** Proof package PDF — assembled at Phase 5

## Phase 4 — Sovereign migration (Aug 10-23, 2 weeks)

- [ ] **4.1** Provision Canadian sovereign cluster per Phase 0 hardware decision
- [ ] **4.2** Migrate vLLM/SGLang serving + DeepSeek V4 weights + Gemma 4 evaluator
- [ ] **4.3** Wire auto-scale: warm pool + spin-up via API on queue depth ≥3
- [ ] **4.4** Re-run benchmark on sovereign cluster (no regression)
- [ ] **4.5** Handover package documentation

## Phase 4.5 — Buffer (Aug 24-30, 1 week)

- [ ] **4.5.1** Address Phase 4 walkthrough findings

## Phase 5 — Carney handover (Aug 31 - Sep 6, 1 week)

- [ ] **5.1** Final user walkthrough with full corpus, recorded — needs user + cluster
- [ ] **5.2** Final Codex sweep all 10 crown jewels — round-3 brief at `.codex/v6_phase_0_1_substrate_round_3_review_brief.md`; needs user-side Codex run
- [~] **5.3** Carney handover package — `docs/carney_handover/{one_pager,5min_video_script,runbook}.md` skeleton; final URL + bundle finalize at Phase 5
- [ ] **5.4** Schedule + execute handover with Carney's office — needs user

## Superseded by v6 (no longer pending)
- ~~Phase D: Top-tier — auto-induction + faster audit + governance~~ (replaced by v6 phase plan)
- ~~M-PROD-2: First paying pilot customer~~ (replaced by Carney handover; no commercial pilot)
