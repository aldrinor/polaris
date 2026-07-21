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
