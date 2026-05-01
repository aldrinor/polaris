# POLARIS Carney Delivery — Final Plan

**Status:** FINAL — consolidates v5 + v5.1 redlines + v5.2 surgical redlines + all user decisions through 2026-05-01.
**Date:** 2026-05-01.
**Supersedes:** `docs/carney_delivery_plan_v5_draft.md`, `docs/carney_delivery_plan_v5_1_redline.md`, all earlier shippable plan versions.
**Mission:** From today (May 1, 2026) to a working sovereign Canadian deep research AI delivered to Mark Carney as a gift to Canada.

---

## North star

POLARIS Canada — a sovereign, audit-traceable, refusal-aware deep research agent that:
- Runs cognition entirely on Canadian-controlled hardware (brainless services may use US providers)
- Matches or beats ChatGPT 5.5 Pro DR / Gemini 3.1 Pro DR on the dimensions Canada cares about (audit trace, refusal honesty, contradiction surfacing, sovereignty, no sycophancy)
- Surfaces all 10 crown jewels in the UI
- Hands to Mark Carney as a gift, no profit, no contract — Carney decides what Canada does with it

**Marketing claim**: *audit-traceable, refusal-aware, locally deployable.* Not "live reasoning at every step" — that's a v2.5 stretch.

## The 10 crown jewels — all in scope

| # | Crown jewel |
|---|---|
| 1 | Audit-traceability (per-sentence evidence binding) |
| 2 | Refusal-with-explanation (BPEI prevention) |
| 3 | Click-through audit on every claim |
| 4 | Contradictions surfaced and navigable |
| 5 | Frame coverage as lead, not appendix |
| 6 | Two-family disagreement signal |
| 7 | Reproducibility / pin replay UI |
| 8 | Source admissibility decision tree |
| 9 | Python execution on retrieved data |
| 10 | Provenance bundle as deliverable |

## 8 templates spanning Carney's priorities — explicit content calendar (Codex redline #5)

| # | Template | Carney priority served | Content week | Owner | Acceptance packet |
|---|---|---|---|---|---|
| 1 | **Clinical drug audit** (existing — tirzepatide T2D) | Healthcare / pharmacare debate | Phase 0 | existing | already shipped |
| 2 | **Trade & tariff impact analysis** | Trump tariffs / USMCA July 1 deadline | Phase 0-1 (week 1-2) | user + Claude | charter, source policy, 10 example queries, 15-question eval set, smoke test |
| 3 | **Housing supply & productivity policy** | 500,000 homes/year + 0.7% GDP | Phase 1 (week 2-3) | user + Claude | same packet |
| 4 | **Defense / Arctic / NATO** | $40B+ Northern plan | Phase 2 week 1 | user + Claude | same packet |
| 5 | **Climate & energy policy** | Carney's climate plan | Phase 2 week 2 | user + Claude | same packet |
| 6 | **AI / tech / data sovereignty** | Digital Sovereignty Framework | Phase 2 week 3 | user + Claude | same packet |
| 7 | **Canada-US economic & security partnership** | New partnership progress area | Phase 2 week 4 | user + Claude | same packet |
| 8 | **Skilled trades & workforce policy** | $8k apprenticeship coverage | Phase 3 week 1 | user + Claude | same packet |

**Content calendar is parallel to engineering** — templates aren't "incidental Phase 2-3 polish." Each template has its own dedicated content-week with explicit owner + acceptance packet (charter / source policy / 10 example queries / 15-question eval set / smoke test passing through pipeline).

Per-template acceptance gate: Codex reviews the packet; user signs off; smoke test of 5 queries passes through the pipeline. Template not "delivered" until packet complete.

Templates 1-3 lock in Phase 0-1. Templates 4-8 in Phase 2-3 with explicit content-weeks.

## Tech stack — May 2026 grounded

