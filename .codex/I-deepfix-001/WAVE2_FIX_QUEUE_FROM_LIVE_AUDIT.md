# Wave-2 fix queue — from the live drb_72 forensic read (2026-07-08)

Captured so the session-limit interruption does not lose the completed root-cause work.
The 4 Fable investigations below COMPLETED with full root causes; only their fix+gate legs
died on the "session limit resets 8:30pm" error. Re-run the fix+gate legs (limit now reset).

Two fixes are ALREADY dual-gate APPROVED (uncommitted in the working tree):
- **NLI-consolidation pre-bucket** (repetition) — flag `PG_CONSOLIDATION_NLI_SUBBUCKET`. Codex+Fable APPROVE.
- **#1373 query-gen status-leak screen** (corrupt off-topic retrieval) — flag `PG_QUERY_META_STATUS_SCREEN`,
  iter-2 fixed Codex's stopword-exemption P1. Codex+Fable APPROVE.

Full per-agent detail lives in the task-output files under
`.../scratchpad` / the workflow journals; summarized here for durability.

---

## FIX 3 — Chrome leak to basket composition (BIGGEST quality issue)
Task wsxr5jp9p. Root cause (confirmed on run data):
- The furniture predicate `is_render_chrome_or_unrenderable` (weighted_enrichment.py:3317) is only
  wired at basket-build (credibility_pass.py:1144) and only as a corroboration-COUNT demotion — the
  member is still appended. There is NO furniture screen upstream of basket-build. Grep proves ZERO
  calls to the furniture predicate anywhere in `src/polaris_graph/retrieval/`.
- Degraded PDF extraction (mineru timeout -> docling skipped >40pg -> PyMuPDF/HTML fallback) returns
  masthead/nav/DOI/license furniture as the body. That furniture becomes the claim-local direct_quote,
  survives strict_verify via the self-citation hole, forms a BasketMember. When EVERY member is
  furniture the basket is all-chrome -> abstractive_writer skips -> K-span fallback.
- Confirmed losing REAL papers: Felten "Occupational Heterogeneity in Exposure to Generative AI"
  (SSRN abstract-page chrome), a DSpace paper (Dublin-Core metadata), AI Review 2024, Oeconomia
  Copernicana 2023, World Bank (chrome-prefixed).
- mineru sub-cause: flat page-agnostic 75s timeout (generous_limits PG_MINERU25_TIMEOUT_S=75) that
  200-458pg reports genuinely exceed + a 3-consecutive-failure breaker -> 300s TOTAL mineru blackout ->
  PyMuPDF chrome for the whole PDF-heavy stretch.
FIX (§-1.3-safe, down-weight/re-fetch/disclose, never hard-drop):
1. Extraction-time furniture-density screen on the FULL body (extend shell_detector beyond short-body):
   furniture-dominant body -> mark fetch-degraded -> A15/AccessBypass re-fetch with a different extractor.
2. If re-fetch still furniture -> down-weight authority/tier + disclose (keep in pool, stop it being a
   sole corroborator).
3. Selection-time: run furniture predicate over candidate spans so a real-content span wins direct_quote.
4. mineru: page-scaled timeout + less-aggressive breaker so mineru stays available on the small PDFs.

## FIX 4 — Connection resilience (disconnect -> writer 180s deadline -> K-span)
Task wt653do23. Root cause = THREE, all ours (glm-5.2 has 27 healthy providers — NOT availability):
1. httpx.AsyncClient (openrouter_client.py:1488) built with NO limits=/http2 -> default keepalive_expiry=5s,
   shared pool reused; sub-5s idle gaps -> provider/LB closes socket -> pool hands back dead conn ->
   "Server disconnected without sending a response" (RemoteProtocolError). Precedent fix already exists at
   entailment_judge.py:726-738 (httpx.Limits max_keepalive=8, keepalive_expiry=30, explicit timeouts).
2. Retry (openrouter_client.py:2427-2461) catches it but `continue`s on the SAME pool — can grab another
   dead conn; each of MAX_RETRIES=2 spends a full connect+write+wait -> the 1-10s -> 51-69s jump.
3. Generator pinned order:[friendli,...] allow_fallbacks:false (openrouter_provider_routing.yaml:7-17) ->
   whole compose burst hammers friendli (order[0]); its concurrency ceiling drops conns; fallbacks blocked
   from the 26 healthy siblings. Same order[0]-burst failure the YAML already documents+fixed for the judge.
