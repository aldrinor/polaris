# Round-2 RACE/FACT rollout — execution plan (Sol-corrected, 2026-07-21)

Three-model audit (Sol · Fable · K3, blind) converged: the fixes are already built but flag-gated OFF /
unwired / stripped from the general path. Round 2 = ARM + WIRE + enforce, all upstream, general, faith-ghost-
clean. Baseline after Step 1: RACE 0.4643 (Readability 0.4428 weakest); FACT 20 cites / 0.85.

## The 7 levers
- **A** STRUCTURE — wire summary_table.py / presentation_tables.py + un-forbid structure (abstractive_writer.py:419) + SectionPlan subsections.
- **B** SOURCE ELIGIBILITY — task-derived eligibility contract from the orphaned constraint_extractor at the citable-pool boundary + citation re-anchoring (secondary→primary before verify).
- **C** COVERAGE — fix verified_compose.py:1978 first-failure break (C1); route/novelty optimizer (C2); multicited (C3).
- **D** SYNTHESIS — typed ComparativeFact cards (do NOT wire the broken contradiction finder; generalize the clinical cross-trial synth).
- **E** FETCH-UNTIL-USABLE — PG_FETCH_MIN_BODY_CHARS floor + DOI/PMID stubs through the frame_fetcher salvage lane.
- **F** CANONICALIZE WORKS — merge 55 same-work groups before numbering.
- **G** HONEST METHODS/LIMITATIONS — render from a typed RunFacts record.

## Sol-corrected execution order (dependency-safe, 4 batches)
`B → E → F → A1+G → C → D+A2`

| Batch | Order | Release constraint |
|---|---|---|
| 1 · Evidence substrate | B contract → E salvage → F canonicalize → primary re-anchor → B final citable gate | **must precede coverage** |
| 2 · Document contract | A1 structure/tables + G RunFacts | independent of coverage; render honest gaps |
| 3 · Coverage | C1 first-failure fix → C2 route optimizer → C3 multicited | requires Batch 1 active |
| 4 · Analytical depth | D comparison cards + A2 tables | requires canonical eligible evidence; after C |

