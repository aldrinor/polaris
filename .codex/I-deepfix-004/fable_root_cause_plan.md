# I-deepfix-004 — Fable root-cause + complete fix plan (wrong-content citable span)

Source: Fable 5 deep investigation, 2026-07-09. Fed the I-deepfix-003 findings + the ultracode workflow's exhaustive log/fix audit. Opus builds; Fable + Codex gate each PR; then relaunch.

## Root cause (one sentence)
The pipeline defines a citable span by POSITION ("the first ~1500 characters of whatever bytes came back for this URL") and NO stage ever checks IDENTITY ("is this text actually the article this citation names?"). Every gate we built asks "is this junk?" or "is this on-topic?"; none asks "is this the cited work?". So any fetch that returns a real, on-topic, non-junk document that is NOT the cited article — a whole journal issue, a proceedings volume, a hub page, an OA-swapped different work — seeds a wrong-content span, and a qualitative claim needs only 2 shared content words (`_MIN_CONTENT_OVERLAP = 2`) to falsely verify against it.

## Three mechanical amplifiers (traced in code)
1. A15 resume re-fetch caps the FETCH at 2000 chars, not just the quote (`live_retriever.py:3112,3167` → `_fetch_content` → `content = _stripped_body[:max_chars]` at 4236). Full content thrown away → `_build_provenance_quote` decimal-window design defeated. 171 rows head-truncated.
2. DOI→PDF redirects never reach the PDF extractor (PDF branch keys on `url.endswith(".pdf")` at access_bypass.py:3746; `doi.org` fails → Jina converts the WHOLE issue). `#page=N` fragment never parsed.
3. No content-identity consolidation — `samework_url_dedup` keys on URL; the 31 dgpu rows have 31 DOIs but one identical blob → don't fold → 31x false corroboration.

## Full scope (one class + side findings)
44 combined-PDF front-matter citations (31 = identical dgpu reb-t-9-2-2026.pdf masthead; + dgpu 8-5, isg-konf x3 vols, naukarus, vsers/Auspicia, ecsoc, efp.in.ua, logos-science); hub/landing heads (Quora ev_337, HBR, Deloitte, ltsgroup); ev_349 OA wrong-work swap; 31x false corroboration; compose core-body screen hole; disclosure-not-in-Methods + missing run-validity summary table; ev_734 unflagged challenge shell; judge max_tokens=2048 < 5024 floor.

## Fix — ordered steps (each: kill-switch env flag DEFAULT ON, OFF = byte-identical; faithfulness engine untouched)
- **A** — stop capping the FETCH at 2000 on A15 re-fetch; fetch full body (`PG_LIVE_CONTENT_MAX` default 300000), keep quote cap via `max_total_chars`. Flag `PG_REFETCH_FULL_BODY`. Must land with B+D.
- **B** — cited-work slice extraction for PDFs: (B1) resolve doi.org redirect + capture `#page=N` from Location header; (B2) fitz page-slice from page N, end from DOI-suffix range / OpenAlex biblio, else forward under existing budget; `strip_pdf_frontmatter` still runs; (B3) no-anchor multi-work container → title-locate the cited work in the BODY (deep occurrence, not TOC), else hand to D; (B4) per-run fetched-blob cache keyed by defragmented resolved URL + blob sha256; stamp `fetched_blob_sha` + `content_source_url` on the row. Flag `PG_PDF_CITED_WORK_SLICE`.
- **C** — carry anchor on the live path (fires via `_fetch_content`); verify frame_fetcher PDF path.
- **D** — cited-work span screen (recover→degrade+disclose, NEVER delete): `is_issue_front_matter(body)` structural TOC/masthead detector (fail-open KEEP) + pool-level identical-span collision (≥2 rows, different works, identical span/blob-sha ⇒ container). Wire into live degraded union (`live_retriever.py:7201`) + A15 resume `_is_degraded` union (`run_honest_sweep_r3.py:12976`, same as the furniture screen) → REPAIRS the current banked corpus on resume. Refetch early-return `wrong_content_front_matter`. Flag `PG_SPAN_CITED_WORK_SCREEN`.
- **E** — content-identity consolidation (31x de-pad): add `fetched_blob_sha` leg to the same-work key in finding_dedup + weighted_enrichment mirror; CONSOLIDATE (count once, keep all citations), delete nothing. Flag `PG_SAMEWORK_CONTENT_LEG`.
- **F** — close compose core-body screen hole: thread `research_question` into `compose_basket_multicited_synth_primary` → `build_verified_span_draft` + apply `_prepare_compose_offtopic_screen` + consult the D `wrong_content_span` flag; fail-open (withhold spans, never sources). Under `PG_COMPOSE_SPAN_TOPICALITY` new leg.
- **G** — reader disclosure: Methods line (deleted N chrome/off-topic, degraded M wrong-content, consolidated K same-work) + the question-mandated run-validity 5-column summary table (verify emit fires; unit test).
- **H** — ev_734 challenge-shell co-signal: URL challenge marker (`/challenge`,`/cdn-cgi/`,`__cf_chl`) AND very-low `_score_content_quality` ⇒ `bot_challenge` at any length (2 signals; fail-open). Feeds junk-deletion (chrome class). Flag `PG_CHALLENGE_SHELL_COSIGNAL`.
- **I** — config: raise starved judge budget to model real max (§9.1.8); add all flags to NEXT_RUN_MANIFEST.

## 6 existing fixes: keep/extend/leave
1 junk_deletion_gate KEEP unchanged (never delete wrong-content — recover+degrade). 2 content_integrity EXTEND with H. 3 tier_t3 LEAVE. 4 samework_url EXTEND with E. 5 compose screen EXTEND with F. 6 disclosure EXTEND with G.

## Tests
Unit (offline, real captured data from the banked corpus_snapshot, not synthetic): full-body refetch decimal-window; redirect+anchor capture; fitz page-slice (no ISSN/TOC in slice); `is_issue_front_matter` positive on the ACTUAL stored dgpu masthead + negative on a real article head; identical-span collision; 31→count 1 / citations 31 / 0 deleted; compose withhold-span fail-open; challenge co-signal; summary-table renders 5 columns.
Small REAL-run proof (mandatory, offline test is not a preflight): VM harness calling `refetch_for_extraction_with_diagnostics` on the live failing URLs (dgpu -203-210 & -87-95, naukarus, isg-konf, ecsoc, vsers) asserting no ISSN/TOC, the two dgpu spans DIFFER, each contains its own article; then one banked-corpus resume with the new flags → 44 rows re-flagged/recovered/degraded, 0 identical-span collisions after, Methods shows counts, run-validity gate passes.

## Fetch-side vs corpus-repair
A,B,C,H = fetch-side (prove on fresh run/re-fetch). D = BOTH (wired into A15 resume it repairs the current banked corpus). E,F,G = corpus/compose-side (act on whatever corpus is loaded). So a resume of the current run with A+D repairs it in place; the planned fresh run exercises everything.

## Build note
Exceeds 200-LOC PR cap → split ordered PRs: (A+B+C fetch) (D screen) (E consolidation) (F compose) (G disclosure) (H+I hardening), each dual-gated (Codex + Fable), GitHub Issue created FIRST (§-1.2). No fixed page-count window / per-source cap anywhere (banned day-waster) — end-page from real metadata only, title-locate is the correctness check.
