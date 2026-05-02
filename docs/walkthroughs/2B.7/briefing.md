# Phase 2B End-of-Phase Walkthrough — Evaluator Briefing

**Task:** `2B.7` per matrix · **Substrate-prep:** `2b_7_prep_briefing_pack` · **Deadline:** 2026-07-13 (§G #7)
**Scope:** Phase 2B Visualization + memory + replay (F6 + F10a-c + F13 + F14)

## What you'll be evaluating

| Feature | Surface |
|---|---|
| F6 Live citation overlay | Hover any sentence → tooltip with quote + tier (Perplexity-parity) |
| F10a Vega-Lite renderer | Inspector "Charts" tab — interactive SVG charts |
| F10b Chart provenance | Click any datum on chart → opens source span |
| F10c Executive summary | Inspector "Executive summary" tab — 4-KPI strip + 3 charts |
| F13 Pin replay + diff | Pin a run → reproduce later → diff view shows what changed |
| F14 Workspace memory | Memory persists across sessions; searchable corpus |

## Test corpus
See `test_inputs.md` (20-input corpus, 5 blocks).

## Recording
See `recording_template.md` (same format as Phase 1.8 / 2A.7).

## Failure flags
- F6 hover-latency >100ms on 100+ tooltip renders → P1
- F10a Vega chart >2.5s to render → P1
- F10b click-through to evidence not working → P0 (breaks crown jewel)
- F13 replay diverges from original (non-determinism) → P0
- F14 memory not searchable OR not isolated per workspace → P1

## Compensation §G #7
$300/session paid, or thank-you for friend-evaluator.
