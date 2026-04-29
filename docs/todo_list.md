# POLARIS Todo List

**Last Updated:** 2026-04-29 (canonical roadmap GREEN-signed by
Claude+Codex, 3 review rounds, locked at `docs/full_online_plan_FINAL.md`)

## ACTIVE: From-today-to-fully-online integration autoloop

The canonical plan is `docs/full_online_plan_FINAL.md` (Claude+Codex
v4 GREEN). Todo items below are sequenced per that plan. Every
milestone runs through the Claude+Codex autoloop:

  1. Claude builds the integration → commits
  2. Claude writes a Codex review brief
  3. Codex reviews → emits GREEN | PARTIAL | BLOCKED
  4. If PARTIAL: integrate findings → re-review (no human needed)
  5. If GREEN: lock + move to next milestone (no human needed)
  6. If BLOCKED: pause + flag user (the only human-intervention case)

Stop conditions per `feedback_autoloop_default_behavior.md` /
`feedback_dont_pause_autoloop.md`:
- BLOCKED verdict from Codex (substantive impossibility)
- Asymptote: 5+ codex rounds with no convergence on the same surface
- Primary-source conflict (Codex finds something contradicting locked memory)
- Cost concern (per-day OpenRouter spend exceeds budget)

Otherwise the autoloop continues without per-round confirmation.

---

## Phase E0 — Observability & repro prerequisites

| ID | Milestone | Days | Rollback flag | Status |
|---|---|---:|---|---|
| **M-INT-0a** | Decision telemetry recording (M-D3 → production) | 2-3 | `PG_RECORD_DECISIONS` | **NEXT** |
| M-INT-0b | Pin capture on every run (M-D11 → production) | 2-3 | `PG_CAPTURE_PIN` | pending |

## Phase E1 — Data-plane integration

| ID | Milestone | Days | Rollback flag | Status |
|---|---|---:|---|---|
| M-INT-1 | Parallel fetch into live_retriever | 3 | `PG_USE_PARALLEL_FETCH` | pending |
| M-INT-2 | Cache + cache-warming around sweep | 3 | `PG_USE_CACHE_WARMING` | pending |
| M-INT-3 | Freshness detector + eviction | 4 | `PG_USE_FRESHNESS_DETECTOR` | pending |

## Phase E2 — Decision-plane integration

| ID | Milestone | Days | Rollback flag | Status |
|---|---|---:|---|---|
| M-INT-4 | OpenRouter ScopeAffinityLLM | 3 | `PG_USE_LLM_SCOPE` | pending |
| M-INT-5 | Domain router into live retrieval | 4 | `PG_USE_DOMAIN_ROUTER` | pending |

## Phase E3 — Auto-induction surfacing

| ID | Milestone | Days | Rollback flag | Status |
|---|---|---:|---|---|
| M-INT-6 | LLMAugmentedInductor in operator-review queue + M-D1 CI | 3-4 | `PG_USE_AUTO_INDUCTION` | pending |

## Phase E4 — Late Phase C wiring

| ID | Milestone | Days | Rollback flag | Status |
|---|---|---:|---|---|
| M-INT-7 | M-NEW billing/quota gating | 3 | `PG_ENFORCE_QUOTA` | pending |
| M-INT-8 | M-22 slide deck endpoint | 2 | `PG_USE_SLIDE_DECK_EXPORT` | pending |
| M-INT-9 | M-26 contract drafting endpoint | 2 | `PG_USE_CONTRACT_DRAFTING` | pending |
| M-INT-10 | M-25 Drive connector v2 | 3 | `PG_USE_DRIVE_CONNECTOR` | pending |
| M-INT-11 | M-24 customer support tickets | 2 | `PG_USE_SUPPORT_TICKETS` | pending |

## Phase F — End-to-end live audit + BEAT-BOTH

| ID | Milestone | Days | Status |
|---|---|---:|---|
| M-LIVE-1 | V19 single-query end-to-end smoke | 3 | pending |
| M-LIVE-2 | BEAT-BOTH head-to-head vs ChatGPT/Gemini DR | 5 | pending |
| M-LIVE-3 | Operator dashboard (Inspector aggregates) | 4 | pending |
| M-LIVE-4 | M-D9 regression-lab CI gate | 1 | pending |

## Phase G — Close BEAT-BOTH gaps (indeterminate, 4-8 weeks)

Each dimension where V_N is BEHIND or BEAT-ONE → concrete fix
milestone. Likely candidates (not yet milestoned, named after
M-LIVE-2 verdict surfaces actual gaps):
- dim 1 (unique_citations) — connector expansion + concurrency tuning
- dim 2 (regulatory_coverage) — V34 expansion + M-D6 phase 2 adapters
- dim 6 (contradiction_handling_grammar) — synthesizer hedging upgrade
- dim 7 (narrative_length) — synthesis capacity tuning

## Phase H — Production hardening + pilot launch

| ID | Milestone | Days | Status |
|---|---|---:|---|
| M-PROD-1 | SOC2 dry-run + remediation | 10 | pending |
| M-PROD-2 | First paying pilot customer | 5 | pending |
| M-PROD-3 | Production observability | 5 | pending |
| M-PROD-4 | Public release notes + supported-scope page | 2 | pending |

---

## Total ETA

84-115 engineering days = **14-23 calendar weeks** to fully online +
tier-1 BEAT-BOTH parity + first paying pilot.

## Acceptance bar (every Phase E milestone)

Codex verifies all 4:
1. Substrate is **imported** by the named production file (grep)
2. Substrate is **invoked** at the import site (grep)
3. **Run-log evidence**: real run shows non-zero invocation count
4. **Rollback flag** actually disables the new path

"Imported but unused" doesn't pass. Locked memory rule:
`feedback_substrate_is_not_product.md`.
