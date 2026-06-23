HARD ITERATION CAP: 5 per document. This is iter 5 of 5.
ITER-4 CHANGE (operator directive): the bake-off decision is SCOREBOARD-ONLY — there is NO human gate. The §-1.1 per-claim line-by-line audit is performed MECHANICALLY by the faithfulness scoreboards (DEER per-claim, DeepTRACE per-statement, DeepScholar per-sentence), not by a human read.
ITER-5 RESOLUTION (iter-4 P1 SCOREBOARD-CANARY-GAP): because there is no human backstop, GATE 0 must PROVE the faithfulness scoreboards catch SEMANTIC unsupportedness, not only reachability/lineage. GATE 0 now has a FOURTH negative canary (semantic-support) below.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings.
- Surface any held-back P1 now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

FRONTIER-TECH MANDATE: reference only 2025-2026 frontier methods, primary-source verified; no grandfather downgrade; build-start frontier rescan with logged include/exclude + exact pins.

# Brief iter 3 — I-qgen-001: Query-Generation Bake-off (first instance of the standard pipeline-section review, GH #1291)
REVIEW for soundness (brief/plan gate, NOT code). Iter-2 returned 4 P1 + 3 P2; this iter resolves each (mapped). Do NOT run anything.

## Goal
Decide which query-generation MECHANISM POLARIS secures in its closed-loop coverage front-end — via a CONTROLLED, isolation bake-off on the locked benchmark set, GLM-5.2, in VMs, faithfulness engine untouched.

## ITER-2 RESOLUTIONS (verify; do not re-raise)

### P1-1 (iter2) — SCREEN NEVER pre-filters DECIDE
DECIDE runs EVERY verified-runnable class-(ii) portable mechanism PLUS the POLARIS template-facets floor — no candidate is dropped before DECIDE. SCREEN (full-stack standalone) is reported SEPARATELY as advisory context only; it never gates which mechanisms enter DECIDE.

### P1-2 (iter2) — DECIDE adapter API for ADAPTIVE (closed-loop) query agents + deterministic per-query snapshot
DECIDE defines a fixed **query-agent adapter API**: each candidate runs its OWN iterative query/roadmap logic but (a) sees IDENTICAL POLARIS retrieval OBSERVATIONS, (b) under an IDENTICAL per-task budget (max query rounds, max searches, wall-clock, tokens), (c) against a **deterministic search snapshot keyed BY QUERY** (same query -> same results for every candidate; NOT a pre-shared evidence basket, which would neutralize query quality). The candidate may issue iterative normalized query/roadmap calls and adapt to what it retrieves — so closed-loop mechanisms (WebWeaver/IterResearch/DuMate/DOLORES/ScaffoldAgent) are tested AS closed-loop, with retrieval held deterministic so only query quality varies. Output of each candidate = the evidence basket it assembled, fed into IDENTICAL downstream POLARIS generation+verification.

### P1-3 (iter2) — ScaffoldAgent PROMOTED (primary source confirmed)
ScaffoldAgent (arXiv 2606.20122, submitted 2026-06-18, "Utility-Guided Dynamic Outline Optimization for Open-Ended Deep Research") is now in the build-start rescan + classification table; excluded only if runnability/adapter evidence fails.

### P1-4 (iter2) — SUBCOMPONENT taxonomy (decompose composite papers)
Classify SUBCOMPONENTS, not whole papers. Each candidate is decomposed into: (a) trained weights (run native, reported separately, not a portable GLM-5.2 front-end), and (b) portable framework/policy (the dynamic-outline / gap-requery / workspace-reconstruction LOGIC — backed by GLM-5.2 in DECIDE). E.g. AgentCPM-Report = trained-8B (a) + WARP dynamic-outline policy (b, portable). DECIDE evaluates the (b) portable scaffolds on GLM-5.2; (a) trained agents are a separate native-reference column.

### P2 (iter2) resolutions
- **Multiple-comparison control:** paired bootstrap winner-vs-floor and winner-vs-runner-up with Holm/FDR correction + the locked minimum effect threshold.
- **GATE 0 lineage hash extended:** the sha256 manifest also covers candidate adapter version, prompt template, retrieval snapshot ID, judge model+version, scorer config (not just the artifact chain).
- **Leakage audit at 3 levels:** exact-question, paraphrase/semantic, and source-domain overlap of the locked subset vs released train/eval data; prefer held-out tasks where any candidate reports on DRB/DRB-II.

## GATE 0 (hard precondition — from iter 1 P1-1, + iter-5 semantic-support canary)
Lineage manifest (incl. adapter/template/snapshot/judge/scorer + GLM-5.2 backbone hashes) with launched==packed==answered==canonical equality; positive canary in-band; FOUR negative canaries fail-loud:
1. wrong-question report scores LOW on the canonical rubric;
2. split-brain pack (canonical Q + substituted report) REJECTED by the lineage check;
3. Title-only-stub source flagged UNREACHABLE, not "unsupported";
4. **SEMANTIC-SUPPORT canary (iter-5):** a report with a REACHABLE cited source whose fetched text does NOT support / CONTRADICTS the generated claim MUST fail-loud on EACH faithfulness scoreboard's REAL DECIDE scoring path against the FINAL rendered artifact — DEER at per-claim granularity, DeepTRACE at per-statement, DeepScholar at per-sentence. This proves the scoreboards catch reachable-but-unsupported/contradicted claims (the failure the removed human read used to catch), not merely reachability/lineage.
Harness GREEN only when the positive passes AND all FOUR negatives fail-loud. No score trusted until GREEN.

