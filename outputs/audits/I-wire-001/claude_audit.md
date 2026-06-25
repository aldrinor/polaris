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
---

# I-wire-001 W1 — consolidation_nli architect audit (Claude)

Issue: https://github.com/aldrinor/polaris/issues/1306 · Plan: `docs/winner_wiring_plan_2026.md` §3 W1.

## 1. Seam correction (DELIBERATE deviation from the plan — surfaced loud)
The plan names `finding_dedup.py:316` `_same_work_key` as a seam. I traced it and deviated:
`_same_work_key`/`consolidate_same_work` merges the SAME work (same DOI / folded title) at
multiple URLs and **folds members to ONE canonical host** (finding_dedup.py:650-656). Running
NLI there would push `corroboration_count`/`member_hosts` DOWN — the OPPOSITE of the canary's
"≥2 distinct hosts multi-cited." The correct sub-function in the same file is the `_finding_key`
cluster-merge inside `dedup_by_finding` (~lines 700-728): unioning literal clusters there pushes
corroboration UP. The plan's file was right; its sub-function was not. The `fact_dedup.build_groups`
companion seam IS wired (mirrors `_build_prose_groups`) but is the sentence-redundancy→cross-ref
path (opposite direction to multi-citation), so the behavioral canary asserts on `dedup_by_finding`.

## 2. Faithfulness (FROZEN — the hard constraint)
- The diff touches NO faithfulness module: not `provenance_generator` (strict_verify), not the
  NLI entailment verifier (`nli_verifier`), not the 4-role D8, not span-grounding. Confirmed by
  the diff scope (finding_dedup.py + fact_dedup.py + new consolidation_nli.py + the test).
- The consumer `credibility_pass._regroup_graph_by_finding_dedup` is "grouping + relabel ONLY —
  no member newly passes any gate" (credibility_pass.py:475 docstring, verified): every basket
  member is still verified IN ISOLATION against its OWN span. `verified_support_origin_count`
  rises only because distinct ALREADY-verified origins share a basket.
- The winner can therefore only UNION clusters (a Signal-D weight goes up); it drops nothing,
  relaxes no gate. `__unknown__`-subject clusters ARE eligible (that is where the brittle clinical
  extractor dumps same-claim paraphrases — the R=0.0 floor the winner fixes); merging them is safe
  because the per-member isolated verify is unchanged.

## 3. Bounded-parallel + determinism (operator mandate)
- `PG_CONSOLIDATION_NLI_WORKERS` (default 8) caps a `ThreadPoolExecutor` over pair-chunks.
- VALUE-BUCKETING (`_cluster_value_bucket`): NLI runs only within same-numeric-value buckets —
  a scale fix (per-bucket O(k²); drb_72 largest bucket 48 → 1128 pairs < the 20000 cap) AND a
  precision guard (never NLI-compare 30% vs 12%).
- Union-find post-step attaches to the lowest index → order-independent. PROVEN: a stub-predict
  unit test gives identical groupings at workers=1 and workers=8.
- Prose path bounded by `PG_CONSOLIDATION_NLI_MAX_SENTENCES` (default 200).

## 4. Behavioral §-1.4 result (the honest record — §-1.1 line-by-line on the merges)
Fire-test `scripts/fire_test_consolidation_nli.py` asserts (all fail-loud):
- CORE: flag-OFF == legacy byte-identical on the REAL drb_75 corpus; `nli_merge_count==0`. PASS.
- MECHANISM (controlled domain-agnostic input): 3 synonym paraphrases merge; antonym stays
  separate; ≥2 hosts. PASS.
- PRECISION (real rows): ev_393/ev_061 and ev_262/ev_779 stay separate. PASS.

**§-1.1 audit of the natural real-corpus merges (the reason activation is BLOCKED):**
- FIRST input choice `_row_text` (full `direct_quote`) → on drb_75, 2 merges, BOTH FALSE:
  ev_393 (dexamethasone, preterm babies, MINIDEX RCT) ⊕ ev_061 (slow/fast protein, older men) —
  DIFFERENT population, intervention, outcome. UNSUPPORTED merge. ev_262 (elderberry, cognition) ⊕
  ev_779 (Mg/Zn/Cu nutrition) — DIFFERENT claim. UNSUPPORTED merge. Cause: bodies are 5k-11k-char
  "Title: … URL Source: …" web-fetch dumps > the cross-encoder ~512-token limit → two unrelated
  papers weakly entail on shared academic boilerplate.
- FIX: feed NLI the focused `context_snippet` claim window, not the full body. Result: both false
  merges GONE; drb_75 `nli_merge_count → 0` (no false positives, no natural merges either).
- drb_72 (workforce) under the snippet input: the surviving merges are still SPURIOUS over-merges
  (AI-employment ⊕ occupational-injury ⊕ digital-twins) from the same boilerplate snippets;
  pairwise density on the largest bucket is 0.00 (2 spurious edges in 1128) that union-find chains.
  Expanding the snippet to the full sentence REGRESSED precision and was reverted.
- VERDICT: the bake-off P=1.0 was on CURATED claim pairs; production input (brittle extractor +
  boilerplate fetched bodies) is a different distribution. The principled remedy is an UPSTREAM
  clean claim-sentence per row — a follow-up, NOT a margin/threshold knob (banned §-1.3).

## 5. Honest acceptance verdict (LAW II)
WIRED, flag-gated DEFAULT-OFF, byte-identical legacy proven on a real corpus; bounded-parallel +
value-bucketed + deterministic; mechanism + bidirectional polarity guard proven on controlled
input; real false-pairs held separate. **NOT claimed:** natural real-corpus firing, report.md
multi-citation propagation. **Activation (flag ON) BLOCKED** pending upstream claim-sentence
extraction; default-OFF ships safe. Follow-up issue to create: "upstream claim-sentence extraction
for consolidation_nli input" before any flag-ON cert run.
