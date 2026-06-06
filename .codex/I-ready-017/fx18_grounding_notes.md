# FX-18 grounding notes (#1122) — S2 short-keyword lane + wire OpenAlex

P1 CORE `live_retriever.py`. Discovery-breadth, faithfulness-SAFE (adds candidates). Author next wake
(new-backend wiring + S2 query reshape; MED risk per cadence). Diff base: FX-06 verified tip `5d7fd51e`.

## Code anchors (verified this wake)
- Per-query search loop: `live_retriever.py:2358` `for q in ([] if seed_only else effective_queries):`
  - Serper: `:2360` `_serper_search(q, num=max_serper)`; dedup `:2364-2366` (`url in seen_urls`).
  - **S2: `:2376` `_s2_bulk_search(q, limit=max_s2)`**; dedup `:2380-2382`. `q` is the NL query
    (40-70 words) — THIS is what returns ~0; feed a keyword-distilled variant.
  - domain backends: import `:2407` + `run_domain_backends(...)` `:2442-2445`; dedup `:2452-2454`.
- `_s2_bulk_search(query, limit=20)` at `:266` (returns list[dict]).
- `_serper_search(query, num=10)` at `:202` (returns list[dict]).
- `openalex_search(query, limit=PG_DOMAIN_MAX_HITS)` at `domain_backends.py:466` — returns
  **list[SearchCandidate]** (NOT dicts), fail-open. Need to confirm how serper/s2 DICT hits become
  candidates vs how openalex SearchCandidate merges (the loop builds `candidates: list[SearchCandidate]`
  — check the dict→SearchCandidate construction for serper/s2 around :2360-2382 to mirror for openalex
  or append the SearchCandidate directly + tag query_origin).
- seen_urls: `:2327` `seen_urls: set[str] = set()` (shared dedup across serper/s2/domain/seed).

## Fix design (3 parts)
1. **S2 short-keyword:** distill `q` -> short keyword phrase for `_s2_bulk_search`. OPEN: locate the
   distillation source — candidates: a `query_decomposer` (grep found none obvious; check
   `agents/searcher.py` / planner sub-queries), or `effective_queries` may already contain shorter
   sub-queries to use for S2 specifically. Word-count cap (e.g. <= 8 keywords). Guard over-generalization
   with the (now seed-safe, FX-15b) semantic prefetch filter.
2. **Wire OpenAlex:** add `openalex_search(q)` in the loop as a parallel academic backend; union+dedup
   via `seen_urls`; tag `query_origin=q` (or `openalex_search`). Flag-gate (e.g. PG_OPENALEX_SEARCH,
   default on in slate). Q8: ADD (union) vs REPLACE S2 NL path -> route to Codex (likely ADD).
3. Tag each new source's `query_origin` so §-1.1 can trace it to the short-keyword S2 query or
   openalex_search.

## Smoke (offline, mock httpx)
- keyword-distillation: non-empty + < N words for a 40-70-word NL question.
- openalex_search invoked + merged + deduped (mock the httpx client); no dup URLs across serper/s2/openalex.
- (Live cheap, at RERUN) `_s2_bulk_search(short_keyphrase)` and `openalex_search(question)` each >0
  for the AI-labor question (was ~0 for S2 on NL).

## §-1.1
`tool_trace.jsonl`: s2 result_count>0 for the golden question; openalex_search rows result_count>0;
evidence_pool academic rows increased; each new source query_origin traces to short-keyword S2 or openalex.

## Faithfulness note
Adds discovery candidates only; all new sources pass the SAME fetch/tier/strict_verify/4-role gates.
Risk = keyword over-generalization pulling off-topic sources -> guard with the semantic prefetch
filter (now seed-safe). OpenAlex fail-open already. Flag-gated + reversible.
