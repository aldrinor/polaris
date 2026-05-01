# POLARIS — Carney Delivery Plan v5.1 (Redline applied to v5 per Codex RED verdict)

**Status:** v5.1 — applies all Codex v5 findings as surgical redlines. Send back to Codex for verification.
**Date:** 2026-05-01.
**Codex v5 verdict:** RED (40-45% odds as-written, 65-70% with redline).

---

## Redline summary — what changed from v5

### 1. Hardware claims pinned (v5.2 redline applied per Codex)

**v5 said:** "8× H200 cluster (~960 GB) per official vLLM recipe"
**v5.2 says:**
- **Phase 0 Task 0.6 must select ONE of these three explicit paths** (the previous "8×H200 FP4 default" is removed as not safely demonstrated for V4 Pro on Hopper):
  - **Path A — 16× H200 FP8 V4 Pro full-context** (per SGLang DeepSeek V4 docs). Highest cost (~$50-100/hr), full 1M context, frontier-comparable benchmark. Requires 2-node NVLink cluster.
  - **Path B — 8× H200 FP8 V4 Pro reduced-context (~512K)** (only if validated by Phase 0 bakeoff and explicitly documented as a context-window trade-off; do NOT mix with marketing claims of 1M context).
  - **Path C — V4 Flash on 1× H200 OR 2× H100 SXM only** (no V4 Pro at all; accept ~5-7% capability gap; lowest cost, fully sovereign-feasible, ~$3-8/hr).
- **The default before Phase 0 commits is Path C (Flash-only).** Paths A or B require Phase 0 task 0.6 to produce hardware quote + bakeoff data + signed decision artifact.
- **The "Flash on 1× H200" claim must be validated against the SGLang and vLLM official recipes during Task 0.7 bakeoff.** If recipes differ from this claim, the path defaults adjust.

### 2. Engine choice — no fallback (was "primary + fallback")

**v5 said:** "SGLang primary; vLLM fallback"
**v5.1 says:**
- **Phase 0 Task 0.7 (NEW)**: measured bakeoff between SGLang v0.5.x and vLLM latest on identical hardware (4× H100 dev cluster), identical workload (DeepSeek V4 Flash + 5 representative POLARIS prompts × 50 iterations). Measure throughput, latency P50/P95/P99, prefix-cache hit rate, KV cache pressure, error rate.
- **End of bakeoff: ONE engine chosen. Choice is frozen for entire build.** No fallback. If chosen engine fails in production, RED escalation, not silent swap.

### 3. Gemma 4 evaluator pinned (was research-memory)

**v5 said:** "Gemma 4 31B Dense (Apache 2.0)" — based on third-party coverage
**v5.1 says:**
- **Phase 0 Task 0.8 (NEW)**: verify Gemma 4 31B against Google's official model card. Required artifacts: official model card link, license text, benchmark table from Google, vLLM/SGLang serving recipe. If Gemma 4 31B is not officially Apache 2.0 with a serving recipe by end of Phase 0, fall back to specifically-named alternative (Llama 4 Scout 17B-active 109B-MoE) — decision documented before Phase 1 starts.

### 4. shadcn/ui license correction

**v5 said:** "shadcn/ui... Apache 2.0"
**v5.1 says:** **shadcn/ui is MIT licensed.** Tailwind v4 is also MIT. Both confirmed via official repos.

### 5. FastAPI version corrected

**v5 said:** "FastAPI 0.98+"
**v5.1 says:** **FastAPI 0.136.x (current as of late April 2026).** Pin specific minor version in `pyproject.toml`. Pydantic v2. Python 3.12 or 3.13. **Do not rewrite the entire backend** — modernize the existing POLARIS substrate, replace only what blocks the crown jewels.

### 6. ARQ replaced (v5.2 redline)

