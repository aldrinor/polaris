# Phase 5 Final Carney Walkthrough — Evaluator Briefing

**Task:** `5.1` · **Substrate-prep:** `5_1_prep_briefing_pack` · **Deadline:** 2026-09-02 (§G #7; pre-Carney handover by 2026-09-06)
**Scope:** FINAL pre-handover walkthrough — full corpus, sovereign cluster, all 8 templates, all 15 features

## What you'll be evaluating

This is the final gate before Carney delivery. Everything must work end-to-end on the sovereign Canadian infrastructure.

| Layer | Expectation |
|---|---|
| Sovereignty | Cognition entirely on 8× H200 OVH BHS; CAN_REAL data never leaves Canadian jurisdiction |
| Templates | All 8 (clinical, trade, housing, defense, climate, AI sovereignty, Canada-US, workforce) exercised |
| Features | F1-F15 all functional |
| Match-or-beat | At least matches ChatGPT 5.5 Pro DR + Gemini 3.1 Pro DR on golden queries (separate Phase 3.5 paid evaluator already verified — this is sanity check) |
| Auth + RBAC | Org isolation correct |
| Audit bundle | Full traceability per Crown jewel C1 |
| Cross-browser | Chromium + Firefox + WebKit |
| Mobile | Essential affordances visible at 375px |
| Accessibility | WCAG-AA, no regressions |
| Performance | All Phase 2C latencies maintained on sovereign infra |

## Test corpus
See `full_corpus_test_inputs.md` — full corpus walkthrough across 8 templates.

## Recording
Use the same per-input observation format as Phase 1.8 / 2A.7 / 2B.7 / 2C.6
(see `docs/walkthroughs/1.8/recording_template.md` for the canonical template).
Recording is **the** handover artifact alongside the proof-package PDF.

## Failure flags

ANY of the following = halt + escalate to user before handover:
- ANY P0 finding (broken core feature)
- ANY sovereignty violation (CAN_REAL data observed crossing to non-Canadian infra)
- ANY benchmark regression vs Phase 3.5 results
- ANY accessibility violation introduced since Phase 2C

## After walkthrough completes

1. GPG-signed attestation per §C-private
2. Recording uploaded to `.private/walkthroughs/5.1_final.mp4`
3. Summary written to `outputs/audits/walkthroughs/5.1_findings.md`

(Codex round-3 P0 correction 2026-05-02: removed an erroneous instruction here
about deleting `state/bootstrap_active`. That flag governs the BOOTSTRAP commit
exemption and is unrelated to the Phase 5.1 walkthrough verdict — it's deleted
at end of Bootstrap §K Step 16 smoke when gate becomes strict, NOT at Phase 5.)

## Compensation

This is THE walkthrough. Pay the evaluator their full $300 + $200 thoroughness bonus if they catch any P0 the autoloop missed.
