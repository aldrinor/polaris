# Phase 2A End-of-Phase Walkthrough — Evaluator Briefing

**Task:** `2A.7` per `docs/task_acceptance_matrix.yaml`
**Substrate-prep:** `2a_7_prep_briefing_pack` (orchestrator-authored 2026-05-02; Phase-2A-PARTIAL-honest bar — see disclosure below)
**Walkthrough deadline:** 2026-06-22 (latest, per Plan v13 §G #7)
**Scope:** Phase 2A Core inspection (features F4-F9 + Templates 4-5)

> **Phase-2A-PARTIAL bar (post halt-resolution path 3 — 2026-05-02).** This
> briefing exercises Phase-2A substrate already in HEAD: Inspector 5-tab
> surfaces (M-3..M-7), progressive in-run surfaces (M-13), templates
> (M-10/M-14). Behavior that requires §G #3 Vast.ai cluster + live LLM
> generation (real F4 SSE events from a running query, real two-family
> evaluator agreement signal, real frame-coverage gap suggestions, etc.)
> is observational-only — see "Phase 2A known gaps" near end of this file.
> Inspector-view static-fixture rendering against `_GOLDEN_RUN_INDEX`
> golden-fixture run IDs (`golden_clinical_001` etc., per
> `src/polaris_v6/api/bundle.py`) IS testable on HEAD without cluster.

## What you'll be evaluating

6 features + 2 new templates that landed in Phase 2A:

| Feature | Surface |
|---|---|
| F4 Live audit run UI | `/runs/<runId>` — SSE stream + 5 affordances panel |
| F5 Generalized Inspector | `/inspector/<runId>` — 5-tab view |
| F7 Frame coverage panel | Inspector "Frames" tab — above-the-fold |
| F8 Contradiction navigation | Inspector "Contradictions" tab — clickable badges |
| F9 Two-family disagreement | Inspector top KPI card — PASS/FAIL signal |
| Templates 4-5 | Defense + Climate templates loaded |

## Test corpus

See `test_inputs.md` (24-input corpus across 5 blocks A-E).

## Recording

See `recording_template.md` for per-input observation format.

## What POLARIS is supposed to do (failure flags — Phase-2A-PARTIAL bar)

- F5 Inspector (testable on HEAD via static fixtures, scoped to what's wired):
  provenance tokens (`[#ev:<id>:<start>-<end>]`) within report sentences
  are wrapped in `EvidenceTooltip` and surface source-span detail on
  hover/focus. **Sentence-level click-to-side-pane is NOT yet wired in
  HEAD** — only provenance-token-level interaction is shipped. Mark
  sentence-level click expectations as observational-only.
- F7 Frame coverage (testable on HEAD when Frames tab selected): the
  Inspector defaults `activeTab` to `summary`. Click the **"Frames"** tab
  to render the frame-coverage panel against the loaded fixture's
  `EvidenceContract.frame_coverage` array. Within the Frames tab, the
  panel content should be visible without further scroll. The
  "above-the-fold" claim is **scoped to the Frames tab itself**, not to
  the default Inspector landing surface.
- F8 Contradictions (testable on HEAD via `golden_housing_002`): clicking
  a contradiction badge shows ALL sides + tier, with the canonical
  `resolution` enum values from `src/polaris_v6/schemas/evidence_contract.py:80`
- F9 Two-family (testable on HEAD): the `family_segregation_passed`
  field is set on every golden fixture; KPI card surfaces it on the
  Inspector view (PASS = green; FAIL = red)
- F4 Live audit run UI (`/runs/<runId>`): **observational-only on HEAD**
  — `/runs/{runId}` reads the in-memory run table populated by submit-
  flow; `_GOLDEN_RUN_INDEX` is wired only to `/runs/{runId}/bundle` and
  the Inspector pages, NOT to the F4 live-progress surface. Real F4
  exercise requires §G #3 cluster online.
- Defense + Climate templates: **observational-only on HEAD** —
  template enum identifiers exist in `src/polaris_v6/schemas/run_request.py:13-14`
  and golden fixtures exist (`golden_defense_004`, `golden_climate_005` per
  `src/polaris_v6/api/bundle.py:32-33`), but explicit required-entity
  manifests (NIST / MITRE / GAO / CVE / CWE / ATT&CK / IPCC / ECCC /
  NRCan listings as authoritative content) are Phase 2A+ work and are
  NOT yet in `src/polaris_v6/templates/registry.py`.

## Phase 2A known gaps (in scope to observe, out of scope to ship in this walkthrough)

Per Plan v13 §F (no SILENT fallback):

- **Live LLM cluster (§G #3 pending)**: Block A (live audit run via SSE)
  cannot fully exercise — backend has no cluster to drive real generation.
  Inspector view loading is testable on HEAD (`/inspector/golden_clinical_001`
  is wired through `_GOLDEN_RUN_INDEX` → `bundle.py` → `EvidenceContract`)
  but `/runs/{runId}` is NOT backed by `_GOLDEN_RUN_INDEX`; F4 live-progress
  surface is not exercisable on golden fixtures alone. Mark Block A inputs
  (#1-#5) as observational-only when stubs are in play.
- **Two-family evaluator runtime check** (Block C inputs #14-#17): the
  family-segregation flag in `EvidenceContract.family_segregation_passed`
  IS set on golden fixtures and IS rendered by Inspector. Live-run real
  agreement-signal generation requires cluster; observe golden-fixture
  rendering only.
- **Defense + Climate template content** (Block D, inputs #18-#21): the
  template ENUM identifiers + golden fixture mappings exist in HEAD, but
  the authoritative required-entity manifests (NIST / MITRE / GAO / CVE /
  CWE / ATT&CK / IPCC / ECCC / NRCan) are NOT yet in
  `src/polaris_v6/templates/registry.py`. Block D collapses to two
  observational checks: (a) the run_request template enum accepts
  "defense" / "climate"; (b) golden_defense_004 / golden_climate_005
  Inspector pages render. The required-entity coverage assertion is
  Phase 2A+ work and out of scope here.

## Compensation per Plan v13 §G #7

$300/session paid, or thank-you for friend-evaluator.