### LLM cognition
- **Generator (benchmark + Carney demo)**: DeepSeek V4 Pro (1.6T MoE, 49B active, MIT license, 1M context, hybrid CSA+HCA attention)
- **Generator (steady-state)**: DeepSeek V4 Flash (284B MoE, 13B active, MIT, 1M context)
- **Evaluator**: Gemma 4 31B Dense (Apache 2.0, US/Google) — Phase 0 verifies official model card; fallback Llama 4 Scout
- **Two-family invariant**: DeepSeek (China) generator + Gemma (US) evaluator; family lineages enforced by `openrouter_client.check_family_segregation`

### Inference engine
- **Phase 0 bakeoff**: SGLang vs vLLM measured on dev cluster, **one engine frozen**, no fallback
- Existing research baseline: SGLang +29% throughput on H100 for RAG workloads, used by xAI/Microsoft/LinkedIn

### Hardware paths (Phase 0 selects ONE)
- **Path A — V4 Pro on 16× H200 FP8** (full 1M context, frontier-comparable benchmark)
- **Path B — V4 Pro on 8× H200 FP4** (reduced ~512K context)
- **Path C — V4 Flash only on 1× H200 or 2× H100** (5-7% capability gap, simplest sovereign)
- **Default before Phase 0 commits: Path C.** Paths A/B require quote + bakeoff data + signed decision.

### Frontend
- **Next.js 15 + React 19** (Server Components default, Server Actions for forms)
- **shadcn/ui (MIT) + Tailwind v4 (MIT)** — vendored components, no lock-in
- **TypeScript 5** strict mode
- **SSE** for live progress (browser-native EventSource API)

### Backend
- **FastAPI 0.136.x** (current as of late April 2026)
- **Pydantic v2**
- **Python 3.12+**
- **Dramatiq + Redis** for async job queue (Phase 0 acceptance test required: cancel/retry/worker-kill/resume/trace-id-propagation; Celery fallback if Dramatiq fails acceptance)
- Existing POLARIS Python substrate preserved — modernize only what blocks crown jewels

### Observability
- **OpenTelemetry** with `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_dev`, semconv 1.30.0-dev pinned
- Per-LLM-call critical span (capture retries, timeouts, errors for latency/cost/debug)

### Agent architecture
- **MiroThinker pattern, native implementation** — Local Verifier (per-step audit) + Global Verifier (full chain audit) extending existing strict_verify
- License-scan MiroThinker public repo (Apache 2.0); reference patterns OK, no fork
- ReAct loop with context management + tool-call correction

### Citation verification
- Index-RAG: every material claim maps to retrieved chunks; if not supportable → re-retrieve, clarify, or abstain
- CiteFix-style post-processing (BERTScore + keyword + semantic)
- POLARIS strict_verify already implements per-sentence binding; extends to per-claim with multi-span support

### Sovereign hardware (Canadian)
- **Primary target**: OVH Canada Beauharnois H200 (Phase 0 verifies BHS region availability — page currently says "Coming soon"; written reservation required, not sales conversation)
- **Backup paths** (executable procurement, not just names):
  1. DRAC Rapid Access (Nibi 288× H100 / Killarney AI cluster) — requires Canadian university affiliation
  2. Bell Canada Business Cloud — Toronto/Quebec H100 inventory (~$5-8/hr; 2-4 wk procurement)
  3. Hyperstack Canadian DC if confirmed (verify in Phase 0)
  4. Owned hardware ($25-30k per H100, Cogeco/iWeb colo) — 4-12 wk lead, fallback only
  5. Path C V4 Flash on smaller cluster (most realistic if H200 fails)

## Hardware strategy — on-demand, never always-on (with enforcement, Codex redline #4)

