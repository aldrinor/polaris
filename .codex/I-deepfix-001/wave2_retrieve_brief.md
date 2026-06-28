HARD ITERATION CAP: 5 per document. This is iter 4 of 5.

## CHANGES SINCE ITER 3 (your continuing P1 — capped quota selection — fixed; re-verify FIRST)
- **P1 (capped quota picks winners before date-window) FIXED.** The demotion now influences SELECTION, not just final order: right after `scored` is built in `_select_evidence_for_generation_impl`, on the TIER-CAPPED path ONLY (`relevance_floor is None and _oow_urls`), each out-of-window row's SELECTION score is multiplied by `_date_demote_weight()`, so the quota allocator + short-pool prefer IN-WINDOW rows for a capped slot. It is GUARDED to the capped path: on the relevance-floor path the score is compared to the floor, so demoting it there could push an out-of-window row below the floor and DROP it (§-1.3 violation) — that path keeps its `_date_window_weight`-in-sort instead. Rows stay in `scored` (selectable when capacity allows); only quota rank drops. The wrapper tail-partition still guarantees final ordering for any selected out-of-window row. Verified offline with a REAL `select_evidence_for_generation` call: max_rows=1, relevance_floor=None, an out-of-window row with HIGHER lexical overlap LOSES the single slot to the in-window row; a no-window control still picks the higher-overlap row (byte-identical when no window).

## CHANGES SINCE ITER 2 (your 3 iter-2 P1s + a P2 fixed — context)
- **P1 (cache not invalidated) FIXED**: `AUTHORITY_CACHE_SCHEMA_VERSION` bumped 2 -> 3 (live_retriever.py:91), so cached payloads predating the `publication_date` field are REBUILT, not served stale — a cached boundary-year row can no longer defeat the month window.
- **P1 (ISO YYYY-MM context-unsafe) FIXED**: removed the blind `_ISO_MONTH_RE` (it set an END ceiling for "since 2020-03", inverting the floor). ISO is now DIRECTION-BOUND: `_SINCE_ISO_RE` ("since 2020-03" -> START 2020-03) + `_BEFORE_ISO_RE` ("before 2023-06" -> END 2023-06). Each only refines its own-direction year; neither sets the opposite bound. Verified: "since 2020-03" sets start only, NO end.
- **P1 (date-window only on relevance_floor path) FIXED**: `select_evidence_for_generation` is now a thin PUBLIC WRAPPER over `_select_evidence_for_generation_impl`. The wrapper applies the month-aware out-of-window tail partition to the FINAL result of EVERY branch (relevance-floor, short-pool, tier-capped — incl. relevance_floor=None callers like the finding-dedup helper). Idempotent (no-op on the already-partitioned+noted floor result), KEEPS every row (§-1.3), FAIL-OPEN (never breaks selection; no window => same object). Verified offline: a capped (relevance_floor=None) result with an out-of-window row gets it sorted LAST + a date-window note; a no-window call returns the same object.
- **P2 (B3 "please " over-strip) FIXED**: dropped bare "please " from `_IMPERATIVE_OPENER_RE` (now `ignore|disregard|do not|don't`); "please compare wage outcomes…" is kept, "please respond only…" still caught by `_DIRECTIVE_MARKERS`.
- **P2 (structured date-exclusion telemetry) DOCUMENTED RESIDUAL**: the date-window disclosure is surfaced as an `EvidenceSelection.notes` entry (carrying the out-of-window count); a dedicated structured `EvidenceSelection.date_excluded` field is deferred to avoid dataclass-field churn across the many `replace()` sites this iter — non-blocking telemetry shape only.
- Verified offline: 11/11 standalone checks this iter (ISO context-safe both directions; opener; wrapper guarantee on the capped path + no-window byte-identical) on top of iter-2's 19/19.