**v5 said:** "ARQ + Redis... modern replacement for Celery"
**v5.2 says:**
- ARQ removed (PyPI shows maintenance-only).
- **Dramatiq + Redis is the proposed default**, but Phase 0 Task 0.5 must produce a **queue-acceptance test** before commit:
  - Cancel an in-flight LLM job; worker stops within 5s; partial state persisted
  - Retry a failed retrieval; trace ID preserved across retries
  - Survive a worker kill (SIGKILL); job resumes on a new worker without data loss
  - Resume status visible to the orchestrator
  - Trace ID propagates through queue events to OpenTelemetry
- **If Dramatiq fails the acceptance test, switch to Celery + Redis** (battle-tested, with async wrappers); test acceptance again.
- **Workflow state durability is via Redis-persisted job records + database checkpoints, NOT relied on from the queue alone.** Dramatiq's interrupt mechanism has CPython/GIL limits and is not sufficient as the only durability layer.

### 7. OpenTelemetry GenAI semconv corrected (v5.2 redline)

**v5 said:** "GenAI semantic conventions stable as of early 2026"
**v5.2 says:**
- OpenTelemetry GenAI semantic conventions are status: **Development** (opt-in transition before stability) per the official semconv page.
- **Opt-in mechanism**: enable via the `OTEL_SEMCONV_STABILITY_OPT_IN` environment variable (the official OTel migration mechanism for evolving semconv), set to `gen_ai_dev`, pin to **semconv spec version 1.30.0-dev** in `pyproject.toml` and `requirements.txt`.
- Track upstream changes via a single `docs/observability/genai_semconv_pinned.md` doc that lists the pinned version, what attributes we depend on, and what we'd need to adjust if upstream stabilizes.
- Otel core instrumentation (FastAPI, HTTPx, distributed tracing) IS stable and used as-is.

### 8. MiroThinker — architecture-only adoption

**v5 said:** "Fork / study MiroThinker for Local + Global Verifier patterns"
**v5.1 says:**
- **No fork of MiroThinker-H1** (proprietary). MiroThinker public repo is Apache 2.0 — license-scan first, then optionally inspect for reference patterns only.
- **Build POLARIS Local Verifier and Global Verifier natively** as extensions to existing strict_verify substrate. Document the pattern adoption (with attribution) but write the code from scratch in POLARIS.
- **Phase 0 Task 0.4 (revised)**: license scan MiroThinker public repo + write a 2-page architecture pattern adoption doc; do NOT plan to depend on or fork MiroThinker code.

### 9. Codex loop discipline — enforceable, not formulaic