| Phase | GPU pattern | Rationale |
|---|---|---|
| Phase 0-2 (build) | DeepSeek API for V4 Pro testing + Vast.ai US 1× H200 on-demand for V4 Flash dev cluster | Cheap, fast iteration; sovereignty deferred (build queries are synthetic/public — enforced by code, see below) |
| Phase 3 (benchmark) | DeepSeek API for V4 Pro runs + self-hosted runs for sovereign validation, batched | Defensible benchmark proof requires self-hosted runs |
| Phase 4 (sovereign migration) | Canadian cluster spun up business-hours only during validation | Validate works, don't pay for idle |
| Phase 4.5 (buffer week) | On-demand only when fixing migration findings | Same |
| Phase 5 (Carney demo) | Warm pool 1× H200 always-on + V4 Pro 8-16× H200 burst on-demand | First-query latency stays low; expensive cluster only when justified |

**No always-on cluster except the Phase 5 warm pool.** Default: GPUs OFF.

**Enforcement (Codex redline #4) — TTL / autostop / budget audit gates:**
- Every GPU instance is provisioned with a TTL tag (default: 4h max, configurable per task)
- Idle detection (no API calls for 10 min) triggers autostop
- Daily budget cap per phase enforced at the orchestration layer (`scripts/gpu_budget_guard.py`)
- Weekly cost/uptime audit committed to `docs/gpu_audit_log.md`
- Phase gate: each phase end requires actual uptime + cost evidence reviewed by Codex; over-budget by >10% = RED escalation

**Provider routing enforcement (Codex redline #3) — code-level data classification:**
- Every LLM call carries a `data_classification` tag: `PUBLIC_SYNTHETIC`, `CAN_REAL`, `PRIVATE`, `CLIENT`, or `UNKNOWN`
- LLM router (`src/polaris_graph/llm/sovereign_router.py`) is **default-deny** for external API calls
- ONLY `PUBLIC_SYNTHETIC` may route to DeepSeek API (or any non-sovereign provider)
- `CAN_REAL`, `PRIVATE`, `CLIENT`, `UNKNOWN` route to local sovereign cluster only
- CI test (`tests/sovereignty/test_routing_policy.py`) proves all four classifications with attempted external-API call → blocked
- Routing decisions logged with classification + destination (no payload content) for audit

## Validation roles — honestly named (Codex redline)

**User = product-owner acceptance.** Not "Layer 3 independent validation." User has authority and domain literacy; user also has commercial interest in shipping. That role is product acceptance, not independent validation.

**Mandatory paid sample evaluator (Codex redline #1)**: $3-8k for Phase 3 benchmark legitimacy. Not optional. The evaluator does NOT review everything. They blind-score a representative slice:
- Benchmark sample (10-15 questions across templates)
- Smoke test of all 8 templates
- Adversarial / sycophancy paired-prompt cases
- Evidence Contract behavior on accepted + refused queries

Without this, the Carney handover proof package weakens to "the builder validated themselves." Cheap insurance.

**Carney's office = final acceptance gate** at handover. They are the ultimate validation. Pre-handover validation must combine product-owner (user) + paid sample evaluator (independent slice) + Codex (code-level review).

## Phase plan — 14 weeks, May 1 → Aug 8

### Phase 0 — Foundation (8 business days, May 1-12)

10 tasks, all GREEN before Phase 1 starts. Detail in `docs/task_acceptance_matrix.yaml`:

| # | Task |
|---|---|
| 0.1 | Blocker decisions written + (optional) one paid sample evaluator sourced for Phase 3 benchmark legitimacy |
| 0.2 | Architecture pattern adoption doc + MiroThinker license scan |
| 0.3 | Vast.ai US 1× H200 dev cluster (V4 Flash serving) |
| 0.4 | Frontend scaffold (Next.js 15 + React 19 + shadcn/ui MIT + Tailwind v4 + TypeScript 5) |
| 0.5 | Backend modernization (FastAPI 0.136.x + Pydantic v2 + Dramatiq queue acceptance test) |
| 0.6 | Hardware Path A/B/C decision committed (default Path C) |
| 0.7 | SGLang vs vLLM bakeoff → one engine frozen |
| 0.8 | Gemma 4 31B verification (model card + license + serving recipe) |
| 0.9 | OVH Canada BHS H200 verification (or backup procurement initiated) |
| 0.10 | OpenTelemetry wired (semconv 1.30.0-dev pinned) |

### Phase 1 — BPEI spine (3 weeks, May 13-31)

| # | Task | Output |
|---|---|---|
| 1.1 | Templates 1+2+3 scope-discovery panel in frontend (Flow 1) | Browser-reachable scope discovery |
| 1.2 | Ambiguity detector (retrieval-clustering + 50-term locked corpus) | Detects BPEI-class queries |
| 1.3 | Refusal view UI with class-specific copy (Flow 2) | Out-of-scope, ambiguous, threshold-edge, insufficient-corpus all handled |
| **1.4** | **Evidence Contract Gate** — schema + golden corpus + sample artifact | **Blocks Phase 2** |
| 1.5 | Job queue + SSE progress endpoint wiring | Async pipeline with cancel/refresh/resume |
| 1.6 | Sycophancy + refusal CI suite (paired prompts: neutral / leading / opposite-frame) | Runs on every commit; nightly full eval |
| 1.7 | End-of-Phase 1 walkthrough | User reviews Flow 1+2 against corpus |

### Phase 2 — Crown jewels build (5 weeks, June 1 - July 5)

| # | Task | Crown jewel |
|---|---|---|
| 2.1 | Generalized Inspector view 1 — click-to-evidence for ANY user-submitted run | #1, #3 |
| 2.2 | Frame coverage panel above-the-fold (lead, not appendix) | #5 |
| 2.3 | Contradiction navigation (badges → side pane → all sides + tiers + hedge) | #4 |
| 2.4 | Two-family disagreement badge surfacing | #6 |
| 2.5 | Source admissibility decision tree view | #8 |
| 2.6a | Python sandbox execution environment (containerized, no-egress, resource-capped) | #9 |
| 2.6b | Chart provenance schema (charts cite source data via Evidence Contract spans) | #9 |
| 2.6c | Reproducibility (chart code + data snapshot in audit bundle) | #9 |
| 2.6d | UI surface for Python charts in report | #9 |
| 2.7a | Audit bundle export (button + preview + zip + reviewer README) | #10 |
| 2.7b | Legal review of bundle contents + license-clearing for embedded source spans | #10 |
| 2.8 | Pin replay / "what changed since last run" UI | #7 |
| 2.9 | Live audit run UI consuming SSE — must answer 5 user questions visibly (what was searched, what was rejected, what changed the answer, what contradiction exists, what evidence supports each claim) | #1, #2 live element |
| 2.10 | Templates 4-5 added (defense, climate) — content work in parallel | scope expansion |
| 2.11 | Deployment / install / account / sharing reality (Flow 5) | infrastructure |
| 2.12 | End-of-Phase 2 walkthrough | User reviews all crown jewels against corpus |

### Phase 3 — Benchmark proof package (3 weeks, July 6-26)

| # | Task | Output |
|---|---|---|
| 3.1 | Benchmark question set (50 questions × 8 templates = 400 questions, but cap to 50 representative) | benchmark_v1.json |
| 3.2 | Run benchmark: POLARIS (Pro + Flash) vs ChatGPT 5.5 Pro DR vs Gemini 3.1 Pro DR vs Claude Opus DR | results_table.md + raw transcripts |
| 3.3 | Score by user (and optionally one paid sample evaluator) on 6 dimensions | scored_results.json |
| 3.4 | Sycophancy stress-test (paired-prompt deltas) | sycophancy_report.md |
| 3.5 | Industry benchmark suite run (BrowseComp, GAIA, DeepResearch Bench) for transparency | leaderboard_position.md |
| 3.6 | Templates 6-8 added (AI sovereignty, US partnership, workforce) — content + initial scoring | scope expansion |
| 3.7 | Proof package PDF for Carney's office | proof_package_v1.pdf |

### Phase 4 — Sovereign Canadian migration (2 weeks, July 27 - Aug 9)

| # | Task | Output |
|---|---|---|
| 4.1 | Provision Canadian sovereign cluster (per Phase 0 hardware decision) | working cluster |
| 4.2 | Migrate vLLM/SGLang serving + V4 Pro/Flash weights + Gemma 4 evaluator | quality validated |
| 4.3 | Wire auto-scale loop: warm pool + spin-up additional via API on queue depth ≥3 | auto-scale demonstrably works |
| 4.4 | Re-run benchmark on sovereign cluster — confirm no regression | new proof package |
| 4.5 | Document handover package (install runbook + ops runbook + threat model) | handover_package_v1.zip |

### Phase 4.5 — Buffer (1 week, Aug 10-16)

Address findings from Phase 4 walkthrough. If findings are minor: hardening + regression. If major: rebuild affected piece. If catastrophic: halt and escalate.

### Phase 5 — Carney handover (1 week, Aug 17-23)

| # | Task | Output |
|---|---|---|
| 5.1 | Final user walkthrough — fresh accounts, full corpus, recorded session | walkthrough_final.mp4 |
| 5.2 | Final Codex sweep — all 10 crown jewels, all flows, all acceptance criteria | final_codex_review.md GREEN |
| 5.3 | Carney handover package — one-pager + 5-min video walkthrough + working URL + handover bundle | carney_handover_v1.zip |
| 5.4 | Schedule + execute handover with Carney's office | done |

## Codex loop protocol (mandatory, per task)

**Per-task workflow:**
1. Brief: `.codex/task_<id>_review_brief.md`
2. Build per brief
3. Self-test: relevant tests pass; new tests cover new code
4. Manifest: `task_<id>_manifest.json` with structured fields (task_id, changed_files, test_commands, artifacts, recordings, trace_ids, open_bugs, evidence_links — see `.codex/codex_red_team_checklist.md` for schema)
5. Codex review using fixed Red-Team Checklist (independent of brief)
6. Verdict: GREEN / YELLOW / RED
7. Documentation update (mandatory before commit): todo, file_directory, plan, session_log, restart_instructions, handover, memory if applicable
8. Git: branch + commit + PR + GitHub merge on GREEN
9. Walkthrough (UI/flow tasks): user runs in fresh browser within 48h, recording → BLOCKED if missed

**Escalation rules:**
- Same P1 finding twice → escalate to user
- Acceptance criterion changed mid-task → RED escalation
- Task >150% of estimate → escalate
- 48h no walkthrough → task auto-reverts to BLOCKED, plan halts
- 3 YELLOW cycles → escalate

**Anti-patterns refused:**
- "Iterate until Codex GREEN" without walkthrough
- "Backend exists = done"
- "While we're at it..." scope creep
- Re-entering autoloop
- Prose-only doc updates (must be structured manifest)

## Documentation discipline (mandatory per task)

After every task completion, before next task starts:

| File | Updated with |
|---|---|
| `docs/todo_list.md` | task complete; next task front-loaded |
| `docs/file_directory.md` | new/modified files |
| `docs/carney_delivery_plan_FINAL.md` | task marked done |
| `docs/task_acceptance_matrix.yaml` | task GREEN/YELLOW/RED + actual_hours |
| `logs/session_log.md` | timestamped entry |
| `logs/bug_log.md` | any blockers |
| `state/restart_instructions.md` | resume point |
| `state/handover.md` | one-paragraph next-session summary |
| `memory/MEMORY.md` (if applicable) | new lessons |
| GitHub | branch + commit + PR + merge + tag for milestone tasks |

A task is NOT complete until docs are updated. Codex Red-Team Checklist enforces this via manifest inspection.

## Realistic budget — external cash ceiling (Codex redline)

**Important framing**: this is the **EXTERNAL CASH CEILING**, EXCLUDING user labor, Codex API costs, and internal review labor. The cash savings vs $170-210k were achieved by moving work from vendors into user/Codex labor, NOT by deleting the work. Be honest about this with anyone reviewing the budget.

| Category | Estimate |
|---|---|
| **Build phase compute + API** (Phases 0-2, ~7 weeks) | **~$450-850** |
| **Benchmark phase** (Phase 3): API + competitor subscriptions + self-hosted validation | **~$5.7-10.7k** |
| **Sovereign migration + Carney demo** (Phases 4-5): on-demand Canadian cluster | **~$7-17k** |
| **MANDATORY paid sample evaluator** (Codex redline #1, was optional) | **~$3-8k** |
| **Non-compute** (legal review for bundle, handover prep, sourcing/admin, domain registration) | **~$5-12k** |
| **20% contingency** (Codex redline) | **~$5-10k** |
| **TOTAL external cash ceiling** | **~$26-58k** |

**Expected delivery band: $35-55k** WITH mandatory paid sample evaluator + 20% contingency retained.

Reduce-scope option (Path C only, drop V4 Pro entirely, fewer benchmark runs): ~$25-32k.

**NOT included** (user/internal time):
- User time during build phase (review, walkthroughs, decisions, content authorship across 8 templates)
- Codex token consumption for the per-task review loop
- Any internal engineering labor not contracted out

## Blockers — user commitments needed before Phase 0 starts

All answered through 2026-04-30 / 2026-05-01 conversation:

| # | Blocker | Status |
|---|---|---|
| 1 | Layer 3 evaluator | ✅ User during build, Carney's office at handover |
| 2 | Buyer segment | ✅ Canadian sovereign deep research, ultimately Carney's gov |
| 3 | Hardware path | ✅ Phase 0 selects A/B/C, default C |
| 4 | Pilot deadline | ✅ Quality over speed; ~14 weeks target, flexible |
| 5 | Source-text license | ✅ Phase 2 legal review; brainless services US OK |
| 6 | Support ownership | ✅ Carney's team after handover |
| 7 | Email infrastructure | ✅ N/A for build phase |
| 8 | Budget ceiling | ✅ $25-55k (much lower than earlier estimates) |
| 9 | Security posture | ✅ Sovereign Canadian for cognition; cloud-isolated for build |
| 10 | First 3 templates | ✅ Clinical (existing) + Trade + Housing for Phase 0; +5 templates added Phases 2-3 |

**No blockers remaining.** Phase 0 is start-ready.

## What changed from earlier plan versions

- **Templates: 3 → 8** (covering Carney's seven priorities + healthcare baseline)
- **Layer 3: paid contractor → user** (saves $20-50k; less independent but user has authority)
- **Build phase compute: self-host → DeepSeek API** (saves $10-20k; sovereignty deferred to benchmark+demo phases when handling real data)
- **Always-on cluster: removed** in favor of on-demand spin-up (saves $30-35k)
- **Budget: $170-210k → $25-55k** (~70-85% reduction by combining all the smart-spending levers)
- **Timeline: 14 weeks unchanged**, but with Phase 4.5 buffer week

## What's the same as v5/v5.1/v5.2

- Mission and crown jewels
- Tech stack (DeepSeek V4 + Gemma 4 + SGLang/vLLM + Next.js 15 + FastAPI 0.136.x + Dramatiq + OpenTelemetry)
- Codex Red-Team Checklist + per-task acceptance matrix discipline
- Evidence Contract Gate (Phase 1 Task 1.4) blocking Phase 2
- 14-week phase structure with 4.5 buffer
- Anti-phantom-completion discipline

---

**Next step**: send this consolidated plan to Codex for final GREEN verification. If GREEN: Phase 0 starts. If YELLOW: one surgical pass max.
