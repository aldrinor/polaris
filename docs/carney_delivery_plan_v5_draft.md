# POLARIS — Carney Delivery Plan v5 (DRAFT)

**Status:** Draft for Codex adversarial review. Date: 2026-05-01.
**Mission:** From today (2026-05-01) to a working sovereign Canadian deep research AI delivered to Mark Carney as a gift to Canada.

**Approach:** Latest-practices stack (May 2026 grounding), tight Claude↔Codex loop, mandatory per-task documentation discipline, no deviation, no mid-execution re-planning.

---

## North star

POLARIS Canada — a sovereign, audit-traceable, refusal-aware deep research agent that:
- Runs entirely on Canadian-controlled cognition (LLM thinking on Canadian hardware)
- Matches or beats ChatGPT 5.5 Pro DR / Gemini 3.1 Pro DR on dimensions Canada cares about
- Surfaces all 10 crown jewels in the UI
- Refuses honestly when it can't answer
- Never sycophantic, surfaces contradictions transparently
- Hands to Mark Carney with a defensible benchmark proof package

## Tech stack — anchored to May 2026 latest-practices research

### LLM cognition layer (sovereign)
- **Generator:** DeepSeek V4 Pro (1.6T MoE, 49B active, MIT license, 1M context, hybrid CSA+HCA attention) for benchmark + demo. **Hardware: 8× H200 cluster (~960 GB mixed-precision) per official vLLM recipe.**
- **Generator (steady-state):** DeepSeek V4 Flash (284B MoE, 13B active, MIT license, 1M context). **Hardware: 1× H200 or 2× H100.**
- **Evaluator:** Gemma 4 31B Dense (Apache 2.0, US/Google origin, beats Llama 4 Scout by 10pts on GPQA Diamond, 89.2% AIME 2026). **Hardware: 1× H100 80GB at fp8.**
- **Two-family invariant maintained:** DeepSeek (China) generator + Gemma (US) evaluator. Different lineages.

### Inference engine
- **SGLang** (primary) — 29% throughput advantage over vLLM on H100, RAG-optimized via RadixAttention prefix caching, recommended for DeepSeek deployments (used by xAI Grok 3, Microsoft Azure, LinkedIn, Cursor).
- vLLM as fallback / hardware-compatibility option.

### Agent architecture (verification-centric per MiroThinker design)
- Local Verifier (per-step intermediate-reasoning audit at inference time)
- Global Verifier (full evidence chain audit)
- ReAct loop with context management + tool-call correction
- 256K-1M context per query
- Up to 400 tool calls per task supported
- **Direct extension of POLARIS's existing strict_verify substrate** — adds per-step verification on top of per-sentence verification.

### Frontend stack
- **Next.js 15 + React 19** — Server Components default, Server Actions for forms, 40% Core Web Vitals improvement, 60% Time-to-Interactive reduction
- **shadcn/ui + Tailwind CSS v4** — vendored components (no lock-in), Apache 2.0, dominant 2026 stack for enterprise dashboards
- **TypeScript 5** — type safety
- **Server-Sent Events (SSE)** for live progress streaming — unidirectional server→client, browser-native EventSource API, simpler than WebSocket for our use case
- **Custom hooks** for EventSource management with reconnect/backoff

### Backend stack
- **FastAPI 0.98+** (existing POLARIS substrate)
- **ARQ + Redis** for async job queue — async-first, modern replacement for Celery, designed for asyncio
- **OpenTelemetry instrumentation** for distributed tracing — FastAPI auto-instrumentation, GenAI semantic conventions stable as of early 2026, each LLM call = one critical span with retry/timeout/error capture
- Existing POLARIS Python codebase preserved (all crown jewel substrate intact)

### Citation verification
- **Index-RAG approach** — every material claim maps to retrieved chunks; if a claim cannot be supported, the system re-retrieves, asks clarifying question, or abstains
- **CiteFix-style post-processing** — keyword + semantic + BERTScore citation correction (15.46% accuracy improvement)
- POLARIS strict_verify already implements per-sentence binding; this extends to per-claim with multi-span support

### Sovereign hardware — Canadian
- **Primary:** OVH Canada (Beauharnois, Quebec) — H200 instances confirmed via product page (141 GB HBM3e, 4.8 TB/s bandwidth). French company, not US-jurisdictional. API + CLI access.
- **Backup:** DRAC (Digital Research Alliance of Canada) — 288 H100s on Nibi cluster + Killarney AI cluster + $40M investment in 2025-2026. Free for academic researchers; requires Canadian university partnership.
- **Build phase:** Vast.ai US H100/H200 (NOT sovereign, NOT for sensitive data, just for fast iteration)
- **Demo period:** sovereign Canadian only

