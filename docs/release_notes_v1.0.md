# POLARIS v1.0 — Release Notes

**Release date:** 2026-04-30
**Status:** Pilot-ready (SOC2 dry-run GREEN, M-LIVE-1..4 LOCKED, 4 of 7 BEAT-BOTH dimensions)

---

## What's new in v1.0

### Phase E — Integration substrates (13 substrates LOCKED via Codex audit loop)

POLARIS V19 ships every Phase D substrate wired into the production audit pipeline:

| Substrate | What it does | Rollback flag |
|---|---|---|
| M-INT-0a | Decision telemetry on scope-gate decisions | `PG_RECORD_DECISIONS` |
| M-INT-0b | Model pin capture on every sweep run | `PG_CAPTURE_PIN` |
| M-INT-1 | Parallel evidence fetch in live_retriever | `PG_USE_PARALLEL_FETCH` |
| M-INT-2 | Cache warming around sweep entry | `PG_USE_CACHE_WARMING` |
| M-INT-3 | Freshness detector + cache eviction | `PG_USE_FRESHNESS_DETECTOR` |
| M-INT-4 | LLM-based scope classification (telemetry-only in v1.0) | `PG_USE_LLM_SCOPE` |
| M-INT-5 | Multi-domain router (telemetry-only in v1.0) | `PG_USE_DOMAIN_ROUTER` |
| M-INT-6 | LLM-augmented inductor + operator review queue | `PG_USE_AUTO_INDUCTION` |
| M-INT-7 | Billing quota gating | `PG_USE_BILLING_QUOTA` |
| M-INT-8 | Slide deck export endpoint | `PG_USE_SLIDE_DECK_ENDPOINT` |
| M-INT-9 | Contract drafting endpoint | `PG_USE_CONTRACT_DRAFT_ENDPOINT` |
| M-INT-10 | Narrow private-corpus connector (Drive) | `PG_USE_DRIVE_CONNECTOR_ENDPOINT` |
| M-INT-11 | Customer support ticket flow | `PG_USE_SUPPORT_TICKET_ENDPOINT` |

**13 substrates total** (M-INT-0a + M-INT-0b + M-INT-1..11). Counted as 13 in `smoke_manifest.expected_substrates` and `outputs/m_live_1_smoke/run_*/smoke_manifest.json`.

### Phase F — Live audit + BEAT-BOTH (4 milestones LOCKED)

- **M-LIVE-1** — V19 single-query end-to-end smoke (13/13 substrates fired, $0.0050/run, ~13 min wallclock)
- **M-LIVE-2** — BEAT-BOTH head-to-head driver vs ChatGPT DR + Gemini DR
- **M-LIVE-3** — Operator dashboard (3 endpoints exposing decision aggregates, freshness aggregates, pin trends)
- **M-LIVE-4** — M-D9 regression-lab CI gate (GREEN/YELLOW → merge OK; RED → block)

### Phase G — BEAT-BOTH gap closure (in progress)

Full-scale POLARIS run vs ChatGPT DR + Gemini DR shows **4 of 7 dimensions BEAT-BOTH**:

| Dimension | POLARIS | ChatGPT | Gemini | Verdict |
|---|---:|---:|---:|---|
| structural_depth | 28 | 0 | 0 | BEAT-BOTH ✓ |
| jurisdictional_precision | 4 | 2 | 2 | BEAT-BOTH ✓ |
| unique_citations | 479 | 20 | 43 | BEAT-BOTH ✓ |
| regulatory_coverage | 49 | 4 | 10 | BEAT-BOTH ✓ |
| narrative_length | 2346 | 4830 | 6835 | BEHIND-BOTH |
| contradiction_handling_grammar | 3 | 27 | 18 | BEHIND-BOTH |
| claim_frames | 0 | 0 | 0 | N/A |

Remaining 2 BEHIND-BOTH dimensions (narrative_length, contradiction_handling_grammar) are synthesizer-side gaps requiring V_N+1 capacity tuning. claim_frames is N/A on regex extraction; LLM extraction is post-v1.0.

### Phase H — Production hardening

- **M-PROD-1** ✓ LOCKED — SOC2 dry-run audit (28/28 evidence references intact + route validation)
- **M-PROD-3** ✓ LOCKED — Production observability (`/api/inspector/metrics` endpoint with substrate counters + p50/p95/p99 latency)
- **M-PROD-4** in progress — this document
- **M-PROD-2** sales-blocked — first paying pilot customer requires real engagement

### Quality gates

- **Two-family evaluator**: generator and evaluator from different training lineages (enforced at construction)
- **Provenance tokens**: every generated sentence carries `[#ev:<id>:<start>-<end>]`
- **Strict verify**: per-sentence numeric + content-word overlap check
- **Zero-verified abort**: if every section fails verification, `report.md` is a verdict artifact, not a pseudo-report
- **Budget cap**: per-run cost ceiling (`PG_MAX_COST_PER_RUN`)
- **Delimiter sanitization**: prompt-injection defense for evidence text

---

## Public template surface (3 clinical variants)

POLARIS v1.0 actually ships **3 curated templates** registered in `src/polaris_graph/audit_ir/template_catalog.py:520`. The 5 YAML configs in `config/scope_templates/` (clinical, due_diligence, policy, tech, custom) are scaffolding for future expansion — only `clinical` is wired through the production routing path in v1.0.