## Evaluation modes (from iter 1 P1-2, refined)
- SCREEN (full-stack standalone): advisory only, never a filter.
- DECIDE (POLARIS-controlled isolation, the adapter API above): the decision basis; only query-gen varies.

## Statistics (iter 1 P1-3 + iter 2 P2)
Locked stratified task list (fixed seed); deterministic per-query retrieval snapshot; paired per-task scoring; bootstrap CIs + Holm/FDR + minimum effect threshold; finalists rerun >=3x; no selection without non-overlapping CIs / passed significance.

## Faithfulness = HARD non-regression gates (iter 1 P1-4)
Per-metric baseline floor + tolerance + noninferiority threshold (DEER support, DeepTRACE unsupported%/citation-accuracy, DeepScholar sentence-verifiability); citation-precision drop or unsupported-severity rise beyond tolerance => candidate LOSES regardless of coverage. POLARIS faithfulness gates never relaxed.

## Candidates (post-rescan, subcomponent-classified) + baselines + floor
- 2026: AgentCPM-Report/WARP (2602.06540), DuMate (2606.07299), FS-Researcher (2602.01566), ScaffoldAgent (2606.20122), PokeeResearch-7B (2510.15862), DeepResearch-R1/9K (2603.01152), DOLORES (2605.11388) — each decomposed (trained vs portable).
- 2025 baselines (REQUIRED, portable scaffolds): IterResearch/Tongyi (2510.24701/2511.07327), WebWeaver (2509.13312), ConvergeWriter (2509.12811).
- FLOOR: current POLARIS template-facets.

## Operative metric
Coverage PRIMARY (DRB-II info_recall + DeepResearch Bench RACE); faithfulness HARD non-regression gates. Regress faithfulness => lose.

## DECISION RULE — SCOREBOARDS ONLY (no human gate, iter 4)
1. ELIGIBILITY: a candidate qualifies only if it passes EVERY faithfulness guardrail at >= (floor - tolerance) on DEER (per-claim support), DeepTRACE (unsupported% + citation accuracy), DeepScholar (sentence verifiability). Regress faithfulness => auto-disqualified. These faithfulness scoreboards ARE the mechanical §-1.1 per-claim line-by-line audit.
2. SELECTION: among eligible candidates, the WINNER is the highest COVERAGE score (DRB-II info_recall + DeepResearch Bench RACE), with the locked statistics (paired bootstrap + Holm/FDR + min-effect threshold) deciding closeness/ties.
3. NO HUMAN READ decides the winner; the whole decision is the numbers. (The Codex CODE-review gate on brief + diff is a separate development gate and remains.)

## Plan
GATE 0 -> frontier rescan + subcomponent-classify + runnability -> SCREEN (advisory) -> DECIDE (all runnable portable scaffolds + floor, adapter API, deterministic snapshot, locked stats) -> finalists rerun -> WINNER = scoreboard result (faithfulness-eligible, highest coverage, significance-confirmed) -> port winner (Codex diff-gate) -> integrated POLARIS replay scored on the FULL 8-benchmark set => SECURED when the scoreboards pass (not before).

## What to check
- Iter-2 P1s resolved (SCREEN non-filtering; adaptive adapter API + deterministic per-query snapshot; ScaffoldAgent promoted; subcomponent taxonomy)?
- Does the adapter API genuinely isolate query quality for CLOSED-LOOP candidates without neutralizing it?
- Any NEW P0/P1 that makes the result untrustworthy or the decision wrong.

## Output schema (this exact schema; loose prose rejected)
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]

## ITER-3 APPROVED (verdict APPROVE, 0 P0 / 0 P1) — P2 refinements incorporated for execution
1. **DECIDE evidence-basket schema guard:** candidates emit ONLY normalized queries/roadmap/gap-labels + selected retrieved source IDs; COMMON POLARIS code performs chunking, dedup, provenance, and basket construction — so candidate-specific summarization never decides the bake-off (closed-loop adaptation preserved, basket build held constant).
2. **GATE 0 lineage manifest extended:** also hash the GLM-5.2 query-agent backbone (exact model/provider/revision), decoding params, reasoning/token caps, timeout/retry policy, and execution seed (in addition to template/snapshot/judge/scorer hashes).
3. **Frontier rescan = explicit build-start file** with include/exclude rationale + exact pins. Codex-verified primary sources: ScaffoldAgent 2606.20122 · AgentCPM-Report 2602.06540 · DuMate 2606.07299 · DOLORES 2605.11388 · FS-Researcher 2602.01566 · PokeeResearch 2510.15862 · DeepResearch-9K/R1 2603.01152 · WebWeaver 2509.13312 · IterResearch/Tongyi 2511.07327 + 2510.24701 · ConvergeWriter 2509.12811.

## ITER-6 SCOPE REFINEMENT (operator directive 2026-06-22): coverage-isolation, NO e2e
The query-gen section is scored IN ISOLATION on COVERAGE only: each method's queries -> retrieve -> required-point retrieval coverage (DRB-II info_recall + DeepResearch Bench RACE potential). NO full-report generation, NO rendering, NO DeepTRACE-judge in this section test (those gate the faithfulness sections + the final combined run). GATE 0 canonical-question binding stays (score vs the right rubrics). Winner is locked, then combined with the other section-winners for ONE final full run. SCREEN/DECIDE-e2e and the per-report faithfulness gates from earlier iters are deferred to the final combined run.
