# POLARIS v6.2 — Blocker Decisions Register

**Last updated:** 2026-05-02 (canonical reconciliation per Plan v13 §A Step 0a)
**Owning task:** Phase 0 Task 0.1
**Plan reference:** `docs/carney_delivery_plan_v6_2.md` (renamed from `_FINAL.md` 2026-05-02)

This document fixes the 10 blocker decisions surfaced during v6 planning. Each decision is either **CONFIRMED** (user direction is durable, build proceeds) or **ACTION-PENDING** (an external procurement / signature must complete before a downstream task can GREEN).

---

## 1. Validation roles (paid Layer-3 evaluator)

**Decision:** CONFIRMED
- Layer 1 = automated CI gates (sycophancy, refusal, contradiction, citation)
- Layer 2 = product-owner walkthroughs (user runs in fresh browser within 48h, recorded)
- Layer 3 = **mandatory paid sample evaluator** with fail authority on Phase 3 benchmark

**Rationale:** Without an independent paid evaluator with fail authority, the Phase 3 head-to-head benchmark vs ChatGPT 5.5 Pro DR + Gemini 3.1 Pro DR has no external legitimacy when delivered to Carney's office.

**Action-pending sub-item:** Sourcing initiated this task. Candidate pool: Canadian academic policy researchers (Munk School, IRPP, CIGI) + one US benchmark-services firm for redundancy. Retainer must be signed by **2026-07-15** (4 weeks before Phase 3 benchmark run begins 2026-07-20).

**Blocking consequence if missed:** Phase 3 cannot GREEN; benchmark is internal-only.

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

## 5. Source-text license (bundle redistribution)

