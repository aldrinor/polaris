# Claude architect audit — I-perm-023 (#1215) PR-1: constrained-greedy diversity-aware selection

## Scope reviewed
- EDIT `src/polaris_graph/retrieval/evidence_selector.py` — taxonomy constants + 3 predicates +
  `_constrained_greedy_config` + `_apply_domain_cap` tuple return + NEW `_apply_coverage_diversification`
  pass + wiring in the #956 region of `select_evidence_for_generation`.
- NEW `tests/polaris_graph/retrieval/test_constrained_greedy_iperm023.py` — 13 tests.
- EDIT `scripts/dr_benchmark/run_gate_b.py` — slate `PG_SELECT_CONSTRAINED_GREEDY=1` + force-on.

## Architecture verdict: SAFE (floor parity by construction)
Per the Codex design-gate iter-2 APPROVE, the diversity step is a THIRD #956-style pass on post-floor
slack, NOT a new owning branch. Every floor (tier quotas + M-42e + M-42c + M-41d + M-42d + M-51) +
the subquery/domain #956 passes run UNCHANGED before it; the new pass only reorders non-protected
free-fill slack via same-tier COVERAGE-MONOTONE swaps that never evict a `protected_ids` row. So it is
structurally incapable of weakening a floor.

## §-1.1 faithfulness verdict: SAFE
- Selection only changes the generator's candidate menu; the effective generator evidence_pool starts
  from selected_rows (+ sanctioned prepends + M-52 live pulls), and strict_verify / 4-role / D8 re-check
  every sentence against the cited span unchanged. A swap can at worst trade one verifiable row for
  another — never admit unsupported prose.
- Coverage-monotone: a swap fires only when the incoming row adds a NOVEL bucket AND the evicted row's
  every bucket stays covered by another selected row. Distinct coverage can only increase.
- The new keyword predicates (safety_category / evidence_class) are PREFERENCE-only — never a gate. A
  miss costs diversity, never faithfulness.
- diversity_score is DIAGNOSTIC-only (labeled), not a §-1.1 superiority signal.

## Design deviation (documented): axes narrowed to floor-uncovered set
The rows reaching the selector carry NO entity/safety/class field. Entity custody is owned by M-42e/M-51,
mechanism by M-42c, the 1-per-jurisdiction reservation by M-41d. So the greedy axes were narrowed to the
genuinely floor-UNCOVERED, content-derivable axes: safety_category + evidence_class (+ jurisdiction
beyond the M-41d floor). Omitting entity/mechanism is correct (they are floor-covered), not a gap.

## Default-OFF + forward-guard verdict: SAFE
- `PG_SELECT_CONSTRAINED_GREEDY` default OFF (dedicated parser, not `_env_flag_on`). OFF → byte-identical.
- No-op when pool ≤ cap (short-pool branch returns before the #956 region). Forward guard: only
  diversifies once retrieval (#1204/#1207) grows the post-extraction pool past the generator cap.

## Build evidence
- 13 new tests pass.
- 215 passed / 8 skipped across the FULL floor regression suite — floors intact, byte-identical-OFF
  confirmed.
- Slate force-on verified (operator =0 overridden to 1).

## Honest scope
PR-1 only. PR-2 (SourceEvidencePack cache + MAP de-sectioning) deferred to a follow-up gated behind the
operator paid §-1.1 audit (behavioral extraction change; unit test insufficient).

VERDICT: APPROVE (architect) — pending Codex diff-gate.
