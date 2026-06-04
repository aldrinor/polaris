HARD ITERATION CAP: 5 per document. This is iter 3 of 5. Reserve P0/P1 for real blockers. APPROVE iff zero P0+P1.
# STORM brief iter-3 — iter-2 P1s FIXED:
# P1-a (import-cached flag): now toggles the MODULE ATTRIBUTE storm_interviews.PG_STORM_ENABLED (set+restore in
#   finally), NOT os.environ. P1-b (call signature): now run_storm_interviews(client, state) with an
#   OpenRouterClient + a minimal ResearchState {original_query, region, web_results(seed), academic_results}.
# Tests assert the MODULE flag restoration. Verify resolved + no new blocker. Output schema (verdict last).
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: []
p2: []
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: []
```

# I-cap-002 feature 1/4: wire STORM perspective questions into the benchmark query fan-out (iter 3)

## Goal
Flag-gated (`PG_STORM_ENABLED_IN_BENCHMARK`, default 0 = byte-unchanged), fallback-safe: the benchmark
(run_gate_b → run_honest_sweep_r3.run_one_query) calls STORM to generate MORE/diverse SEARCH QUERIES,
raising retrieval breadth WITHOUT touching the verifier seam or the verbatim-span faithfulness path
(evidence still flows live_retriever → strict_verify; STORM never produces direct_quote/evidence rows).

## Verified facts (storm_interviews.py)
- `PG_STORM_ENABLED = os.getenv("PG_STORM_ENABLED","0")=="1"` is CACHED at import (L37).
- Entrypoint: `async run_storm_interviews(client: OpenRouterClient, state: ResearchState) -> dict` (L1175).
  At L1200 it checks the MODULE variable `PG_STORM_ENABLED` and returns {} if false.
- Returns dict: {storm_conversations: list[serialized StormConversation], storm_outline, web_results,
  academic_results}. Each StormConversation has rounds: [{question, answer, sources, key_findings}].
- run_one_query (run_honest_sweep_r3.py ~L1408) builds its own state; STORM does NOT run there today.

## Integration (run_one_query, between decompose ~L1968 and build_amplified_query_list ~L1981)
1. Module-level `PG_STORM_ENABLED_IN_BENCHMARK = os.getenv("PG_STORM_ENABLED_IN_BENCHMARK","0")=="1"`.
2. If ON, in a try/except (STORM error NEVER aborts the run — log loud + proceed with non-STORM queries):
   a. **Gate coordination (iter-2 P1-a FIX):** env-toggling does NOT work because the flag is import-cached.
      Toggle the MODULE ATTRIBUTE: `import src.polaris_graph.agents.storm_interviews as _storm;
      _prev=_storm.PG_STORM_ENABLED; _storm.PG_STORM_ENABLED=True; try: ... finally: _storm.PG_STORM_ENABLED=_prev`.
   b. **Call contract (iter-2 P1-b FIX):** the entrypoint is `run_storm_interviews(client, state)`.
      - client: build/reuse an `OpenRouterClient` (the benchmark already constructs one for the generator —
        reuse it or instantiate with the writer model).
      - state: a minimal `ResearchState` dict carrying `original_query=q["question"]`, `region` (from q or
        default), `web_results` (a SMALL bounded seed live search of the hand-authored+decomposed queries,
        capped by env PG_STORM_SEED_MAX; results DISCARDED after STORM — used only to ground personas), and
        `academic_results=[]`. If the seed is empty/fails, STORM falls back to template personas (still yields
        perspective questions — acceptable).
      - `await run_storm_interviews(client, state)` (run_one_query is async; await directly).
   c. Extract QUESTIONS-ONLY: from each conversation in the returned `storm_conversations`, iterate `rounds`
      and collect `round["question"]` (str). Do NOT read `.search_queries` (not persisted in the serialized
      rounds). Dedup, cap at env PG_STORM_MAX_BENCHMARK_QUERIES.
   d. Append those list[str] to the amplified query list (existing case-insensitive dedup handles overlaps).

## Faithfulness (SAFE)
STORM only adds search queries; evidence is fetched verbatim by live_retriever and verified by strict_verify
+ the 4-role seam. No faithfulness path touched.

## Fallback honesty
Flag OFF (default): the STORM block is never entered → run path + module attribute BYTE-IDENTICAL to today.
Flag ON + STORM error: falls back to the non-STORM query list (run completes correctly) but STORM may have
logged/seeded/cost before failing — so byte-identity is claimed ONLY for flag-OFF.

## Test plan
- Unit: questions-only extractor (storm_conversations → list[str]); dedup; bounded; non-empty.
- Flag-OFF regression: PG_STORM_ENABLED_IN_BENCHMARK unset → STORM block not entered; amplified query list
  byte-identical; assert `_storm.PG_STORM_ENABLED` UNCHANGED (no toggle).
- Non-no-op + gate proof: flag ON, monkeypatch run_storm_interviews to return 2×2 conversations → assert (i)
  the amplified query list GREW by the extracted questions, (ii) `_storm.PG_STORM_ENABLED` was True DURING the
  call and RESTORED to its prior value AFTER (even on error — wrap a raising mock to assert restoration).

## Deps / risk
storm_interviews imports resolve; isolated. Cost: persona+question-gen+seed calls — bound via
PG_STORM_PERSPECTIVES_COUNT / PG_STORM_ROUNDS_PER_PERSPECTIVE + PG_STORM_SEED_MAX. One heavy job at a time.