**Decision:** ACTION-PENDING (Phase-1/2 legal review — Plan v13 §G #5). **NOT a Phase-0 / Day-1 gate** per user directive (reconciled 2026-05-02).
- Audit bundle (F15) embeds source spans from cited documents
- For PUBLIC government / open-licensed sources: bundle redistribution is permitted
- For COPYRIGHTED journal / paywalled sources: legal review required before bundle export of full spans
- **Halt-and-decide branch (NOT a silent fallback per Plan v13 §F):** if counsel opinion is unavailable by the F15-evaluator-walkthrough deadline (Phase 1 close, target 2026-06-04), the orchestrator halts at the relevant Phase 1 / 2 task per Plan v13 §H halt-condition #5. User explicitly authorizes one of: (a) ship F15 with verbatim spans for PUBLIC sources only + citations + DOI links for COPYRIGHTED (the lower-fidelity branch), (b) delay F15 until counsel opinion lands, or (c) revise canonical via signed reconciliation commit. Whatever the user authorizes is documented in `outputs/audits/halt_resolutions/<task_id>.md` and is not a silent degradation.

**Rationale:** Bundle's value to Carney's office depends on traceability; verbatim spans for paywalled sources may require fair-use opinion or licensing.

**Action-pending sub-item:** Engage Canadian intellectual-property counsel during **Phase 1** (May 13-31), with opinion in hand before the F15 walkthrough at Phase-1 close. NOT before Phase 0 closes.

**Sequencing note (reconciled 2026-05-02):** This is a Phase-1-timing item, not a Day-1 user action. POLARIS does not need counsel opinion to BUILD F15 substrate (already shipped pre-bootstrap as task 1.6); counsel opinion gates only the bundle-export-with-verbatim-spans behavior at Phase-1 walkthrough.

**Blocking consequence if missed:** Halt at the F15 walkthrough task; user resolves per the three branches above. F15 cannot ship with auto-degraded behavior. Phases 0-1 build proceed regardless.

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

**Decision:** STAGED commitment (user signs each tranche when its phase activates). **Day-1 ceiling commitment removed per user directive (reconciled 2026-05-02) — staged-commit replaces all-at-once.**

**External cash ceiling (informational, NOT a Day-1 sign-off):** **$32,000–$70,000 CAD** total across all phases.

**Tranche schedule (each tranche signs only when prior phase justifies):**

| # | Tranche | Amount (CAD) | Signs when | Phase |
|---|---|---|---|---|
| T1 | DeepSeek API + OpenRouter (build-phase API spend) | $250–450 | If/when a build task explicitly requires it; current Phases 0-2C substrate is already shipped pre-bootstrap so T1 may be $0 | 0-3 |
| T2 | Vast.ai US dev cluster (conditional) | $1,800–3,200 | ONLY if a Phase 0/1/2 task explicitly requires bare-metal validation that API can't satisfy | conditional |
| T3 | Paid sample evaluator retainer | $8,000–12,000 | Phase 3 entry (~2026-07-15) | 3 |
| T4 | OVH Canada BHS H200 (Phase 4 sovereign) | $18,000–48,000 | Phase 4 entry (~2026-08-10), gated on Phase 3 benchmark APPROVE | 4 |
| T5 | Legal IP opinion | $2,000–4,000 | Phase 1 (during build, before F15 walkthrough) | 1 |
| T6 | Misc tooling, domain, SSL, observability | $2,000–3,000 | As-needed across all phases | 0-5 |
| T7 | Contingency (20%) | $5,000–12,000 | Reserved | — |

**Rationale:** User must NOT commit the full $32-70k on Day 1 with API-level validation unproven. Each tranche is justified by its phase's prerequisite results (Phase 3 benchmark must show match-or-beat before Phase 4 hardware procurement; Phase 1 F15 must be evaluator-validated before legal IP spend, etc.). This is API-first sequencing per the user directive.

**Action-pending sub-item:** User signs each tranche **at its phase entry**, NOT all at once on 2026-05-12. T1/T2 may be $0 if existing API budgets cover; T3-T4 sign at Phase 3 / Phase 4 entry respectively.

**Blocking consequence if missed:** Each tranche's phase cannot start until its tranche signs. Phases 0-1 are currently un-blocked because no tranche signature is required for them yet (substrate already shipped).

**Reconciliation note (2026-05-02):** The "user signs $32-70k by 2026-05-12" framing in the original doc was over-aggressive — it presumed all phases would commit cash on Day 1. Per user directive, the staged-tranche schedule replaces it.

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
| 1 | Layer-3 evaluator + sourcing | CONFIRMED + sourcing initiated | Retainer signed by Phase 3 entry (~2026-07-15) | Claude (research) → user (sign) |
| 2 | Buyer = Carney as gift | CONFIRMED | — | — |
| 3 | Hardware path A/B/C | **CONFIRMED Path C locked 2026-05-02**; doc signing deferred to Phase 4 entry | ~2026-08-10 (Phase 4 entry) | User (sign at Phase 4) |
| 4 | Pilot 2026-09-06 quality-flexible | CONFIRMED | — | — |
| 5 | Source-text license opinion | ACTION-PENDING (Phase 1 timing, NOT Day-1) | Before F15 walkthrough at Phase 1 close (~2026-06-04) | User (engage counsel) |
| 6 | Support ownership = Carney's team | CONFIRMED | — | — |
| 7 | Email infra N/A | CONFIRMED | — | — |
| 8 | Budget ceiling $32-70k | **STAGED tranches** (T1-T7); each signs at its phase entry | T1/T2 conditional; T3 ~2026-07-15; T4 ~2026-08-10; T5 during Phase 1 | User (sign each tranche) |
| 9 | Sovereign cognition + isolated build | CONFIRMED | — | — |
| 10 | 8 templates locked | CONFIRMED | — | — |

**Phase 0 Task 0.1 GREEN criteria (per `docs/task_acceptance_matrix.yaml`):**
- [x] All 10 blockers documented with status
- [x] CONFIRMED decisions captured for downstream task referencing
- [x] ACTION-PENDING items have explicit dates + owners
- [x] Layer-3 evaluator candidate list initiated (sourcing in progress; retainer at Phase 3 entry, NOT Phase 0)
- [x] **API-first sequencing locked** (reconciled 2026-05-02): #3 hardware, #5 license, #8 budget are NOT Phase 0 gates per user directive. They ship at their phase-correct entry points.

**Reconciliation log (2026-05-02):** The original "User commits #3, #5, #8 by Phase 0 end (2026-05-12)" line was over-aggressive — it conflated the cycle-11 LOCKED Path C decision with a procurement signature, and treated the staged $32-70k ceiling as a Day-1 commit. Per user directive, all three are now phase-staged (Path C signing at Phase 4 entry; license counsel during Phase 1; budget as tranches). Phases 0-1 substrate is unblocked; build proceeds on API.