## CHANGES SINCE ITER 1 (your 3 P1s + P2 fixed — context)
- **P1 (B10 month extraction + enforcement) FIXED.** `intake_constraint_extractor` now parses MONTH precision ("before June 2023" -> date_end_year=2023, date_end_month=6; "since March 2020"; "YYYY-MM") via new `_SINCE_MONTH_RE`/`_BEFORE_MONTH_RE`/`_ISO_MONTH_RE` + `_MON_NAMES`; `date_end_iso()`/`date_start_iso()` carry the month ("2023-06"). `scope_gate` writes the ISO month bound into protocol.date_range. `live_retriever` now fetches `publication_date` (added to OPENALEX_WORKS_SELECT + the authority_signals dict) and carries `row['pub_date']` (full ISO). `evidence_selector` gained `_ym_window_bounds` + `_row_pub_ym` + `_row_out_of_window_ym`: enforcement is MONTH-precision when the row has a pub_date month, else YEAR-precision; a boundary-year row whose month is unknown is KEPT (never demote what we can't prove out-of-window); undated KEPT (fail-open).
- **P1 (B10 out-of-window must sort last, survive rerank) FIXED.** New `_partition_out_of_window_last` does a STABLE partition moving out-of-window rows to the TAIL as the LAST step AFTER `_maybe_rerank_selection` — so a hard date ceiling cannot be out-ranked by a high relevance score or washed out by the reranker. KEEPS every row (§-1.3 demote-not-drop); same object when no window (byte-identical).
- **P1 (B3 URL/DOI overmatch) FIXED.** The URL/DOI directive leg now fires ONLY on a BARE payload (`_is_bare_url_doi_payload`: a dict/list literal, or a clause that is essentially just URLs/DOIs with <=2 content words) — a prose research query that cites a DOI ("What does DOI 10.x report about wages?") is KEPT. A real deny-list instruction is still caught by `_DIRECTIVE_MARKERS`.
- **P2 (structured date exclusion records)**: each `_date_excluded_records` entry now also carries `pub_ym` (the row's resolved year-month). The full structured list still lives in the selection telemetry path.
- Verified offline: 19/19 standalone checks (B3 prose-with-DOI kept / bare-payload caught; "before June 2023" -> month 6; July-2023 OUT, May-2023 IN, boundary-year-only KEPT, undated KEPT; stable tail partition; no-window byte-identical).

## (Original iter-1 brief follows.)
HARD ITERATION CAP (orig): 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding. Same bar every iter.
- Reserve P0/P1 for real execution risks; classify minor issues P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW MODE: STATIC ONLY. Do NOT run pytest / pipeline / broad exploration. Read the diff `.codex/I-deepfix-001/wave2_retrieve.patch` and the changed regions only. Emit the schema at the end.

# I-deepfix-001 WAVE 2 — WIRER-RETRIEVE: wire the retrieval-side firing-seams

Wave-1 shipped leaf modules + flags; this wires them at the run path. Files: corpus_adequacy_gate.py, scope_gate.py (CRLF), evidence_selector.py, live_retriever.py, query_decomposer.py + test.

## Seams wired
- **B14** title<->body consistency at the live_retriever fetch loop: metadata-title vs body-derived-title cross-check; on mismatch re-derives classifier_title from body and carries identity_consistent/title_source onto the row. NEVER drops. Flag PG_TITLE_BODY_CONSISTENCY.
- **B10(b)** publication_year carry: live_retriever surfaces OpenAlex publication_year onto evidence_rows as row['year'] (the key evidence_selector recency reads) + row['publication_year']. Absent => undated => never demoted.
- **B10(a)** intake constraint extract in scope_gate run_scope_gate: NL "before June 2023" -> protocol.date_range (FILL-ONLY; override/template wins) + new ProtocolDocument.user_constraints field. Flag PG_EXTRACT_USER_CONSTRAINTS.
- **B10(d)** date-window demotion in evidence_selector.select_evidence_for_generation: out-of-window rows get a demotion WEIGHT (sort last) but are KEPT (exclusion record + disclosure note); recency tiebreak forced OFF when a max-date is present; undated never demoted. Flag PG_SELECT_DATE_WINDOW_WEIGHT.
- **B3** decomposer leg: query_decomposer.decompose_question calls scope_query_validator.strip_directive_clauses on decomposed sub-clauses before they become search queries. Flag PG_QUERY_DIRECTIVE_SCREEN.
- **B7** adequacy on_topic predicate: corpus_adequacy_gate counts a row toward grounded+tier denominators only if relevance_weight >= PG_ADEQUACY_RELEVANCE_FLOOR (default 0.30); surfaces raw + on-topic denominators + disclosure note. assess_corpus_adequacy keeps its EXACT existing signature (evidence_rows kw-only).

## VERIFY HARDEST (adversarial — the real risks)
1. **§-1.3 no forbidden drop:** confirm B10(d) and B7 only WEIGHT/demote or gate on the DATE WINDOW (a hard user constraint) or OFF-TOPIC relevance — NEVER on credibility tier. A date-window source is KEPT (demoted + disclosed), not dropped. B7's on_topic floor gates a DENOMINATOR (an adequacy-count), not the corpus itself — confirm it does not delete rows.
2. **FAIL-OPEN (wave-1 P0 class):** confirm every new predicate is fail-open — a row with NO relevance_weight key (B7), NO year (B10), or a scorer/extractor error must NOT be demoted/dropped/excluded. Default to keep/neutral.
3. **B14 never drops:** confirm a title<->body mismatch only re-derives the title + flags identity_consistent, never removes the source.
4. **B10 fill-only:** confirm intake date_range only FILLS an empty field; an operator/template-set window is never overwritten.
5. **B3 reuses the (wave-1 narrowed) directive predicate** and cannot strip a legitimate research sub-query (the opener is now `please/ignore/disregard/do not/don't` only).
6. **No faithfulness-engine edit:** strict_verify / NLI / span / 4-role / provenance untouched. assess_corpus_adequacy signature unchanged (kw-only evidence_rows).

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
