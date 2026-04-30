# POLARIS — Supported Scope

**Version:** v1.0
**Last updated:** 2026-04-30

This document defines what research questions POLARIS will and will not accept in v1.0, and the criteria the production code uses to route each query. **All claims here are backed by code references; if the code doesn't enforce something, this document does not claim it does.**

---

## Public template surface (3 clinical variants in v1.0)

POLARIS v1.0 ships **3 curated templates** in the public `TEMPLATE_CATALOG` (`src/polaris_graph/audit_ir/template_catalog.py:520-523`):

| Template ID | Domain | Coverage |
|---|---|---|
| `v30_clinical` | Clinical (general) | Drug trial efficacy + safety, comparative therapeutics, regulatory submissions |
| `v30_clinical_oncology` | Clinical oncology | Oncology drug efficacy + safety, biomarker outcomes |
| `v30_clinical_cardio` | Clinical cardiovascular | Cardiovascular outcomes, MACE endpoints |

The 5 YAML scope templates in `config/scope_templates/` (`clinical`, `due_diligence`, `policy`, `tech`, `custom`) are **scaffolding for future expansion**. Only the 3 clinical variants above are wired through the production routing path in v1.0. `due_diligence`, `policy`, `tech`, `custom` are not exposed in `TEMPLATE_CATALOG`.

---

## In-scope research questions

The 3 v1.0 templates accept questions in their respective scopes:

### `v30_clinical` (general clinical)

Accepts:
- Drug trial efficacy comparisons (e.g., "tirzepatide vs semaglutide HbA1c outcomes in T2DM")
- Comparative therapeutics across drug classes
- Regulatory submission summaries (FDA, EMA, Health Canada, NICE, PMDA, TGA, MHRA)
- Adverse event surveillance (FAERS, EudraVigilance)
- Mechanism-of-action questions when grounded in clinical trial evidence

### `v30_clinical_oncology`

Accepts:
- Oncology drug efficacy + safety in specific tumor types
- Biomarker-stratified outcomes (PD-L1, HER2, EGFR, etc.)
- Comparative oncology trial analyses

### `v30_clinical_cardio`

Accepts:
- Cardiovascular outcomes trials (CVOTs)
- MACE endpoints, HF outcomes, stroke prevention
- Lipid management + comparative agent analyses

---

## What v1.0 actually enforces (refusal logic per substrate)

**Honest accounting** of what code in v1.0 actually refuses, vs what FINAL_PLAN aspires to:

| Refusal class | Enforced by | v1.0 status |
|---|---|---|
| Question outside the 3 clinical templates | `template_classifier.py` confidence threshold | **Enforced**: returns `unsupported` if no template matches above threshold |
| Patient-specific medical advice | None (v1.0) | **Not enforced**: operator review responsibility |
| Real-time market quotes | Structural (evidence has provenance dates) | **Not enforced**: scope_gate doesn't refuse, but evidence is dated |
| Bioweapon / CBRN synthesis | None (v1.0) | **Not enforced** in v1.0 — relies on upstream LLM provider safety |
| Active election misinformation | None (v1.0) | **Not enforced** in v1.0 |
| Non-English questions | None (v1.0) — `language` field in scope_gate copies but doesn't refuse (`src/polaris_graph/nodes/scope_gate.py:419-421`) | **Not enforced**: documented as out-of-scope but not auto-refused |
| Multi-step reasoning > 3 hops | None (v1.0) — no hop-count logic in `domain_router.py:250-398` | **Not enforced**: V19 is single-query by `--only` semantics |

The original v1 of this document claimed M-INT-4 and M-INT-5 enforce non-English and multi-hop refusals. **They don't in v1.0.** M-INT-4 (LLM scope classifier) and M-INT-5 (domain router) run in telemetry-only mode in v1.0 — they observe and log routing decisions but do not gate retrieval. Production routing decisions in v1.0 come from the deterministic `template_classifier` + curated catalog.

M-INT-4/5 enforcement (gating instead of telemetry) is a v1.1 milestone.

---

## v1.0 routing flow (actual code path)

```
Research question
   ↓
template_classifier.classify_query() → CuratedTemplate match or unsupported
   ├── verdict: routed (high confidence on a v30_clinical_* template)
   ├── verdict: ambiguous → operator review
   └── verdict: unsupported → refuse
   ↓
[scope_gate] → strict checks on protocol fields → live retrieval
   ↓
M-INT-4 / M-INT-5 / M-INT-6 → telemetry-only observation
   (do NOT gate; v1.1 will promote to enforcement)
   ↓
live_retriever (M-INT-1 parallel + M-INT-2 cache + M-INT-3 freshness)
   ↓
generator + strict_verify → report.md or abort_no_verified_sections
```

---

## Quality gates per template

Each template defines minimum thresholds for:

- **Corpus adequacy**: minimum sources per evidence tier (T1 primary, T2 secondary, etc.)
- **Frame coverage**: % of slot fields that must be populated from evidence (M-58 frame validator)
- **Strict verify**: per-sentence content-word + numeric match rate (≥40% per section)

A query that fails corpus adequacy → `abort_corpus_inadequate` (no LLM tokens billed).

A query whose generated prose fails strict verify on every section → `abort_no_verified_sections` (verdict report, not a hallucinated pseudo-report).

---

## Operator override

Operators with `admin` or `owner` role on an org can:

- Override the `template_classifier` routing decision (logged in M-D3 telemetry)
- Inject a custom evidence corpus via `M-INT-10` Drive connector
- Adjust the corpus adequacy threshold per-run (logged with reason)

Each override generates a decision-telemetry record (M-D3 phase 1) for downstream M-D4 calibration.

---

## Roadmap (post-v1.0)

| Stretch goal | Earliest version |
|---|---|
| M-INT-4/5 promoted from telemetry to enforcement | v1.1 |
| Public exposure of `due_diligence`, `policy`, `tech`, `custom` templates | v1.2 |
| Multilingual scope classifier (DE/FR/ES/JA/ZH) | v1.2 |
| Real-time financial data integration | v1.3 (requires licensed feed) |
| Patient-specific clinical decision support | NEVER (legal moat) |
| Multi-hop reasoning (≥3 hops) | v2.0 |
| Custom domain template authoring UI | v1.1 |

---

## Compliance posture

POLARIS v1.0 supports:

- **SOC2 Type II evidence map** (`docs/compliance/soc2_evidence_map.md`) — 28/28 evidence references intact per M-PROD-1 audit
- **HIPAA audit trail** (`docs/compliance/hipaa_audit_trail.md`) — clinical template only, deployer-side prerequisites still apply (BAA + tenant isolation per `hipaa_audit_trail.md:386-394`)
- **EU AI Act Article 14** (human oversight) — POLARIS v1.0 supports operator review via M-INT-6 induction queue + M-INT-9 contract drafting + M-LIVE-3 dashboard. Full Article 14 compliance per `docs/compliance/eu_ai_act_template.md:254-267` is operator-implemented control surfaces, not a single milestone
- **GDPR data minimization** via M-INT-10 narrow Drive connector + workspace_id scoping

Multi-tenant isolation requires either separate FastAPI processes per tenant OR explicit org-role checks on every endpoint (M-15a/b auth substrate). Per-tenant metric isolation (the M-PROD-3 metrics endpoint is process-global) deferred to v1.1.
