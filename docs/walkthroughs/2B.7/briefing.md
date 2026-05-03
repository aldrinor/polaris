# Phase 2B End-of-Phase Walkthrough — Evaluator Briefing

**Task:** `2B.7` per matrix · **Substrate-prep:** `2b_7_prep_briefing_pack` · **Deadline:** 2026-07-13 (§G #7)
**Scope:** Phase 2B Visualization + memory + replay (F6 + F10a-c + F13 + F14)

> **Phase-2B-PARTIAL bar (post halt-resolution path 3 — 2026-05-02).**
> This briefing exercises Phase-2B substrate already in HEAD: charts module
> at `src/polaris_v6/charts/`, replay module at `src/polaris_v6/replay/`,
> memory module at `src/polaris_v6/memory/`. Behavior that requires §G #3
> Vast.ai cluster + live LLM generation (real pinned-run replay-determinism,
> real V4 model-upgrade diff, real multi-session memory persistence with
> real-corpus content) is observational-only. See "Phase 2B known gaps"
> below. Static-fixture rendering of Charts tab + Executive summary tab on
> golden-fixture run IDs IS testable on HEAD.

## What you'll be evaluating

| Feature | Surface |
|---|---|
| F6 Live citation overlay | Hover any sentence → tooltip with quote + tier (Perplexity-parity) |
| F10a Vega-Lite renderer | Inspector "Charts" tab — interactive SVG charts |
| F10b Chart provenance | Click datum on charts whose spec emits an evidence-id-keyed identifier (per `src/polaris_v6/charts/from_bundle.py` evidence-keyed paths) → opens source span. Frame-coverage-derived charts (forest_plot / comparison_table rows from frame_coverage) emit `frame_id` and intentionally do NOT resolve through `evidenceById` in this phase. |
| F10c Executive summary | Inspector "Executive summary" tab — 4-KPI strip + 3 charts |
| F13 Pin replay + diff | Pin a run → reproduce later → diff view shows what changed |
| F14 Workspace memory | Memory persists across sessions; searchable corpus |

## Test corpus
See `test_inputs.md` (20-input corpus, 5 blocks).

## Recording
See `recording_template.md` (same format as Phase 1.8 / 2A.7).

## Failure flags (Phase-2B-PARTIAL bar)

Testable on HEAD via golden fixtures:
- F6 hover-latency >100ms on EvidenceTooltip provenance-token renders → P1
- F10a Vega-Lite chart >2.5s to render against `EvidenceContract` data
  for any `_GOLDEN_RUN_INDEX` ID → P1
- F10b click-through to source span on chart datums where the chart spec
  emits an `evidence_id` that resolves to a `SourceSpan` via
  `evidenceById` — testable only on the **subset** of golden charts that
  use evidence-id-keyed datums. Charts whose datums use frame-keyed
  identifiers (e.g., comparison_table / forest_plot rows derived from
  `frame_coverage` per `src/polaris_v6/charts/from_bundle.py`) emit
  `frame_id` values that are NOT in `evidenceById`; clicks on those
  datums do NOT open a side pane and that is **expected Phase-2B-PARTIAL
  behavior** (frame-keyed-to-source-span resolution is Phase-2B+ work).
- F10c Executive summary tab not surfacing 4-KPI strip → P1

Observational-only on HEAD (require cluster — see known gaps):
- F13 pin replay determinism / V4 model-upgrade diff (no real LLM to
  drive original or replay run)
- F14 cross-session memory persistence with real-corpus content (no
  cluster-driven runs to populate the searchable corpus)

## Phase 2B known gaps (in scope to observe, out of scope to ship in this walkthrough)

Per Plan v13 §F (no SILENT fallback):

- **F13 pin replay determinism**: substrate at `src/polaris_v6/replay/`
  is wired and tested on synthetic fixtures (see `tests/v6/test_replay.py`),
  but a real "pin a run, wait 24h, replay" cycle requires §G #3 cluster
  to produce the original run. Block D inputs #12-#15 are observational-
  only when stubs are in play.
- **F14 workspace memory cross-session**: substrate at
  `src/polaris_v6/memory/` provides the storage layer (see
  `tests/v6/test_workspace_memory.py`), but populating real findings
  requires cluster-driven query runs. Block E inputs #16-#20 are
  observational-only.
- **F10b/F10c click-to-source on charts**: implemented for golden-fixture
  contradictions/forest_plot data; behavior on freshly-generated runs
  cannot be verified until cluster online.

## Compensation §G #7
$300/session paid, or thank-you for friend-evaluator.
