# Codex DIFF review — I-ready-004 (#1078) CAPPED finding-dedup — ITER 1

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

You APPROVED the brief at iter-2 (`.codex/I-ready-004/brief.md`; dedup_mode=capped_dedup,
defer_model_rerank=yes). This is the DIFF. Diff: `.codex/I-ready-004/codex_diff.patch` (vs base
bot/I-ready-016, 247 lines).

## What the diff does (exactly as the approved brief specified)

**P1-1 fix — capped finding-dedup in `scripts/run_honest_sweep_r3.py` (run_one_query):**
- New flag `_capped_dedup = PG_CAPPED_FINDING_DEDUP` (default OFF). The block runs ONLY when
  `_use_finding_dedup AND _capped_dedup AND _relevance_floor is not None`.
- It sits immediately AFTER the floor-selection (`evidence_for_gen = evidence_selection.selected_rows`)
  and BEFORE the `_selection_base_rows` snapshot + the contract/upload prepends. It:
  (1) `dedup_by_finding(evidence_for_gen, gov_suffixes=load_authority_data()["psl_gov_suffixes"])`
      → collapses near-duplicate findings to one corroboration-counted representative;
  (2) re-runs `select_evidence_for_generation(evidence_rows=<deduped base>, max_rows=max_ev,
      relevance_floor=None)` → tier-balanced top-PG_LIVE_MAX_EV_TO_GEN.
  Net: the base is ≤ max_ev (so #1070's cap holds) AND the relevance floor still applied (it was
  applied in the floor-selection above). The contract/upload prepends below stay ADDITIVE (identical
  to OFF-mode: a 150-cap base + additive prepends — #1070's contract). The EXISTING post-prepend
  dedup at ~L3760 (PG_USE_FINDING_DEDUP) still runs on (capped base + prepends), collapsing any
  base↔prepend duplicate + emitting the canonical `finding_dedup` manifest telemetry. Default OFF
  outside Gate-B → the legacy no-cap relevance-floor mode is byte-unchanged for non-Gate-B callers.

**P1-2 fix — float-safe PG_RELEVANCE_FLOOR in `scripts/dr_benchmark/run_gate_b.py`:**
- Slate `_FULL_CAPABILITY_BENCHMARK_SLATE` += `PG_USE_FINDING_DEDUP=1`, `PG_CAPPED_FINDING_DEDUP=1`,
  `PG_RELEVANCE_FLOOR=0.30`.
- All three added to `_BENCHMARK_FORCE_ON_FLAGS` so they are force-SET as STRINGS (the numeric FLOOR
  path `int(max(...))` would coerce `0.30` → `0` and break `parse_relevance_floor`).
- Both flags added to `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` (capped mode can't be silently off).
- `preflight_full_capability` now validates `PG_RELEVANCE_FLOOR` via `parse_relevance_floor`
  (float (0,1]) when capped-dedup is on → a bad float ("0", "1.5", "abc") fails CLOSED before spend.

## Evidence (offline, no model, no spend)
- 61/61 PASS: new `test_capped_finding_dedup_iready004.py` (config lock; slate does NOT int-coerce the
  float floor; preflight rejects bad floors ["1.5","0","-0.2","abc"]; preflight accepts 0.30;
  dedup-then-cap composition is ≤ max_rows) + `test_evidence_to_generation_cap_iready001` (#1070 cap) +
  `test_m201_evidence_selection` + `test_finding_dedup_phase5` + `test_run_gate_b_cli` +
  `test_benchmark_stack_activation_meta007`.
- `py_compile` clean on all 3 edited files. 191 insertions (< 200-LOC cap).

## Review focus
(1) Does the capped block truly keep the generator base ≤ PG_LIVE_MAX_EV_TO_GEN (so #1070's cap
holds) while preserving the relevance floor? (2) Is the prepend interaction correct — prepends stay
additive (not capped), and the snapshot `_selection_base_rows` correctly reflects the capped base?
(3) Is the float-safe slate/preflight handling complete (no path where 0.30 → 0 survives)? (4) Is the
default-OFF legacy no-cap mode byte-unchanged for non-Gate-B? (5) Faithfulness: selection only
changes WHICH evidence rows the generator sees; strict_verify + 4-role D8 are downstream + untouched.

## NOTE — deferred + pre-existing (do not block on these)
- The model-based cross-encoder + SemHash/MinHash semantic-embedder rerank is DEFERRED to an
  operator-gated follow-up per §8.4 (you approved defer_model_rerank=yes) — a follow-up issue will be
  filed; not in this diff.
- The broad sweep has ~46 PRE-EXISTING failures (offline entailment-judge + env/network + test-
  pollution) unrelated to this diff (base-confirmed); tracked separately.

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
