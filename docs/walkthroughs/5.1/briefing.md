# Phase 5 Final Carney Walkthrough — Evaluator Briefing

**Task:** `5.1` · **Substrate-prep:** `5_1_prep_briefing_pack` · **Deadline:** 2026-09-02 (§G #7; pre-Carney handover by 2026-09-06)
**Scope:** FINAL pre-handover walkthrough — full corpus, sovereign cluster, all 8 templates, all 15 features

> **Phase-5-SKELETON status (post halt-resolution path 3 — 2026-05-02).**
> Unlike the Phase 1-2C `*_PARTIAL_honest` packs, this pack's bar
> intentionally is NOT lowered: 5.1 is the FINAL walkthrough by design,
> and its acceptance criteria require cluster + sovereignty migration
> complete (Phase 4 finishes 2026-08-23 per §G #7). What is APPROVE'd
> here is the **briefing skeleton** — its structure, scope assertions,
> and disclosure framing. Actual evaluator execution against running
> sovereign infrastructure happens between 2026-08-31 and 2026-09-02.
> Do NOT lower the Phase-5-END bar; treat the validation steps as
> "MUST be true at execution time" rather than "MUST be true now."

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

ANY of the following = halt + escalate to user before handover (canonical
task_5_1 green criteria — "No P0/P1 found" — applies):
- ANY P0 finding (broken core feature)
- ANY P1 finding (phase-rework severity, including any sovereignty,
  benchmark, or accessibility regression rising to P1)
- ANY sovereignty violation (CAN_REAL data observed crossing to non-Canadian infra)
- ANY benchmark regression vs Phase 3.5 results
- ANY accessibility violation introduced since Phase 2C
P2/P3 findings may ship with a written followup item per Plan v13 §H, but
must be enumerated before handover sign-off.

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
