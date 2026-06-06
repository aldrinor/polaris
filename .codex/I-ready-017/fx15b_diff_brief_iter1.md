# FX-15b (#1119) diff-gate — ITER 1 of 5

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
Quality/precision fix. **Faithfulness-safety hinges on precision** (must NOT drop a real article)
AND on the seed-exclusion (must NOT drop the entire agentic seed lane). No grounding /
strict_verify / 4-role-decision change. Depends on FX-15a (#1118, DONE). Diff:
`.codex/I-ready-017/fx15b_codex_diff.patch` (vs FX-15a verified tip `83e7ebfd`).

## Bug (RB-02b)
Agentic lane: `enable_prefetch_filter=False` + no structural filter → aeaweb nav/SERP/conference
pages enter the merge (now-droppable after FX-15a) adding ~0 evidence (held drb_72: 69 merged → 14
selectable).

## CRITICAL grounding finding that shaped the fix (please scrutinize)
Step-3 (`live_retriever.py` `if enable_prefetch_filter and candidates:`) ran `filter_search_results`
on ALL candidates INCLUDING the injected empty-snippet seeds. Agentic seeds are URL-only (no
snippet) → the embedder scores them ~0 similarity → would REJECT every agentic seed if
`enable_prefetch_filter=True` were passed naively. So the plan's "enable the semantic filter" is
only safe once Step-3 excludes seeds.

## Fix
1. **Structural filter** `_is_low_content_host_or_page(url, title='')` (pure, live_retriever):
   reject `/search`, `/browse`, `/conference`, `/annual-meeting`, `/issues/`, `/forum/`, `/toc/`;
   SERP `search-results` / `per-page=`; reuse `tier_classifier._detect_conference_abstract`.
   PRECISION-FIRST — `/issue/` (singular) is NOT rejected (can prefix a real article); conference
   programs caught by the heuristic. Applied to `_ag_urls` on the agentic lane
   (`run_honest_sweep_r3.py`), flag-gated `PG_AGENTIC_HOST_FILTER` (default on). `urls_selectable`
   telemetry added (post-filter count).
2. **Seed-safe Step-3** — split seeds out via `_SEED_SOURCE_LABELS`, filter only non-seeds,
   re-prepend seeds. Then `enable_prefetch_filter=True` on the agentic call (inert for the URL-only
   seed_only set — no non-seed candidates to score — but fixes the latent seed-drop for ANY caller).

## Evidence
- **§-1.1 on REAL held trace** (`outputs/audits/I-ready-017/fx15b_s11_audit.md`): 41 agentic rows →
  DROP 13 / KEEP 28, **0 real articles dropped**. The single URL a loose heuristic flagged
  (`oup.com/.../article/3/Supplement_1/i906/...`) is a CONFERENCE SUPPLEMENT abstract, correctly
  caught by `_detect_conference_abstract` (a correct drop). Real working-paper PDFs (NBER/MIT/Oxford)
  + journal articles all KEPT.
- **Offline smoke — `test_fx15b_host_filter_iready017.py` → 4 passed**: structural reject table;
  precision gate (6 real articles, ZERO dropped); empty-URL kept; seed-exclusion repro (with
  `enable_prefetch_filter=True` + a reject-ALL embedder stub, the empty-snippet agentic seed STILL
  survives and produces an evidence row — pre-fix it would be dropped).
- **Regression**: FX-15a (6) + `test_live_retriever_rerank` (8) + `test_bug776_layer4_doi_seeds`
  (5) + `test_retrieval_trace` (7) + `test_plan_sufficiency_phase3` (26) all pass.

## Known recall gap (deferred — not a precision issue)
3 atypical citation-stub / news pages survive the structural floor (`/news/cnn`, `scirp.org/
reference/referencespapers?referenceid=`, `socqa.../bibcite/reference/`). Caught downstream by tier
classifier + `is_content_starved` + the (now seed-safe) semantic filter. `/news/` deliberately NOT
rejected (a news URL can be a legitimate citation — precision over recall).

## Questions for you
1. Is the precision boundary right — i.e. is rejecting `/conference/` programs + `_detect_conference_abstract`
   supplement abstracts on the agentic lane correct, and is excluding `/issue/` (singular) + `/news/`
   from the reject set the right precision call?
2. Is the Step-3 seed-exclusion correct + complete (seeds never off-topic-dropped; non-seeds still
   filtered; re-prepend order fine)?
3. Anything blocking APPROVE?