| Template | Public ID | Coverage in v1.0 |
|---|---|---|
| Clinical (general) | `v30_clinical` | Drug trial efficacy + safety, comparative therapeutics, regulatory submissions |
| Clinical oncology | `v30_clinical_oncology` | Oncology drug efficacy + safety, biomarker outcomes |
| Clinical cardiovascular | `v30_clinical_cardio` | Cardiovascular outcomes, MACE endpoints |

The `M-INT-4` LLM scope classifier and `M-INT-5` domain router run in **telemetry-only mode in v1.0** (see `scripts/run_honest_sweep_r3.py:1055-1097`). They observe and log routing decisions but do not gate retrieval. Production routing decisions are made by the curated `template_classifier`. M-INT-4/5 enforcement is a v1.1 milestone.

The 5 YAML scope templates in `config/scope_templates/` are **non-public** in v1.0 — they exist as data scaffolding for future template additions but the public catalog (`TEMPLATE_CATALOG`) only enumerates the 3 clinical variants above.

---

## Out-of-scope (not enforced by v1.0 substrates)

The original v1 release notes claimed M-INT-4/5 enforce non-English refusal and >3-hop reasoning refusal. **Neither is true in v1.0.** What v1.0 actually does:

- Non-English questions: scope_gate copies the `language` field from the protocol but does not auto-refuse. Operator review can flag.
- Multi-hop questions: no hop-count logic anywhere in `domain_router.py`. Single-query semantics enforced by the `--only` argument; multi-step is up to the caller.
- Real-time / streaming: minimum 5-minute wallclock per query is structural, not policy-enforced
- Patient-specific medical advice: no automated refusal in v1.0; operator review responsibility

For an honest refusal matrix backed by actual code, see `docs/supported_scope.md`.

---

## Breaking changes vs v0.x

- Output layout: `outputs/m_live_1_smoke/run_<timestamp>/` (was `outputs/m_live_1_smoke/clinical/...`)
- Substrate count: 13 (M-INT-0a + 0b + 1..11), not 12 — `smoke_manifest.expected_substrates: 13`
- BEAT-BOTH verdict: `N/A` is now a possible verdict (was `TIE` for triple-zero dimensions)

---

## Pricing tier

Per `docs/pricing_and_positioning.md`:

| Tier | Annual contract | Use case |
|---|---|---|
| **Pilot** | $30k–$80k | Single-team evaluation in regulated org (50 audit runs/mo, 5 workspaces, 60-day eval) |
| **Startup** | $120k–$240k | Small biotech / early-stage pharma |
| **Production** | $400k–$900k | Pharma R&D unit / regulatory affairs department |
| **Enterprise** | $1M+ | Multi-country pharma / large CRO |

$20/mo entry-level explicitly refused per locked positioning.

---

## Known limitations

- **claim_frames BEAT-BOTH dimension**: extraction of N + baseline + endpoint + CI from prose is regex-based in v1.0; LLM-based extraction deferred to v1.1
- **Pin trends org-scoping**: pin files do not carry `org_id` in v1.0; auth gates dashboard access but per-org pin filtering is best-effort. Closes when M-INT-0b v2 adds org_id to capture path
- **CI workflow YAML**: `.github/workflows/m_live_4_regression_gate.yml` deferred to user-side push (OAuth `workflow` scope required)
- **M-INT-4/5 telemetry-only**: LLM scope classifier and domain router observe but do not gate. Production gating is v1.1
- **Template scope is clinical-only**: `due_diligence`, `policy`, `tech`, `custom` YAMLs are scaffolding; only `clinical` variants are public in v1.0
- **Synthesizer narrative depth**: 2 BEAT-BOTH dimensions remain BEHIND-BOTH (narrative_length, contradiction_handling_grammar). Closes with V_N+1 synthesizer capacity tuning

---

## Migration guide (pilot → v1.0)

```bash
# 1. Pull latest
git pull origin polaris

# 2. Verify SOC2 evidence intact
python scripts/run_m_prod_1_soc2_dry_run.py
# Expect: 28/28 intact, exit 0

# 3. Smoke single query end-to-end (REQUIRED FIRST — produces "current" manifest)
python scripts/run_m_live_1_smoke.py
# Expect: 13/13 substrates fired, all_phase_e_fired=true, ~13 min wallclock

# 4. Run regression gate (uses fresh smoke manifest as "current" against
#    the checked-in fixture at tests/fixtures/m_live_4_baseline/ as baseline)
python scripts/run_m_live_4_regression_gate.py
# Expect: verdict=YELLOW (or GREEN), exit 0
#
# YELLOW is the expected default in v1.0 because the fixture baseline is
# `partial_qwen_advisory` / release_allowed=false (a SMOKE-time snapshot),
# while a fresh full smoke produces `status=success` / release_allowed=true.
# That manifest drift is non-regressive (status improved) → YELLOW per
# `regression_lab.py:693` (verdict logic). RED would block merge;
# GREEN/YELLOW pass with exit 0.

# 5. Score against competitors (uses Phase G full-scale baseline by default)
python scripts/run_m_live_2_beat_both.py
# Output: outputs/m_live_2_beat_both/manifest.json
# Note: driver currently auto-discovers from outputs/phase_g_full_scale/.
# To score against your fresh smoke run, override POLARIS_SMOKE_ROOT
# in the driver (or pass explicit --polaris-manifest in v1.1).
```

Step 3 must come before step 4 — the regression gate requires a fresh smoke manifest.

---

## Acknowledgements

This release includes 14+ Codex review rounds across 4 Phase F milestones plus 3 Phase H milestones, surfacing 25+ P0/P1 findings closed via the autoloop V3 lean brief format.
