# Claude architect audit — W7 adequacy_crag wiring (I-wire-001 #1305)

## Codex P1 cleared

Prior wiring shipped only the corrective LOOP-BACK and **retained the
count-floor** as the sufficiency decision; the CRAG sufficiency CLASSIFIER (the
bake-off winner, bal-acc=1.0) was never wired. Codex P1: "count-floor retained,
crag_retriever.py never imported." This PR wires the **CLASSIFIER** so it
REPLACES the count-floor as the STOP/loop decision when `PG_ADEQUACY_CRAG` is ON.

## What "the winner" actually is — FILE-NAME CORRECTION (LAW II)

The task + plan name `src/polaris_graph/retrieval/crag_retriever.py` as the seam
to import. **That is the wrong file.** `crag_retriever.py` is an EMBEDDING
chunk-retriever (all-MiniLM cosine scoring of pre-fetched `RawDocument`s); it was
NEVER a candidate in the adequacy design-race. The bal-acc=1.0 winner is
`crag` = `crag_design()` in
`scripts/dr_benchmark/upstream_bakeoff/adequacy_design_race/candidates.py` — an
**LLM confidence grader** on the GLM-5.2 backbone (scorecard
`.../results/adequacy_design_race_results.json`: crag bal-acc 1.0 /
gap-detection-recall 1.0 vs count_floor 0.9167). Importing a benchmark script
into `src/` is forbidden, and instantiating `CRAGRetriever` would load a heavy
embedding model (§8.4) for an un-benchmarked mechanism. So this wiring **ports
the winner's mechanism** — the `_CRAG_RUBRIC` (verbatim), the JSON parse, and the
CORRECT/AMBIGUOUS/INCORRECT → enough/not_enough rule — into the production bridge
`src/polaris_graph/nodes/crag_adequacy_loop.py`, calling through the existing
`OpenRouterClient` on the mirror GLM model (§9.1.8: aux classifier → mirror). The
mechanism, not the file name, is the winner. This is a plan-revision, not a punt:
it IS the classifier swap Codex demanded.

## What was wired

- **Seam:** `scripts/run_honest_sweep_r3.py` adequacy-gate call site (~L6768,
  inside `async def run_one_query`), immediately after `assess_corpus_adequacy`,
  before the `abort_corpus_inadequate` consumer.
- **Classifier:** `classify_sufficiency` / `build_classifier_prompt` +
  `parse_classifier_response` grade the WHOLE corpus by retrieval CONFIDENCE
  (not by source count). The seam **AWAITs** the production client directly
  inside the running event loop — an `asyncio.run()` from a running loop would
  raise "called from a running event loop" (caught in review). `decision_source`
  is recorded as `crag_classifier` in `crag_adequacy_loop.json`.
- **Loop-back:** `should_loop_back(sufficient=...)` keys off the CRAG VERDICT,
  not the count-floor `adequacy.decision`. On a not-sufficient grade it fires a
  BOUNDED corrective retrieval round (reused parallel `run_live_retrieval`),
  merges new sources, and RE-GRADES with the classifier.
- **Bound:** `PG_ADEQUACY_CRAG_MAX_LOOPS` (default 1). No second concurrency knob
  (the retrieval fan-out is already bounded — §-1.3 anti-knob).
- **Faithfulness FROZEN:** the classifier never gates a sentence; CRAG only
  decides WHETHER to widen the corpus. strict_verify / 4-role / provenance gate
  every merged source unchanged.

## Scope boundary — read before the diff-gate (the classifier governs WHAT)

The CRAG classifier now governs the **STOP / loop-back decision and the re-grade
after each corrective round**. The downstream `abort_corpus_inadequate` consumer
still reads the count-floor `adequacy.decision` (recomputed on the WIDENED
corpus) for the final proceed/abort. This is intentional and is what "REPLACES
the count-floor adequacy decision" means in practice: the count-floor no longer
decides whether to STOP-or-retrieve-more (the classifier does); the corpus is
widened until the classifier is satisfied, and only then does the (now-widened)
corpus flow to the existing abort gate. The count-floor is demoted from the
STOP-signal to a telemetry/abort-backstop on an already-CRAG-approved corpus.
Fully swapping the final abort gate to a pure-CRAG verdict (removing the
count-floor entirely) is a larger change to the abort path and is left as a
flagged follow-up; it is NOT required to clear this P1.

