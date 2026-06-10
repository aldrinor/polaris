# POLARIS — todo / active scope (RE-PRIORITIZED 2026-05-20)

## ⭐⭐⭐ TOP PRIORITY (2026-06-10, operator-directed): PERMANENT ARCHITECTURE FIX — the 9 issues

Governing reframe: the pipeline changes from **WITHHOLD-when-imperfect → ALWAYS-RELEASE with honest per-claim confidence + provenance; user judges** (never assert an ungrounded claim as fact). Subsumes the beat-both completeness gap: the held/over-cautious gate stack is the root, not faithfulness (zero fabrication confirmed). Umbrella **#1194** (I-perm-000), issues **#1195–#1203** (I-perm-001…009). Charter `docs/permanent_fix_9_issues.md`; migration blueprint `docs/permanent_fix_migration_blueprint.md` (Codex architecture **APPROVE iter2** — locked). Per issue: research best-practice → line-by-line our code → permanent migration → build → SERIOUS stress smoke (I-perm-009 replay harness on saved beatboth8) → Codex review (only gate).

**STATUS (2026-06-10):**
- Architecture **LOCKED** (Codex APPROVE iter2) + operator safety-floor decision baked in.
- **I-perm-009 proof harness DONE + Codex APPROVE iter3** (commit 35071c47): `tests/polaris_graph/replay/` replays the real saved drb_76 run offline (no spend); reproduces the D8 decision bit-for-bit + §-1.1 zero-fabrication invariant. The pre-spend proof ledger.
- **Honest finding (reshapes I-perm-002 #1196):** the drb_76 `missing:contraindications` hold is a LITERAL-TOKEN gap — the VERIFIED Safety claims say "not recommended for immunocompromised" but the S0 gate demands the literal word "contraindicated". Fix = **I-perm-001 relabel (primary: BLOCK→LABEL, releases with caveat)** + **I-perm-002 semantic/qualitative contraindication recognition + R6 same-substance/population guard (credit, not just caveat).** Not a naive evidence_id credit (proven insufficient in the harness).
- **I-perm-008 deeper root cause found** (`.codex/I-perm-008/empirical_finding.md`): KF cruft is a verdict-aware-rebuild problem (header-leak + pre-four-role DOTALL lift), not a post-hoc filter (a quick slice was smoked + reverted as a no-op).

**PARALLEL EXECUTION (operator-directed 2026-06-10, standard Claude Codex Workflow, ≤3 parallel codex):** dependency-aware batches (file-conflict-avoided; CORE lane serialized):
- **Batch 1 (parallel now, file-disjoint INDEP):** I-perm-008 (#1202 KF verdict-aware rebuild + cruft) ∥ I-perm-003 (#1197 selection, behind flags) ∥ I-perm-007 (#1201 quantified + hard-PDF extraction).
- **Batch 2 (keystone, CORE):** I-perm-001 (#1195) — BLOCK→LABEL gate stack + PG_ALWAYS_RELEASE + ReleaseDisclosure (Decision-B schema) + status vocab + bundle-422-on-hard_block + regression alerts + the 2 folded P2s (hard_block_reasons, zero-grounding wording). Dependency for 002/004/005/006.
- **Batch 3 (after 001):** I-perm-002 (#1196 corpus-wide + semantic contraindication + R6 guard) ∥ I-perm-004 (#1198 span recovery + label-not-delete; shares span_resolver primitive with 002).
- **Batch 4 (after 001/004):** I-perm-005 (#1199 per-claim render + 4-role→labeler + credibility weight).
- Each: build → harness smoke + targeted tests → Codex diff gate (5-cap, only gate). Honest corrections baked in: I-perm-003 selector drops 0 (the ~90% loss is upstream extraction/I-perm-007); I-perm-006 pending-rewrite is a phantom.
- **Exit:** all 9 Codex-APPROVED → serious preflight (Claude Codex Workflow) → present summary → operator go for the full beat-both run.

## ⭐⭐ PRIOR PRIORITY (2026-06-09, now SUBSUMED by the 9-issue program): BEAT-BOTH fix campaign — never stop until beat-both

The released 5-question beat-both run (drb_72/75/76/78/90, branch `bot/I-ready-017-faithfulness`) was §-1.1 dual-audited: POLARIS is genuinely faithful + **beats Gemini on all 5**, but does **NOT beat gpt_5_5_pro** (careful, no fabrication). Gap = **completeness, not faithfulness**. 7-lane bug forensic → ~54 bugs → 2 P0 roots. Full ranked list + ordered sequence: `outputs/audits/beatboth5/FULL_BUG_LIST.md`. Loop state: `state/beat_both_loop_state.json`. Mission: fix → re-deploy 5-Q on VM → re-audit dual §-1.1 → loop until beat-both (both auditors agree). Each fix = GitHub issue-first + Codex-gated brief + diff (§-1.2 + §8.3.1 5-cap); Codex the only gate.

**Ordered fix sequence:**
1. **BB5-F01 redactor S3-leak (P0 faithfulness) — `I-faith-004` #1174 — ✅ DONE (commit c790d627, Codex APPROVE).**
2. **BB5-C01/C02 fetch global-deadline starvation (P0 completeness, dominant lever) — `I-fetch-003` #1175 — IN PROGRESS (brief Codex-gating).**
3. F02 clinical overgeneralization (P1 faithfulness).
4. S02/S03 abandoned-thread teardown + SIGSEGV subprocess isolation.
5. C05 extractor fallback chain; C06/C07 stop forcing prefer-abstract + render dropped-section stubs.
6. **RE-MEASURE consequences** (C03 must-cover / C04 pool / C08 coverage / C09 drop-rate) — do NOT pre-fix.
7. S01 drb_90 stale pending_rewrite latch (flips one answer to released).
8. K01/K02/K03 quantified-no-op + STORM seed injection + legal connector.
9. P01/P02/P03 [REVIEW]-dump cap + semantic-dump trim + drb_90 dedup; P11 unify fetch ledger.
10. P2/P3 sweep.
**6 by-design DO-NOT-TOUCH** (BB5-D01 analyst-synthesis-off is CORRECT; re-enabling = faithfulness regression).

---

## ⭐ PRIOR PRIORITY (2026-05-28, operator-flagged): I-safety-002b (#925) — proper DR head-to-head benchmark
Benchmark POLARIS **as a deep-research tool** vs ChatGPT/Gemini/Perplexity DR on the **5 GOLDEN DRB-EN questions** (NOT homegrown), POLARIS at MAX POWER, **per-run §-1.1 line-by-line dual audit** (Claude+Codex, claim → fetched cited span → verdict). Plan Codex-APPROVE'd iter 5: `.codex/I-safety-002b/execution_plan_pathB.md`. Active per `state/active_issue.json`.
- **Questions LOCKED** (`.codex/I-safety-002b/golden_questions_locked.md`, Codex-confirmed `codex_lock5.txt`): DRB-EN **#75/#76/#78** (clinical) + **#72** (AI-labor lit review, journal-only citation constraint) + **#90** (ADAS liability, case law). Homegrown Q02–Q08 rejected as selection-biased. Honest label: *"DRB-EN high-stakes citation-faithfulness stress slice: 3 clinical + 2 source-critical"* — NOT "objectively hardest." Report clinical-3 + overall-5 SEPARATELY.
- **Scorer**: pre-existing `beat_both_scorer.py`/`dimension_scorers.py` §-1.1-BANNED + rigged → discarded; rebuilt as `src/polaris_graph/benchmark/claim_audit_scorer.py` (two-lane: faithfulness + pre-registered rubric coverage ≥0.70). 12 fixtures green.
- **Done**: `pathB_run_gate.py` (14 fixtures) + `claim_audit_scorer.py` (12) + golden questions locked + `gold_rubrics_pathB.md` re-authored against the golden 5 (DRAFT).
- **OPEN (Codex step-3 P1-3)**: gate enforces only in fixtures — NOT yet wired into a real run path.
- **Next**: Codex §-1.1-verify the 5 rubrics against fetched sources + gold spans + hash-pin (freeze) → wire gate into runner → POLARIS full-power runs + dual line-by-line. Operator pulling competitor DR exports now. **P2 UI umbrella (#821) PAUSED.**

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