### Deployment
- **Kubernetes** for production orchestration (vLLM Production Stack reference architecture)
- **Docker** for development and demo
- Auto-scale via OVH Canada API + warm pool baseline
- Hard daily budget cap

---

## The 10 crown jewels — all in scope, all with browser-reachable UI

| # | Crown jewel | Substrate status | UI status |
|---|---|---|---|
| 1 | Audit-traceability (per-sentence evidence) | ✅ strict_verify | partial (canned demo only) |
| 2 | Refusal-with-explanation (BPEI prevention) | ⚠️ abort statuses exist; ambiguity detection NEW | ❌ |
| 3 | Click-through audit on every claim | ✅ provenance tokens, multi-span needed | partial (canned demo) |
| 4 | Contradictions surfaced and navigable | ✅ detector + hedging | static text only |
| 5 | Frame coverage as lead, not appendix | ✅ manifest | buried in JSON |
| 6 | Two-family disagreement signal | ✅ verification_details | ❌ |
| 7 | Reproducibility / pin replay UI | ✅ pin replay logic | ❌ |
| 8 | Source admissibility decision tree | ✅ T1-T7 + sanitizer | ❌ |
| 9 | Python execution on retrieved data | ✅ env | ❌ |
| 10 | Provenance bundle as deliverable | ✅ audit-bundle.zip endpoint | ❌ |

---

## Phases — from today to Carney handover

### Phase 0 (Days 1-3, May 1-3, 2026): Foundation

**Goal**: lock all blockers, fork MiroThinker and study its verification architecture, set up Layer 3 evaluator contract, scaffold the Next.js frontend.

Tasks (each = one Codex review cycle + one human walkthrough where applicable):

| Task | Output | Doc updates required | Codex review |
|---|---|---|---|
| 0.1 Blocker decisions — Layer 3 evaluator named, buyer segment, deadline, hardware target | written commitments in `docs/carney_delivery_blockers.md` | session_log, todo_list, blockers doc | brief: "is this evaluator profile real and enforceable?" |
| 0.2 Fork / study MiroThinker repo for Local + Global Verifier patterns | analysis doc with adoption strategy | session_log, file_directory, plan-update | brief: "is the architecture port realistic given POLARIS substrate?" |
| 0.3 Provision Vast.ai US 4× H100 dev cluster for V4 Flash testing | working SGLang serving DeepSeek V4 Flash with OpenAI-compatible endpoint | session_log, runbook, .env (gitignored) | brief: "production-style SGLang config? security hardened?" |
| 0.4 Scaffold Next.js 15 + React 19 + shadcn/ui + Tailwind v4 frontend in new `web/` directory | `web/` builds, lints, dark/light theme, basic auth shell | session_log, file_directory, frontend-readme | brief: "stack matches latest 2026 best practices? type safety?" |
| 0.5 Wire OpenTelemetry into FastAPI backend | trace collection working, single LLM-call span per generator/evaluator call | session_log, runbook, observability-readme | brief: "GenAI semantic conventions correctly applied?" |

**Codex loop discipline (applies all phases):**
- Each task gets a written brief in `.codex/task_<id>_review_brief.md`
- Codex reviews; verdict GREEN/YELLOW/RED with P0/P1/P2 findings
- YELLOW or RED = fix before next task starts (no deviation, no fallback)
- GREEN = task complete, advance
- Per-task git commit + push + GitHub PR (auto-merged if Codex GREEN)
- Per-task documentation update (todo, handover, memory, file_directory, plan)

### Phase 1 (Weeks 1-3, May 4-24): Foundation + BPEI spine

**Goal**: ship Flow 1 (scope discovery) and Flow 2 (refusal/disambiguation) with minimum viable report rendering. End of phase: a user can submit a clinical/regulatory query and either get a refusal with explanation OR a basic verified report.

