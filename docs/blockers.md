# POLARIS v6.2 — Blocker Decisions Register

**Last updated:** 2026-05-01
**Owning task:** Phase 0 Task 0.1
**Plan reference:** `docs/carney_delivery_plan_FINAL.md`

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

**Decision:** ACTION-PENDING (commitment in Task 0.6)
- **Build phase**: Vast.ai US 4× H100 dev cluster (decided this task; provisioned in Task 0.3)
- **Sovereign migration**: A/B/C committed in Task 0.6, default **Path C V4 Flash only** (8× H200 OVH Canada BHS)
  - Path A: 16× H200 FP8 V4 Pro full (capacity for 5+ concurrent sessions)
  - Path B: 8× H200 reduced V4 Pro (capacity for 2 concurrent sessions)
  - Path C: 8× H200 V4 Flash only (capacity for 5+ concurrent sessions, slightly lower quality)

**Rationale:** Capacity vs cost vs quality trade-off cannot be locked until Task 0.6 (DeepSeek V4 head-to-head between V4 Pro and V4 Flash on 8 templates).

**Blocking consequence if missed:** Task 0.9 (OVH BHS H200 procurement) cannot start; Phase 4 sovereign migration slips.

---

## 4. Pilot deadline

**Decision:** CONFIRMED
- Target Carney handover: **2026-09-06** (end of Phase 5)
- Quality > speed: ship a system that beats GPT 5.5 Pro DR + Gemini 3.1 Pro DR head-to-head, not a system that ships on day-1 but loses the comparison
- Buffer week (Phase 4.5, 2026-08-24..30) absorbs Phase 4 walkthrough findings

**Rationale:** Carney's office is not blocked on a contractual date. Underdelivering on quality is worse than slipping by 1-2 weeks.

---

## 5. Source-text license (bundle redistribution)

**Decision:** ACTION-PENDING (Phase 1/2 legal review)
- Audit bundle (F15) embeds source spans from cited documents
- For PUBLIC government / open-licensed sources: bundle redistribution is permitted
- For COPYRIGHTED journal / paywalled sources: legal review required before bundle export of full spans
- Fallback: bundle exports verbatim spans for PUBLIC sources, citations + DOI links only for COPYRIGHTED sources

**Rationale:** Bundle's value to Carney's office depends on traceability; verbatim spans for paywalled sources may require fair-use opinion or licensing.

**Action-pending sub-item:** Engage Canadian intellectual-property counsel by **2026-05-31** (end of Phase 1) to issue opinion before Phase 1 walkthrough.

**Blocking consequence if missed:** F15 ships with citation-only fallback for COPYRIGHTED sources, with disclosure in handover package.

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

**Decision:** ACTION-PENDING (user signature)
- External cash ceiling: **$32,000–$70,000 CAD**
- Build-phase compute (Vast.ai US): ~$1,800–3,200 (cluster on-demand only during test runs)
- DeepSeek API for V4 Pro testing during build: ~$250–450
- OVH Canada BHS H200 (Phase 4 sovereign): $18,000–48,000 depending on Path A/B/C and 6-month vs 12-month commit
- Paid sample evaluator retainer: ~$8,000–12,000
- Legal IP opinion: ~$2,000–4,000
- Misc tooling, domain, SSL, observability: ~$2,000–3,000

**Rationale:** User must commit ceiling before Phase 0 Task 0.9 (OVH procurement) can execute.

**Action-pending sub-item:** User signs commitment by **2026-05-12** (end of Phase 0).

**Blocking consequence if missed:** Phase 0 cannot GREEN as a whole; Phase 1 cannot start.

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
| 1 | Layer-3 evaluator + sourcing | CONFIRMED + sourcing initiated | Retainer signed 2026-07-15 | Claude (research) → user (sign) |
| 2 | Buyer = Carney as gift | CONFIRMED | — | — |
| 3 | Hardware path A/B/C | ACTION-PENDING (Task 0.6 decision) | 2026-05-12 | Claude (data) → user (commit) |
| 4 | Pilot 2026-09-06 quality-flexible | CONFIRMED | — | — |
| 5 | Source-text license opinion | ACTION-PENDING | 2026-05-31 | User (engage counsel) |
| 6 | Support ownership = Carney's team | CONFIRMED | — | — |
| 7 | Email infra N/A | CONFIRMED | — | — |
| 8 | Budget ceiling $32-70k | ACTION-PENDING | 2026-05-12 | User (sign) |
| 9 | Sovereign cognition + isolated build | CONFIRMED | — | — |
| 10 | 8 templates locked | CONFIRMED | — | — |

**Phase 0 Task 0.1 GREEN criteria (per `docs/task_acceptance_matrix.yaml`):**
- [x] All 10 blockers documented with status
- [x] CONFIRMED decisions captured for downstream task referencing
- [x] ACTION-PENDING items have explicit dates + owners
- [ ] Layer-3 evaluator candidate list initiated (in progress; sourcing this task)
- [ ] User commits #3, #5, #8 by Phase 0 end (blocking next-phase entry)
