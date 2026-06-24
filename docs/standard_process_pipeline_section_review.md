# Standard Process — Systematic Pipeline-Section Review via Claude Codex Bake-off

**Status:** STANDARD (operator-locked 2026-06-22, GH #1291). Apply to every pipeline section.
**Purpose:** make every "which approach do we secure in section X" decision **data-driven, on real benchmarks, on our model (GLM-5.2), in a VM, with Codex as the only review gate** — never opinion, never an unverified literature number, never a green-tests-only claim.

## Why this exists
The drb_72 disaster (2026-06-22) showed two failure modes that this process structurally prevents:
1. A scoring harness with a wiring bug (wrong-question / split-brain-scoring / Title-only-stub) produces **garbage numbers that look real**. → GATE 0.
2. "Committed + green + Codex-approved" is **not** "the effect fired in the real output" (§-1.4). → behavioural acceptance + §-1.1 audit.

## The locked benchmark set (the yardstick for every section — from the 2026-06-22 relevance filter, GH #1291)
- **PRIMARY (5):** DeepTRACE (faithfulness) · DeepResearch Bench II (coverage) · DEER (runnable per-claim faithfulness) · DeepScholar-Bench (live public faithfulness board) · DRACO (regulated-buyer trophy).
- **SECONDARY (3):** DeepResearch Bench v1 (recognized headline leaderboard) · ReportBench (internal 2-axis regression) · ResearchRubrics (Scale AI / ICLR credential).
- **SKIP:** MMDeepResearch-Bench, DeepResearchEval (citation-free), Dr.Bench, MDPI, FINDER.
- Each section names which subset + which axis it primarily drives (e.g. query-gen → coverage primary, faithfulness watched).

## The 9 steps (every section, in order)
0. **GATE 0 — harness validity (HARD PRECONDITION).** Fix + sanity-canary the benchmark harness. A canary must show the harness scores a KNOWN report correctly (right question launched; the packed question == the answered question; sources not reduced to Title-only stubs). **No score is trusted, and no bake-off runs, until the canary passes.**
1. **GitHub Issue** (`gh issue create`, title `I-<prefix>-NNN — …`, acceptance criteria). FIRST task-work call.
2. **Define** the section, the candidate approaches, and the operative metric (which benchmarks + axis). **Always include verified baselines AND the current POLARIS behaviour as the floor** — never bake-off only the new candidates.
3. **Brief** (Claude-authored) with the §8.3.1 cap directive + the frontier-tech mandate on top → **Codex gate (APPROVE)**. Re-scan the frontier at start (the field moves monthly).
4. **Stand up** candidate implementations: open-source where runnable, adapted to GLM-5.2. Honest scope — only runnable candidates are tested; unrunnable ones are noted, not faked. Standalone bake-off **selects the mechanism**; the winner is then **ported into POLARIS** (the standalone number selects, the integrated run decides).
5. **Execute in VM** (one VM per candidate or per benchmark, parallel): candidate × benchmark-subset × GLM-5.2; score **BOTH axes** (coverage + faithfulness). **Behavioural acceptance = the effect appears in the REAL rendered output**, fail-loud, not green tests, not a diff approval.
6. **§-1.1 line-by-line audit** of the winning output (per-claim VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE + human-quality read). A score without a §-1.1 audit is not a decision.
7. **Codex gate on the diff** when porting the winner into the pipeline.
8. **Decide → secure → document → close** the issue. **Faithfulness gates are NEVER relaxed to lift a coverage score** (§-1.3).

## Invariants (apply to every instance)
- Faithfulness engine (strict_verify / span-grounding / provenance / 4-role) is untouchable; the bake-off only changes the section under test.
- GLM-5.2 is the fixed backbone (apples-to-apples; sovereignty constraint).
- Cost is not the limiter; time is — run candidates in parallel across VMs (per operator DNA).
- Every external runtime is pattern-inspiration only until proven on our own slate (frontier-tech rule).
- Single-writer per artifact; PID-scoped python-only kills; orphan-process audit between runs (§8.4).

## Instances
- **I-qgen-001 (GH #1291)** — query generation (first instance). ⚠️ **PROVISIONAL — recency-completion
  pending (I-recency-001 #1296).** Bake-off (10 methods, drb_72, DRB-II info_recall coverage, on a VM) →
  IterResearch/Tongyi won (0.386); floor last (0.000). Wired flag-gated (`PG_QGEN_ITERRESEARCH`),
  Codex-APPROVED, committed under **I-qgen-002 (#1292)**, commit 84bb2d86. **NOT a lock:** field is
  recency-INCOMPLETE — 2 methods (FS-Researcher/ConvergeWriter) errored + never scored, single task only,
  floor 0.000 looks like a harness hang. Must clear the recency bar before lock.
- **I-ret-002 (GH #1294)** — retrieval, per-layer. ⚠️ **PROVISIONAL** pending recency-completion (#1296).
  dedup → POLARIS ContentDeduplicator held (1.0/1.0; the 2025 SemHash LOST). embedder → Qwen3-Embedding-8B
  (0.7173) HELD vs jina-v5-text-small (Feb 2026 leaderboard leader, 0.7132). reranker → Qwen3-Reranker-4B
  (0.7654) HELD vs jina-reranker-v3 (Sep 2025). Gaps (dep-conflict models) running in isolated envs.
- **I-cons-001 (GH #1295)** — consolidation/baskets. Landscape done (`docs/consolidation_landscape_2026.md`);
  bake-off not yet run.
- (next) composition · verify-render · …

## RECENCY-COMPLETENESS — a HARD gate before any section LOCK (operator-locked 2026-06-24, #1296)
A section winner is valid ONLY when its candidate field is **recency-complete**: every recency-verified
absolute-latest model/method either RAN on the section axis, OR is documented as genuinely un-runnable
(license-NC → yardstick-only OK; OOM/dep-conflict must be retried in a per-model ISOLATED env before being
called un-runnable). A pick is **PROVISIONAL**, never "decided," until then. Re-check "is anything newer?"
at DECISION time, not just design time. Picking best-of-an-old-subset in a clinical pipeline is the §-1.1
lethal class. The latest models have conflicting deps → build per-model isolated conda/venv envs on the VM.
Ref: `feedback_bakeoff_must_include_absolute_latest_or_lethal_2026_06_24`.

## Section sequence + when the e2e run happens (operator-locked 2026-06-23)
Per section: (1) isolation bake-off → pick winner, (2) wire the winner flag-gated + Codex-gate +
commit. **NO per-section e2e.** The single end-to-end VM run happens ONCE, at the very end, after
EVERY section's winner is wired — that combined run (all winners ON together) is the integrated
validation + where interaction effects surface + where the final benchmark score is taken. So the
query-gen e2e is deferred into that final combined run, not run standalone now.

## REFINEMENT (operator directive 2026-06-22) — ISOLATION scoring, no e2e per candidate
The bake-off does NOT run full e2e per candidate. Each section is scored IN ISOLATION on the benchmark axis it drives, then winners are combined for ONE final full run.
- **Query generation -> COVERAGE**: run each method's queries -> retrieve -> score = required-point retrieval coverage (DRB-II info_recall + DeepResearch Bench RACE potential). No report generation / rendering / DeepTRACE-judge in the section test.
- **General rule:** test a section on the axis it CONTROLS (query-gen=coverage, verify=faithfulness, composition=presentation, ...), holding the rest fixed; pick the highest; lock it.
- **Combine:** lock every section-winner -> ONE full run -> highest overall score = the integrated validation that the per-section optima compose (and the place interaction effects surface).
- Keep GATE 0 canonical-question binding so coverage is scored against the correct rubrics. Faithfulness boards (DeepTRACE/DEER/DeepScholar) gate the faithfulness sections + the final combined run, not query-gen.
