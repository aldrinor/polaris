# Wave-3 ACTIVATE-surface map (scout a355d8b32271f4e7b, 2026-07-06)

Ignore stale duplicate copies under `.codex-tmp/wire3-iter4-wt/` and `.codex/I-deepfix-001/coverage_wiring_snapshot/` — worktree/snapshot artifacts, NOT live code.

## Paid-path activation mechanism
- `_PAID_PATH_WINNER_FLAGS` (run_honest_sweep_r3.py:20092-20103) = tuple of env names, hard-forced "1" by `apply_winner_slate_on_paid_path()` (:20113-20128, `os.environ[flag]="1"`), gated by default-ON `PG_APPLY_WINNER_SLATE_ON_PAID_PATH` (:20106-20110). Called ONLY from `main_async()` (:20209) — the DIRECT script launch. **run_gate_b.py NEVER calls main_async → this tuple does nothing on the sanctioned paid path.**
- Sanctioned paid launcher = `scripts/dr_benchmark/run_gate_b.py`. QUAD slate applied by `apply_full_capability_benchmark_slate()` (:3004-3068): FORCE_ON/FORCE_EXACT → hard `os.environ[name]=value`; else `setdefault` (operator .env wins).
  - (a) `_FULL_CAPABILITY_BENCHMARK_SLATE` dict name→value (:529-1612).
  - (b) `_BENCHMARK_FORCE_ON_FLAGS` frozenset (coverage-lever group :2003-2012, scope :2016-2019, 22-fix :2026+).
  - (c) `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` (truthy) + `_BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS` (NO-LOSER), fail-CLOSED ~:1745-1830.
  - (d) `_BENCHMARK_FORCE_EXACT_FLAGS` frozenset (:2053+).
  - `_WINNER_FLAG_ALLOWLIST` (slate-purity) :2711+; ad-hoc setdefault arms :3092, :3102.

## The 12 flags — env-read site / default / gated module / paid-path status
1. PG_SYNTH_PRIMARY — verified_compose.py:1328 (`_synth_primary_enabled`, const :62), default "" OFF. Gates compose-then-verify PRIMARY body in `_compose_one_basket`; also multi_section_generator.py:5050,5192. **NOT WIRED**.
2. PG_BASKET_CONSUME_FINDING_DEDUP — credibility_pass.py:76 (const :65), default "" OFF. Regroup claim-graph by finding_dedup before `_assemble_baskets`. **GATE-B setdefault only** (slate 1317, NOT force-on).
3. PG_FINDING_DEDUP_NLI — finding_dedup.py:940 (const :891), default "0" OFF. Directional bidirectional-entailment same-claim grouping (Wave-1b). **NOT WIRED**.
4. PG_EXPERT_FACET_PLANNER — expert_facet_planner.py:56, default "0" OFF. R1 facet retrieval-breadth planner. **GATE-B FORCE-ON** (slate 1257, force_on 2007, required 1771, allowlist 2827, preflight 3234).
5. PG_SUBENTITY_QUERY_EXPANSION — sub_entity_query_expander.py:62 (consumer fs_researcher_query_gen.py:382), default "0" OFF. R2 sub-entity/STORM query expansion. **GATE-B setdefault** (hardcoded run_gate_b.py:3092, not slate-dict member).
6. PG_PROVENANCE_REANCHOR — provenance_generator.py:1338 (`_reanchor_enabled` ~:1335), default "" OFF. Re-anchor wrongly-cited claim to best ENTAILING span (argmax). **NOT WIRED**.
7. PG_SPAN_RESOLVER — provenance_generator.py:1351 (const :1342), default "" OFF. Re-point surviving token to rescue-window entailing span (:2119); also verified_compose.py:1519. **GATE-B FORCE-ON** (slate 1064, force_on 1714, required 1948, allowlist 2751).
8. PG_MIN_CITE_SET — citation_set_minimizer.py:81 (const :58), default "0" OFF. Minimal independently-entailing INLINE cite set vs weight-channel demotion. Consumed run_honest_sweep_r3.py:3583-3604. **NOT WIRED**. RENDER/presentation lever.
9. PG_CROSS_SOURCE_BODY — cross_source_synthesis.py:508 (const :501), default "0" OFF. Plan-driven candidate pairing vs legacy anchor-equality, inside `compose_cross_source_analytical_units` (:679, called verified_compose.py:2470). **NOT WIRED**.
10. PG_NUMERIC_COMPARATOR — numeric_comparator.py:68 (const :59), default "0" OFF. Upgrade NEUTRAL fully-comparable pair to `comparison` connective (consumed verified_compose.py:2477, cross_source_synthesis.py:649, multi_section_generator.py:5167+). **NOT WIRED**. RENDER/presentation lever.
11. PG_TWO_SIDED_DEBATE — multi_section_generator.py:4885 (const :4876) + expert_facet_planner.py:128. Two legs: composer debate-disclosure (multi_section 5308) + con-side retrieval guarantee (expert_facet_planner 268). default "0" OFF. **NOT WIRED**.
12. PG_SHALLOW_REPORT_CANARY — run_honest_sweep_r3.py:19250 + run_gate_b.py:2589 (const :2579), default OFF. Wave-1d fail-loud DETECTOR (not a capability). **NOT WIRED** (opt-in).

Already force-on: #4, #7. setdefault-only: #2, #5. Still-need-adding (8): #1,3,6,8,9,10,11,12.

## CORRECTION (Fable routing-proof gate R1, 2026-07-06): PG_SPAN_RESOLVER is NOT inert
The tracer's "span-resolver fires on gate-B" was wrong for the LOCAL-WINDOW leg (allow_local_window_fallback=False pins it shut, abstractive_writer.py:302; only `reanchored_local_window:` emit at provenance_generator.py:2892 — must stay ABSENT = inverted canary). BUT PG_SPAN_RESOLVER has a SECOND live consumer: the reanchor ARGMAX leg (provenance_generator.py:1583-1617, marker `reanchored_argmax:` :1614) which ARMS once PG_PROVENANCE_REANCHOR is force-ON. Its accepts re-pass the full gate with allow_local_window_fallback=False (:1580/:1607/:1632) → faithfulness-safe. So post-Wave-3a span-resolver goes LIVE again via the reanchor leg; its POSITIVE fire marker is `reanchored_argmax:`, and the inverted canary is scoped to the exact literal `reanchored_local_window:`.

## Activation-canary seam
run_gate_b.py post-run canary block ~5288-5347 (beside breadth :5288, M6 :5304, shallow :5320). Reuse `_CrossSourceMarkerCaptureHandler` (:2516-2530) attach-to-logger + post-run stable-literal-marker parse (M6 pattern `_run_m6_firing_canary` :2533-2563, gate `_m6_firing_canary_enabled` :2508). Set overall_rc=1 on a genuine "activated module did NOT fire"; append to `_record` (:5354-5370). STRUCTURAL marker, NOT count threshold (§-1.3).
