# Joint plan v3 — POLARIS from today to fully functional online

**Author:** Claude (Opus 4.7), drafting WITH Codex (gpt-5.4 xhigh).
**Date:** 2026-04-29.
**Round:** 3 — closing Codex round-2 single-finding (M-24 missing).

Round-2 Codex verdict was PARTIAL with one HIGH:
> "M-24 / audit_ir/support_ticket_store.py is still unplanned.
> Section A.2 lists it as substrate-only late Phase C module,
> but Phases E0-E4/F never assign it an integration milestone."

Round-2 Codex final word:
> "The remaining fix is narrow: add an explicit M-24 integration
> milestone in Phase E4, or explicitly de-scope M-24 from the
> 'fully functional online' finish line and update A.2/C
> accordingly. After that, this roadmap is green."

v3 chose the integration option. M-24 becomes M-INT-11 in
Phase E4. No other changes from v2.

---

## Phase E4 — Late Phase C wiring (UPDATED, +1 milestone)

**Phase E4 day total revised:** 8-10 → **10-12 days** (+2 for
M-INT-11).

**M-INT-7 — M-NEW billing/quota gating** (3 days) [unchanged]
**M-INT-8 — M-22 slide deck endpoint** (2 days) [unchanged]
**M-INT-9 — M-26 contract drafting endpoint** (2 days) [unchanged]
**M-INT-10 — M-25 connector v2** (3 days, narrow) [unchanged]

**M-INT-11 — M-24 customer support flow integration** (2 days) [NEW v3]
- Wire `audit_ir/support_ticket_store.py` into the inspector
  router with a minimal ticket-CRUD surface
- Endpoints:
  - `POST /api/inspector/tickets` (create)
  - `GET /api/inspector/tickets` (list workspace-scoped)
  - `GET /api/inspector/tickets/{ticket_id}` (read)
  - `POST /api/inspector/tickets/{ticket_id}/comments` (operator
    response)
- Flag: `PG_USE_SUPPORT_TICKETS=0` disables the route
- Acceptance:
  - Customer creates ticket via UI; operator sees it in queue
  - Workspace isolation: tickets in ws_a invisible to ws_b
  - Run-log evidence: `support_ticket_store` invocation count > 0
  - Rollback flag actually disables (route returns 404)
- Codex review: workspace_id propagation, no PII in payload
  by default (operator can override for required-PII tickets),
  SOC2 audit trail intact

---

## Updated phase ETAs (D)

| Phase | Days | Weeks | Outcome |
|---|---:|---:|---|
| E0 (observability) | 5-6 | 1-1.5 | Telemetry + pinning live |
| E1 (data-plane) | 8-10 | 2-2.5 | Parallel + cache + freshness |
| E2 (decision-plane) | 6-8 | 1.5-2 | Real LLM scope + domain router |
| E3 (auto-induction) | 3-4 | 0.5-1 | Inductor in operator queue |
| E4 (Phase C wiring) | **10-12** | **2-2.5** | Billing/deck/contract/connector + **support tickets** |
| F (live audit + BEAT-BOTH) | 10-13 | 2-3 | Verdict on tier-1 |
| G (close gaps) | 20-40 | 4-8 | BEAT-BOTH on all 7 dims |
| H (pilot launch) | 22 | 3-4 | One paying pilot live |
| **Total** | **84-115** | **14-23** | **Fully online + tier-1 parity** |

(Total range slightly widened: 14-22 → 14-23 weeks for the +2
days E4 increase, propagated to upper bound.)

---

## Coverage check (every A.2 substrate now has an
integration milestone)

| A.2 substrate | Phase E milestone |
|---|---|
| M-D1 validation set | M-INT-6 (E3) — runs as CI test on every release |
| M-D2 phase a/b inductor | M-INT-6 (E3) — wired into operator-review queue |
| M-D3 phase 1+2 telemetry | M-INT-0a (E0) |
| M-D5 phase 1+2 scope+LLM | M-INT-4 (E2) |
| M-D6 phase 1 domain router | M-INT-5 (E2) |
| M-D7 phase 1+2 cache+warming | M-INT-2 (E1) |
| M-D8 phase 1 parallel fetch | M-INT-1 (E1) |
| M-D9 phase 1 regression lab | M-LIVE-4 (F) — CI gate |
| M-D9 phase 2 BEAT-BOTH scoring | M-LIVE-2 (F) — head-to-head |
| M-D10 phase 1+2 freshness | M-INT-3 (E1) |
| M-D11 phase 1+2+v2 pin+replay+trends | M-INT-0b (E0) + M-LIVE-3 (F, trends panel) |
| M-NEW billing/quota | M-INT-7 (E4) |
| M-22 slide deck | M-INT-8 (E4) |
| M-24 support ticket | **M-INT-11 (E4)** [v3 NEW] |
| M-25 private corpus sync | M-INT-10 (E4) |
| M-26 contract drafting | M-INT-9 (E4) |

**21 substrate modules → 21 integration milestones.** Every
A.2 module now has a named milestone, acceptance criterion,
and rollback flag. Coverage gap from round-2 is closed.

---

## All other sections (unchanged from v2)

Sections A.1, A.3, A.4, B (wishlist), and all other Phase E0,
E1, E2, E3, F, G, H content + risks remain identical to v2.
Only delta is M-INT-11 + the day-total update + the coverage
check.

---

## Codex output requested for round 3

Sign as canonical roadmap, or list residual fixes.

Output format:

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Round-2 fix integration
- [x/ ] HIGH M-24 explicit integration milestone (M-INT-11) added in E4
- [x/ ] A.2 ↔ Phase E milestone coverage table added

## New findings (if any)
[SEVERITY] specific finding

## Final word
[Sign or list residual fixes]
```

Tool hints:
- DO NOT run rg/find — state already audited.
- DO NOT run pytest — planning review only.
- v2 brief at `outputs/codex_findings/full_online_plan_round2/brief.md`
  for diff comparison.