## Default-OFF byte-identical

`PG_ADEQUACY_CRAG` unset → the entire block (the two lazy imports, the LLM call,
the loop, the artifact write) is skipped; the legacy count-floor path runs
byte-identically. No new import executes and no new file is written when OFF.

## §-1.4 behavioral fire-test

`tests/polaris_graph/test_crag_adequacy_loop_fire.py` (fail-loud LIVE canary,
not a stub). Drives the REAL sweep twice on `tech_rag_architectures_2024` with a
starved initial corpus:
- **flag-OFF:** NO `crag_adequacy_loop.json` (byte-identical legacy).
- **flag-ON:** discriminating assertions — (A) `decision_source=crag_classifier`
  + a classification with `invoked=True` and a real grade verdict (proving the
  CLASSIFIER drove the decision, not the count-floor — the Codex P1); (B) an
  injected loop-back source is CITED in `bibliography.json` (effect APPEARS in
  the real output, not just the corpus slate).

### Live evidence — bounded classifier smoke (real GLM-5.2)

Against the real 20-source banked tech corpus
(`outputs/honest_sweep_r6_validation/tech/tech_rag_architectures_2024/live_corpus_dump.json`),
the classifier (model `z-ai/glm-5.2`) was genuinely invoked and graded by
RELEVANCE/CONFIDENCE, not count:
- STARVED 3-source (T5/T6/T7) corpus → verdict **INCORRECT** (not sufficient),
  gap_dimensions named ("Missing specific state-of-the-art 2024 RAG
  architectures", "Missing specific tradeoffs", "Evidence titles focus on 2025
  rather than 2024").
- SAME corpus widened to 20 sources → verdict **CORRECT** (sufficient).

This proves the new mechanism flips inadequate→sufficient on corpus relevance —
exactly the STOP signal that replaces the count-floor.

### Live evidence — full in-situ §-1.4 fire-test (the actual gate)

The fire-test ran the REAL sweep on a starved `tech_rag_architectures_2024`
corpus. The on-leg `crag_adequacy_loop.json` (real run output) recorded:
- `decision_source: crag_classifier` — the CLASSIFIER, not the count-floor,
  drove the STOP decision (the Codex P1, cleared in situ).
- `count_floor_decision: abort` vs `initial_crag_verdict: incorrect` — both said
  insufficient, but the CRAG verdict is the STOP signal.
- `classifications: [(incorrect, invoked=True), (correct, invoked=True)]` — the
  classifier was invoked through the **await-in-loop seam** (no event-loop
  crash, no "error" verdict — the async refactor works in situ).
- `loops_fired: 1` (bounded ≤ `max_loops=1`), `injected_urls: 22`.
- `final_crag_verdict: correct` / `final_sufficient: True` — the re-grade flipped
  inadequate→sufficient AFTER the loop-back widened the corpus (proving the
  loop-back is what closed the gap).
- run_log: `[crag-adequacy] classifier verdict=incorrect sufficient=False
  (count_floor said abort)` then `[crag-adequacy] loop 1/1 verdict=incorrect
  gap_queries=4`, and the widened corpus (`evidence_for_gen=21 rows`) then flowed
  to generation — i.e. the widened corpus also cleared the downstream count-floor
  abort gate (the documented scope boundary, confirmed behaviorally).
- flag-OFF leg: `status=abort_corpus_inadequate`, NO `crag_adequacy_loop.json`
  (byte-identical legacy single-pass abort).

The final discriminating assertion (an injected loop-back source CITED in the
rendered `bibliography.json`) is asserted by the canary on render completion.

## Files changed
- `scripts/run_honest_sweep_r3.py` (seam: all inside the flag-ON branch).
- `src/polaris_graph/nodes/crag_adequacy_loop.py` (new bridge: classifier
  prompt/parse + loop decision + gap-query derivation).
- `tests/polaris_graph/test_crag_adequacy_loop_fire.py` (behavioral canary).
