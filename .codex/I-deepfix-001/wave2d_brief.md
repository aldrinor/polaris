# Wave 2d brief — two-sided pro/con for debate sections (`PG_TWO_SIDED_DEBATE`, default OFF)

I-deepfix-001 (#1344). Branch `bot/I-wire-001-integration`. Composition-layer only; faithfulness engine BYTE-UNTOUCHED.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Goal (REAL_PLAN traceability item 4)

DeepTRACE One-Sided (#1, binary, debate queries only) = 1 unless BOTH a pro AND a con statement are present; Overconfident (#2) = 1 if one-sided AND max confidence. A debate-framed section that renders only the majority (pro) side scores one-sided. Wave 2d makes a debate-framed section either (a) present BOTH a verified pro clause and a verified con clause, or (b) DISCLOSE the evidence asymmetry honestly when the con side is genuinely absent — NEVER fabricate a con, NEVER assert an ungrounded balancing claim. Under-relax is safe; fabricating balance is the lethal direction.

## The two halves (plan-time detector + `counter_evidence` lens)

**Retrieval half — `src/polaris_graph/retrieval/expert_facet_planner.py`.** The `counter_evidence` lens (`_ANGLE_LENSES[2]` :44, "criticism limitations counter-evidence dissent") already sources con material for every facet when `PG_EXPERT_FACET_PLANNER` is ON. Wave 2d adds a shared pure detector `is_debate_question(text)` and, when `PG_TWO_SIDED_DEBATE` is ON AND the question is debate-framed, GUARANTEES the `counter_evidence` lens is emitted even under a reduced `PG_EXPERT_FACET_ANGLES` budget (it is index 2, so a budget of 2 would otherwise drop it). Additive widener; drops nothing; caps nothing (§-1.3 WEIGHT-not-FILTER). Default OFF => `debate_active=False` => `_ANGLE_LENSES[:n_angles]` exactly as today => byte-identical.

**Composition half — `src/polaris_graph/generator/multi_section_generator.py`, `_run_section`.** After `_compose_section_per_basket` builds the section's verified units and `partition_composed_disclosures` splits them (`:5181`), a `PG_TWO_SIDED_DEBATE`-gated pass:
1. `_is_debate_section(section)` — debate framing from the section PLAN (`title` + `focus`), via `is_debate_question`. NOT a content guess.
2. Classify the con side deterministically: `con_cluster_ids = referenced_con_cluster_ids(_vc_baskets)` (reused from `debate_consolidation.py` — the `refuter_cluster_ids` the certified contradiction detector produced; the SAME signal B1 consolidates and M6's "; in contrast, " connective is licensed by). `con_ev_ids` = the `supporting_members` evidence_ids of baskets whose `claim_cluster_id ∈ con_cluster_ids`.
3. Scan the composed real units' `[#ev:<id>:...]` tokens: `has_con` = a real unit cites a con ev_id; `has_pro` = a real unit cites a non-con ev_id (an M6 conflict unit cites both, so it sets both).
4. If `has_pro AND NOT has_con` (a verified pro clause but no verified con clause — the exact one-sided-pro case) → append ONE marker-less asymmetry disclosure `[no verified counter-evidence was found for: <focus>]` to `_vc_degraded_disclosures`. It renders via the EXISTING `render_degraded_disclosures` AFTER strict_verify — never verified prose, never counted as support, `[`-prefixed (redactor no-touch). Otherwise no-op.

The con clause itself is already PLACED by existing machinery: B1 (`PG_DEBATE_CON_BASKET_CONSOLIDATION`, default-ON) consolidates the refuter con-basket into `_vc_baskets`, and `_compose_section_per_basket` composes every basket per-clause-verified against its OWN basket-scoped pool. Wave 2d never composes a new clause; it INSPECTS the composed units and discloses on absence. So the "each per-clause-verified against its OWN basket-scoped pool, NEVER a union pool" invariant is inherited unchanged from Wave-2a's per-basket path.

## Files / functions / flag

- **flag** `PG_TWO_SIDED_DEBATE` (default OFF, LAW VI). Also reuses the DEFAULT-ON `PG_DEBATE_CON_BASKET_CONSOLIDATION` (B1) placement.
- `expert_facet_planner.py`: `two_sided_debate_enabled()`, `is_debate_question(text)` (precision-first phrase regex), `_angle_lenses_for(n_angles, debate_active)`; thread `debate_active` through `plan_expert_facets`/`_facet_angle_queries`.
- `multi_section_generator.py`: `_two_sided_debate_enabled()`, `_is_debate_section(section)`, `_debate_con_cluster_ids(baskets)`, `_con_evidence_ids(baskets, con_cluster_ids)`, `_unit_evidence_ids(text)`, `_two_sided_debate_asymmetry_disclosure(section)`, `_maybe_two_sided_debate_disclosure(...)`; one gated call after `partition_composed_disclosures`.

## The never-fabricate-balance invariant (clinical-safety)

- The con side is only ever a REAL, already-verified basket clause (B1-consolidated, span-grounded, [#ev]-tokened, strict_verify-passed per clause against its own scoped pool). Wave 2d never writes a con sentence.
- When no verified con clause exists, Wave 2d appends ONLY an honest marker-less disclosure naming the absence. It contains NO `[#ev]` token, NO numeric claim, NO invented con content — it is the same faithfulness class as the existing gap / degraded-verify disclosures.
- Faithfulness engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding) is byte-untouched. The disclosure renders after strict_verify and is never re-verified, never counted as `sentences_verified`.

## Tests (`tests/polaris_graph/generator/test_two_sided_debate_wave2d.py`, offline)

- `is_debate_question` precision: True on "benefits and risks", "advantages vs disadvantages", "positive and negative views", "pros and cons", "for and against", "debate over X", "both sides"; False on "mechanism of X", "how does X work", bare "drug A vs drug B" comparison.
- OFF byte-identical: `_two_sided_debate_enabled()` False by default; expert_facet_planner emits `_ANGLE_LENSES[:2]` (no counter_evidence guarantee) under `PG_EXPERT_FACET_ANGLES=2` when the flag is off.
- ON both sides: con basket referenced by pro's `refuter_cluster_ids`, real units cite both pro and con ev_ids => `_maybe_...` returns disclosures UNCHANGED.
- ON only pro (con basket present but its unit did not compose, AND con basket absent): => exactly one `[no verified counter-evidence` disclosure appended; con NOT fabricated (no [#ev] token, no con prose); real_units untouched.
- Non-debate section: `_is_debate_section` False (never discloses even when con absent).
- ON counter_evidence guarantee: `PG_TWO_SIDED_DEBATE=1` + debate question + `PG_EXPERT_FACET_ANGLES=2` => "counter-evidence" appears in `facet_seed_queries`.

## Files I have ALSO checked and they're clean

- `src/polaris_graph/generator/debate_consolidation.py` (B1) — the con-basket consolidation + `referenced_con_cluster_ids` / `should_hedge_confidence` that Wave 2d reuses; unchanged.
- `src/polaris_graph/generator/cross_source_synthesis.py` (Wave-2a) — the M6 conflict connective ("; in contrast, ") + `LICENSED_CONNECTIVES`; a conflict unit cites both pro+con ev_ids so the Wave-2d scan counts it as two-sided; unchanged.
- `verified_compose.py`: `_compose_section_per_basket` / `_section_baskets_for_compose` (B1 already wired here) / `_per_basket_verified_clause` / `_basket_scoped_pool` (own-pool invariant) / `partition_composed_disclosures` / `render_degraded_disclosures` / the `[`-prefixed disclosure-carrier contract — all read, none modified.
- `credibility_pass.ClaimBasket` / `BasketMember` shapes (`claim_cluster_id`, `refuter_cluster_ids`, `supporting_members[].evidence_id`) — read for the con classifier; unchanged.
- `_run_section` branch selection (FIX-K / verified-compose / legacy) — Wave 2d fires only inside the verified-compose branch where `_vc_baskets` exists; other branches unchanged.

## `git diff --stat` expectation

ONLY `src/polaris_graph/generator/multi_section_generator.py` + `src/polaris_graph/retrieval/expert_facet_planner.py` + `tests/polaris_graph/generator/test_two_sided_debate_wave2d.py`.
