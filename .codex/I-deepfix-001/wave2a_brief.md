# Wave 2a brief — cross-source analysis into the body (pairing predicate + numeric comparator)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What this wave is

I-deepfix-001 (#1344) Wave 2a: the cross-source-analysis-into-the-body unit. Clinical-safety-critical, faithfulness-adjacent. Three items from `REAL_PLAN_2026.md` `coverage_fix` items 2 + 3 and the `faithfulness` section. Builds on Wave 1a (composition core) + 1b (basket regroup) which are already committed. ALL new behavior is behind default-OFF flags; OFF => byte-identical.

## Ground-truth state I verified before coding (matters — the parent's framing predates Wave 1a)

- `compose_cross_source_analytical_units` (`cross_source_synthesis.py`) is **already in the body**: it is called from `verified_compose._compose_section_per_basket` (`verified_compose.py:2467-2496`), gated by `PG_CROSS_SOURCE_SYNTHESIS` (**DEFAULT-ON**, `verified_compose.py:214-229`). `edges`/`equiv_clusters`/`agree_map` are already threaded (`multi_section_generator.py:5101-5145`). It is **NOT** in the fail-open tail.
- Only `depth_synthesis.synthesize_cross_source_findings` (a **top-of-report DIGEST layer**, gated `PG_SWEEP_DEPTH_LAYER`) lives in the fail-open tail (`run_honest_sweep_r3.py:15964-16038`).
- Baskets (`ClaimBasket`, `credibility_pass.py:403-426`) carry `claim_cluster_id`, `claim_text`, `subject`, `predicate`, `supporting_members`, `refuter_cluster_ids` — **no `facet` field exists**.
- `AtomicClaim` (`claim_graph.py:152-186`) retains `normalized_key` (the merge-key tuple) but NOT the raw numeric fields. The REDESIGN key (`build_merge_key`) singleton-forces on any unknown discriminator; the LEGACY key (`_normalized_key_numeric`) only sentinels on a blank SUBJECT (a blank predicate/unit/dose/arm/endpoint passes as `""`) — so the comparator enforces the non-blank guard itself (Fable P1, see decision 3).

## Design decisions (call these out — they shape the build)

1. **Facet proxy = same normalized `subject`.** No `facet` field exists on baskets, and every basket handed to `compose_cross_source_analytical_units` is already the same *section*, so "same section facet" cannot be a basket attribute or "same section" (too broad => O(N^2) random juxtaposition). The current anchor is `subject|predicate` (both must match) which self-annuls because consolidation merges same-subject-same-predicate claims into ONE cluster. The minimal, bounded relaxation that stops the self-annulment is **subject-only** grouping: two baskets about the SAME entity/subject (differing predicate) are on the same facet. Bounded by subject; never arbitrary.
2. **Depth-tail relocation DEFERRED to Wave 3.** I do NOT move `depth_synthesis.synthesize_cross_source_findings` out of the tail. It is async (LLM pre-pass), top-of-report (all baskets, not per-section), and duplicative of the body (there is already a #1335 body-vs-DS dedup). `REAL_PLAN_2026.md` `wave_3_activate_and_archive` step 2 explicitly archives the advisory tail AFTER the body units are proven — that is the right sequencing. Relocating it now is non-surgical and risks duplication; I report rather than guess (per the STOP-and-report instruction).
3. **Numeric comparator emits a NON-directional comparative connective** (`"; for comparison, "`), never a directional "higher/lower than" arithmetic claim. This matches the codebase's own conservative stance (`relational_quantifier_guard.py:154-168,391-396`: "comparative full-rewrite is a DEFERRED increment"). Under-relax is safe; a directional claim is the over-relax risk. The connective asserts only that the two verified numbers are directly comparable (all discriminators equal + positively known); each clause keeps its OWN token. **Fable P1 fix (clinical-safety):** the legacy `_normalized_key_numeric` only sentinels on a blank SUBJECT (`claim_graph.py:240-241`), so a blank predicate/unit/dose/arm/endpoint slips through as `""`. Blank is UNKNOWN — so `_numeric_comparability_key` ADDITIONALLY requires EVERY discriminator to be non-blank (fail-closed). This is a strict tightening enforced in `numeric_comparator.py` (NO-OP on redesign keys, which already singleton-force on any unknown field); it CLOSES the "compare %-points vs mmol/mol whose unit was never established" hole. Reachable only under `PG_SWEEP_CREDIBILITY_REDESIGN=0` + `PG_NUMERIC_COMPARATOR=1`, but clinical => fixed.
4. **No `relational_quantifier_guard.py` edit.** The guard's `_neutralize_unlicensed_connectives` only NEUTRALIZES *known* connective phrases whose relation is unlicensed. The composer only ever emits `"; for comparison, "` when it has *licensed* "comparison", so there is no unlicensed case to neutralize. Adding "for comparison" to the guard regex would risk neutralizing a source-prose "for comparison" on the DEFAULT-ON `PG_CROSS_SOURCE_SYNTHESIS` path (an OFF-byte-identity break). Leaving the guard untouched => the licensed comparison connective passes through unchanged AND OFF stays byte-identical. Safer, fewer files.

## Files / functions / flags

**New flags (both default-OFF; LAW VI):**
- `PG_CROSS_SOURCE_BODY` — switches the pairing predicate in `compose_cross_source_analytical_units` from anchor-equality to plan-driven. OFF => the existing `_basket_anchor` (`subject|predicate`) grouping, byte-identical.
- `PG_NUMERIC_COMPARATOR` — enables the deterministic numeric comparator. OFF (or no lookup threaded) => the comparator is never consulted; the relation set stays {conflict, agreement, extension, neutral}, byte-identical.

**NEW `src/polaris_graph/generator/numeric_comparator.py`** (pure, deterministic, offline):
- `numeric_comparator_enabled()` — `PG_NUMERIC_COMPARATOR` reader (default OFF).
- `_numeric_comparability_key(normalized_key)` — returns `(discriminators_tuple, value)` iff the key is a numeric merge-key (`[0]=="numeric"`, float value at `[3]`); the discriminators tuple is the key WITHOUT the value slot. Any sentinel (`__numeric_unknown__` / `__unresolved__` / qualitative) or unknown discriminator => `None` (FAIL-CLOSED — the merge key already singleton-forces on any unknown field). Value position invariant (`[0]=="numeric"`, value at `[3]`) holds across the legacy `_normalized_key_numeric` AND both redesign `MERGE_KEY_SPEC` numeric specs.
- `license_numeric_comparison(key_a, key_b)` — `"comparison"` iff both comparability keys are non-None AND their discriminator tuples are EQUAL (measure/unit/entity/qualifiers all match, all positively known) AND the two verified values DIFFER; else `None` (fail-closed to neutral). Pure arithmetic (`==` / `!=`) over already-verified values.
- `build_numeric_key_lookup(claims)` — `{claim_cluster_id: normalized_key}` for `kind=="numeric"` claims (all claims in a cluster share the key).

**`src/polaris_graph/generator/cross_source_synthesis.py`:**
- Add `"comparison": "; for comparison, "` to `LICENSED_CONNECTIVES` (unused unless comparison is licensed => OFF byte-identical).
- Add `cross_source_body_enabled()` (`PG_CROSS_SOURCE_BODY`, default OFF).
- Refactor the per-pair processing (clause build via `_first_verified_clause` -> distinct-id -> shared NLI signals -> `license_relation` -> comparator upgrade -> join -> guard -> >=2-distinct-id keep) into `_process_pair(...)`, sharing a per-basket clause cache. The OFF (anchor) enumeration and the ON (plan-driven) enumeration both feed the SAME processing + the SAME `eligible_pairs`/`units`/loud-canary accounting => OFF byte-identical.
- `_plan_driven_candidate_pairs`: all unordered distinct-cluster pairs admitted iff same-facet (subject) OR `_edge_between` OR refuter cross-reference OR `_agree` lookup. (Pure cross-subject NLI-only candidacy is deferred for cost; NLI still refines the connective within candidates.)
- Comparator hook: after `rel = license_relation(...)`, when `rel == "neutral"` AND `numeric_comparator_enabled()` AND a `numeric_key_by_cluster` lookup is threaded, upgrade to `"comparison"` iff `license_numeric_comparison` licenses it. conflict/agreement/extension always take precedence.
- New optional param `numeric_key_by_cluster: Optional[dict] = None` (default None => comparator never consulted).

**`src/polaris_graph/generator/verified_compose.py`:** thread `numeric_key_by_cluster` (optional, default None) through `_compose_section_per_basket` into the `compose_cross_source_analytical_units` call. None => byte-identical.

**`src/polaris_graph/generator/multi_section_generator.py`:** at the two `_compose_section_per_basket` call sites (`:5101`, `:5137`), pass `numeric_key_by_cluster=` built once from `credibility_analysis.claims` via `build_numeric_key_lookup` — but ONLY when `numeric_comparator_enabled()`; else `None`. OFF => None => byte-identical.

## The per-clause-verify invariant (NON-NEGOTIABLE — clinical-safety)

Each factual clause of a cross-source unit is built by `_first_verified_clause` -> `verified_compose._per_basket_verified_clause` -> `_compose_one_basket`, which strict_verifies EACH sentence against THAT basket's OWN `_basket_scoped_pool` + the own-region gate (`_tokens_within_basket_regions`). **NEVER one aggregate sentence verified against a union pool** — that is the lethal trap the F1-1 comments name (`verified_compose.py:1576-1583`). The connective carries NO token and is licensed ONLY by the certified engines (`_edge_between` / `consolidation_nli.entails_directional` / the deterministic numeric comparator), failing CLOSED to neutral. `strict_verify` / NLI / D8 / provenance / span-grounding are BYTE-UNTOUCHED. Under-relax is safe; over-relax is lethal.

## Tests (`tests/polaris_graph/generator/test_cross_source_body_wave2a.py`) — offline, no model, no GPU

- OFF byte-identical: `PG_CROSS_SOURCE_BODY` unset => anchor-equality pairing (same subject|predicate pairs unit; different-predicate pairs do NOT); tail location unchanged (comparator/plan-driven never consulted).
- ON plan-driven: same-facet (same subject, diff predicate) => a unit forms (did not under OFF); contradiction-edge => conflict connective; agreement (bidirectional NLI stub / agree_map) => agreement connective.
- ON per-clause own pool: a recording stub `verify_fn` proves EVERY verify call receives a single basket's OWN scoped pool (never the {A,B} union); a foreign-cited clause fails closed (no unit).
- ON numeric comparator: full match-key + differing values => `"comparison"` licensed; any differing/unknown discriminator => fail-closed to neutral.
- ON canary: eligible candidate pairs but 0 surviving units => the loud `logger.warning` fires (failed validation).

## Files I have ALSO checked and they're clean

- `relational_quantifier_guard.py` — NOT edited (decision 4); the licensed comparison connective passes through, and `_COMPARATIVE_RE` needs "…than" so "for comparison" never trips it.
- `depth_synthesis.py` / `key_findings.build_depth_layer` — the depth tail; NOT touched (decision 2, Wave 3).
- `run_honest_sweep_r3.py` / `run_gate_b.py` — the fail-open tail + slate; NOT touched this wave.
- `claim_graph.py` `MERGE_KEY_SPEC` / `_normalized_key_numeric` — READ-ONLY; the comparator consumes the retained `normalized_key`. The redesign key is fully fail-closed; the legacy key only sentinels on subject, so the comparator enforces the non-blank-discriminator guard itself (Fable P1).
- `both_sides.py`, `finding_dedup.py`, `consolidation_nli.py` — read; the comparator does not touch consolidation/merge semantics (it reads keys, never merges).
- Existing tests `test_cross_source_synthesis_m6.py`, `test_d2_extension_relation_ideepfix001.py`, `test_cov_c2_synthesis_default_on_ideepfix001.py` — the OFF path must keep these green (no regression).

## Runtime note (paid-run monitor, Fable P2c)

`PG_CROSS_SOURCE_BODY=1` on a LARGE same-subject section is `O(N^2)` candidate pairs, each costing up to 2 resident-cross-encoder NLI forward passes (per-basket clause is cached, so clause-build is `O(N)`). There is **no cap** — this is correct per §-1.3 (breadth EMERGES; a cap would be the banned filter-and-cap anti-pattern), and the NLI reuses the resident consolidation encoder (zero extra OpenRouter/GPU spend). But a pathological section with a very large single-subject basket set could add measurable wall-clock. The paid-run 5-minute forensic monitor should watch the cross-source pass timing on any section whose baskets collapse to one subject; if it dominates, the right lever is a per-section bounded-parallel NLI budget (a WEIGHT on compute order, never a breadth DROP), not a pair cap.
