RULE NOW — emit the YAML verdict block FIRST. Read the patch at
`.codex/I-meta-002-q1d-query-decomposition/codex_diff.patch` (3 files, +272/-2). Do NOT explore beyond it.

HARD ITERATION CAP: 5. Iter 1 of 5. Front-load all findings; reserve P0/P1 for real execution risks.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex diff-gate (iter 1) — PR2 query decomposition (#951 q1d-a). Verify the diff implements the brief-gate iter-1 required-changes. NO SPEND / NO NETWORK / NO LLM.

The brief-gate returned REQUEST_CHANGES with required-changes (no bare-comma split; conjunction/`versus`
splits need BOTH sides ≥4 content words; pure list-builder helper; clause-splitter-only). This diff
implements them. Verify each + no regression.

## Required-changes to verify in the diff
1. **No bare-comma split.** `query_decomposer.py`: `_TERMINATOR_RE` splits only on `.`/`;`/`?` (+ pipes);
   `_CONNECTIVES = (" as well as ", " versus ", " vs ", " vs. ", " and ")`. Commas are NEVER split points.
2. **Conjunction/`versus` guard:** `_split_on_connectives` splits on a connective ONLY when BOTH sides
   have `>= MIN_SPLIT_CONTENT_WORDS (4)` content words — so "safety and efficacy", "type 2 diabetes",
   "non-small cell lung cancer" are preserved by construction. Same guard applies to `versus`/`vs`.
3. **Pure list-builder:** `build_amplified_query_list(*, hand_authored, decomposed, regulatory, trial)` —
   deterministic prepend order + case-insensitive dedup; anchor NOT added (run_live_retrieval seeds it).
4. **Clause-splitter-only:** PICO `plan_queries` is NOT used in PR2 (deferred).
5. **Wiring:** `run_honest_sweep_r3.py` — flag `PG_SWEEP_QUERY_DECOMPOSE` (default "1"); computes
   `_decomposed = decompose_question(q["question"])` and builds `_amplified_effective` via the helper
   (replaces the old `list(q.get("amplified",[])) + _reg + _trial`).

## Evidence (verified by Claude main-thread)
- 9 new tests (`tests/polaris_graph/test_query_decomposer.py`) PASS: multi-clause → multiple sub-queries;
  "safety and efficacy" NOT split; "type 2 diabetes"/"non-small cell lung cancer" preserved; `versus`
  short NOT split / long split; NO bare-comma split; short single-clause → []; dedup+cap+determinism;
  list-builder order+dedup; case-insensitive dedup + blank filter.
- `verify_lock --consistency` OK. Imports clean. Diff +272/-2 (module 136 mostly comments, tests 116,
  wiring 22; ~80 executable LOC).
- Frozen/untouched: strict_verify / provenance_generator / D8 / runtime lock / evidence_selector / the 5
  PR-10 contracts. This only adds INPUT sub-queries; verification semantics unchanged. Sub-queries pass
  the same `validate_amplified_queries` scope gate; the anchor full question is still seeded separately.

## Rule on
1. Can `decompose_question` EVER split a protected compound ("type 2 diabetes", "safety and efficacy",
   "non-small cell lung cancer", "chronic kidney disease")? (Must be NO — the ≥4 guard.)
2. Any network / LLM / model import in the decomposition path? (Must be NO — pure `re` + sets.)
3. Could the wiring drop hand-authored amplified queries or the anchor, or change order in a harmful way?
4. Recursion in `_split_on_connectives`: any infinite-loop / unbounded risk on adversarial input?
5. Determinism: same input → same output (no set-ordering leakage into the output list)?

APPROVE iff the required-changes are correctly implemented, no protected-compound shredding, no
network/LLM, the anchor + scope gate + hand-authored queries are preserved, strict_verify/D8 untouched,
and it's test-proven.
