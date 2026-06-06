# FX-13 §-1.1 audit — _domain_of lstrip→removeprefix (#1125)

**Standard:** §-1.1 over the REAL held drb_72 `run_artifacts/retrieval_trace.jsonl` URLs, comparing
the OLD `lstrip("www.")` domain vs the corrected `removeprefix("www.")`.

## The bug, on the real artifact (line-by-line)
`_domain_of` did `netloc.lower().lstrip("www.")`. `str.lstrip` strips any leading char in the SET
{w, .}, NOT the literal "www." prefix. Over the held trace's 145 unique URLs, **2 domains were
corrupted**:
- `wol.iza.org` → `ol.iza.org` (the leading `w` of `wol` — IZA World of Labor, a REAL labor-economics
  source — stripped; NOT even a www. host).
- `www.weforum.org` → `eforum.org` (the `w` of `weforum` stripped after the `www.` prefix).

`removeprefix("www.")` yields the correct `wol.iza.org` / `weforum.org` in both cases. The corrupted
domain feeds `_domain_of(cand.url)` (`live_retriever.py:2757`) used for domain-based dedup/diversity —
so two real sources were mis-bucketed on the held run.

## The fix
`lstrip("www.")` → `removeprefix("www.")` (Python 3.9+; repo 3.13) in ALL 3 instances of the identical
bug: `live_retriever.py:1901` (production), `scripts/compare_live_vs_pg_lb_sa_02.py:32`,
`scripts/run_honest_on_prerebuild_corpus.py:81`. Other `lstrip(...)` calls in retrieval
(`qualitative_conflict_detector.py:279` `lstrip(" :,")`, `tier_classifier.py:624` `lstrip("\"'([ ")`)
are LEGITIMATE leading-punctuation char-set strips — left as-is.

## Offline smoke (proves the fix)
`pytest tests/polaris_graph/test_fx13_domain_of_iready017.py` → 4 passed:
- `www.who.int → who.int` (was `ho.int`), `www.washington.edu → washington.edu` (was `ashington.edu`),
  aeaweb/nature unchanged.
- `wwwhost.example.com → wwwhost.example.com` (NOT over-stripped to `host.example.com`); `web.mit.edu`
  intact.
- plain hosts + subdomains (`pubs.aeaweb.org`, `arxiv.org`, `nber.org`) unchanged; bad URL → `''`.
- Regression: `test_live_retriever_rerank` (8) + `test_fx15b_host_filter` (5) green.

## Faithfulness check
Telemetry/diversity correctness. Pure string fix; no grounding / strict_verify / 4-role-decision
change. Makes the domain label truthful (used for source-diversity dedup) — on the held run it
un-corrupts `wol.iza.org` (a real source) + `weforum.org`.
