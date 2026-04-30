# POLARIS v1.0 — Release Notes

**Release date:** 2026-04-30
**Status:** Pilot-ready (SOC2 dry-run GREEN, M-LIVE-1..4 LOCKED)

---

## What's new in v1.0

### Phase E — Integration substrates (12 substrates LOCKED via Codex audit loop)

POLARIS V19 ships every Phase D substrate wired into the production audit pipeline:

| Substrate | What it does | Rollback flag |
|---|---|---|
| M-INT-0a | Decision telemetry on scope-gate decisions | `PG_RECORD_DECISIONS` |
| M-INT-0b | Model pin capture on every sweep run | `PG_CAPTURE_PIN` |
| M-INT-1 | Parallel evidence fetch in live_retriever | `PG_USE_PARALLEL_FETCH` |
| M-INT-2 | Cache warming around sweep entry | `PG_USE_CACHE_WARMING` |
| M-INT-3 | Freshness detector + cache eviction | `PG_USE_FRESHNESS_DETECTOR` |
| M-INT-4 | LLM-based scope classification | `PG_USE_LLM_SCOPE` |
| M-INT-5 | Multi-domain router | `PG_USE_DOMAIN_ROUTER` |
| M-INT-6 | LLM-augmented inductor + operator review queue | `PG_USE_AUTO_INDUCTION` |
| M-INT-7 | Billing quota gating | `PG_USE_BILLING_QUOTA` |
| M-INT-8 | Slide deck export endpoint | `PG_USE_SLIDE_DECK_ENDPOINT` |
| M-INT-9 | Contract drafting endpoint | `PG_USE_CONTRACT_DRAFT_ENDPOINT` |
| M-INT-10 | Narrow private-corpus connector (Drive) | `PG_USE_DRIVE_CONNECTOR_ENDPOINT` |
| M-INT-11 | Customer support ticket flow | `PG_USE_SUPPORT_TICKET_ENDPOINT` |

### Phase F — Live audit + BEAT-BOTH (4 milestones LOCKED)

- **M-LIVE-1** — V19 single-query end-to-end smoke (13/13 substrates fired, $0.0067/run, 13 min wallclock)
- **M-LIVE-2** — BEAT-BOTH head-to-head driver vs ChatGPT DR + Gemini DR
- **M-LIVE-3** — Operator dashboard (3 endpoints exposing decision aggregates, freshness aggregates, pin trends)
- **M-LIVE-4** — M-D9 regression-lab CI gate (GREEN/YELLOW → merge OK; RED → block)

### Phase H — Production hardening (in progress)

- **M-PROD-1** ✓ — SOC2 dry-run audit (21/21 evidence references intact)
- **M-PROD-3** ✓ — Production observability (`/api/inspector/metrics` endpoint)
- M-PROD-2, M-PROD-4 — pending

### Quality gates

- **Two-family evaluator**: generator and evaluator from different training lineages (enforced at construction)
- **Provenance tokens**: every generated sentence carries `[#ev:<id>:<start>-<end>]`
- **Strict verify**: per-sentence numeric + content-word overlap check
- **Zero-verified abort**: if every section fails verification, `report.md` is a verdict artifact, not a pseudo-report
- **Budget cap**: per-run cost ceiling (`PG_MAX_COST_PER_RUN`)
- **Delimiter sanitization**: prompt-injection defense for evidence text

---

## Supported domains (5 scope templates)

POLARIS v1.0 ships with 5 curated scope templates — research questions outside these domains route via `M-INT-5` to a fallback path or are flagged for operator review.

| Template | Domain | Coverage |
|---|---|---|
| `clinical.yaml` | Clinical efficacy + safety | Drug trials, regulatory submissions, comparative therapeutics |
| `due_diligence.yaml` | Investment due diligence | Company financials, market sizing, competitive landscape |
| `policy.yaml` | Public policy + regulation | Legislative analysis, agency guidance, comparative policy |
| `tech.yaml` | Technology + engineering | Software architecture, deployment patterns, comparative tech analysis |
| `custom.yaml` | User-defined | Operator-driven scope; requires explicit definition |

---

## Out-of-scope (explicit)

POLARIS v1.0 deliberately does NOT support:

- **Real-time / streaming research questions** — minimum 5-minute wallclock per query
- **Pure opinion or recommendation tasks** — POLARIS produces evidence-bound prose, not advice
- **Questions requiring private/non-licensed data** — narrow private corpus support exists (`M-INT-10`) but is org-scoped and requires explicit data provisioning
- **Multi-step reasoning chains > 3 hops** — V19 is single-query; multi-query reasoning is M-LIVE-2's BEAT-BOTH dimension
- **Languages other than English** — extraction + scoring substrates assume English prose; multilingual support is post-v1.0

---

## Breaking changes vs v0.x

- Output layout: `outputs/m_live_1_smoke/run_<timestamp>/` (was `outputs/m_live_1_smoke/clinical/...`)
- Substrate count: 13 (M-INT-0a + 0b + 1..11), not 12 — `smoke_manifest.expected_substrates: 13`
- BEAT-BOTH verdict: `N/A` is now a possible verdict (was `TIE` for triple-zero dimensions)

---

## Pricing tier

Per `docs/pricing_and_positioning.md`: **workspace/pilot tier** at $TBD (refused $20/mo entry-level per locked positioning).

---

## Known limitations

- **claim_frames BEAT-BOTH dimension**: extraction of N + baseline + endpoint + CI from prose is regex-based in v1.0; LLM-based extraction deferred to v1.1
- **Pin trends org-scoping**: pin files do not carry `org_id` in v1.0; auth gates dashboard access but per-org pin filtering is best-effort. Closes when M-INT-0b v2 adds org_id to capture path
- **CI workflow YAML**: `.github/workflows/m_live_4_regression_gate.yml` deferred to user-side push (OAuth `workflow` scope required)

---

## Migration guide (pilot → v1.0)

```bash
# 1. Pull latest
git pull origin polaris

# 2. Verify SOC2 evidence intact
python scripts/run_m_prod_1_soc2_dry_run.py
# Expect: 21/21 intact, exit 0

# 3. Run regression gate against your baseline
python scripts/run_m_live_4_regression_gate.py
# Expect: verdict=GREEN, exit 0

# 4. Smoke single query end-to-end
python scripts/run_m_live_1_smoke.py
# Expect: 13/13 substrates fired, all_phase_e_fired=true

# 5. Score against competitors (optional)
python scripts/run_m_live_2_beat_both.py
# Output: outputs/m_live_2_beat_both/manifest.json
```

---

## Acknowledgements

This release includes 14+ Codex review rounds across 4 Phase F milestones, surfacing 17 P0/P1 findings closed via the autoloop V3 lean brief format.
