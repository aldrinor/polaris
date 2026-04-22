# Restart Instructions — 2026-04-21 (latest)

## Autoloop V2 is in force (user directive 2026-04-21)

Full runbook: `state/autoloop_v2_runbook.md`.

Short form: every V{N} sweep → parallel Claude + Codex output
audits → cross-review → both green = ship / either red = Claude
writes fix plan → Codex reviews plan for band-aid-vs-root-cause →
implement on green → re-launch. Fully autonomous; no user
intervention expected between sweeps.

Memory rule: `autoloop_v2_audit_cross_review.md`.

## Current state

V25 is the first V to run under V2 protocol. M-41 bundle pass-2
(last V1-protocol code fix) is in Codex audit at time of writing.

**Latest durable state**: V23 sweep complete, DR audit pass 11 = PARTIAL.

Read the current handover FIRST:
`state/autoloop_handover_2026-04-21_current.md`

Older restart content (2026-04-19 "APPROVED-FOR-FULL-SCALE-RUN") is
archived at the bottom of this file. It reflects a pre-BEAT-BOTH
stop criterion and is historical only — do NOT resume from it.

## Quick resume (for wake-up)

1. V23 post-M-34 is the latest sweep artifact.
   `outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/`
   status=success, release_allowed=true, 1455 prose words, 31 cites,
   5 sections, 12/13 rules pass.

2. Codex DR pass 11 verdict = **PARTIAL** — 1 BEAT_BOTH / 2 BEAT_ONE
   / 4 LOSE_BOTH. See `outputs/codex_findings/dr_output_pass_11/findings.md`.

   **Note**: the session commit message for pass 11 mis-summarized the
   verdict as "Regulatory BEAT_BOTH; 5 dims LOSE_BOTH". The actual
   verdict table is in the handover file and in findings.md — the
   BEAT_BOTH dimension is Contradiction handling, not Regulatory.

3. V24 fix candidates ordered by leverage (see handover for detail):
   - **M-35** SURPASS-1..6 / CVOT / SURMOUNT-2/4 primary-paper
     retrieval anchors (biggest single lever)
   - **M-36** trial-summary + benefit-risk tables
   - **M-37** Health Canada anchors + jurisdictional polish
   - **M-38** trial-framed claim prompt
   - **M-39** contradiction adjudication
   - **M-40** mechanism/pharmacology narrative expansion

4. Two outstanding protocol-compliance items (user flagged): retroactive
   Codex audit of `scripts/regate_v23.py` and `scripts/run_full_scale_v23.py`.
   Committed without code review. The re-gate script mutated
   manifest.json on disk and flipped release_allowed false→true — the
   higher-risk of the two.

## Autoloop rules in force

Per `C:\Users\msn\.claude\projects\C--POLARIS\memory\full_scale_dr_auto_loop.md`:
1. implement → unit tests → Codex code audit
2. if green → full-scale at MAX capacity (V{N} wrapper script, NOT bare
   `run_honest_sweep_r3.py` — see `autoloop_full_scale_launcher_pattern.md`)
3. Codex DR output audit head-to-head vs competitor PDFs
4. if not BEAT_BOTH → loop back

No cycle cap. User mandate is BEAT-BOTH, not threshold-only.

## Files the autoloop consults

- `docs/todo_list.md` — backlog, ACTIVE section at top
- `state/autoloop_handover_2026-04-21_current.md` — this cycle's handover
- `state/compare_chatgpt_dr.txt`, `state/compare_gemini_dr.txt` —
  competitor outputs for head-to-head
- `logs/session_log.md` — stops at 2026-04-19 06:15; a consolidated
  M-25..M-34 resume entry is appended on 2026-04-21. Commit messages
  are the authoritative per-fix record between those two points.

---

## Archived — 2026-04-19 "APPROVED-FOR-FULL-SCALE-RUN" (historical)

The autonomous loop finished at pass 16. 16 Codex audits + 10 sweep
cycles, M-1 through M-15 fixes. Cycle-10 profile: 0 clean releases,
1 partial_qwen_advisory, 7 abort_corpus_inadequate. Final commit:
`157aa0f PL: ★ Codex pass 16 verdict: APPROVED-FOR-FULL-SCALE-RUN ★`.

That approval predates the BEAT-BOTH head-to-head mandate (2026-04-20).
Under the current stop criterion the pass-16 state would be classified
LOSE_BOTH on most dimensions — it was single-query-release-rate tuning,
not DR-grade narrative/citation competition. Do not use it as the resume
baseline.

Full pass-16 narrative is preserved in
`archive/2026-04-18-pre-audit-cleanup/` for post-mortem.