**Mandatory dependencies (Sol, verified in code):** B before C (else route-all amplifies ineligible/secondary/post-cutoff material); F before C (optimize distinct canonical works, not URLs); E before C (stubs aren't coverage); A independent of C (render structure even with thin evidence); D after C; A2 co-ships with D. Don't co-ship all of C as one treatment — C1 is a safe bugfix, C2 (route-all) is the risky nonlinear component.

## Flag manifest (env presence ≠ treatment)
Several "OFF" flags are actually ON-but-unwired (cross-source-synthesis, subtopic-decomposition default-on; summary-table flag on but renderer never called; route-all already on in the runner). Every lever's manifest records `resolved_value` AND `fired_count`.

## Validation (Sol-corrected — replaces leave-one-out)
Staged cumulative scoring: baseline → +B/E/F/re-anchor → +A1/G → +C1 → +C2 → +C3 → +D/A2 → fresh all-on. Plus factorial interaction checks: B×C2 (4 cells) and C2×C3 (4 cells). Re-score each artifact ≥3× (LLM-judge variance). Deterministic levers (B/E/F/A/G) need contract/fixture tests + one stage-boundary score; C1/C2/C3/D need sequential full RACE scoring.

## Biggest risk + de-risk
Risk: **coverage amplification** — route-all floods low-value/stub/ineligible/duplicate rows, hurting FACT+Readability even as raw citation count rises. De-risk: a zero-generation **shadow routing manifest** that flags any proposed addition lacking eligibility+cutoff / usable body / canonical identity / primary preference / positive marginal coverage / context-budget fit — before it routes.

## Infra
Every lever: own config flag (default = current, byte-identical off), central config (resolve()+config_defaults), plain names, docs, checkpoint-safe, faith-ghost untouched, general (reads the task's own words — no benchmark literals). Executed batch-by-batch via workflow; each batch gated by Sol+K3 and scored before the next. Rollback tag `foundation-faithoff-v1`.

## Batch-3 follow-ups (recorded during Batch-1 gate)
- **Multi-cited re-anchor consistency (K3, non-blocking):** `verified_compose.py` `_multicited_writer_clause` (~:2297) and `compose_basket_multicited_synth_primary` (~:2466) build `scoped_pool`/`regions` WITHOUT first calling `_maybe_reanchor_basket_members`. Harmless today (fires only when BOTH `PG_VERIFIED_COMPOSE_MULTICITED` and `PG_CITATION_REANCHOR_PRIMARY` are ON; fail-open — citations simply aren't upgraded, scoped_pool stays id-consistent, verify unaffected). When Batch 3 arms C3 (multicited), head those two paths with the re-anchor call for parity with `_compose_one_basket`.

## Update 2026-07-21 — generator swap + Batch-2 structure (part 1) + Sol re-sequence
- **Generator locked in: GLM-5.2 -> Kimi K3** (scripts/run_k3.sh, commit 1a5b751). A/B RACE 0.4605 -> 0.4903 (+0.030), Insight +0.045, Comprehensiveness +0.030. General (frontier open model). Inkling deferred: OpenRouter serves it only via Together @ 512K (native 1M needs a paid dedicated Fireworks/Baseten deploy); its 512K overflowed one 581K-token section. A general provider-transient retry-resilience change (openrouter_client.py) was built for it and is gate-pending.
- **Batch 2 (structure) part 1: PG_SECTION_STRUCTURE** — a default-OFF section-prompt transform (rule 7 flips flat-prose -> ###/table/bullet, keeping the [ev_XXX]-per-unit contract). Sol(max)+K3 dual-approved on code. BUT K3's gate found the render seam FLATTENS it: provenance_generator.py:5121 `" ".join(findings_lines)` + 5106 citation-to-unit-end + _strip_bogus_ev_markers:714 `\s{2,}` collapse newlines even under strict_verify_off. So the prompt-transform is a NO-OP until paired with a render-preservation pass.
- **Sol (max reasoning) re-sequenced the remaining work:** Readability is 1 of 4 dims (+0.05 Readability ~ +0.0125 overall), so run **C (coverage: route-all-into-eligible-sections + multi-citation) FIRST** (Comprehensiveness + recovers K3's FACT), THEN the structure fix as a GATED post-resolution LAYOUT REPLAY at provenance_generator.py:5106/5121 (reuse the finalized ev_to_num, join structured units with "\n"; never a second resolver; fix the 714 whitespace collapse to `[^\S\r\n]`), validated by REPLAYING the saved K3 draft through old+new renderers before paying for a new generation. Long-term correct design = typed blocks/cards (D comparison cards then lift Insight AND Readability).

## Update 2026-07-21 (evening) — the route-all contamination + 3-model audit + the 6-step recovery
**Contamination found.** `scripts/compose_agentic_report_s3gear329.py` carried
`os.environ.setdefault("PG_ROUTE_ALL_BASKETS","1")`, which silently forced route-all ON for EVERY run
(env overrides the config default of 0). So every recent scored run (b1_run, k3gen_run, k3_b1_run, and
the route-all run) was route-all-ON, and the route-all A/B (0.5084 vs 0.5023) was VOID — both arms had it.

**Three-model forensic audit (Sol + Fable + K3, full repo access + web search, max reasoning), verdicts:**
- Fable: caught the contamination (champion log `routed 949 orphan baskets`); the -0.0061 is generation noise below the repo's ~0.007 SD floor. VOID the A/B, re-run clean.
- Sol (strongest): pinned the leak (compose script `setdefault(...,"1")`); showed the delta is UPSTREAM outline stochasticity (route-all run drew 2 agent-turns vs 5 -> the Skills section got 21 ev_ids vs 49 -> fewer sentences), REFUTED dilution as the cause (section-level rows-vs-sentences is non-monotonic) and REFUTED displacement (ids appended, order preserved). KEEP off; replace force-all with a relevance+marginal-novelty router; retest from a FROZEN pre-routing checkpoint.
- K3 (weakest — MISSED the contamination, assumed champion=off; several claims refuted by Sol): but a valid DESIGN critique — the off-topic judge is bypassed (priors-only gov-suffix baskets), shallow one-word overlap mis-routes, ~40% of routed evidence goes to a residual section the render drops.

**What we accept / reject:** accept the contamination + leak-line (Fable+Sol, verified in logs/code); accept the delta = outline-noise (Sol+Fable, logic: both arms route-all-on); accept route-all-off + marginal-coverage-router-if-revisited (K3+Sol design critique) + frozen-checkpoint methodology (Sol+Fable). Reject K3's "dilution/displacement caused the delta" (wrong premise, refuted). The prior +0.048 climb (GLM 0.4605 -> K3 0.4903 -> K3+B/E/F 0.5084) STANDS as relative deltas (route-all was a constant across all runs), but the ABSOLUTE champion number is route-all-ON and must be re-measured clean.

**6-step recovery (in progress):** (1) kill the setdefault leak so config default 0 governs [DONE, Sol-gated]; (2) re-measure the true champion clean (route-all verified OFF via absence of the routing log line; 3 generator draws x 3 judge draws) + FACT; (3) adopt frozen pre-routing checkpoint + multi-draw for all future lever A/Bs; (4) route-all stays off, no force-all; (5) skip composing the residual section that render drops (efficiency); (6) resume the real levers (structure/Readability + more high-value coverage) under the clean method. Every step: claude implements -> test -> Sol (full --search, max reasoning) gate -> commit + doc.

## Update 2026-07-21 (late) — the clean measurement REVERSES the route-all verdict
Step 2 (clean champion, route-all genuinely OFF, K3+B/E/F, 3 generator x 3 judge draws) scored RACE
**0.4722** (0.4765/0.4703/0.4698, tight) vs route-all-ON **0.5084** = route-all is worth **+0.036**
(Comprehensiveness 0.521->0.478, Insight 0.524->0.478; report 5081w/21cites vs 9438w/144cites). So
route-all is LOAD-BEARING, not noise. The three-model audit correctly caught the A/B was contaminated
(both arms ON, delta=outline noise) but wrongly extrapolated "keep OFF" — none of them had measured
the clean OFF arm. CORRECTION: route-all is now EXPLICITLY ON in run_raw_a.sh (the silent setdefault
stays removed so config governs; the recipe chooses on). True champion = 0.5084. NEXT: build the
marginal-coverage router (relevance + marginal-novelty gate on the orphan routing) to KEEP the +0.036
coverage and drop the off-topic orphans the audit flagged -> target > 0.5084.
