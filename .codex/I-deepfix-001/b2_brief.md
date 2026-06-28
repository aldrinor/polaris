HARD ITERATION CAP: 5 per document. This is iter 2 of 5 (FOCUSED RE-VERIFY).

## CHANGES SINCE ITER 1 (your P1 fixed — re-verify FIRST)
- **P1 (render backstop cleaned bibliography AFTER report assembly) FIXED** in scripts/run_honest_sweep_r3.py: added a PRE-RENDER bibliography screen IMMEDIATELY BEFORE `_render_bibliography_lines(multi.bibliography, ...)` — it builds the registry from q['question'] and drops blocked entries from multi.bibliography BEFORE the section is rendered, so report.md's Bibliography can NEVER ship a blocked entry. Disclosed via blocked_reference_excluded_bibliography.json; fail-open. The existing post-assembly backstop remains as the body-text-leak defense-in-depth scan. NOTE: `BlockedRegistry.is_empty` is a @property (returns True when empty) — both the new pre-render guard and the existing backstop correctly use `not <registry>.is_empty` (property access, no call). Verify: a blocked bibliography entry cannot reach report.md; the pre-render screen is fail-open + §-1.3 (operator-prohibition hard-drop only).
- **P2 (query-gen/fetch exclusions log-only, not persisted)**: DOCUMENTED RESIDUAL — the keystone SELECTION seam (c) DOES persist blocked_reference_excluded_*.json and keeps the blocked work out of the corpus; the query-gen drop produces no source (nothing "vanishes") and the fetch skip is logged loud. Surfacing a dedicated record for (a)/(b) is a disclosure-completeness nicety folded to a follow-up. Non-blocking.
- **P2 (CRLF whitespace warnings on run_honest_sweep hunks)**: EXPECTED — scripts/run_honest_sweep_r3.py is CRLF-in-HEAD by repo convention; the diff is a real partial change, not a whole-file EOL flip (verified HEAD==WT both CRLF). git diff --check flags CRLF as trailing-whitespace for that file regardless.
- Verified offline: the B2 registry test (real gold appendix fixture) passes 12/12 after the run_honest_sweep edits; py_compile clean; CRLF preserved.

## (Original iter-1 brief follows.)
HARD ITERATION CAP (orig): 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding. Same bar every iter.
- Reserve P0/P1 for real execution risks; classify minor issues P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW MODE: STATIC ONLY. Read the diff `.codex/I-deepfix-001/b2.patch` and the changed regions. No pytest/pipeline/broad exploration. Emit the schema at the end.

# I-deepfix-001 B2 (#1346) — blocked-reference deny-list (the ONE legitimate HARD DROP)

## Problem
A DeepResearch-Bench-II question carries a "do-not-view / blocked references" appendix (operator prohibition). Today it is NEVER parsed into a deny-list, so the prohibited paper (Salari, DOI 10.1016/j.chbr.2025.100652, PII S2451958825000673) is queried across ~6 mirrors, fetched, tiered T1/T2, selected into evidence_for_gen, corpus-approved, and CITED. This is the ONE place a HARD DROP is correct per §-1.3 — an EXPLICIT operator prohibition, NOT a relevance/credibility call.

## The change (6 files)
- NEW `src/polaris_graph/retrieval/injection_appendix.py`: the prohibition-appendix LOCATOR regexes LIFTED out of run_honest_sweep_r3.py into a shared util (ONE source of truth; run_honest_sweep's `_strip_injected_instruction_appendix` now imports from here — the existing echo-strip test still passes 6/6).
- NEW `src/polaris_graph/retrieval/blocked_reference_registry.py`: `build_blocked_registry(question)->BlockedRegistry` parses the located appendix into FOUR OR'd normalized key-sets — canonical_urls (w3lib.url.canonicalize_url), dois (lowercase prefix-free), publisher_piis (Elsevier PII + arXiv, also extracted from sciencedirect/linkinghub URLs), title_keys (normalized fuzzy, threshold >=0.92, rapidfuzz-or-difflib). `is_blocked(url,doi,title)->(bool,reason)`. ENV `PG_BLOCKED_REFERENCE_DENYLIST` default-ON (kill-switch only; OFF => empty registry => byte-identical). FAIL-OPEN: a malformed/empty question => empty registry, never raises.
- FOUR fail-loud enforcement seams (each writes a DISCLOSED-exclusion record, never silent):
  (a) QUERY-GEN — query_decomposer.decompose_question drops a sub-query carrying a blocked title/URL/DOI fragment.
  (b) FETCH — live_retriever sets a per-run module-global registry at the top of run_live_retrieval; _fetch_content short-circuits a blocked url/embedded-doi/embedded-pii BEFORE the HTTP call (returns a blocked sentinel, records telemetry). (Title-only mirrors can't be matched pre-fetch — caught at seam c.)
  (c) SELECTION/CORPUS-APPROVAL (keystone) — run_honest_sweep_r3 screens retrieval.evidence_rows + classified_sources before approved_source_urls is built AND screens evidence_for_gen at the money-gate before the generator bills; disclosed blocked_reference_excluded_*.json.
  (d) RENDER (defense-in-depth) — after final report assembly, drops blocked bibliography entries + scans the rendered body for blocked locators; writes blocked_reference_render_leak.json if any slipped. Body TEXT is NOT rewritten (citation-index/faithfulness stability) — a leak is recorded LOUD for the §-1.1 audit.

## VERIFY HARDEST (adversarial)
1. **§-1.3 scope:** confirm the HARD DROP fires ONLY on an explicit operator-prohibited reference (the parsed appendix), NEVER on a relevance/credibility/tier signal. A non-blocked source is never dropped by this code. (This is the one allowed hard drop.)
2. **No over-block:** confirm the title fuzzy leg (>=0.92) + URL/DOI/PII legs cannot block a legitimate on-topic paper that merely shares words with the blocked title. An empty/absent appendix => empty registry => is_blocked always False.
3. **FAIL-OPEN on build:** a malformed question / locator miss must yield an empty registry (no crash, no accidental block-all).
4. **Faithfulness engine untouched:** strict_verify / NLI / 4-role / provenance / span unchanged. The deny-list is a pre-generation corpus exclusion + a post-render audit, not a verification change.
5. **Fetch seam saves spend, never lies:** the blocked sentinel from _fetch_content must not be mistaken for a real fetch (no tier laundering of a blocked url).
6. **Disclosure not silence:** every exclusion writes a record/log (blocked_reference_excluded_* / render_leak). A blocked source is disclosed-excluded, never vanished.
7. **CRLF:** run_honest_sweep_r3.py is CRLF-in-HEAD — confirm the diff is a real partial change, not a whole-file EOL flip.
8. **Shared locator refactor:** confirm lifting the locator regexes into injection_appendix.py preserved the original _strip_injected_instruction_appendix behavior (the echo-strip path).

## Output schema (REQUIRED, last lines)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
