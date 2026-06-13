# Codex diff review — I-bench-veracity-003 18-blocker remediation (#1226–#1243) — ITER 2

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Context
Your iter-1 review returned REQUEST_CHANGES with 0 P0, 3 P1, 2 P2 on this 18-blocker diff (the
faithfulness gates — strict_verify, NLI entailment, 4-role D8, provenance — were confirmed untouched,
0 P0). All 5 findings have now been addressed. VERIFY each is resolved and that the fixes introduced
NO new P0/P1. The faithfulness lock is unchanged: no fix relaxes any gate; all changes are env-gated
(default-OFF) or the existing default-ON kill-switches.

Offline tests after the fixes: 303 passed, 0 failed (full blocker suite + existing-module regression
for fact_dedup / provenance / completeness / evaluator_gate / multi_section / source_breadth /
subquery_floor / role_transport). One PRE-EXISTING collection error in an untouched file
(test_provenance_generator_entailment.py, `polaris_graph` vs `src.polaris_graph` import) is unrelated.

## Your iter-1 findings → how each was resolved (VERIFY)

### P1 #1233 — canary measured assigned MENU breadth, not verified CITED breadth
Iter-1: multi_section_generator.py:1154-1168 raised on `len(global_used)` (distinct sources ASSIGNED to
section menus at SELECTION time, pre-generation) while the error text claimed "distinct cited sources".
RESOLUTION:
- Removed the RuntimeError from `_augment_legacy_section_breadth`; it now logs the menu breadth honestly
  labeled "candidate menu breadth (pre-generation, not the cited count)".
- Added a PURE module helper `enforce_breadth_canary(distinct_cited_sources, minimum)` (raises iff
  minimum>0 and below; minimum<=0 no-op).
- run_honest_sweep_r3.py now calls it AFTER the bibliography is built (`multi.bibliography` = the distinct
  CITED sources), counting DISTINCT normalized source keys (url → DOI → __bibnum__ fallback), reading
  PG_BREADTH_CANARY_MIN (default 0=off, fail-closed when set). VERIFY the count is over the final cited
  set, not the menu, and that default 0 is a no-op.

### P1 #1239 — bib "require locator" orphaned body [N] citations; DOI-only rendered blank URL
RESOLUTION (run_honest_sweep_r3.py `_render_bibliography_lines`):
- A locator-less CITED entry now KEEPS its `[num]` and renders
  `[{num}] {statement} — no resolvable URL/DOI locator (disclosed evidence gap, tier {tier})` so the body
  `[N]` marker still resolves (no orphan). The number-less `[gap]` line is gone.
- When require_locator is ON and url is blank but a non-blank DOI exists, render `https://doi.org/{doi}`.
- require_locator=False (PG_BIB_REQUIRE_LOCATOR off) stays byte-identical. VERIFY no orphan + DOI locator.

### P1 #1242 — tier disclosure not single-source (Methods deterministic vs Limitations LLM-authored)
RESOLUTION:
- live_deepseek_generator.py `_format_telemetry_block` gained keyword-only `tier_disclosure_override`:
  when non-None it emits that EXACT canonical tier string verbatim instead of re-deriving per-tier from
  fractions (None => byte-identical legacy).
- Threaded through multi_section_generator.py `_call_limitations` → `generate_multi_section_report`.
- run_honest_sweep_r3.py passes `tier_disclosure_override=_tier_mix_disclosure_summary(dist.tier_fractions)`
  — the SAME canonical string Methods renders (run_honest_sweep_r3.py:3578) — when
  PG_TIER_DISCLOSURE_SINGLE_SOURCE (default ON) else None. So the LLM's only tier figure is the canonical
  one. VERIFY both sections now derive from one rendered string and the model is told to use it verbatim.

### P2 #1228 — capped-dedup reassignment laundered the real floor cut to dropped=0 on the [select] line
RESOLUTION: captured `_floor_dropped_count = evidence_selection.dropped_count` BEFORE the
`if _use_finding_dedup and _capped_dedup and _relevance_floor is not None:` reassignment; added
`floor_dropped={_floor_dropped_count}` to the [select] log + an additive manifest key
`evidence_floor_dropped` (gated on `_relevance_floor is not None`). Telemetry-only; selection unchanged.

### P2 #1240 — module-global token-honesty counters not reset between runs
RESOLUTION: run_honest_sweep_r3.py calls `reset_token_honesty_telemetry()` near the start of
`run_one_query` (~L2517) and snapshots `get_token_honesty_telemetry()` into `manifest['token_honesty']`
at success-manifest assembly, gated on `_token_honest_drop_enabled()` (PG_PROVENANCE_TOKEN_HONEST_DROP).

## Things to scrutinize for NEW P0/P1 introduced by these fixes
1. #1233: the post-bibliography canary call — confirm it runs on the SUCCESS path only and a default
   (PG_BREADTH_CANARY_MIN unset) run is unaffected; confirm distinct-key counting does not crash on a
   bibliography entry missing both url and doi (uses __bibnum__ fallback).
2. #1239: confirm a normal entry WITH a url renders EXACTLY as before (the DOI fallback must not alter the
   present-url path), and that require_locator=False is byte-identical.
3. #1242: tier_disclosure_override threading — confirm None default keeps `_format_telemetry_block` output
   byte-identical, and the override string is the SAME value Methods uses (no second derivation).
4. #1228/#1240: confirm the new manifest keys are purely additive and gated so a flag-off run's manifest is
   unchanged; confirm reset_token_honesty_telemetry() at run start cannot drop a real signal mid-run.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
APPROVE iff zero P0 and zero P1. Default-OFF dormant code, the intended default-ON behavior of the two
existing kill-switches, honest cross-file defers, and config-only items are NOT defects.
