# DUAL INDEPENDENT AUDIT — I-meta-008 #1034 (prefer clean abstract over non-deterministic OA scrape)

You are one of TWO independent auditors (Claude + Codex) running in PARALLEL (§-1.1). This is
a DESIGN-DECISION review as well as a code review — scrutinize the decision, not just the syntax.

## LIVE GROUND TRUTH (verified this session, deployed path, DOI 10.1257/jep.33.2.3 = Acemoglu
"Automation and New Tasks", the canonical paper that read "not extractable" in run 6)

Three repeated fetches of the SAME entity returned THREE different `oa_full_text` values:
1. 25,000-char **Sci-Hub HTML** page (`<!DOCTYPE html> ... <title>Sci-Hub. Automation...`).
2. 25,000-char **Jina landing-page markdown** (`Title: Automation... Markdown Content: Jo...`).
3. Clean **1,331-char CrossRef abstract** (`We present a framework for understanding...`).

So the OA scrape is NON-DETERMINISTIC and junk-prone, while the abstract is clean + stable.
The earlier thin-stub fix (length >= 1200 → "real full text") could NOT catch the 25K Sci-Hub
HTML (it passes any length check) → generator got 25K of HTML → "not extractable".

After this fix, with PG_FRAME_PREFER_ABSTRACT=1, Acemoglu grounds DETERMINISTICALLY across 3
repeated live fetches: quote_source=crossref_abstract, 1331 chars, clean prose, identical each time.

## The change
1. `_looks_like_html_junk(text)` — head contains `<!doctype`/`<html`/`<head`/`<body`/`sci-hub` → junk.
2. `_is_usable_full_text(text)` — usable only if `len >= _OA_FULLTEXT_MIN_CHARS (1200)` AND NOT junk.
   Used in Step 4 OpenAlex gate + the decision `real_full_text`.
3. `_FRAME_PREFER_ABSTRACT` (env `PG_FRAME_PREFER_ABSTRACT`, default OFF). When ON: the decision
   prefers the clean abstract (CrossRef/OpenAlex/PubMed) over a scraped full text; Step 4 also
   fetches OpenAlex even when a usable full text exists (so the abstract is available to prefer).
4. `run_gate_b.py` sets `PG_FRAME_PREFER_ABSTRACT=1` + `PG_OPENALEX_FRAME_FALLBACK=1` via setdefault.
5. Default OFF preserves the M-66b-T clinical full-text path (trial 9-field rosters live in tables,
   not abstracts); existing M-66b-T tests stay green (full_text ~1650 clean → still oa_full_text).

Diff: `.codex/I-meta-008-htmljunk/codex_diff.patch`. Full file: `src/polaris_graph/retrieval/frame_fetcher.py`.

## Audit questions (independent, line-by-line)
1. **Is preferring the abstract the RIGHT design** for frame-contract grounding, given the scrape's
   proven non-determinism? Or does it lose important content vs a clean full text? Consider that the
   contract required_fields for these entities are abstract-level (thesis/mechanism/displacement_vs_
   reinstatement/empirical_support). Is the OFF-by-default + run_gate_b-ON gating correct (no clinical
   regression)?
2. **Determinism**: is the fix deterministic under the flag? (Abstract source is CrossRef→OpenAlex,
   both deterministic; scrape is bypassed.) `_pick_richest_abstract` tie-handling.
3. **`_looks_like_html_junk` robustness**: false positives (a real abstract that happens to contain
   "<html>" or the word "sci-hub")? false negatives (other junk shapes)? Is head-only (600 chars) right?
4. **`_is_usable_full_text` + the flag interaction** in Step 4 and the decision — any path where a
   junk scrape still becomes direct_quote, or a real full text is wrongly dropped?
5. **Regression**: M-66b-T (flag off) unchanged? The provenance labels (OPEN_ACCESS vs ABSTRACT_ONLY)
   correct under the new prefer-abstract branch?
6. **Sci-Hub**: the access layer pulled content from Sci-Hub. Flag the legal/provenance severity for a
   clinical product (is rejecting it in frame_fetcher enough, or does the access_bypass Sci-Hub method
   itself need gating? — note as a finding; out of scope for THIS diff to fully fix).

## Output schema (end with this)
```yaml
verdict: APPROVE | REQUEST_CHANGES
design_call: <prefer-abstract is correct | wrong-because... | conditional...>
novel_p0: [...]
p1: [...]
p2: [...]
scihub_severity: <P0|P1|P2 + one line>
```
