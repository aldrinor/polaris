# POLARIS — todo / active scope (RE-PRIORITIZED 2026-05-20)

**Active scope: the Carney demo, RE-PRIORITIZED by demo value.**

APD Scope source (in precedence order):
- `state/polaris_phase2_ui_breakdown_2026_05_21.md` — **PHASE-2 GRANULAR SEQUENCE (military order), 2026-05-21 — THE authoritative Phase-2 execution order.** 27 issues I-p2-001..027 (#740–766) in strict sequence; each Codex-audited at the top-tier 8-dimension design rubric (screenshots in loop) + code diff + UAT. Embeds the binding audit rubric. Supersedes the coarse #729/#731-738 stubs (closed).
- `state/polaris_ux_research_consolidated_2026_05_21.md` — consolidated Claude×3 + Codex deep web research (2025-2026 UI/UX/UAT best practice for AI deep-research tools). Basis for the breakdown + rubric.
- `state/polaris_ui_design_plan_2026_05_21.md` — TOP-TIER UI design plan, Codex APPROVE iter 5 ("ahead of frontier"). Differentiation = provable + sovereign + snowball graph; signature = Proof Replay; LOCKED = Frontier Minimal. Per-page wireframes (chat).
- `state/polaris_carney_reprioritization_2026_05_20.md` — **the authoritative order**, Codex serious review **APPROVE iter 2** (0 P0 / 0 P1). Supersedes the 2026-05-19 strict-Seq breakdown for ORDERING.
- `state/polaris_carney_issue_breakdown_2026_05_19.md` — the original 48-issue breakdown (still valid for per-issue acceptance/gates; ORDER superseded by the reprioritization).
- `state/polaris_ui_rebuild_matrix.md` — UI rebuild route matrix + gates G1-G8.

## CURRENT PRIORITY (2026-05-21): PHASE 2 = top-tier UI rebuild, GRANULAR military-order sequence
Why re-scoped: PHASE 2 v1 (#704/#707/#542/#543) merged + Codex-passed but came out PLAIN B+ — because Codex reviewed CODE correctness, never top-tier DESIGN. Fix: 27 granular issues, each Codex-audited at the **top-tier 8-dimension design rubric** (visual / user-flow / data-flow / focus / clarity / frontier-head-to-head / accessibility / provability — **screenshots in the loop**) + code diff + UAT. Authoritative order: `state/polaris_phase2_ui_breakdown_2026_05_21.md`.

**Execute in STRICT sequence (cannot start N+1 until N merged + screenshot-verified + UAT-passed):**
- TIER 0 standards: **#740 I-p2-001** (Codex locks the standard) → **#741 I-p2-002** (audit protocol into templates)
- TIER 1: **#742 I-p2-003** design-system re-audit (+ accent decision)
- TIER 2 components: **#743..#751** (citation chip, verdict chip, source card, Proof-Replay split-view, progress checklist, sovereignty panel, contradiction/refusal, states kit, knowledge-graph)
- TIER 3 pages: **#752..#762** (home, intake, plan-review, run, **#756 report=Proof-Replay [closes #728]**, compare, knowledge-graph, audit/export, sign-in, dashboard, sovereignty integration)
- TIER 4 verify: **#763** frontier benchmark · **#764** UAT U-01..06 · **#765** WCAG 2.2 AA · **#766** demo journey + handover
- Parallel backend (non-blocking): #727, #702/#703, #720.
- In-flight: #734 (Proof Replay WIP, branch bot/I-ui-014-proof-replay) → finished under #756 I-p2-017.

## Why re-prioritized (2026-05-20)

The original strict-Seq order was marched mechanically ("issue merged = done"), so GPU-procurement substrate was being shipped while the deployed UI was still ugly + the live journey was never browser-validated. Operator flagged the priority as fundamentally backwards. New order: product-quality + live-journey FIRST, sovereign GPU DEAD LAST (demo is months away + OpenRouter is a working fallback).

## Execution rule (military order)

Strict phase sequence P0 → P7, one issue at a time. Per issue: analyze → grep adjacent → offline smoke → Codex brief → APPROVE → diff → Codex diff APPROVE → merge → close. Codex reviews EVERY task at the highest quality bar. Any P1 open at iter-5 → new follow-up issue (never buried). "Merged" ≠ "done": user-facing surfaces close only after an authenticated browser walkthrough screenshot against a REAL run on the deployed VM.

## Priority order (the sequence to execute)

### PHASE 0 — URGENT (blocks trust)
- **#567** — make `codex-required` actually block merges (inert today: PR #709 merged with it failing). Structural enforcement before any more "Codex APPROVE → merge" cycles.

### PHASE 1 — Real-run backend foundations
- #682 ✅ DONE (metadata schema) · **#680** EvidenceContract real runs ← next · #705 list endpoint · #706 SSE instrumentation

### PHASE 2 — Demo surface beautiful + complete
- #704 UI overhaul · #707 staged-progress run UI · #542 follow-up UI · #543 run-compare

### PHASE 3 — Run output audit-grade
- #702 repetition · #703 AIDA gap · #675 model='unknown' · #676 GPG preflight · #537 doc grounding · #708 conformance fixtures

### PHASE 4 — Live journey validated
- #634 matrix on live VM · #473 10-q rehearsal (frozen pack) · #403 per-claim audit · #629 hard-kill/resume

### PHASE 5 — Infra hygiene
- #589 stop hook · #658 pin verifier · #432 repo cleanup

### PHASE 6 — Sovereign GPU (DEAD LAST, no spend until operator re-raises)
- #641 FP4 spike · #642 capacity hold · #643 provisioning order ($) · #644/#645/#646 sovereign window + regression

### PHASE 7 — Demo endgame (final week)
- #647 dress rehearsal · #649 full sovereign rehearsal · #699 TLS renewal gate · #650 fallback drill · #651 walkthrough · #652 handover · #653 the demo

## Current position

**PHASE 0 / #567 — make the codex-required gate enforce.**

## Trackers (synced 2026-05-20)

- GitHub `aldrinor/polaris`: re-prioritized; closed #636/#682; re-scoped #699 (TLS renewal-watch); new #705/#706/#707 (Codex-surfaced foundations); new bugs #708; #567 pulled to PHASE 0.
- Claude session task list: PHASE tasks **#433-#442** (P0-P3 active); later phases tracked in the reprioritization doc, added as phases begin.

## Historical (do NOT use as scope)

`docs/task_acceptance_matrix.yaml`, `state/polaris_restart/issue_breakdown.md` — superseded. The 2026-05-19 Seq order is superseded for ORDERING by the 2026-05-20 reprioritization (per-issue acceptance still valid).
