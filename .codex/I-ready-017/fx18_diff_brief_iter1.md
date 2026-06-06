# FX-18 (#1122) diff-gate — ITER 1 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope
**Discovery-breadth — faithfulness-SAFE** (ADDS candidates; every new source passes the SAME
fetch/tier/strict_verify/4-role gates; no grounding/verification change). Diff:
`.codex/I-ready-017/fx18_codex_diff.patch` (vs FX-06 verified tip `5d7fd51e`).

## Bug — confirmed §-1.1 on the REAL held retrieval_trace
Per-backend search `return_count` across the 5 effective queries (held drb_72):
- **`semantic_scholar` (S2): [0, 0, 0, 0, 4]** — 4/5 NL queries returned ZERO (S2 is a keyword index;
  the sweep fed it 40-70-word NL queries).
- `serper`: [10×5] = 50.
- **`openalex_search`: absent** — the NL-friendly OpenAlex backend (already built, fail-open) was
  never wired into the search lane.
Full §-1.1: `outputs/audits/I-ready-017/fx18_s11_audit.md`.

## Fix
1. **S2 short-keyword:** new `query_decomposer.distill_keywords(q, max_terms=8)` (content tokens via
   the existing `_content_tokens`, stopword-filtered, deduped first-seen, capped, pure). The per-query
   S2 call sends the distilled phrase instead of NL `q`. Flag `PG_S2_KEYWORD_DISTILL` (default on);
   empty distillation → NL fallback. The candidate `query_origin` STAYS the NL `q` (rerank
   reservation + plan-sufficiency unchanged).
2. **Wire OpenAlex:** `openalex_search(q)` in the per-query loop as a PARALLEL academic backend
   (ADD/union, NOT replace S2 — my Q8 call), union+dedup via the shared `seen_urls`; candidates carry
   `source="openalex_search"`, default `query_origin=q`. Flag `PG_OPENALEX_SEARCH` (default on);
   fail-open (lazy import inside try/except — a fault adds 0 hits).

## Evidence
- **§-1.1 on REAL held trace**: S2 [0,0,0,0,4]; OpenAlex absent (above).
- **Offline smoke — `test_fx18_s2_keyword_openalex_iready017.py` → 3 passed**: `distill_keywords`
  (≤8 terms, stopwords dropped, deduped, shorter; all-stopword → '' fallback); integration (mocked
  serper/s2/openalex/fetch) — **S2 receives the distilled phrase** (not NL), **OpenAlex's new URL
  merged** (source=openalex_search), a URL shared with serper **deduped** (kept once as serper).
- **Regression**: query_decomposer (14) + FX-15a (6) + FX-15b (5) + live_retriever_rerank (8) +
  retrieval_trace (7) + research_planner phase1 — 68 passed.

## Decisions made (please confirm)
- **Q8 ADD vs REPLACE:** chose ADD (union OpenAlex with S2's NL path), per the plan's lean — S2's
  keyword path now also fires (distilled), and OpenAlex covers NL. Confirm ADD is right.
- **Keyword distillation = first-≤8 content tokens** (leading terms = the topic). Bounded
  over-generalization (keeps the same content words, drops stopwords + caps length); downstream
  semantic prefetch (now seed-safe) + tier classifier still filter. Acceptable, or do you want a
  different distillation (e.g. salience-ranked)?

## Question
Is the S2 distillation + OpenAlex wiring correct, dedup sound (shared `seen_urls`), and the
query_origin tagging consistent (NL `q` for S2; `q` default for OpenAlex)? Anything blocking APPROVE?
