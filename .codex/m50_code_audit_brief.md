M-50 audit — sixth of 7 V28 bundle items.

## Commit

`12dd342` PL: M-50 — per-trial subsection generator (4th BEAT_BOTH target)

## Plan reference

`outputs/audits/v27/fix_plan_v28.md` M-50 (NEW per your V28 plan
pass-1 completeness review). Your verbatim:

> "Per-trial subsection outline generator: add a small V28 item if
> the goal is a fourth BEAT_BOTH. M-45's table + timeline likely
> moves Structural depth from LOSE_BOTH to BEAT_ONE, but ChatGPT
> still wins on per-trial PICO/effect details and Gemini still
> wins on narrative trial subsections. Minimal acceptance:
> subsections for SURPASS-2, SURPASS-4, SURPASS-CVOT, and
> SURMOUNT-2 with N, population, comparator, endpoint/timepoint,
> effect estimate, uncertainty/interpretation, and safety caveat."

## What changed

`src/polaris_graph/generator/multi_section_generator.py`:
- `_M50_MIN_PRIMARIES_FOR_SUBSECTIONS = 2` (strict gating).
- `_M50_SUBSECTION_SYSTEM_PROMPT` (4-6 sentence prose requiring
  7 elements inline; placeholders only, no drug names).
- `_call_m50_per_trial_subsection()` — single LLM call per trial.
- `_m50_select_candidate_trials()` — filters by direct_anchors,
  ≥100 char quote (direct or refetched), valid bibliography.
  Returns [] below 2-trial threshold.
- Wired into `generate_multi_section_report` after Trial Summary
  table. Parallel gathers via existing sem.
- `MultiSectionResult` gets 4 new fields (text, entries, in_tokens,
  out_tokens).

`scripts/run_honest_sweep_r3.py`:
- Derives direct_trial_anchors from
  per_query_trial_population_scope (SURMOUNT-2 direct;
  SURMOUNT-1/3/4 excluded).
- Inserts "## Per-Trial Summaries" block into report.md between
  Trial Program Timeline and Limitations.
- Persists m50_per_trial_subsections.json.

## Tests

11 new M-50 tests in
`tests/polaris_graph/test_m50_per_trial_subsections.py`:
- Candidate selection: 2-primary pass, 1-primary below threshold,
  indirect excluded, thin-quote excluded, refetched qualifies,
  missing biblio excluded, empty-direct-set fail.
- Constants: min_primaries=2.
- Prompt structure: 7 elements present, citation-per-claim,
  placeholders only.

292/292 full M-series regression.

## What to audit

1. **Strict gating**: ≥2 primaries required; below threshold
   suppresses all subsections. Matches your plan?
2. **Indirect exclusion**: SURMOUNT-1/3/4 (obesity-only) excluded
   via direct_trial_anchors param sourced from
   per_query_trial_population_scope. Sufficient for the T2D
   question context?
3. **Quote selection**: picks richer of direct_quote or
   _m42b_refetched_quote (same pattern as M-47 pass-2 after
   Codex audit). Consistent?
4. **Prompt rule**: 7 elements (N, population, comparator,
   endpoint, timepoint, effect-with-uncertainty, safety). All
   present?
5. **Report placement**: "## Per-Trial Summaries" block sits
   between Trial Program Timeline and Limitations. Logical?
6. **Parallelism**: subsection generation uses the same sem as
   per-section gen. Rate-limit concerns?
7. **Coverage gap**: the plan names 4 candidate trials (SURPASS-2,
   SURPASS-4, SURPASS-CVOT, SURMOUNT-2). My implementation is
   template-driven — all T2D-direct anchors in the template's
   scope dict are candidates, not a hard-coded list. Acceptable
   generalization?

Write verdict to `outputs/codex_findings/m50_code_audit/findings.md`.
On READY/CONDITIONAL-no-blockers: Claude proceeds to M-49
(preservation suite extension).