| Task | User flow / output | Codex review brief focus |
|---|---|---|
| 1.1 Port POLARIS scope_gate to new Next.js frontend; render scope-discovery panel | Flow 1 (Scope discovery) | "does it actually prevent BPEI? test corpus inputs?" |
| 1.2 Build ambiguity detector: cluster retrieval candidates by primary entity, flag if >1 plausible meaning | new substrate code | "does it catch 'BPEI', 'GLP-1', similar acronyms? false-positive rate?" |
| 1.3 Refusal view UI with class-specific copy (out-of-scope, ambiguous, threshold-edge, insufficient corpus) | Flow 2 (Refusal/disambiguation) | "human-readable copy? specific gates named? unblock paths real?" |
| 1.4 Minimum viable report rendering — basic markdown render for accepted queries | Flow 1+2 transition target | "does Sprint 1 dead-end? what state if user runs accepted query?" |
| 1.5 Job queue (ARQ + Redis) wiring + SSE progress endpoint | infra | "is the queue actually feeding SSE? cancel works? two-tab safe?" |
| 1.6 End-of-phase walkthrough: 3 evaluators run full Phase 1 corpus | Layer 3 walkthrough | "are 3 distinct evaluators? recordings async-reviewed?" |

### Phase 2 (Weeks 4-7, May 25 - June 21): Crown jewels build

**Goal**: ship Flow 3 (Report inspection with click-through audit) + Flow 4 (Audit bundle export) + Flow 5 (Deployment reality) — and surface all 10 crown jewels in the UI.

| Task | Crown jewel(s) | Codex review brief focus |
|---|---|---|
| 2.1 Generalized Inspector view 1 (Report click-to-inspect for ANY user-submitted run) | #1, #3 | "works for the corpus content classes (200-sentence, multi-span, etc.)?" |
| 2.2 Frame coverage panel as lead-of-report (above-the-fold) | #5 | "first thing visible? gap reasons human-readable?" |
| 2.3 Contradiction navigation with badges, side pane, T1-vs-T1 handling | #4 | "vacuous-pass on zero contradictions handled? sample sizes shown?" |
| 2.4 Two-family disagreement badge surfacing | #6 | "actually flagged when generator/evaluator disagree?" |
| 2.5 Source admissibility decision tree view | #8 | "shows rejected sources + reasons? not aggregate-only?" |
| 2.6 Python execution + chart rendering (matplotlib in audit bundle) | #9 | "charts cite their source data? reproducible?" |
| 2.7 Audit bundle export with embedded source spans (≤500 chars summary), legal review | #10 | "third-party can verify offline? license cleared?" |
| 2.8 Pin replay / "what changed since last run" UI | #7 | "diff visible? regressions flagged?" |
| 2.9 Live audit run UI consuming SSE — search candidates, tier classification, evidence pool, per-sentence verify, contradictions detected — visible in real-time | #1, #2 (live element) | "becomes telemetry dump under pressure? actually reasoning-visible?" |
| 2.10 Deployment / install docs + first-run setup + invite + share-URL | Flow 5 | "60-min new-machine install actually works? non-developer can follow?" |
| 2.11 End-of-phase walkthrough: 3 evaluators run all 5 flows + corpus | Layer 3 | "all 22 input + 17 content classes covered by evaluator-prioritized subset?" |

### Phase 3 (Weeks 8-10, June 22 - July 12): Benchmark proof package

**Goal**: produce the defensible "we match or beat ChatGPT 5.5 Pro DR / Gemini 3.1 Pro DR on Canadian-relevant axes" evidence.

| Task | Output | Codex review |
|---|---|---|
| 3.1 Define 50-question benchmark across pharma R&D, regulatory, defense, legal verticals (with help from Layer 3 evaluators — they own corpus) | benchmark_v1.json + rationale | "questions adversarial enough? evaluator-owned not author-owned?" |
| 3.2 Run benchmark on POLARIS (Flash + Pro), ChatGPT 5.5 Pro DR, Gemini 3.1 Pro DR, Claude Opus DR for comparison | results_table.md with raw transcripts | "transcripts archived? scoring rubric visible?" |
| 3.3 Score by Layer 3 evaluators on 6 dimensions (audit-traceability, refusal honesty, contradiction handling, factuality, presentation efficiency, sycophancy resistance) | scored_results.json | "scoring is independent? not author-defined?" |
| 3.4 Sycophancy stress-test (same topic, opposite-frame prompts; measure bias delta) | sycophancy_report.md | "covers leading-frame + neutral-frame + opposite-frame?" |
| 3.5 Industry-standard benchmark suite run (BrowseComp, GAIA, DeepResearch Bench) for transparency | leaderboard_position.md | "are we transparent about gaps?" |
| 3.6 Write proof package — single PDF readable by non-technical reader, summary + methodology + raw data appendix | proof_package_v1.pdf | "would Carney's office find this credible?" |

### Phase 4 (Weeks 11-12, July 13 - July 26): Sovereign Canadian deployment

