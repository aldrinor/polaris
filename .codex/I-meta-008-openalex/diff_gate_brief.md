# Codex DIFF review — I-meta-008 (#1033): frame_fetcher OpenAlex abstract fallback

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (required — loose prose rejected)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Context — why this change

Q1 (drb_72 AI-and-labor) run 6 on the VM fixed the missing-canonical-journals problem
(V30 contract path now fetches all 7 canonical entities), BUT 5/7 canonical report
sections printed **"thesis/mechanism/effect: not extractable from available primary
content"**. Root cause, confirmed from `outputs/q1_run6/manifest.json` frame_coverage_report
+ the run logs:

- For Acemoglu-Restrepo JEP (10.1257/jep.33.2.3), Robots-JPE (10.1086/705716),
  Brynjolfsson QJE (10.1093/qje/qjae044), Eloundou Science (10.1126/science.adj0998):
  Unpaywall surfaced an OA locator (aeaweb / publisher PDF) so `any_oa_url` was truthy →
  provenance OPEN_ACCESS, but the OA full-text fetch **403'd** (`trafilatura ERROR not a
  200 response: 403` at aeaweb), so `oa_full_text=""`. CrossRef returned metadata with
  **no abstract** for these DOIs in the live run, and these are econ papers with **no PMID**
  → PubMed step never runs. So `direct_quote` fell through to `""` → the generator emitted
  "not extractable".

- `frame_fetcher.py` fetch chain was CrossRef → Unpaywall → PubMed. **No OpenAlex layer.**

- Verified LIVE (this session, via urllib direct to api.openalex.org): OpenAlex's
  `abstract_inverted_index` holds these abstracts — Acemoglu-JEP 1331 chars, Autor-JEP 1530,
  Brynjolfsson-QJE 1113, Robots-JPE 688 (Eloundou thin at 56). All `doi_match=True`.

## What the diff does

Adds **Step 4: OpenAlex abstract fallback** to `_fetch_frame_entity_inner`, firing ONLY when
`PG_OPENALEX_FRAME_FALLBACK` enabled (default on) AND `doi` present AND
`not abstract_crossref AND not abstract_pubmed AND not oa_full_text`. On success it
reconstructs the abstract from `abstract_inverted_index`, applies a **DOI-consistency guard**
(reject + log `error:doi_mismatch` if OpenAlex's own DOI disagrees with the bound DOI —
mirrors the existing PubMed guard at the SPRINT-vs-SURPASS defense), maps to
`FrameRow.direct_quote` with `quote_source="openalex_abstract"`, provenance ABSTRACT_ONLY
(or stays OPEN_ACCESS when an OA locator existed but full-text failed).

New units (all in frame_fetcher.py, deterministic, DI-client + RetrievalAttempt logged):
- `_reconstruct_inverted_abstract(inv)` — sort-by-position reconstruction (positions unique → total order → byte-deterministic). Mirrors the proven logic in `agents/searcher.py:204`.
- `_parse_openalex_response(data)` — abstract + title/authors/journal/year/doi (prefix-stripped, lowercased).
- `_call_openalex(client, doi)` — GET `/works/https://doi.org/{doi}?mailto=...` via `_request_with_retry` (same retry/attempt discipline as the other callers).
- `_pick_abstract(crossref, pubmed, openalex)` — priority CrossRef > PubMed > OpenAlex; replaces the inline `abstract_crossref or abstract_pubmed` selection in the decision block (behavior-preserving for the existing two sources).
- Config: `_OPENALEX_WORK_BASE`, `_OPENALEX_FRAME_FALLBACK_ENABLED`.

## Files I have ALSO checked and they're clean

- **Reuse check (LAW V):** existing OpenAlex code is all keyword/query search —
  `agents/searcher.py:_search_openalex`, `domain_backends.openalex_search`,
  `live_retriever._openalex_enrich` — exactly the non-deterministic retrieval frame_fetcher
  was built to AVOID (module docstring). `tools/openalex_client.py:canonicalize_sync` does a
  DOI fetch but parses to `OpenAlexWork` (no abstract) via its own requests+cache layer, not
  the deterministic DI-client + RetrievalAttempt contract. So a small self-contained DOI-direct
  fetch in frame_fetcher is the correct call per its isolation design; reconstruction logic
  intentionally mirrors searcher.py (8 lines) rather than importing the agent stack.
- **Downstream consumers of `quote_source`:** only `frame_manifest.py:525` (`out.append(row.quote_source)` — opaque string) + `human_gap_completion.py` (HUMAN_CURATED sentinel). New `"openalex_abstract"` value is consumed only as an opaque string. CLEAN.
- **Downstream consumers of `provenance_class`:** `claim_atom_extractor.py`, `contract_section_runner.py`, `frame_manifest.py`, `regulatory_synthesizer.py`, `slot_fill.py`, `audit_ir/loader.py` — all branch only on `FRAME_GAP_UNRECOVERABLE` or read `.value` as a string. I reuse the EXISTING `ABSTRACT_ONLY`/`OPEN_ACCESS` enums — **no new enum value** → no consumer can break. CLEAN.
- **No new hardcoded source allowlist** (operator constraint, frontier-gap #benchmark): the path is DOI-driven for ANY entity, not a per-paper whitelist.

## Tests / evidence (LAW II)

- `tests/polaris_graph/test_m56_frame_fetcher.py`: **52/52 pass** (46 prior regression + 6 new). New tests cover: inverted-index ordering, empty/bad input, field extraction, the Q72 root case (CrossRef-empty+no-PMID → OpenAlex rescues → ABSTRACT_ONLY/openalex_abstract), DOI-mismatch rejection → METADATA_ONLY, OA-locator-but-paywalled-fulltext rescue (exact Q72 path, monkeypatched `_fetch_url_pattern` → ("","")), CrossRef-present-skips-OpenAlex (priority + no wasted request), disabled-flag-skips.
- Consumer suites: `test_m58_slot_fill.py` + `test_m60_frame_manifest.py` + `test_m57_contract_outline.py` = **94/94 pass**.
- LIVE OpenAlex probe (urllib) confirmed abstracts present for all 5 canonical DOIs with DOI match.

## Specific things to scrutinize

1. **Determinism**: is `_reconstruct_inverted_abstract` byte-deterministic? (positions unique within a work; `word_positions.sort()` on `(pos, word)`.) Any case where two words share a position?
2. **DOI guard correctness**: does the OpenAlex `doi` normalization (`https://doi.org/` strip + lowercase) correctly match `bound_doi_l = doi.lower()`? Bound DOI from EvidenceBinding is the raw `10.xxxx/...` form.
3. **OPEN_ACCESS-with-empty-quote residual**: when `any_oa_url` True, full-text fails, AND all three abstracts empty (OpenAlex miss), the row stays OPEN_ACCESS with `direct_quote=""` (pre-existing behavior, unchanged by this diff). Is leaving that as-is acceptable, or should it downgrade to METADATA_ONLY? (I left it to keep the diff focused + avoid touching existing tests — flag if you consider it a P1.)
4. **Network discipline**: OpenAlex only fires when the prior three sources yielded nothing — confirm no extra request when CrossRef/PubMed already produced an abstract (test `test_crossref_abstract_present_skips_openalex` asserts the call_log has no openalex entry).
5. **LOC**: production file +191/-16 (153 non-comment), under the 200-LOC cap.

The diff under review is committed as `.codex/I-meta-008-openalex/codex_diff.patch`.