FIX (transport/routing, faithfulness-neutral):
- Give AsyncClient httpx.Limits(bounded max_keepalive, LOW keepalive_expiry ~1-2s via env) + explicit timeouts.
- On RemoteProtocolError/ReadError force a FRESH connection (drop idle pool) before retry.
- Generator provider routing: allow_fallbacks:true OR unpin `order` (as the judge was unpinned) so the burst
  load-balances across glm-5.2's 27 endpoints.
- Writer 180s deadline: do NOT count connection-retry/stall time against it (transport-aware).

## FIX 5 — Writer 720s pre-pass WALL mass-K-span abandonment
Task wm9ulbavt. Root cause: 720s wall was sized for 23 baskets at concurrency 8 (code comment
abstractive_writer.py:102-107). drb_72 sections carry 71/82/86/104/113 baskets at DEFAULT concurrency=8,
wall=720s -> at the disconnect-slow 60-144s/call the wall exhausts and ABANDONS all still-pending baskets
to raw K-span with no recovery (19/104, 14/86, 9/113 drafted). Healthy math: at conc=8, 104 baskets healthy
~260-390s (fits) but only 1.7-2.8x margin -> a 2-3x slowdown tips it; at conc=24 the same spell survives.
FIX (NOT a blind wall raise):
- Raise bounded PG_ABSTRACTIVE_WRITER_CONCURRENCY 8 -> ~24-32 (box already runs VERIFY_CONCURRENCY=30).
- Basket-count-scaled wall from the code's own makespan formula, not flat 720s.
- Transport-aware wall (composes with FIX 4).
- Recovery second-pass over still-pending baskets before dumping ALL to K-span.
- ALSO: wrap `_call_writer` (abstractive_writer.py:445/475) to CATCH httpx.ConnectTimeout -> K-span cleanly
  (a raw ConnectTimeout currently escapes as "Task exception was never retrieved" — unhandled asyncio leak).

## FIX 6 — genai_productivity contract slot rendered as a GAP (Brynjolfsson QJE)
Task w9oix6yip. Root cause = downstream plumbing (NOT weighting; the papers weight fine):
1. Contract-entity binding miss: no evidence row was stamped v30_entity_id='brynjolfsson_genai_at_work'
   (5/6 entities bound; brynjolfsson bound to none). Its sentences carried the bare marker
   [brynjolfsson_genai_at_work] which citation-rewrite could not resolve -> strict_verify dropped all 13 for
   no_provenance_token. Sibling eloundou_gpts_are_gpts bound correctly and was kept -> entity-specific.
2. Chrome-contaminated span: the bound abstract copy (ev_907/905) is prefixed "## Author Listed: * Erik
   Brynjolfsson ... ## Abstract We study..." -> all sentence units screen as chrome -> all-chrome drop. A
   CLEAN copy ev_915 (crw=1.0) and the T1 QJE ev_013/ev_1017 exist but were never bound (ev_013/1017 not even
   in the 999-row gen pool).
FIX (faithfulness-strengthening):
- Bind by DOI (10.1093/qje/qjae044) + title/author fuzzy; prefer the clean ev_915; keep ev_013/1017 in gen pool.
- Chrome-strip the "## Author Listed ... ## Abstract" prefix at extraction/normalization.
- Contract basket re-anchor to a same-DOI clean sibling when the bound entity is hollow.

## FIX 7 (NEW — found in the live D8 read) — judge provider-availability tears the D8 seam
Live log 01:58-02:38: repeated `judge off-enum token (JudgeEnumError)`, `judge blank verdict with bare
reasoning`, `sentinel role force-close`, `POST exceeded PG_ROLE_TRANSPORT_TOTAL_S`, + `quantified_silent_no_op`
canary. Same provider-availability class as the historical judge-model render-blocker. The D8 4-role judge
model is returning off-enum/blank verdicts under concurrency -> the validity gate grinds 40+ min.
FIX direction: apply the SAME transport resilience (FIX 4) to the role-transport client, and/or move the
judge/sentinel role to a higher-provider-count open model (measure /models/{id}/endpoints count).

---

## Assembly rule (CRITICAL)
FIX 4 + FIX 5 both edit abstractive_writer.py; FIX 4 also edits openrouter_client.py. Do NOT trust the
raw parallel diffs. Assemble on a clean tree, resolve the shared-file overlap by hand, run ONE combined
Codex+Fable gate before the next launch. The two already-approved fixes (NLI-prebucket, #1373) are the base.
