# FX-15b (#1119) diff-gate — ITER 2 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
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
Quality/precision fix; faithfulness-safety = precision (never drop a page that bears evidence) +
seed-exclusion (never drop the agentic seed lane). Diff: `.codex/I-ready-017/fx15b_codex_diff.patch`
(vs FX-15a verified tip `83e7ebfd`).

## Your iter-1 verdict (addressed)
- **P1:** blanket `/conference` reject false-dropped real papers — `evidence_pool.json` shows
  `/conference/2025/program/paper/S7SHZQ4n` + `/S25ktKkD` fetched real content; same shape as junk
  `8A8RRTQY`. "Narrow the filter; add regression fixtures for the held S7SHZQ4n/S25ktKkD URLs."
- **P2:** the precision smoke omitted the held program-paper URLs that yielded full evidence.

## What iter-2 changed (exactly your findings)
1. **Narrowed `_LOW_CONTENT_PATH_MARKERS`** to PURE-nav only: `/search`, `/browse`, `/issues/`,
   `/forum/`, `/toc/` + SERP query strings (`search-results`, `per-page=`). **REMOVED** `/conference`
   and `/annual-meeting` (can prefix real papers) AND the `_detect_conference_abstract` call from the
   pre-fetch path (supplement abstracts bear abstract-level evidence) — these are now decided by the
   POST-fetch tier classifier + content-starvation check, never pre-fetch dropped. (Removed the now
   unused `_detect_conference_abstract` import.)
2. **P2 regression**: added `test_held_conference_papers_not_dropped_regression` asserting the exact
   held URLs (S7SHZQ4n, S25ktKkD) are KEPT, plus those + 8A8RRTQY + the OUP supplement + a synthetic
   annual-meeting paper added to the precision KEEP set.

## Evidence — §-1.1 re-audit with evidence_pool.json cross-reference
`outputs/audits/I-ready-017/fx15b_s11_audit.md`: 41 agentic rows → **DROP 7 / KEEP 34, 0 false
drops**. All 7 dropped have **0 evidence** in evidence_pool (issues / forum / search-results×2 /
search-index / toc×2). Both real conference papers (S7SHZQ4n=50k, S25ktKkD=30k chars) now KEPT.
- **Offline smoke — `test_fx15b_host_filter_iready017.py` → 5 passed**: pure-nav reject table;
  precision gate (11 KEEP incl. the held conference papers + supplement + working-paper PDFs, ZERO
  dropped); the P1 regression; empty-URL kept; seed-exclusion repro (reject-ALL embedder + empty
  seed → seed survives).
- Regression: FX-15a (6) + `test_live_retriever_rerank` (8) + `test_retrieval_trace` (7) +
  `test_plan_sufficiency_phase3` (26) all pass.

## Division of labor (the precision principle now applied)
The pre-fetch STRUCTURAL floor drops ONLY pages that cannot contain a paper (SERP/TOC/browse/forum).
Conference papers, supplement abstracts, working-paper PDFs are KEPT and go to fetch; the existing
POST-fetch tier classifier + `is_content_starved` + the (now seed-safe) semantic filter handle their
tiering/dropping. The seed-exclusion in Step-3 is unchanged from iter-1.

## Question
Is the narrowed precision boundary correct (drop only pure-nav; keep anything that could fetch
evidence), and the seed-exclusion still sound? Anything blocking APPROVE?
