# Brief — I-arch-s5-001: S5 COMPOSE section-basket map keystone (Design 4 D1) + D2 compose fast-path

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Scope (ONE work package of the S5 section; not all of S5)

Per `MASTER_EXECUTION_PLAN.md` v2 S5 + `04_baskets_per_section.md` (Design 4) WP1/WP2-fast-path.
Builds the deterministic basket→section map that replaces the global basket→section
intersection leak (drb_72: ~600 of 657 baskets stranded) with per-section placement + roles
(one primary home per basket + corroborating facets), `stranded_count == 0` by construction.

**Deferred to later S5 WPs (LOUDLY, not silently):** holistic whole-report review
(`generator/holistic_review.py` + `:10633` seam, Design 2), the deliverable style block
(Design 3 consumer 2), fact_dedup changes, the full map threading through
`generate_multi_section_report` (:9762) with the primary/corroborating role compose policy,
per-section merge-refinement NLI (Design 4 D4), and the cp5 generation snapshot writer. Those
need the live generator/LLM stack and cannot be proven offline this turn.

## Files touched
- NEW `src/polaris_graph/synthesis/section_basket_map.py` — pure module (no LLM/network).
  Dataclasses `SectionBasketView` / `SectionBasketMap`; `build_section_basket_map(...)`;
  `section_basket_map_enabled()`; `resolve_weights()`; `dumps_map()`.
- EDIT `src/polaris_graph/generator/verified_compose.py` — `_section_baskets_for_compose`
  gains keyword-only `section_basket_map` + `section_index`; Design 4 D2 fast path returns the
  section's mapped baskets when `PG_SECTION_BASKET_MAP` is ON; default None + flag OFF =
  byte-identical legacy intersection. Two helpers added (`_section_basket_map_consume_enabled`,
  `_baskets_from_section_map`).
- NEW fixture `tests/fixtures/section_basket_map/drb72_mini.json` — real drb_72 evidence_ids.
- NEW tests `tests/polaris_graph/test_section_basket_map.py` (12) +
  `test_section_basket_map_compose_seam.py` (3).
- NEW `scripts/replay_section_basket_map.py` — offline replay harness (Design 4 §7a).

## Contract proven offline (Design 4 §7b acceptance subset)
- A1 coverage: `stranded_count == 0`; every basket has a home; orphan → residual section.
- A2 uniqueness: exactly one primary home per basket; corroborating facet = section-matched subset.
- A4 determinism: byte-identical across 3 repeated builds AND basket input-permutation.
- A6 (module + seam half): `PG_SECTION_BASKET_MAP` default OFF; seam byte-identical OFF; ON uses map.
- Plus: tie-break → lowest section index; sub-query lineage signal fires; weights read via env (LAW VI).
- Deferred to VM hamster (need rendered report / NLI cross-encoder): A3 no-duplication in a
  rendered report, A5 faithfulness before/after §-1.1 audit, A7 recall merge, A8 wall-clock.

## §-1.3 / faithfulness
Pure PLACEMENT + ROLE tagging. Drops nothing, caps nothing, targets no number. Never reads or
mutates sentence text or the `[#ev:<id>:<start>-<end>]` provenance token (source-tie neutral).
Zero diffs under strict_verify / NLI / D8 / provenance / span-grounding.

## Test command
`python -m pytest tests/polaris_graph/test_section_basket_map.py tests/polaris_graph/test_section_basket_map_compose_seam.py -q`

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
