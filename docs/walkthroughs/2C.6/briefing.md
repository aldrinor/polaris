# Phase 2C End-of-Phase Walkthrough — Evaluator Briefing

**Task:** `2C.6` · **Substrate-prep:** `2c_6_prep_briefing_pack` · **Deadline:** 2026-07-19 (§G #7)
**Scope:** Phase 2C UI polish + integration — full-feature walkthrough

## What you'll be evaluating

This is the **comprehensive** walkthrough — all 15 features (F1-F15) on a real query, all the way through:

1. Type a query → scope detected → ambiguity check → run starts
2. Live audit run shows reasoning visibly
3. Report renders with click-to-evidence on every claim
4. Hover citations show tooltips
5. Charts render in Inspector
6. Pin replay reproduces deterministically
7. Memory persists
8. Bundle exports cleanly
9. Cross-browser parity (Chromium, Firefox, WebKit)
10. WCAG-AA passes (axe-core)
11. Performance: hover <100ms, FCP <1.5s

## Test corpus
See `test_inputs.md` — single end-to-end golden flow on 3 templates × 3 browsers = 9 walkthroughs.

## Failure flags
Any feature regression vs Phase 1/2A/2B walkthroughs → halt.
Any cross-browser inconsistency → P1.
Any axe-core violation introduced → P1.