**Goal**: migrate everything to Canadian sovereign hardware. Full POLARIS running on OVH Canada Beauharnois H200.

| Task | Output | Codex review |
|---|---|---|
| 4.1 Provision OVH Canada BHS 8× H200 cluster (verify availability via API) | working cluster, sovereign | "verified Canadian-hosted? CLOUD Act exposure documented?" |
| 4.2 Migrate SGLang serving + V4 Pro weights + Gemma 4 evaluator to sovereign cluster | quality validated against US cluster baseline | "fp8 quality matches? batching tuned?" |
| 4.3 Wire auto-scale loop: warm pool of 1× H200 + spin-up additional via OVH API on queue depth ≥3 | auto-scale demonstrably works | "10-min idle spin-down works? hard daily budget cap enforced?" |
| 4.4 Re-run benchmark suite on sovereign cluster to confirm no regression | new proof package | "any quality regression vs build cluster?" |
| 4.5 Document handover package — install runbook, ops runbook, threat model, operations playbook | handover_package_v1.zip | "would a Canadian gov sysadmin be able to operate this?" |

### Phase 5 (Week 13, July 27 - Aug 2): Carney handover

| Task | Output | Codex review |
|---|---|---|
| 5.1 Final Layer 3 walkthrough — fresh accounts, full corpus, recorded async-reviewed | walkthrough_final.mp4 + sign-off | "all gates passed? any cracks?" |
| 5.2 Final Codex sweep — all 10 crown jewels, all flows, all acceptance criteria | final_codex_review.md | "GREEN on every flow? P0/P1 all addressed?" |
| 5.3 Prepare demo package for Carney's office — one-pager + 5-min video walkthrough + working URL + handover bundle | carney_handover_v1.zip | "is this what a PM's office can act on?" |
| 5.4 Schedule + execute handover — Carney's office gets the gift | done | — |

---

## Codex loop protocol (mandatory, applies all phases)

**Per-task workflow:**

1. **Brief the task**: Claude writes `.codex/task_<phase>_<id>_review_brief.md` describing what's being built, acceptance criteria, what to attack
2. **Build the task**: Claude implements per the brief
3. **Self-test**: Claude runs all relevant tests (unit, integration, smoke, type-check, lint)
4. **Codex review**: send brief + diff + test results to `codex exec`
5. **Verdict**:
   - **GREEN** → task complete, advance
   - **YELLOW** → P1 findings; Claude fixes; re-review (max 3 cycles before escalation)
   - **RED** → P0 findings; full halt; escalate to user before any fix
6. **Documentation update** (mandatory before commit):
   - `docs/todo_list.md` — mark task done, add next
   - `docs/file_directory.md` — new files / changed files
   - `logs/session_log.md` — full action+rationale+findings entry
   - `state/restart_instructions.md` — current resume point
   - `state/handover.md` — what changed, what's next, any open questions
   - `memory/MEMORY.md` — if new lesson learned, add memory file
7. **Git workflow**: branch per task, commit, push, PR, auto-merge on GREEN+walkthrough
8. **Walkthrough** (per-flow tasks): Layer 3 evaluator runs in fresh browser, recorded
9. **Mandatory pause-conditions** (only):
   - Codex RED verdict
   - Layer 3 walkthrough fail
   - Hardware/dependency blocker requiring user procurement
   - Cost overrun against budget cap
10. **Auto-resume**: when conditions clear, loop continues without user re-confirmation

**No deviation rule**: scope cannot expand mid-execution. New ideas → next plan revision, not this one. If a crown jewel is harder than estimated, escalate to user explicitly with timeline impact; do not silently descope.

---

## Documentation discipline (NON-NEGOTIABLE per task)

After every task completion, before next task starts, the following are updated:

| File | Updated with |
|---|---|
| `docs/todo_list.md` | task complete; next task front-loaded |
| `docs/file_directory.md` | new/modified files with one-line description |
| `docs/carney_delivery_plan_v5.md` | task marked done; any clarifications |
| `logs/session_log.md` | timestamped entry with action/rationale/evidence/status/next |
| `logs/bug_log.md` | any blockers encountered |
| `state/restart_instructions.md` | resume point if session crashes |
| `state/handover.md` | one-paragraph summary for any incoming Claude session |
| `memory/MEMORY.md` (if applicable) | new lessons learned |
| GitHub | branch + commit + PR + merge + tag for milestone tasks |

A task is NOT complete until docs are updated. This is enforced by Codex review checking the doc updates as part of the verdict.

---

## Acceptance criteria (per Codex's tightened "done" definition)

