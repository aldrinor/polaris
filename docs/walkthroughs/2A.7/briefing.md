# Phase 2A End-of-Phase Walkthrough — Evaluator Briefing

**Task:** `2A.7` per `docs/task_acceptance_matrix.yaml`
**Substrate-prep:** `2a_7_prep_briefing_pack` (orchestrator-completed 2026-05-02)
**Walkthrough deadline:** 2026-06-22 (latest, per Plan v13 §G #7)
**Scope:** Phase 2A Core inspection (features F4-F9 + Templates 4-5)

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

See `test_inputs.md` (24-input corpus, 4 blocks).

## Recording

See `recording_template.md` for per-input observation format.

## What POLARIS is supposed to do (failure flags)

- F5 Inspector: every claim sentence in body clickable → side pane within 1s
- F7 Frame coverage: panel renders ABOVE-the-fold (before user scrolls)
- F8 Contradictions: clicking a flag shows ALL sides (T1 vs T1 with sample sizes)
- F9 Two-family: visible KPI card on every Inspector view
- Defense template: surfaces NIST + MITRE + GAO sources
- Climate template: surfaces IPCC + ECCC + NRCan sources

## Compensation per Plan v13 §G #7

$300/session paid, or thank-you for friend-evaluator.