**v5 said:** "Codex reviews; verdict GREEN/YELLOW/RED; max 3 cycles before escalation"
**v5.1 says:**
- **Codex Red-Team Checklist (NEW, fixed independent of Claude's task brief)** at `.codex/codex_red_team_checklist.md`:
  - Diff inspection: actual code change matches spec
  - Tests inspection: relevant tests pass; new tests cover new code
  - Screenshots/recordings present (if UI task)
  - Trace IDs from OpenTelemetry verifying behavior
  - Corpus outputs (if applicable): expected vs actual on adversarial inputs
  - Doc diffs: structured manifest update (see below)
  - Acceptance artifact (recording, screenshot bundle, transcript)
- **Structured doc manifest** (replaces "doc updates checked"): each task produces `task_<id>_manifest.json` with: task_id, changed_files[], test_commands[], artifacts[], recordings[], trace_ids[], open_bugs[], evidence_links[]. Codex inspects this manifest, not the prose.
- **Escalation rules (refined)**:
  - Same P1 finding twice → escalate to user
  - Any acceptance criterion changed mid-task → RED escalation
  - Task exceeds 150% of estimate → escalate
  - P2 doc nits batchable only if no evidence gap

### 10. Layer 3 walkthrough cadence — not just end-of-phase

**v5 said:** "End-of-phase walkthrough by 3 evaluators"
**v5.1 says:**
- End-of-phase walkthroughs continue.
- **NEW: any task touching refusal, report rendering, audit inspection, bundle export, or share/install flow requires fresh-browser evaluator walkthrough or recorded async review within 48h of task GREEN.**
- This is enforced by the Codex Red-Team Checklist requiring a recording artifact for those task types.

### 11. Phase 0 timing — 5-8 business days, not 3 calendar days

**v5 said:** "Phase 0 (Days 1-3, May 1-3, 2026)"
**v5.1 says:**
- **Phase 0 (Business days 1-8, calendar May 1-12 considering weekend)**: realistic for evaluator contracting + SGLang/vLLM bakeoff + MiroThinker license scan + frontend scaffold + OTel wiring + DeepSeek V4 Pro hardware decision + Gemma 4 31B verification.
- Most likely slip in this phase: evaluator contracting (2-4 weeks possible). Mitigation: start sourcing on Day 1, accept that Phase 1 cannot start until evaluator contracted.

### 12. Phase 1 ambiguity detection — narrow first version

**v5 said:** "Build ambiguity detector"
**v5.1 says:**
- Scope to: retrieval-clustering of top-K candidates by primary entity (using embedding similarity + heuristic entity extraction), trigger disambiguation modal when >1 cluster above threshold.
- Locked acronym/entity corpus: 50 known-ambiguous Canadian-relevant terms (BPEI, GLP-1, MoH/Ministry of Health, etc.). Maintained by evaluators.
- NOT a tuned semantic safety system. Phase 2/3/4 may iterate.

### 13. Task 1.4 → Evidence Contract Gate (THE ONE FIX per Codex)

**v5 said:** "Minimum viable report rendering" (vague)
**v5.1 says (the singular biggest change):**

**Task 1.4 replaced with `Evidence Contract Gate`. NEW concrete spec:**

`docs/evidence_contract.md` defines:
- **Run artifact schema (JSON)**:
  - `claims[]`: each with `claim_id`, `text`, `evidence_spans[]`, `support_tier`, `verifier_state`, `contradicted_by[]`, `ungated: bool`
  - `evidence_spans[]`: each with `span_id`, `source_id`, `text` (≤500 chars summarized), `url`, `tier`, `retrieval_trace`, `evaluator_agreement`
  - `sources[]`: each with `source_id`, `url`, `tier_classification`, `admissibility_decision` (accepted/rejected with reason)
  - `contradictions[]`: each with `flag_id`, `claim_ids[]`, `values[]`, `tiers[]`, `hedge_language`, `pt08_disclosure`
  - `frame_coverage[]`: each with `slot_name`, `populated: bool`, `gap_reason` if not populated
  - `refusal[]`: each with `gate_name`, `threshold_value`, `actual_value`, `unblock_action`
  - `trace_id`: links to OpenTelemetry distributed trace
  - `bundle_ref`: link to audit bundle zip
- **Report rendering rules**: every claim from `claims[]` either renders with click-to-evidence OR renders with `ungated — no accepted evidence span` badge. No exceptions. Tables/headings/captions either render claims (gated/ungated) OR render structural-only labels.
- **Refusal outcomes**: refusal renders as a typed view, not error text. Each `refusal[]` entry maps to a UI block.
- **Audit bundle reference**: every artifact in `bundle_ref` zip is verifiable offline by a reviewer with no POLARIS access.

**Acceptance for Task 1.4 (Evidence Contract Gate):**
- The schema is documented and an example run produces a conforming artifact
- An arbitrary accepted query AND an arbitrary refused/ambiguous query both serialize correctly
- A Layer 3 evaluator can inspect both end-to-end through this contract (recorded session)
- Codex reviews the schema and a sampled artifact for soundness
- **No Phase 2 crown jewel work begins until Task 1.4 GREEN.**

This is the gate. All UI surfaces in Phase 2 render against this schema.

### 14. Phase 2 — split 2.6 and 2.7 (was overpacked)

**v5 said:** Tasks 2.6 (Python execution + charts) and 2.7 (audit bundle + legal review) as single tasks
**v5.1 says:**
- **Task 2.6 split into 4 sub-tasks**:
  - 2.6a: Python sandbox execution environment (containerized, no-egress, resource-capped)
  - 2.6b: Chart provenance schema (charts cite their source data via Evidence Contract spans)
  - 2.6c: Reproducibility (chart code + data snapshot stored in audit bundle)
  - 2.6d: UI surface for Python charts in report
- **Task 2.7 split into 2 sub-tasks**:
  - 2.7a: Audit bundle export (button + preview + zip generation + standalone reviewer README)
  - 2.7b: Legal review of bundle contents + license-clearing for embedded source spans
- **New Phase 2 task count: 14** (was 11). Phase 2 timeline extends from 4 weeks to **5 weeks** to accommodate.

### 15. Task 2.9 (live audit UI) — UX contract added

**v5 said:** "Live audit run UI consuming SSE"
**v5.1 says:**
- Acceptance criterion: Task 2.9 must answer 5 specific user questions visibly in the UI:
  1. What was searched? (query reformulations + retrieval candidates)
  2. What was rejected? (sources dropped + reasons per source)
  3. What changed the answer? (synthesis decisions, regeneration triggers)
  4. What contradiction exists? (contradiction-detection events as they fire)
  5. What evidence supports each claim? (evidence pool building, per-sentence verify)
- **Raw event log is NOT acceptable.** Each user question must have a dedicated UI affordance with replayable trace links.

### 16. Phase 3 evaluator hours realistic

**v5 said:** "$8k evaluator scoring"
**v5.1 says:**
- 50 questions × 4 systems × 6 dimensions = 1,200 scoring decisions
- At 5-15 min/decision (ranges with rubric difficulty) = 100-300 evaluator-hours
- Heavy sampling + automated pre-scoring + targeted human review of disputed scores reduces to 80-150 hours
- **Phase 3 evaluator budget revised to $20-30k** at $200-500/hr × 100-150 hours

### 17. Phase 4 — OVH BHS H200 verification moved to Phase 0

**v5 said:** Phase 4 starts with "Provision OVH Canada BHS 8× H200 cluster"
**v5.1 says:**
- **Phase 0 Task 0.9 (NEW): OVH Canada Beauharnois H200 quota verification.** Required proof artifacts:
  - Region SKU confirmed via OVH API (not just product page)
  - Quota for 8× H200 (or 16× if FP8) — written confirmation from OVH sales
  - Topology: single-instance vs cluster network
  - Hourly price (Canadian region, in CAD/USD)
  - Earliest available start date
  - Data residency statement: data physically stays in Beauharnois Quebec
  - Jurisdiction note: OVH France parent — not US-jurisdictional
  - Security posture: who has physical access, encryption-at-rest, network isolation
- If OVH BHS H200 cannot be confirmed by end of Phase 0, the backup paths are **executable procurement steps, not just names**:
  - **Backup 1 — DRAC Rapid Access** (RAS): if the user has a Canadian university affiliation OR can secure a co-PI from one in <2 weeks, submit a Rapid Access request for H100/A100 access at Nibi (288 H100s) or Killarney AI cluster. Free; cycle time ~1-2 weeks.
  - **Backup 2 — Bell Canada Business Cloud**: written quote for H100 inventory at Bell Toronto/Quebec data centers. Quote-to-provision typically 2-4 weeks; price ~$5-8/hr for H100.
  - **Backup 3 — Hyperstack Toronto/Montreal**: confirmed in Phase 0 search to operate beyond UK; if Canadian DC available, treat as primary fallback. Per-hour pricing similar to OVH.
  - **Backup 4 — Owned hardware in Canadian colo**: 1-2× H100 80GB SXM ($25-30k each) + Cogeco/iWeb colo ($300-500/month). Lead time 4-12 weeks for H100; not viable for Phase 4-5 timeline unless ordered in Phase 0.
  - **Backup 5 — Path C of hardware (V4 Flash only on 2× H100)**: drops V4 Pro entirely; runs everything on smaller-cluster Canadian sovereign hardware that's much easier to source. Most realistic fallback if OVH H200 fails.
- **OVH H200 is NOT confirmed available in Beauharnois yet**: the OVH H200 product page says "Coming soon" and OVH Canada public pricing currently lists H100 but not H200. Phase 0 Task 0.9 must produce a written reservation, not just a sales conversation.

### 18. Phase 5 buffer restored

**v5 said:** "Phase 5 (Week 13): final walkthrough + handover"
**v5.1 says:**
- **Phase 4 trimmed to weeks 11-12 (sovereign migration + validation)**
- **NEW Phase 4.5 (Week 13): buffer week for migration findings**
- **Phase 5 (Week 14): final walkthrough + Codex sweep + handover prep + execute handover**
- **Total timeline: 14 weeks (May 1 → Aug 8) — was 13.**

### 19. Budget revised realistic

**v5 said:** "$45k total"
**v5.1 says:**

| Phase | GPU compute | Evaluator hours | Other | Total |
|---|---|---|---|---|
| Phase 0 (8 business days) | $1k (Vast.ai US 4× H100 + bakeoff cluster) | $3k (kickoff + onboarding) | $2k (sourcing/contracting) | ~$6k |
| Phase 1 (3 weeks) | $2k | $5k | $1k | ~$8k |
| Phase 2 (5 weeks) | $4k | $8k | $3k (legal review) | ~$15k |
| Phase 3 (3 weeks) | $5k (8× H200 benchmark runs ≈ 200 GPU-hr) | $25k (1,200 scoring decisions) | $1k | ~$31k |
| Phase 4 (2 weeks) | $20k (8× H200 OVH Canada migration + always-on validation) | $5k | — | ~$25k |
| Phase 4.5 (buffer week) | $8k (continued sovereign + spot fixes) | $3k | — | ~$11k |
| Phase 5 (1 week) | $10k (Carney demo period 8× H200) | $4k (final walkthrough + sign-off) | $2k (handover package prep) | ~$16k |
| **Total (14 weeks)** | **$50k** | **$53k** | **$9k** | **~$112k** |

**Budget exposure: $112k baseline + $30-60k reserve = $140-170k commit ceiling.** Codex flagged the $112k as "no longer fantasy but lacks reserve for 16× H200, contracting overhead, legal review expansion, queue/ops hardening, CI/evaluator maintenance." Reserve covers:
- 16× H200 path if Phase 0 selects FP8 ($25-40k extra Phase 4-5 compute)
- Evaluator contracting / sourcing / NDA / admin overhead ($5-10k)
- Legal review expansion if source-text redistribution gets thorny ($5-10k)
- Queue/ops hardening if Dramatiq fails acceptance test → Celery migration ($3-5k)
- CI/evaluator maintenance during Phases 2-5 ($5k)

User must commit budget at the $140-170k ceiling, OR scope reduces explicitly:

**Scope reduction options (explicit trade-offs):**
- **Reduction A — Path C hardware (V4 Flash only)**: saves ~$30-50k Phase 4-5 compute. Capability trade-off: ~5-7% behind V4 Pro on hard benchmarks. Defensible — POLARIS still uses world's strongest open-weight model (V4 family) on Canadian sovereign hardware.
- **Reduction B — Drop benchmark vs Claude Opus DR**: saves ~$5k of evaluator hours in Phase 3. Still benchmark vs ChatGPT 5.5 Pro DR + Gemini 3.1 Pro DR (the original target).
- **Reduction C — Heavy automated pre-scoring**: saves ~$10-15k of evaluator scoring hours by automating the easy decisions. Risk: pre-scoring quality not validated by Layer 3.
- **Reduction D — Smaller benchmark (25 questions instead of 50)**: saves ~$8-12k of evaluator scoring hours. Risk: weaker statistical signal in proof package.

Recommended reduction if needed: **A + C** (saves ~$45-65k, preserves benchmark scope, sovereignty intact).

### 20. Sycophancy + refusal honesty in CI from Week 1

**v5 said:** mentioned but not operationalized
**v5.1 says:**
- **Phase 1 Task 1.7 (NEW): paired-prompt CI suite for sycophancy and refusal honesty.**
  - 20 paired prompts: neutral / leading / opposite-frame on identical topics
  - Same source corpus, same scoring rubric for each pair
  - Measure: stance delta, evidence-selection delta, refusal/uncertainty delta
  - Run on every commit; regression alerts on stance delta >5%
- Operationalizes the "non-sycophantic" claim from Day 1 of build, not Day 60.

---

## Final Phase 0 task list (v5.1)

| # | Task | Output | Dependency |
|---|---|---|---|
| 0.1 | Blocker decisions written + evaluator contracting started | `docs/blockers.md` + signed retainer | — |
| 0.2 | Architecture pattern adoption doc (no MiroThinker fork) + license scan | `docs/agent_architecture.md` | — |
| 0.3 | Vast.ai US 4× H100 dev cluster | working SGLang + DeepSeek V4 Flash | — |
| 0.4 | Frontend scaffold (Next.js 15 + React 19 + shadcn/ui MIT + Tailwind v4 MIT + TypeScript 5) | `web/` builds | — |
| 0.5 | Backend modernization (FastAPI 0.136.x + Pydantic v2 + Dramatiq + Redis) | working backend | — |
| 0.6 | DeepSeek V4 Pro hardware decision (8× H200 FP4 OR 16× H200 FP8) | written decision | hardware quote |
| 0.7 | SGLang vs vLLM bakeoff on dev cluster | choice frozen for build | 0.3 |
| 0.8 | Gemma 4 31B verification (model card + license + serving recipe) | written confirmation | — |
| 0.9 | OVH Canada BHS H200 quota verification | written quote/reservation | OVH sales contact |
| 0.10 | OpenTelemetry wired (with `gen_ai.experimental` flag, version-pinned) | trace collection working | 0.5 |

**Phase 0 cannot end until all 10 tasks GREEN. Phase 1 cannot start until Phase 0 ends.**

**Per-task GREEN definition (v5.2 redline — eliminates "undefined GREEN" phantom):**

Every task in every phase has a structured acceptance row defined BEFORE work starts. The row lives in `docs/task_acceptance_matrix.yaml` and contains:

```yaml
task_id: "0.6"
title: "DeepSeek V4 Pro hardware decision"
owner: "Claude (planning) + user (procurement)"
estimate_hours: 16
green_criteria:
  - "Path A/B/C committed in writing in docs/hardware_decision.md"
  - "If Path A or B: written quote from hardware provider on file"
  - "If Path C: bakeoff data from Task 0.7 confirms V4 Flash on chosen hardware meets latency/throughput targets"
  - "Decision artifact signed (commit hash) by user"
required_artifacts:
  - docs/hardware_decision.md
  - quote.pdf or bakeoff_results.json
blocking_consequence: "Phase 1 cannot start"
codex_review_brief: ".codex/task_0_6_review_brief.md"
walkthrough_required: false
```

Codex Red-Team Checklist (`.codex/codex_red_team_checklist.md`) is created as a separate file BEFORE Phase 0 starts (not promised in plan text). Both files are committed to the repo before any Phase 0 task begins.

---

## Revised odds and verdict request to Codex

Per Codex's v5 finding: 40-45% as-written, 65-70% with redline.
**v5.1 applies the redline. Re-submit to Codex for verification.**

If Codex GREEN on v5.1: blockers committed, Phase 0 starts.
If Codex YELLOW: another small redline pass, max one more iteration.
If Codex RED again: structural issue not yet resolved; halt and escalate to user.
