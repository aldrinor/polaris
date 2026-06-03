HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Output schema (return EXACTLY this, no prose outside it):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

# Diff review — I-faith-002 / #1035 / #1039: CORE legal-OA full text replaces Sci-Hub

## What this change does
Replaces the illegal Sci-Hub access path with CORE (core.ac.uk) v3 as the LEGAL
best-effort OA full-text source. This is a CLINICAL-SAFETY path: full text from
this layer feeds POLARIS's span-grounded faithfulness verifier, so a WRONG paper
returned here would let a fabrication cite a "matching-DOI" span.

## The diff: `.codex/I-faith-002/codex_diff.patch` (also committed at HEAD 0d66d578)
Files: `src/tools/core_client.py` (NEW), `src/polaris_graph/retrieval/frame_fetcher.py`,
`src/tools/access_bypass.py`, `tests/polaris_graph/{conftest.py,test_core_client.py,test_m56_frame_fetcher.py}`.

## Context you should VERIFY (not take on trust)
The unit-tested build passed but the LIVE smoke (real key, real api.core.ac.uk,
3 real DOIs) found TWO coupled P0 bugs; this diff fixes BOTH. Please verify the
fixes are correct and complete, and look for any NEW issue the fixes introduce.

**Bug 1 — redirect.** CORE v3 301-redirects `/v3/search/works` → `/v3/search/works/`.
Fix: `httpx.Client(timeout=_CORE_TIMEOUT, follow_redirects=True)` in
`fetch_core_oa_fulltext`. Verify the production client (client=None branch) sets
it; the test `test_production_client_follows_redirects` asserts it.

**Bug 2 — wrong-paper fabrication (the dangerous one).** CORE mis-tags DISTINCT
papers under one exact DOI. The Acemoglu DOI `10.1257/jep.33.2.3` returns 3
results ALL carrying that exact DOI; result[0] is a *Spanish* paper with 65k
chars of fullText, the correct paper has empty fullText. DOI-equality alone
returned the wrong paper. Fix: a content-identity guard — `expected_title` /
`expected_year` (CrossRef-resolved, passed by frame_fetcher Step 2b) must match
(title-token overlap-coefficient ≥ `PG_CORE_TITLE_MATCH_MIN`=0.5; year within
`PG_CORE_YEAR_TOLERANCE`=1). With NO caller hint, a set of exact-DOI results with
conflicting titles is rejected as a mis-tag.

Please scrutinize SPECIFICALLY:
1. Is the title-overlap guard sound? Could a DIFFERENT paper with a coincidentally
   token-overlapping title (≥0.5 overlap-coefficient on significant tokens) pass?
   Is overlap-coefficient-vs-min-set the right metric vs Jaccard? Stopword list
   adequate? Any way the WRONG-paper fabrication still leaks?
2. The no-hint conservative path: single exact-DOI result with no sibling and no
   `expected_title` STILL returns its fullText (back-compat). Is that an
   acceptable residual risk given the production caller (frame_fetcher) ALWAYS
   passes the CrossRef title when CrossRef resolved one? Should the no-hint
   single-result case be tightened?
3. frame_fetcher wiring: `title`/`year` are the CrossRef-parsed values
   (initialized None at lines ~1114-1117, set at ~1138-1141). When CrossRef
   fails they are None → client falls to the no-hint path. Correct? Telemetry
   parity (every attempt logged) preserved?
4. Sci-Hub OFF: `access_bypass.py:955` default flipped to "0"; the single
   `_try_scihub` call site (line 959) is inside the `== "1"` guard. Any other
   path that could still issue a sci-hub.* request?
5. LAW VI (no hardcoding), determinism, never-raise contract, content cap.

## Tests
130 passed: test_core_client.py (21 = 14 base + 7 #1039 regression),
test_m56_frame_fetcher.py (67, incl. 4 CORE wiring), access_bypass suites (4 files),
test_faith_rescue_guard.py (9). conftest autouse sets PG_CORE_ENABLED=0 so the
M-56 OA tests stay hermetic (.env carries CORE_API_KEY).

## Files I have ALSO checked and they're clean
- `_try_scihub` has exactly ONE call site in src/ (grep-verified), gated.
- frame_fetcher `_is_usable_full_text` / `_looks_like_html_junk` run downstream
  source-agnostically on whatever oa_full_text we capture (CORE or AccessBypass).
- The `core_oa_fulltext` quote_source label has zero strict consumers
  (frame_manifest.py appends it as a free string).

## Honest scope note
Diff is ~417 src LOC (mostly the new core_client.py, heavy docstrings/comments) —
above the 200-LOC backstop. It is ONE coherent feature the operator requested as
a single task (replace Sci-Hub with CORE) plus the two smoke-found safety fixes;
splitting the fabrication guard from the client it guards would be worse. Flagging
explicitly per §3.0.

Verify against the patch + live behavior described in
`.codex/I-faith-002/core_1039_fix_proof.md`. Return the schema verdict.
