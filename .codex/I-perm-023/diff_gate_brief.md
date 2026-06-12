# Codex DIFF gate — I-perm-023 (#1215) PR-1: constrained-greedy diversity-aware selection

## ITER-1 P1 RESOLUTION — verify this fix (the crux of iter 2)
Your iter-1 P1: the greedy pass could undo `_apply_domain_cap` — it protected domain-pass BROUGHT-IN
rows, but could still admit a novel-bucket candidate from an AT-CAP domain by evicting a DIFFERENT-domain
row, pushing that domain back over the #956 cap (regressing source diversity on the force-on path).

**Fix applied (verify in the patch):**
1. `_apply_coverage_diversification` now takes a `domain_cap: int | None` and maintains a live
   `domain_count = Counter(_row_domain(...))`. A candidate from a domain already at/over the cap is only
   admissible if the chosen evictee is the SAME domain (net-zero); otherwise the candidate's evictables
   are filtered to same-domain rows, and if none qualify the swap is REJECTED. `domain_count` is updated
   on every swap (decrement evicted domain, increment candidate domain).
2. The caller passes the ACTIVE #956 cap: `domain_cap = max(1, ceil(_dom_frac*max_rows)) if _dom_enabled
   else None`.
3. Two NEW regression tests: `test_greedy_does_not_pull_at_cap_domain_over_the_cap` (your exact repro —
   x.com at cap 2, unique-bucket x rows + a y.com no-bucket row + an x.com novel candidate → the swap is
   REJECTED, x.com stays 2, swaps==0) and `test_greedy_swaps_within_domain_when_at_cap` (a redundant
   same-domain row IS available → the candidate is admitted by a same-domain eviction, cap preserved,
   coverage improves).

**Verify:** (a) the domain-cap arithmetic is correct (admitting a cross-domain candidate when its domain
is at cap is now impossible); (b) when the domain cap is disabled (`domain_cap=None`) the pass behaves as
before; (c) no remaining path lets the greedy pass raise any domain above the post-domain cap. 33
selector tests pass (incl. test_source_diversity); 15 #1215 tests pass.

---

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; cosmetic = P3/P2.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining non-P0/P1; no iter 6.
- If you're holding a P1 for "next round" — surface it NOW; iter 6 doesn't exist.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

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

## Context: this implements the Codex DESIGN-gate iter-2 APPROVE
`.codex/I-perm-023/codex_design_verdict_iter2.txt` APPROVE'd the architecture: a THIRD #956-style
diversity PASS on post-floor slack (NOT a new owning branch), so floor parity is BY CONSTRUCTION. The
4 design P2s are folded into this diff — verify each:
- **P2.1 (faithfulness wording):** the module docstring now states the generator evidence_pool STARTS
  from selected_rows (and may add sanctioned prepends + M-52 live pulls); the safety claim is "selection
  cannot relax strict_verify or admit unsupported prose," not "verifies against the full retrieved pool."
- **P2.2 (`_apply_domain_cap` brought-in ids):** `_apply_domain_cap` now returns `(moved, brought_in)`;
  the caller does `protected_ids |= _dom_brought` BEFORE the greedy pass, so the greedy pass cannot undo
  the domain-diversity pass.
- **P2.3 (default-OFF parser):** `_constrained_greedy_config` reads `PG_SELECT_CONSTRAINED_GREEDY`
  defaulting "0" (NOT `_env_flag_on`, which defaults "1"/ON). OFF → the block is skipped entirely.
- **P2.4 (explicit eviction order):** worst evictable = `max(... key=(redundancy, -relevance, idx))`
  (highest redundancy, lowest relevance, highest original idx — total order).

## The diff (`.codex/I-perm-023/codex_diff.patch`, staged). Read these EXACT files:
- EDIT `src/polaris_graph/retrieval/evidence_selector.py` — new taxonomy constants + 3 predicates
  (`_greedy_match_category`, `_greedy_active_axes`, `_row_coverage_buckets`) + `_constrained_greedy_config`
  + the `_apply_domain_cap` tuple-return change + the NEW `_apply_coverage_diversification` pass + the
  wiring in `select_evidence_for_generation`'s #956 region (after `_apply_domain_cap`, before the final
  sort).
- NEW `tests/polaris_graph/retrieval/test_constrained_greedy_iperm023.py` — 13 tests.
- EDIT `scripts/dr_benchmark/run_gate_b.py` — slate `PG_SELECT_CONSTRAINED_GREEDY=1` + force-on (NOT
  preflight-required: a no-op until the pool exceeds the cap, never a fail-closed precondition).

## ONE DESIGN DEVIATION from the brief — verify it (the crux of this review)
The design brief listed axes = entity ∪ safety_category ∪ evidence_class ∪ jurisdiction. While building I
found there is **NO `v30_entity_id` (or safety/class) field on the rows reaching the selector** — the
forensic was wrong about a reusable entity field. So I NARROWED the greedy axes to the ones the existing
floor stack does NOT already cover and that ARE derivable from row content:
- **entity** → DROPPED as a greedy axis: entity/anchor custody is already owned by the M-42e + M-51
  primary-custody floors (full-pool anchor scan). A greedy entity axis would duplicate a floor, and
  there is no entity field to bucket on anyway.
- **mechanism** → DROPPED: already owned by the M-42c mechanism floor (your design q2 logic).
- **safety_category** (NEW keyword predicate, FDA/SPL taxonomy) + **evidence_class** (NEW keyword
  predicate) → KEPT: these are the genuinely floor-UNCOVERED axes (the real topical/safety monoculture
  risk).
- **jurisdiction** → KEPT as a soft axis (diversity BEYOND the M-41d 1-per-jurisdiction floor), reusing
  the existing `_row_jurisdiction` predicate.
Verify: (a) this narrowing is sound (entity/mechanism ARE floor-covered, so omitting them as greedy axes
is correct, not a gap); (b) `PG_GREEDY_AXES` (default safety/class/jurisdiction) lets an operator re-add
or restrict axes; (c) the keyword predicates are PREFERENCE-only (a miss costs diversity, never
faithfulness — they are never used as a gate).

## §-1.1 / faithfulness — red-team this
1. **Coverage-monotone.** A swap fires only when the incoming candidate adds a NOVEL bucket (count 0)
   AND every bucket of the evicted (non-protected) selected row is covered by ≥2 selected rows (so after
   removal each stays ≥1). Confirm distinct coverage can only INCREASE — no covered axis is ever dropped.
   A row with NO buckets is vacuously evictable (contributes no coverage) — confirm that is safe (it
   loses no bucket) and that its redundancy score 0 makes it the LAST-preferred eviction.
2. **Floor parity by construction.** The pass runs AFTER the entire floor stack + M-51 + the #956
   subquery/domain passes, on `selected` in place, and NEVER evicts an id in `protected_ids`
   (`m42e | m42c | m51 | _t3_floor | subquery-brought | domain-brought`). It touches no quota, no tier
   allocation. Confirm it is structurally incapable of weakening any floor.
3. **Same-tier only.** A swap brings in a same-tier candidate for a same-tier evictee → tier quotas
   preserved. Confirm (test `test_swap_stays_same_tier`).
4. **Selection cannot relax a gate.** strict_verify / 4-role / D8 re-check every sentence against the
   cited span; the pass only changes the candidate menu. Worst case it trades one verifiable row for
   another (coverage shift), never admits unsupported prose. Confirm.
5. **Default-OFF byte-identical.** OFF → `_constrained_greedy_config` returns (False, …) → the block is
   skipped → selected/notes/to_dict identical (test `test_selector_byte_identical_when_off`). Confirm
   the `protected_ids |= _dom_brought` line added on the (default-ON) domain-cap path has NO downstream
   effect when greedy is off (protected_ids is not read again after this region).
6. **No-op when pool ≤ cap.** The #956 region only runs on the truncating path; pool ≤ cap returns via
   the short-pool branch first → forward-guard no-op at drb_76 scale (test `test_selector_noop_when_pool_below_cap`).
7. **Deterministic.** Total-ordered tie-breaks, no RNG (test `test_pass_is_deterministic`).
8. **diversity_score is DIAGNOSTIC-only** (labeled in telemetry + note) — not a §-1.1 superiority signal.

## Build evidence
- 13 new tests pass (`tests/polaris_graph/retrieval/test_constrained_greedy_iperm023.py`).
- 215 passed / 8 skipped across the FULL floor regression suite (m41/m42/m42c/m42d/m42e/m46/m48/m51/
  m201/pass2/recency/selection-scale/source-diversity/subquery-floor/finding-dedup/adequacy-selector +
  the iready001 cap test) — floors intact, byte-identical-OFF confirmed.
- Module AST-parses; slate force-on verified (operator =0 overridden to 1).

## LOC note
The diff adds ~186 non-test/non-blank lines to the two source files, but the EXECUTABLE logic is ~120 LOC
— the remainder is the SPL safety/evidence-class TAXONOMY DATA (versioned constants) + docstrings +
design-rationale comments. Your design-iter2 P2 already flagged "200-prod-LOC plausible but tight." If
you judge it over a hard cap, the exemption is: a forward-guard with heavy faithfulness documentation +
taxonomy data; no logic split would reduce risk (the pass is one cohesive function).

## Honest scope
PR-1 only: deterministic, default-OFF, post-floor-slack diversity pass (forward guard, no-op until the
pool exceeds the cap). PR-2 (SourceEvidencePack cache + MAP de-sectioning) is a separate follow-up gated
behind the operator paid §-1.1 audit. No paid run required to land PR-1.