For each user-flow task:
- Fresh user account, clean state, production-like environment
- No direct API calls; no JWT in browser console
- Real, target-user-supplied inputs (evaluator-owned corpus, NOT plan-authored)
- All input classes pass: supported, unsupported, ambiguous, failing
- 3 walkthroughs by 3 different evaluators
- Layer 3 evaluator (named, buyer-workflow-literate, fail-authority)
- Recorded raw session reviewed asynchronously
- Codex code review GREEN
- Codex user-flow adversarial review: P0/P1 addressed
- User sign-off after walkthrough
- All documentation updated
- GitHub commit + PR merged + tag (if milestone)

**For each crown jewel**: every user-visible factual assertion is either strict_verify-gated and clickable to its evidence span, OR visibly marked `ungated — no accepted evidence span`. `strict_verify` does not get to decide its own coverage.

---

## Blockers — must be resolved by user before Phase 0 starts

(Same as v4 plan; restated for completeness.)

1. **Layer 3 evaluator named, contracted, with fail authority** — absolute blocker
2. **Buyer segment confirmed** (pharma R&D / gov / legal / compliance / defense) — absolute blocker
3. **Hardware target for sovereign deployment** (OVH Canada confirmed available; user confirms commitment)
4. **Pilot deadline / Carney handover target date** (current plan: ~13 weeks = end of July 2026)
5. **Source-text redistribution rights / license policy** (resolve before Phase 2 bundle work)
6. **Support ownership** (real email + named human, before Flow 5)
7. **Email infrastructure** (invites + share URLs)
8. **Model + retrieval budget** for sovereign install
9. **Security posture** (air-gapped vs cloud-isolated vs sovereign-cloud)
10. **First 3 templates locked** (sets corpus and scope_summary copy)

---

## Total budget exposure (revised based on May 2026 hardware research)

| Phase | GPU compute | Evaluator hours | Other | Total |
|---|---|---|---|---|
| Phase 0 (3 days) | $200 (Vast.ai US 4× H100 dev) | $1k (kickoff) | $500 (UI scaffolding) | ~$2k |
| Phase 1 (3 weeks) | $1.5k (sporadic Vast.ai US) | $3k | — | ~$5k |
| Phase 2 (4 weeks) | $3k (heavier dev cluster) | $5k | $2k (legal review for bundle) | ~$10k |
| Phase 3 (3 weeks) | $2k (8× H200 for V4 Pro benchmark runs ≈ 100 GPU-hr) | $8k (extensive benchmark scoring) | — | ~$10k |
| Phase 4 (2 weeks) | $5k (8× H200 OVH Canada migration + validation) | $4k | — | ~$9k |
| Phase 5 (1 week) | $3k (Carney demo period 8× H200 always-on) | $3k (final walkthrough) | $1k (handover package prep) | ~$7k |
| **Total (13 weeks)** | **$15k** | **$24k** | **$3.5k** | **~$45k** |

This excludes any owned-hardware purchase. If Canadian sovereign deployment beyond demo period is desired, owned 8× H200 (~$200-250k capital) becomes part of Carney handover discussion.

---

## What's different from v4 plan

| Aspect | v4 | v5 (this) |
|---|---|---|
| Generator | DeepSeek V3.2 / unspecified | DeepSeek V4 Pro (benchmark) + V4 Flash (steady-state), MIT license, 1M context |
| Evaluator | Qwen 3-8B | Gemma 4 31B Dense (Apache 2.0, US, beats Llama 4 Scout) |
| Inference | OpenRouter / vLLM | SGLang primary (29% throughput advantage) |
| Frontend | Existing live_dashboard.html | Next.js 15 + React 19 + shadcn/ui + Tailwind v4 (full rebuild) |
| Backend queue | M-8 substrate (existing) | ARQ + Redis (modern async) |
| Observability | partial | OpenTelemetry full distributed tracing |
| Agent design | strict_verify only | strict_verify + Local Verifier + Global Verifier (MiroThinker pattern) |
| Hardware | unspecified Canadian path | OVH Canada Beauharnois H200 confirmed available |
| Crown jewels | 4-flow MVP | All 10 in scope |
| Scope | pilot-grade | frontier-comparable proof package for Carney |
| Codex loop | 3-layer review post-hoc | Per-task review + automated doc update + GitHub workflow |
| Timeline | 8-12 weeks | 13 weeks (May 1 - July 26) |
| Documentation | end-of-sprint | every-task |

---

**Next step**: send to Codex for adversarial review of this plan v5.
