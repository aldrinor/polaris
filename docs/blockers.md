# POLARIS v6.2 — Blocker Decisions Register

**Last updated:** 2026-05-02 (canonical reconciliation per Plan v13 §A Step 0a)
**Owning task:** Phase 0 Task 0.1
**Plan reference:** `docs/carney_delivery_plan_v6_2.md` (renamed from `_FINAL.md` 2026-05-02)

This document fixes the 10 blocker decisions surfaced during v6 planning. Each decision is either **CONFIRMED** (user direction is durable, build proceeds) or **ACTION-PENDING** (an external procurement / signature must complete before a downstream task can GREEN).

---

## 1. Validation roles (internal benchmark — paid evaluator removed)

**Decision:** CONFIRMED — **internal benchmark via API replaces paid Layer-3 evaluator** (user-signed reconciliation 2026-05-03).
- Layer 1 = automated CI gates (sycophancy, refusal, contradiction, citation)
- Layer 2 = product-owner walkthroughs (user runs in fresh browser within 48h, recorded)
- Layer 3 = **internal benchmark suite** (POLARIS API vs ChatGPT 5.5 Pro DR API vs Gemini 3.1 Pro DR API). Per-template scoring rubric committed alongside benchmark runner. **No paid third-party evaluator retainer.**

**Rationale (reconciled 2026-05-03):** User directive: the head-to-head benchmark IS the validation. POLARIS already builds the benchmark suite (task 3.4 schema + 3.7 industry adapters APPROVE'd). Adding a paid evaluator on top duplicates the validation surface and incurs $8-12k that doesn't change the technical outcome. The benchmark runner produces the comparative scoring; the user reviews results and signs off.

**Action items:** None user-side. Benchmark runner is orchestrator-completable (task 3.5 substrate_prep). User reviews benchmark output at Phase 3 close.

**Blocking consequence if missed:** N/A — internal benchmark is canonical validation.

**Reconciliation log:** Original v6.2 plan + v5 lineage required a paid Layer-3 evaluator ($8-12k retainer signed by 2026-07-15). Per user directive 2026-05-03 ("I won't pay anyone for evaluate, we have benchmark test"), this entire requirement is removed. Budget tranche T3 (evaluator $8-12k) eliminated. Phase 3 task 3.5 reframes around the API-driven benchmark with no external evaluator.

---

## 2. Buyer / recipient segment

**Decision:** CONFIRMED
- Single recipient: PM Mark Carney's office, as a gift to Canada
- No commercial pilot, no paying customer, no SaaS conversion
- 8 templates aligned to Carney's seven officially-named priorities: clinical (existing), trade, housing, defense, climate, AI sovereignty, Canada-US, workforce

**Rationale:** This is sovereign delivery, not a product launch. Removes commercial-pilot scope from previous v5 plan.

---

## 3. Hardware path (build phase + sovereign migration)

**Decision:** CONFIRMED — **Path C V4 Flash only on 8× H200 OVH Canada BHS** (locked 2026-05-02 per Plan v13 §F user-signed canonical reconciliation)
- **Build phase**: API-only via OpenRouter / DeepSeek API (~$250-450 over Phases 0-3). NO physical-cluster procurement during build. Vast.ai dev cluster (Task 0.3) is **conditionally activated** only if a Phase 0/1/2 task explicitly requires it; until then it is a deferred sub-task.
- **Sovereign migration**: **Path C — 8× H200 V4 Flash only** (capacity for 5+ concurrent sessions; capacity > marginal quality for Carney scope)
  - Paths A and B remain documented below for reference but are NOT the build path.
  - ~~Path A: 16× H200 FP8 V4 Pro full (capacity for 5+ concurrent sessions)~~ — not selected
  - ~~Path B: 8× H200 reduced V4 Pro (capacity for 2 concurrent sessions)~~ — not selected (concurrency below requirement)
  - **Path C: 8× H200 V4 Flash only** — SELECTED. Capacity for 5+ concurrent sessions; quality differential from V4 Pro confirmed acceptable in Phase 0 Task 0.6 bakeoff (or, if bakeoff not yet run, lock holds and bakeoff validates rather than selects).

**Rationale (reconciled):** User-signed lock at Plan v13 §F. Capacity is the dominant constraint for sovereign deployment at Carney scope; V4 Flash quality delta vs V4 Pro is acceptable for the use case. Path C is also the lowest-risk procurement (8× H200 well within OVH BHS quoted availability). If Phase 0.7 bakeoff data later materially contradicts (e.g., V4 Flash quality fails on 2+ template families), the orchestrator halts per Plan v13 §H halt-condition #5; user re-signs canonical to switch to Path A or B (NOT a silent fallback — explicit user re-decision per Plan v13 §F "no silent fallback" semantics).

**API-first sequencing (reconciled 2026-05-02):** Per user directive, hardware procurement is NOT a Day-1 / Phase-0 gate. The plan validates via API service first across Phases 0-3 (build + benchmark vs ChatGPT/Gemini DR). Only when API-level results justify it does sovereign procurement engage. Concretely:
- **Phase 0-3 (May 1 - Aug 9):** API-only. No physical-cluster commitment.
- **Phase 4 entry (~2026-08-10):** decision-doc signing + OVH BHS procurement engaged, gated on Phase 3 benchmark APPROVE.
- **Phase 4 (Aug 10-23):** sovereign migration executes.

**Blocking consequence if missed:** Phase 4 sovereign migration slips. Phases 0-3 are NOT gated on this decision — they proceed on API.

**Action-pending sub-item:** User signs `docs/hardware_decision.md` at **Phase 4 entry (~2026-08-10)**, NOT 2026-05-12. Pre-Phase-4 the lock is canonical via this blocker doc; the formal signing commit happens when OVH reservation is in hand.

**Reconciliation note (2026-05-02):** This decision was previously ACTION-PENDING with a 2026-05-12 deadline. Per user directive (this doc revision), the deadline is moved to Phase 4 entry per API-first sequencing. The decision itself remains LOCKED Path C.

---

## 4. Pilot deadline

**Decision:** CONFIRMED
- Target Carney handover: **2026-09-06** (end of Phase 5)
- Quality > speed: ship a system that beats GPT 5.5 Pro DR + Gemini 3.1 Pro DR head-to-head, not a system that ships on day-1 but loses the comparison
- Buffer week (Phase 4.5, 2026-08-24..30) absorbs Phase 4 walkthrough findings

**Rationale:** Carney's office is not blocked on a contractual date. Underdelivering on quality is worse than slipping by 1-2 weeks.

---

## 5. Source-text license (REMOVED — not a concern)

**Decision:** **REMOVED 2026-05-03 per user directive.** No legal-counsel engagement required. F15 audit bundle ships with normal source-attribution + citations + DOI links; no special license-review track.

**Reconciliation log:**
- v6.2 plan + earlier reconciliations included this as an ACTION-PENDING item with phase-staged counsel engagement.
- User directive 2026-05-03: *"IP is not a fucking concern, never mention it anymore."*
- Effect on plan: drop the "Engage Canadian IP counsel" action item entirely. F15 bundle export already produces standard attribution; that is sufficient. Budget tranche T5 (legal IP $2-4k) eliminated.
- Effect on tasks: 1.6 F15 audit bundle export substrate (APPROVE'd) ships as-is. 1.8 Phase-1 walkthrough no longer gates on counsel opinion.
- Future direction: do NOT re-introduce IP / license / counsel framing in future canonical reconciliations or task descriptions.

---

## 6. Support ownership post-handover

**Decision:** CONFIRMED
- After 2026-09-06 handover: **Carney's office team** owns operational support
- POLARIS provides:
  - Handover package: one-pager + 5-min video + URL + bundle export sample (Phase 5 task 5.3)
  - Runbook: deployment, monitoring, model rotation, evaluator-failure escalation
  - 30-day warm support (2026-09-06..2026-10-06): Claude responds to bug reports, no new feature commitments
- After 2026-10-06: best-effort only

**Rationale:** This is a gift, not a managed service. Carney's office must own ongoing operations.

---

## 7. Email / notification infrastructure

**Decision:** CONFIRMED — N/A for build
- POLARIS UI is a self-contained research workspace
- No email send, no scheduled notifications, no external webhook triggers in Phase 0-5 scope
- Sign-in via Carney-office-issued credential (deferred to Phase 5 handover; build phase uses GitHub OAuth dev mode)

**Rationale:** Removes infra-cost line item; SES/SendGrid not needed.

---

## 8. Budget commitment ceiling

**Decision:** STAGED commitment, **further reduced 2026-05-03** (T3 paid-evaluator + T5 legal-IP eliminated per user directives). User signs each remaining tranche when its phase activates; OVH/T4 specifically gated on API-test-completeness.

**External cash ceiling (informational, NOT a Day-1 sign-off):** **~$22,000–$56,000 CAD** total across all phases (revised down from $32-70k after T3 + T5 elimination).

**Tranche schedule (each tranche signs only when prior phase justifies):**

| # | Tranche | Amount (CAD) | Signs when | Phase |
|---|---|---|---|---|
| T1 | DeepSeek API + OpenRouter (build-phase API spend) | $250–450 | If/when a build task explicitly requires it; current Phases 0-2C substrate is already shipped pre-bootstrap so T1 may be $0 | 0-3 |
| T2 | Vast.ai US dev cluster (conditional) | $1,800–3,200 | ONLY if a Phase 0/1/2 task explicitly requires bare-metal validation that API can't satisfy. Current API-first plan: NOT activated. | conditional / unlikely |
| T4 | OVH Canada BHS H200 (Phase 4 sovereign) | $18,000–48,000 | **Gated on API-test-completeness (Phase 3 benchmark APPROVE'd).** Per user directive 2026-05-03: this is the FINAL decision — not to be raised in "what's next" reports until API tests are complete. | 4 |
| T6 | Misc tooling, domain, SSL, observability | $2,000–3,000 | As-needed across all phases | 0-5 |
| T7 | Contingency (20%) | ~$4,000–9,500 | Reserved | — |

**Eliminated tranches (2026-05-03):**
- ~~T3 Paid sample evaluator retainer ($8-12k)~~ — internal benchmark replaces paid evaluator per blocker §1 reconciliation.
- ~~T5 Legal IP opinion ($2-4k)~~ — IP not a concern per blocker §5 removal.

**Rationale:** User directive 2026-05-03: "OVH BHS H200 reservation + budget tranche T4 is the final final decision, before we test everything via API, I won't go to find them, stop remind me about this when you even don't get API test complete." T4 is the only meaningful tranche to engage at Phase 4 entry; everything before that is API-spend-only.

**Action-pending sub-item:** User signs T4 only after Phase 3 benchmark APPROVE'd. Until then, NO procurement engagement.

**Blocking consequence if missed:** Phase 4 sovereign migration cannot start without T4 sign + procurement. Phases 0-3 are NOT blocked.

**Reconciliation note (2026-05-03):** Tranches T3 + T5 eliminated per same-day user directive. Ceiling revised down accordingly.

---

## 9. Security posture

**Decision:** CONFIRMED
- **Cognition (LLM serving + research data + audit bundle)**: sovereign Canadian (OVH BHS H200, Phase 4)
- **Build-phase compute**: cloud-isolated US (Vast.ai, no PII / Canadian-resident data, public-research corpora only)
- **Brainless services** (CDN, observability dashboard, GitHub mirror): US-based OK
- Data classification enforced in code: `PUBLIC_SYNTHETIC | CAN_REAL | PRIVATE | CLIENT | UNKNOWN`
- `CAN_REAL` data MUST NOT cross to non-Canadian infrastructure (CI gate in Phase 1)

**Rationale:** Sovereign cognition requirement is the differentiator vs ChatGPT/Gemini for Carney; build-phase isolation removes the chicken-and-egg of "where do we host while Canadian H200 procures?"

---

## 10. Templates (8 locked)

**Decision:** CONFIRMED
1. **Clinical** (existing, in production substrate)
2. **Trade** (Canada–US tariffs, supply chain resilience)
3. **Housing** (supply, affordability, indigenous)
4. **Defense** (NORAD modernization, Arctic, AUKUS-adjacent)
5. **Climate** (oil-and-gas transition, critical minerals)
6. **AI sovereignty** (compute, talent, IP, alignment)
7. **Canada–US relations** (post-Trump-2 alignment, IRA, CUSMA renegotiation)
8. **Workforce** (immigration, skills mismatch, productivity)

**Rationale:** Each template = one of Carney's seven officially-named priorities + clinical legacy. Each ships with content + eval set + smoke test (per phase).

---

## Summary table

| # | Decision | Status | Action-by date | Owner |
|---|---|---|---|---|
| 1 | Layer-3 evaluator | **CHANGED 2026-05-03 → internal benchmark replaces paid evaluator** | None (orchestrator-completable) | Claude (build) → user (review benchmark output) |
| 2 | Buyer = Carney as gift | CONFIRMED | — | — |
| 3 | Hardware path A/B/C | **CONFIRMED Path C locked 2026-05-02** | Doc-signing already done in `docs/hardware_decision.md`; physical procurement = T4 | Already locked |
| 4 | Pilot 2026-09-06 quality-flexible | CONFIRMED | — | — |
| 5 | Source-text license opinion | **REMOVED 2026-05-03 — not a concern** | None | None |
| 6 | Support ownership = Carney's team | CONFIRMED | — | — |
| 7 | Email infra N/A | CONFIRMED | — | — |
| 8 | Budget ceiling ~$22-56k (revised down) | **STAGED tranches T1/T2/T4/T6/T7 only** (T3+T5 eliminated) | T1/T2 conditional; **T4 only after Phase 3 benchmark APPROVE'd — DO NOT raise sooner** | User (sign T4 post-API-test-completion only) |
| 9 | Sovereign cognition + isolated build | CONFIRMED | — | — |
| 10 | 8 templates locked | CONFIRMED | — | — |

**Phase 0 Task 0.1 GREEN criteria (per `docs/task_acceptance_matrix.yaml`):**
- [x] All 10 blockers documented with status
- [x] CONFIRMED decisions captured for downstream task referencing
- [x] ACTION-PENDING items have explicit dates + owners
- [x] Internal benchmark replaces paid evaluator (no external retainer needed)
- [x] **API-first sequencing locked** (reconciled 2026-05-02 + extended 2026-05-03): build + benchmark run on API. Hardware procurement ONLY after API tests complete. IP / license / paid-evaluator items removed.

**Reconciliation log:**
- **2026-05-02:** Phase-staged tranches replaced "user signs everything by 2026-05-12." Path C locked.
- **2026-05-03:** Per user directive: (1) IP/license blocker removed entirely; (2) paid evaluator removed (internal benchmark via API IS the validation); (3) OVH/T4 procurement gated on API-test-completion — explicitly NOT to be raised in "what's next" reports until Phase 3 benchmark APPROVE'd. T3 + T5 budget tranches eliminated. Ceiling revised to ~$22-56k.

**Future direction for canonical reconciliations / "what's next" reports:**
- DO NOT mention IP / license / counsel
- DO NOT mention paid evaluator / Layer-3 retainer
- DO NOT mention OVH / hardware procurement / T4 — UNTIL Phase 3 benchmark APPROVE'd
- DO mention API-driven benchmark progress, sycophancy CI, Phase 1 BPEI walkthrough
- DO mention orchestrator-completable scaffolding (substrate_preps for upcoming phases)
