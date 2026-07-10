# CODEX DIFF REVIEW — I-deepfix-004 PR-1 (frontmatter-core: fetch steps A/B/C + span screen D)

HARD ITERATION CAP: 5 per document. Front-load ALL real findings now. Same quality bar. Don't pick bone from egg — reserve P0/P1 for real execution risks. Verdict APPROVE iff zero novel P0 AND zero continuing P0 AND zero P1.

Please return your verdict in this exact schema as the LAST block of your output:

```
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

The final `verdict:` line is machine-parsed. Emit exactly one of `verdict: APPROVE` or `verdict: REQUEST_CHANGES` as the last `verdict:` line.

## What PR-1 does (steps A/B/C/D per fable_root_cause_plan.md)

1. Root cause fixed here: the pipeline defined a citable span by POSITION (first ~1500 chars of whatever bytes came back) and NO stage checked IDENTITY (is this text actually the cited article?). A whole journal-issue PDF, proceedings volume, or hub page seeded a wrong-content span that a 2-content-word qualitative claim could falsely verify against.
2. STEP A (`PG_REFETCH_FULL_BODY`, default ON): stop capping the A15 resume re-fetch at 2000 chars; fetch full body (`PG_LIVE_CONTENT_MAX` default 300000) so `_build_provenance_quote`'s decimal-window can find the real deep-number span; the quote itself is still capped by `max_total_chars`.
3. STEP B (`PG_PDF_CITED_WORK_SLICE`, default ON): cited-work slice extraction for PDFs — resolve `doi.org` redirect + capture `#page=N` from the Location header; fitz page-slice from page N (end from DOI-suffix range / OpenAlex biblio, else forward under existing budget); `strip_pdf_frontmatter` still runs; no-anchor multi-work container → title-locate the cited work in the BODY (deep occurrence, not TOC); per-run blob cache keyed by defragmented resolved URL + blob sha256; stamps `fetched_blob_sha` + `content_source_url` on the row.
4. STEP C: carry the page anchor on the live path (via `_fetch_content`); verify the frame_fetcher PDF path reaches the extractor.
5. STEP D (`PG_SPAN_CITED_WORK_SCREEN`, default ON): cited-work span screen — `is_issue_front_matter(body)` structural TOC/masthead detector (fail-open KEEP) + pool-level `identical_span_collision` (≥2 rows, different works, identical STORED SPAN ⇒ container). Wired into the live degraded union AND the A15 resume `_is_degraded` union so a resume REPAIRS the current banked corpus in place; refetch early-returns `wrong_content_front_matter`.
6. Tests: 24 offline pytest cases over real captured data from the banked corpus_snapshot (full-body refetch decimal-window; redirect+anchor capture; fitz page-slice with no ISSN/TOC in slice; `is_issue_front_matter` positive on the ACTUAL stored dgpu masthead + negative on a real article head; identical-span collision; consolidation count-once-keep-all).

## Binding constraints (verify the diff HONORS every one)

- **RECOVER → DEGRADE → DISCLOSE, NEVER DELETE.** A wrong-content / front-matter / collision row is RE-FETCHED to recover the real cited work; if unrecovered it is KEPT as a DISCLOSED degraded row. No code path may hard-DROP a credible on-topic source because its span is wrong-content. (Chrome/off-topic junk deletion from I-deepfix-003 is separate and unchanged.)
- **Faithfulness engine UNTOUCHED.** strict_verify / NLI entailment / 4-role D8 / provenance / span-grounding logic must not be modified. This PR only changes what BYTES seed a span and flags wrong-content spans; it never relaxes or alters the verification gate.
- **Flags default ON; with every flag OFF the behavior is BYTE-IDENTICAL to base.** `PG_REFETCH_FULL_BODY`, `PG_PDF_CITED_WORK_SLICE`, `PG_SPAN_CITED_WORK_SCREEN` each OFF must reproduce the exact prior code path (no extra rows flagged, no extra fetch, no changed output).
- **NO fixed page-count window / per-source cap anywhere** (banned day-waster). End-page comes from real metadata only (DOI suffix range / OpenAlex biblio); title-locate is the correctness check, not a hardcoded window.

## Review focus (line-by-line, §-1.1)

Audit the diff claim-by-claim against these constraints. Specifically confirm:
- Every degraded/wrong-content disposition RECOVERS-then-DISCLOSES and never deletes; a recovered row has its wrong-content flag CLEARED after a successful re-fetch.
- `is_issue_front_matter` cannot false-flag a legitimate long article/report body that merely contains a normal TOC (Step A now feeds it the full 300k body).
- `identical_span_collision` keys on the extracted STORED SPAN identity, not the whole-PDF `fetched_blob_sha` (two correctly-sliced distinct articles from the same issue PDF share a blob hash and must NOT be flagged as a collision).
- OFF-path byte-identity for all three flags.
- No hardcoded page window; end-page derives from real metadata only.

## THE DIFF (git diff 63ea46f0..bot/I-deepfix-004-frontmatter-core)

```diff
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index 2aca4a4f..fe8159c0 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -12964,6 +12964,39 @@ async def run_one_query(
                 except Exception:  # noqa: BLE001 — no predicate => no furniture flag (fail-open)
                     _b1_furniture_screen_on = False
                     _b1_is_furniture_dominant = None
+                # I-deepfix-004 D (RESUME WIRING, 2026-07-09) — extend the A15 degraded
+                # predicate with the cited-work span screen so a banked row whose stored
+                # span is journal-issue FRONT-MATTER (cover / TOC / masthead) OR whose
+                # evidence_id is in the pool-level identical-span COLLISION set (one issue
+                # PDF cited under ≥2 distinct DOIs = the 31x dgpu false corroboration) is
+                # ALSO flagged degraded and re-fetched through the SAME step-B sliced
+                # extractor to RECOVER the real cited article — REPAIRING the current banked
+                # corpus in place. READ-ONLY reuse of shell_detector.is_issue_front_matter +
+                # identical_span_collision (never forked, LAW V). Gated STRICTLY on the
+                # default-ON PG_SPAN_CITED_WORK_SCREEN: OFF => the screen is never consulted
+                # => NO extra rows flagged => byte-identical. Isolated try/except so a step-D
+                # import error never perturbs the existing A15 detection (fail-open: no
+                # front-matter/collision flag). §-1.3 recover→degrade→disclose: a flagged
+                # row is RE-FETCHED then, if unrecovered, kept as a DISCLOSED degraded row —
+                # NEVER deleted.
+                _d_span_screen_on = False
+                _d_is_front_matter = None
+                _d_collision_eids: set = set()
+                try:
+                    from src.polaris_graph.retrieval.shell_detector import (  # noqa: PLC0415
+                        identical_span_collision as _d_collision,
+                        is_issue_front_matter as _d_is_front_matter,
+                        span_cited_work_screen_enabled as _d_screen_enabled,
+                    )
+                    _d_span_screen_on = _d_screen_enabled()
+                    if _d_span_screen_on:
+                        _d_collision_eids = _d_collision(
+                            [_r for _r in evidence_for_gen if isinstance(_r, dict)]
+                        )
+                except Exception:  # noqa: BLE001 — no predicate => no wrong-content flag (fail-open)
+                    _d_span_screen_on = False
+                    _d_is_front_matter = None
+                    _d_collision_eids = set()
                 _a15_stale_rows: list[str] = []
                 _a15_degraded_dicts: list[dict] = []
                 for _row in evidence_for_gen:
@@ -12973,6 +13006,21 @@ async def run_one_query(
                     _grounding = (
                         _row.get("direct_quote") or _row.get("statement") or ""
                     )
+                    # I-deepfix-004 D: wrong-CONTENT verdict for THIS banked row — its
+                    # stored span is journal-issue FRONT-MATTER, OR its evidence_id is in
+                    # the pool-level identical-span COLLISION set (a multi-work container
+                    # blob laundered into ≥2 distinct citations). Fail-open: screen OFF or
+                    # any detector error => False (never flags).
+                    _d_wrong_content = False
+                    if _d_span_screen_on:
+                        try:
+                            _d_wrong_content = (
+                                (_d_is_front_matter is not None
+                                 and bool(_d_is_front_matter(_grounding)))
+                                or (str(_eid) in _d_collision_eids)
+                            )
+                        except Exception:  # noqa: BLE001 — fail-open: never flag on detector error
+                            _d_wrong_content = False
                     _is_degraded = (
                         bool(_row.get("content_starved"))
                         or bool(_row.get("fetch_failed"))
@@ -12983,6 +13031,7 @@ async def run_one_query(
                             screen_on=_b1_furniture_screen_on,
                             is_dominant_fn=_b1_is_furniture_dominant,
                         )
+                        or _d_wrong_content
                     )
                     if _is_degraded:
                         _a15_stale_rows.append(str(_eid))
@@ -12990,6 +13039,13 @@ async def run_one_query(
                         # FLAG the row so a downstream refresh / composition layer can see it needs a
                         # re-fetch (additive key; asserts nothing, drops nothing).
                         _row["resume_refresh_pending"] = True
+                        # I-deepfix-004 D: stamp wrong_content_span on rows the cited-work
+                        # span screen flagged (front-matter / identical-span container) so
+                        # disclosure + compose see the wrong-CONTENT reason distinctly. The
+                        # row is RE-FETCHED (recover) then, if unrecovered, kept as a
+                        # DISCLOSED degraded row — §-1.3 NEVER deleted. Additive key.
+                        if _d_wrong_content:
+                            _row["wrong_content_span"] = True
                 if _a15_stale_rows:
                     _log(
                         f"[resume]      A15 refresh: {len(_a15_stale_rows)} reloaded row(s) are "
diff --git a/src/polaris_graph/retrieval/live_retriever.py b/src/polaris_graph/retrieval/live_retriever.py
index 25ad787f..b46d79be 100644
--- a/src/polaris_graph/retrieval/live_retriever.py
+++ b/src/polaris_graph/retrieval/live_retriever.py
@@ -3164,6 +3164,20 @@ def _m45_pop_fetch_telemetry(url: str) -> dict[str, Any]:
     return _M45_LAST_FETCH_TELEMETRY.pop(url, {})
 
 
+def _refetch_full_body_enabled() -> bool:
+    """I-deepfix-004 A (#1375) — True (default) ⇒ the A15 re-fetch fetches the FULL
+    body (``PG_LIVE_CONTENT_MAX`` = ``DEFAULT_CONTENT_MAX_CHARS``) and caps only the
+    QUOTE at the caller's ``max_chars``, so ``_build_provenance_quote``'s decimal-window
+    design can reach a real number DEEP in a long body (the prior code truncated the
+    FETCH at ``max_chars`` = 2000 BEFORE the quote was built, so 171 A15 rows were head-
+    truncated and any deep number was thrown away). ``PG_REFETCH_FULL_BODY=0`` (or
+    off/false/no/disabled) ⇒ the FETCH is capped at ``max_chars`` exactly as before ⇒
+    byte-identical. Read at call time (LAW VI)."""
+    return os.environ.get("PG_REFETCH_FULL_BODY", "1").strip().lower() not in (
+        "0", "false", "off", "no", "disabled",
+    )
+
+
 def refetch_for_extraction_with_diagnostics(
     url: str, max_chars: int = 2000,
 ) -> tuple[str, dict[str, Any]]:
@@ -3194,9 +3208,13 @@ def refetch_for_extraction_with_diagnostics(
           eligible: bool — True iff quote was emitted (≥100 chars)
           failure_mode: str — one of:
             '' (eligible), 'exception', 'fetch_failed',
-            'thin_content', 'paywall_shell', 'fetch_shell'
+            'thin_content', 'paywall_shell', 'fetch_shell',
+            'wrong_content_front_matter'
             ('fetch_shell' = clean_fetch_body reported the whole body is a
-            boilerplate/interstitial shell — not extractable, not cited)
+            boilerplate/interstitial shell — not extractable, not cited;
+            'wrong_content_front_matter' = I-deepfix-004 D: the cleaned body is
+            a journal-issue cover/TOC/masthead, not the cited article — an A15
+            recovery must NEVER adopt a front-matter span as the cited work)
           exception_type: str — class name when failure_mode=exception
     """
     diagnostics: dict[str, Any] = {
@@ -3239,8 +3257,15 @@ def refetch_for_extraction_with_diagnostics(
     _fetch_succeeded = False
     try:
         diagnostics["attempted"] = True
+        # I-deepfix-004 A (#1375): SEPARATE the FETCH-body cap from the QUOTE cap. Fetch
+        # the FULL body (default ``DEFAULT_CONTENT_MAX_CHARS`` = ``PG_LIVE_CONTENT_MAX`` =
+        # 300000) so ``_build_provenance_quote`` below can window a decimal DEEP in the
+        # body; the QUOTE stays capped at the caller's ``max_chars`` via
+        # ``max_total_chars`` (unchanged). OFF (``PG_REFETCH_FULL_BODY=0``) ⇒ fetch cap =
+        # ``max_chars`` ⇒ byte-identical to the prior head-truncating behaviour.
+        _body_cap = DEFAULT_CONTENT_MAX_CHARS if _refetch_full_body_enabled() else max_chars
         try:
-            content, ok, _title, body_type, _jsonld = _fetch_content(url, max_chars)
+            content, ok, _title, body_type, _jsonld = _fetch_content(url, _body_cap)
         except Exception as exc:
             logger.warning(
                 "[refetch_for_extraction] fetch failed for %s: %s", url, exc,
@@ -3309,6 +3334,25 @@ def refetch_for_extraction_with_diagnostics(
             )
             diagnostics["failure_mode"] = "fetch_shell"
             return "", diagnostics  # failure (settled in finally)
+        # I-deepfix-004 D (step 1): an A15 recovery re-fetch must NEVER adopt a
+        # journal-issue COVER / TABLE-OF-CONTENTS / MASTHEAD span as the cited
+        # article. AFTER clean_fetch_body, if the default-ON cited-work span screen
+        # (``PG_SPAN_CITED_WORK_SCREEN``) confirms the cleaned body is issue
+        # FRONT-MATTER (structural TOC dot-leader density OR ISSN masthead + contents
+        # vocab), route it to the SAME EXISTING not-extractable failure branch used for
+        # a fetch shell (return "" with a diagnostic failure_mode) — recover→degrade→
+        # disclose, NEVER a DROP of the source (the caller keeps the row as a disclosed
+        # degraded gap). Fail-open: the screen OFF or any detector error => skipped =>
+        # byte-identical. Adds NO new cap/threshold; consumes the EXISTING early-return.
+        if _span_is_issue_front_matter(content):
+            logger.info(
+                "[refetch_for_extraction] front-matter rejected url=%s len=%d → "
+                "not-extractable (A15 recovery must not adopt a cover/TOC/masthead span "
+                "as the cited article; §-1.3 recover→degrade→disclose, source kept)",
+                (url or "")[:200], len(content),
+            )
+            diagnostics["failure_mode"] = "wrong_content_front_matter"
+            return "", diagnostics  # failure (settled in finally)
         quote = _build_provenance_quote(
             content, head_chars=min(_PROVENANCE_HEAD_CHARS_CAP, max_chars),
             window_chars=500, max_total_chars=max_chars,
@@ -4477,6 +4521,27 @@ def _is_access_denial_stub(content: str) -> bool:
     return shell_detector.is_access_denial_stub(content, max_chars=_ACCESS_DENIAL_MAX_CHARS)
 
 
+def _span_is_issue_front_matter(content: str) -> bool:
+    """I-deepfix-004 D — fail-open wrapper around the cited-work FRONT-MATTER screen
+    (``shell_detector.is_issue_front_matter``), gated by the default-ON
+    ``PG_SPAN_CITED_WORK_SCREEN`` (``shell_detector.span_cited_work_screen_enabled``).
+
+    True iff the screen is ON AND ``content`` (a cited SPAN / fetched body) is a
+    journal-issue COVER / TABLE-OF-CONTENTS / MASTHEAD rather than the cited article's
+    prose (structural TOC dot-leader density OR ISSN masthead + contents vocab). The
+    screen OFF, or ANY detector/import error, returns ``False`` (skip) so the OFF path
+    is byte-identical and a detector fault NEVER breaks retrieval. DETECTS only — a True
+    verdict routes the span into the EXISTING recover→degrade→disclose branch, NEVER a
+    DROP of the source (§-1.3: never delete a credible on-topic source; only the wrong
+    SPAN is unusable for grounding)."""
+    try:
+        if not shell_detector.span_cited_work_screen_enabled():
+            return False
+        return bool(shell_detector.is_issue_front_matter(content))
+    except Exception:  # noqa: BLE001 — fail-open: any detector error => skip the screen
+        return False
+
+
 def is_content_starved(content: str, min_useful_chars: int = 200) -> bool:
     """R-5 Fix D: detect evidence rows whose fetched content is PDF
     metadata / formatting fragments / empty text — not useful prose.
@@ -7165,6 +7230,21 @@ def run_live_retrieval(
                 and (not _is_landing)
                 and _is_citation_metadata_shell(content)
             )
+            # I-deepfix-004 D (step 2): a cited SPAN that is journal-issue FRONT-MATTER
+            # (cover / TOC / masthead) is wrong-CONTENT — right topic, right journal, but
+            # NOT the cited article. Route it into the SAME EXISTING degraded re-fetch /
+            # down-weight / disclose branch as a starved/landing/shell row (§-1.3:
+            # recover→degrade→disclose, NEVER a DROP). Disjoint from the other signals
+            # (only flagged when NOT already starved/landing/shell) so the telemetry stays
+            # clean. Fail-open via ``_span_is_issue_front_matter``: the screen OFF
+            # (``PG_SPAN_CITED_WORK_SCREEN`` off) or any detector error => False => never
+            # computed into the union => byte-identical.
+            _is_front_matter = (
+                (not _starved)
+                and (not _is_landing)
+                and (not _is_shell)
+                and _span_is_issue_front_matter(content)
+            )
             # I-deepfix-001 (Codex P1 #2): tracks whether the forced re-fetch below upgraded a
             # degraded stub to full text. A recovered row is a NORMAL full-text row, so the stale
             # classification-time ``tier_result.fetch_degraded`` must NOT be propagated onto it
@@ -7199,7 +7279,7 @@ def run_live_retrieval(
             # would MISS it). Reusing the fetch layer's settled ok=False here is
             # NOT a new cap — it is the same stub decision already made upstream.
             if (
-                _starved or _is_landing or _is_shell or not ok
+                _starved or _is_landing or _is_shell or _is_front_matter or not ok
             ) and _refetch_degraded_enabled() and not _wall_rescue_mode:
                 _refetched = _try_refetch_degraded_row(
                     cand.url, DEFAULT_CONTENT_MAX_CHARS,
diff --git a/src/polaris_graph/retrieval/shell_detector.py b/src/polaris_graph/retrieval/shell_detector.py
index bf80c8b5..f320e58a 100644
--- a/src/polaris_graph/retrieval/shell_detector.py
+++ b/src/polaris_graph/retrieval/shell_detector.py
@@ -571,3 +571,198 @@ def select_real_content_span(candidate_spans: "list[str]") -> "tuple[int, str]":
         if not _is_furniture_segment(span):
             return (i, span)
     return (fallback_index, fallback_span)
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# I-deepfix-004 D (#1375) — CITED-WORK SPAN SCREEN (issue front-matter / masthead).
+#
+# WHY (distinct from the furniture screen above): the furniture screen catches a
+# body that is MOSTLY masthead/nav/DOI chrome welded together. It does NOT catch a
+# stored SPAN that is a journal ISSUE'S COVER / TABLE-OF-CONTENTS / MASTHEAD sitting
+# at the head of an otherwise real multi-article container PDF. That is the
+# I-deepfix-004 failure: a doi.org URL redirected to a whole issue PDF, the first
+# ~2000 chars (= the cover/TOC/masthead) became the cited direct_quote, and a
+# qualitative claim verified against it on 2 shared content words (the "wrong
+# CITED-WORK, right topic" hole — every prior gate asked "is this junk?" / "is this
+# on-topic?"; none asked "is this the cited ARTICLE?").
+#
+# ``is_issue_front_matter`` is a STRUCTURAL detector on the STORED SPAN (not the raw
+# full body — a 40-page issue body is mostly article prose, so the density signal
+# only reads true on the head SPAN that was actually stored). PRECISION-FIRST +
+# FAIL-OPEN (any uncertainty ⇒ KEEP): calibrated on the real banked drb_78 corpus so
+# genuine article heads / reference lists / an incidental "contents" mention never
+# fire. NEVER used to DROP — only to mark a span ``wrong_content_span`` so the caller
+# RE-EXTRACTS (step B) to RECOVER; if unrecovered the SOURCE is KEPT as a DISCLOSED
+# DEGRADED row (§-1.3: recover→degrade→disclose, never delete a credible on-topic
+# source; only the wrong SPAN is unusable for grounding).
+#
+# Both behaviours sit behind the default-ON ``PG_SPAN_CITED_WORK_SCREEN``; OFF => the
+# functions are never called on the hot path => byte-identical.
+# ─────────────────────────────────────────────────────────────────────────────
+
+_ENV_SPAN_CITED_WORK_SCREEN = "PG_SPAN_CITED_WORK_SCREEN"
+
+# Minimum dot-leader / page-number TOC lines that must appear in the span for the
+# structural TOC signal to fire. Calibrated on the real banked drb_78 corpus: genuine
+# issue/report TOC heads carry 13–14 dot-leaders in the first 2000 chars, while every
+# real article head + reference list + an incidental "contents" mention carries 0. A
+# high floor (default 8) is precision-first — it never fires on a real article head.
+_ENV_FRONT_MATTER_TOC_LINE_MIN = "PG_FRONT_MATTER_TOC_LINE_MIN"
+_DEFAULT_FRONT_MATTER_TOC_LINE_MIN = 8
+
+# The structural verdict is meaningless on a tiny stub (the short-body shell gates own
+# those); the screen only reads a body at/above this length (a masthead/TOC head span).
+_ENV_FRONT_MATTER_MIN_BODY_CHARS = "PG_FRONT_MATTER_MIN_BODY_CHARS"
+_DEFAULT_FRONT_MATTER_MIN_BODY_CHARS = 400
+
+# Dot-leader run (three-or-more dots) followed by a page number (arabic or roman) — the
+# canonical Table-of-Contents line shape, robust to the space-collapsed single-line PDF
+# extraction output. High-precision: a run of ``...`` before a page number never occurs
+# in real article prose.
+_FRONT_MATTER_DOT_LEADER_RE = re.compile(r"\.{3,}\s*[ivxlcdm\d]{1,5}\b", re.IGNORECASE)
+
+# Contents / masthead vocabulary — REQUIRED as a co-signal for the ISSN masthead path
+# (never fires alone; an incidental "contents" mention in a real article must not trip
+# the screen — verified on the real corpus: netce "course/content" + a caregiving
+# report both carry "contents" yet are genuine articles). Includes the Cyrillic
+# journal-issue "СОДЕРЖАНИЕ" (contents) + "РЕДАКЦИОННАЯ КОЛЛЕГИЯ" (editorial board) for
+# the dgpu-class Russian-journal masthead.
+_FRONT_MATTER_CONTENTS_VOCAB: tuple[str, ...] = (
+    "table of contents",
+    "содержание",
+    "editorial board",
+    "editor-in-chief",
+    "editorial office",
+    "редакционная коллегия",
+    "редакционный совет",
+)
+
+# ISSN masthead marker (print/electronic serial number) — a strong journal-issue
+# front-matter signal, but REQUIRED to co-occur with contents vocab so a reference
+# list that merely cites an ISSN never trips the screen.
+_FRONT_MATTER_ISSN_RE = re.compile(r"issn\s*:?\s*\d{4}-\d{3}[\dxX]", re.IGNORECASE)
+
+
+def span_cited_work_screen_enabled() -> bool:
+    """True (default) ⇒ the cited-work span screen (``is_issue_front_matter`` +
+    ``identical_span_collision``) participates in the degraded-detection unions.
+
+    ``PG_SPAN_CITED_WORK_SCREEN=0`` (or off/false/no/disabled) ⇒ the screen is never
+    consulted ⇒ byte-identical. Read at call time so tests toggle without re-import."""
+    return os.environ.get(_ENV_SPAN_CITED_WORK_SCREEN, "1").strip().lower() not in _OFF_VALUES
+
+
+def _front_matter_toc_line_min() -> int:
+    """Minimum dot-leader TOC lines for the structural TOC signal to fire."""
+    return _env_int(_ENV_FRONT_MATTER_TOC_LINE_MIN, _DEFAULT_FRONT_MATTER_TOC_LINE_MIN)
+
+
+def _front_matter_min_body_chars() -> int:
+    """Minimum span length at/above which the front-matter screen reads a verdict."""
+    return _env_int(_ENV_FRONT_MATTER_MIN_BODY_CHARS, _DEFAULT_FRONT_MATTER_MIN_BODY_CHARS)
+
+
+def is_issue_front_matter(body: str) -> bool:
+    """I-deepfix-004 D — True iff ``body`` (a STORED cited SPAN) is a journal-issue
+    COVER / TABLE-OF-CONTENTS / MASTHEAD rather than the cited article's prose.
+
+    STRUCTURAL + DETERMINISTIC + PRECISION-FIRST + FAIL-OPEN (any uncertainty ⇒ KEEP,
+    i.e. return ``False``). Two independent high-precision signals — either fires:
+
+      1. TOC-shaped: at least ``PG_FRONT_MATTER_TOC_LINE_MIN`` (default 8) dot-leader
+         runs (``...`` before a page number). A real article head / reference list
+         carries ZERO (calibrated on the real banked drb_78 corpus: genuine TOC heads
+         carry 13–14, every real article head carries 0).
+      2. ISSN masthead: an ``ISSN dddd-dddd`` marker AND contents/editorial-board vocab
+         co-occur (both required — an incidental "contents" mention or a lone ISSN
+         citation in real prose trips neither). Covers the Cyrillic dgpu-class masthead
+         (``СОДЕРЖАНИЕ`` / ``РЕДАКЦИОННАЯ КОЛЛЕГИЯ`` + ISSN).
+
+    NEVER a DROP: a ``True`` verdict marks the SPAN ``wrong_content_span`` so the caller
+    re-extracts (step B) to recover the real article, else keeps the SOURCE as a
+    DISCLOSED DEGRADED row (§-1.3). Pure; no LLM / network / row mutation.
+    """
+    if not body:
+        return False
+    if len(body.strip()) < _front_matter_min_body_chars():
+        return False  # fail-open: too short to read a structural verdict
+    low = body.lower()
+    # Signal 1 — dot-leader TOC density (any-length; the run-of-dots-before-a-page-number
+    # shape never occurs in real article prose).
+    if len(_FRONT_MATTER_DOT_LEADER_RE.findall(body)) >= _front_matter_toc_line_min():
+        return True
+    # Signal 2 — ISSN masthead AND contents/editorial vocab co-occur (both required).
+    if _FRONT_MATTER_ISSN_RE.search(body) and any(
+        marker in low for marker in _FRONT_MATTER_CONTENTS_VOCAB
+    ):
+        return True
+    return False
+
+
+def _collision_span_key(row: "dict") -> str:
+    """The content-identity key for the identical-span collision screen: the stamped
+    ``fetched_blob_sha`` when present (a raw-blob / span fingerprint), else the raw
+    ``direct_quote`` text. Empty when neither is present (an empty-keyed row can never
+    collide). Pure."""
+    if not isinstance(row, dict):
+        return ""
+    sha = str(row.get("fetched_blob_sha") or "").strip()
+    if sha:
+        return f"sha:{sha}"
+    quote = str(row.get("direct_quote") or "").strip()
+    return f"q:{quote}" if quote else ""
+
+
+def _collision_work_id(row: "dict") -> str:
+    """The cited-WORK identity for the collision screen: the DOI (normalized) when
+    present, else the source URL. Two rows with the SAME work-id sharing an identical
+    span are legitimate duplicates (CONSOLIDATE, step E) — NOT a container collision.
+    Two rows with DIFFERENT work-ids sharing an identical span ARE a multi-work
+    container (one blob cited under many DOIs = the 31x-dgpu false corroboration)."""
+    if not isinstance(row, dict):
+        return ""
+    doi = str(row.get("doi") or "").strip().lower()
+    if doi:
+        return f"doi:{doi}"
+    url = str(row.get("source_url") or row.get("url") or "").strip().lower()
+    return f"url:{url}"
+
+
+def identical_span_collision(rows: "list[dict]") -> "set[str]":
+    """I-deepfix-004 D — pool-level content-identity collision detector.
+
+    Returns the set of ``evidence_id`` values whose stored span is shared, VERBATIM, by
+    at least two rows citing DIFFERENT cited works (different DOI/URL) — the signature of
+    a single multi-article CONTAINER blob (e.g. a whole journal issue) laundered into N
+    distinct citations. That is the 31x-dgpu false-corroboration class: 31 DOIs, one
+    identical masthead blob.
+
+    NOT flagged: two rows with an identical span AND the SAME cited work (a legitimate
+    duplicate → CONSOLIDATE in step E, never a container). A unique span → never flagged.
+
+    Pure; DETECTS only. The caller stamps ``wrong_content_span`` on the flagged rows so
+    they route through re-extraction / disclosure — NEVER deletes a source (§-1.3)."""
+    from collections import defaultdict
+
+    by_span: "dict[str, list[tuple[str, str]]]" = defaultdict(list)
+    for row in rows or []:
+        if not isinstance(row, dict):
+            continue
+        span_key = _collision_span_key(row)
+        if not span_key:
+            continue
+        eid = str(row.get("evidence_id") or "")
+        work_id = _collision_work_id(row)
+        by_span[span_key].append((eid, work_id))
+
+    flagged: "set[str]" = set()
+    for members in by_span.values():
+        if len(members) < 2:
+            continue  # a unique span cannot be a container collision
+        distinct_works = {work_id for _eid, work_id in members if work_id}
+        if len(distinct_works) >= 2:
+            # ≥2 DIFFERENT cited works share ONE identical span ⇒ multi-work container.
+            for eid, _work_id in members:
+                if eid:
+                    flagged.add(eid)
+    return flagged
diff --git a/src/tools/access_bypass.py b/src/tools/access_bypass.py
index cab0dc39..5c43ac3d 100644
--- a/src/tools/access_bypass.py
+++ b/src/tools/access_bypass.py
@@ -2941,6 +2941,93 @@ def strip_pdf_frontmatter(text: "Optional[str]") -> str:
     return body
 
 
+# ---------------------------------------------------------------------------
+# I-deepfix-004 STEP B — cited-work slice extraction for PDFs.
+#
+# Root cause (Fable 5, 2026-07-09): the pipeline defines a citable span by
+# POSITION ("first N chars of whatever bytes came back") and never checks
+# IDENTITY ("is this text the article the citation names?"). DOI->PDF
+# redirects never reach the PDF extractor (the branch keys on
+# url.endswith('.pdf')), so a `doi.org/...` that redirects to a WHOLE-issue
+# combined PDF is scraped as one blob and the `#page=N` anchor is thrown away.
+# STEP B resolves the redirect, captures the page anchor, and slices the cited
+# work out of the combined PDF.
+#
+# All of STEP B is gated by PG_PDF_CITED_WORK_SLICE (default ON; OFF =>
+# byte-identical). Faithfulness engine (strict_verify / provenance / NLI /
+# 4-role) is UNTOUCHED — this only changes WHICH verbatim span is extracted,
+# never how a claim is verified against it. No fixed page-count window and no
+# per-source cap: the end page comes from real metadata only, and slicing
+# accumulates under the SAME existing char budget the caller already applies.
+# ---------------------------------------------------------------------------
+
+# The caller (fetch_with_bypass PDF branch) already caps PDF content at 50 000
+# chars (`content=pdf_text[:50000]`). The cited-work slice accumulates forward
+# under that SAME budget when no explicit end page is known — it is NOT a new
+# page-count window, just the existing char ceiling surfaced as a named
+# constant so the accumulation loop stops at parity with the caller cap.
+_PDF_EXTRACT_CHAR_CAP = 50000
+
+
+def pdf_cited_work_slice_enabled() -> bool:
+    """True iff STEP B (cited-work PDF slice extraction) is enabled.
+
+    Gated by PG_PDF_CITED_WORK_SLICE. DEFAULT ON — enabled by
+    '1'/'true'/'yes'/'on' (case-insensitive) AND by unset/empty (default).
+    Only an explicit falsey value ('0'/'false'/'no'/'off') turns it OFF, in
+    which case every STEP-B call site is byte-identical to the prior behaviour
+    (no redirect resolution, no page slice, no extra metadata keys)."""
+    raw = os.getenv("PG_PDF_CITED_WORK_SLICE")
+    if raw is None or not raw.strip():
+        return True
+    return raw.strip().lower() in ("1", "true", "yes", "on")
+
+
+def _parse_pdf_page_fragment(text: "Optional[str]") -> "Optional[int]":
+    """Parse a 1-indexed PDF page anchor from a `#page=N` fragment.
+
+    Accepts a raw fragment, a full URL, or a Location-header value. Prefers the
+    canonical PDF open-parameter form `#page=N`; falls back to a `?page=` /
+    `&page=` query form. Returns the integer N (>=1) or None. Pure / no
+    network — a malformed value simply yields None (fail-open: no anchor)."""
+    if not text:
+        return None
+    m = re.search(r"#page=(\d+)", text, re.IGNORECASE)
+    if not m:
+        m = re.search(r"[?&]page=(\d+)", text, re.IGNORECASE)
+    if not m:
+        return None
+    try:
+        n = int(m.group(1))
+    except (TypeError, ValueError):
+        return None
+    return n if n >= 1 else None
+
+
+def _parse_doi_page_range(doi: "Optional[str]") -> "tuple[Optional[int], Optional[int]]":
+    """Parse a (start_page, end_page) range from a DOI whose suffix encodes the
+    article's page span, e.g. `10.34142/...-2026-9-2-203-210` => (203, 210).
+
+    Matches the LAST two hyphen-separated numeric groups at the end of the DOI
+    (`-<start>-<end>`). Returns (None, None) when the DOI does not end that way
+    or when end < start (an inconsistent range is discarded, not trusted). Pure
+    / deterministic — no network. Fail-open: any parse miss yields (None, None)
+    so the caller simply carries no page anchor from the DOI suffix."""
+    if not doi:
+        return (None, None)
+    m = re.search(r"-(\d+)-(\d+)\s*$", doi)
+    if not m:
+        return (None, None)
+    try:
+        start = int(m.group(1))
+        end = int(m.group(2))
+    except (TypeError, ValueError):
+        return (None, None)
+    if start < 1 or end < start:
+        return (None, None)
+    return (start, end)
+
+
 # M-23c: Structural markers for content quality scoring.
 # Presence of academic-paper markers indicates full article body
 # (vs paywall stub or landing page).
@@ -3739,13 +3826,44 @@ class AccessBypass:
                                           "source": "pmc_bioc_oa_via_unpaywall"},
                             )
 
+        # I-deepfix-004 STEP B1 (gated by PG_PDF_CITED_WORK_SLICE, default ON;
+        # OFF => this block is skipped and the url/anchors are untouched =>
+        # byte-identical). A `doi.org` / `dx.doi.org` citation URL currently
+        # never reaches the PDF branch below (it fails `.endswith('.pdf')`), so a
+        # DOI that redirects to a WHOLE-issue combined PDF is scraped as one blob
+        # and the `#page=N` cited-work anchor is thrown away. Resolve the
+        # redirect: if the FINAL target is a PDF, swap `url` to it so the branch
+        # below fires, and carry the parsed page anchor/range into the slice.
+        _slice_on = pdf_cited_work_slice_enabled()
+        _pdf_page_anchor: "Optional[int]" = None
+        _pdf_page_end: "Optional[int]" = None
+        if _slice_on and "doi.org/" in url.lower():
+            _doi_target = await self._resolve_doi_pdf_target(url)
+            if _doi_target and _doi_target.get("is_pdf"):
+                logger.info(
+                    "[B1-DOI] doi->pdf resolved %s -> %s (page_anchor=%s page_end=%s)",
+                    url[:50], str(_doi_target.get("final_url"))[:70],
+                    _doi_target.get("page_anchor"), _doi_target.get("page_end"),
+                )
+                url = _doi_target["final_url"]
+                _pdf_page_anchor = _doi_target.get("page_anchor")
+                _pdf_page_end = _doi_target.get("page_end")
+
         # FIX-CITE-3/GAP4: Detect PDF URLs and extract text directly.
         # Academic open-access PDFs (from S2 openAccessPdf) need PDF parsing,
         # not HTML scraping. This gives the analyzer full paper content with
         # forest plots, I² values, GRADE ratings — the detail Gemini captures.
         if url.lower().endswith(".pdf") or "/pdf/" in url.lower():
             try:
-                pdf_text = await self._extract_pdf_text(url)
+                # B4: collect blob identity only when STEP B is ON (out_meta
+                # None when OFF => no sha computed, metadata byte-identical).
+                _pdf_out_meta: "Optional[Dict[str, Any]]" = {} if _slice_on else None
+                pdf_text = await self._extract_pdf_text(
+                    url,
+                    page_anchor=_pdf_page_anchor,
+                    page_end=_pdf_page_end,
+                    out_meta=_pdf_out_meta,
+                )
                 if pdf_text and len(pdf_text) > 500:
                     # ev_461: strip a leading journal-masthead block (running-head /
                     # author-affiliation list / submission-date line) from the
@@ -3757,6 +3875,19 @@ class AccessBypass:
                         "[ACCESS] FIX-GAP4: PDF text extracted for %s (%d chars)",
                         url[:60], len(pdf_text),
                     )
+                    # B4: stamp blob identity onto the evidence row's metadata so
+                    # downstream content-identity consolidation (STEP E) can fold
+                    # combined-issue PDFs that share one blob but carry many DOIs.
+                    # Only when STEP B is ON (out_meta populated) => flag-OFF keeps
+                    # metadata byte-identical to the prior {"content_type": ...}.
+                    _pdf_metadata: "Dict[str, Any]" = {"content_type": "application/pdf"}
+                    if _slice_on and _pdf_out_meta:
+                        _blob_sha = _pdf_out_meta.get("fetched_blob_sha")
+                        _src_url = _pdf_out_meta.get("content_source_url")
+                        if _blob_sha:
+                            _pdf_metadata["fetched_blob_sha"] = _blob_sha
+                        if _src_url:
+                            _pdf_metadata["content_source_url"] = _src_url
                     return AccessResult(
                         url=url,
                         content=pdf_text[:50000],  # Cap at 50K chars
@@ -3769,7 +3900,7 @@ class AccessBypass:
                         access_method="pdf_extract",
                         legal_alternative=None,
                         success=True,
-                        metadata={"content_type": "application/pdf"},
+                        metadata=_pdf_metadata,
                     )
             except Exception as pdf_exc:
                 logger.warning(
@@ -4483,11 +4614,104 @@ class AccessBypass:
             # concurrent Crawl4AI calls race: one call's restore undoes
             # another call's reconfigure. utf-8 is strictly superior.
 
-    async def _extract_pdf_text(self, url: str) -> str:
+    async def _resolve_doi_pdf_target(
+        self, url: str
+    ) -> "Optional[Dict[str, Any]]":
+        """I-deepfix-004 STEP B1 — resolve a doi.org / dx.doi.org URL to its
+        FINAL target and, when that target is a PDF, capture the cited-work page
+        anchor.
+
+        Does a lightweight aiohttp GET (``allow_redirects=True``) and inspects
+        ONLY the response headers + redirect chain — it never reads the body
+        (the real byte fetch stays in :meth:`_extract_pdf_text`). Captures:
+
+          * the FINAL url (``resp.url`` after redirects) so the existing
+            ``.pdf`` / ``/pdf/`` PDF branch fires on the resolved publisher URL;
+          * a 1-indexed page anchor ``N`` from a ``#page=N`` fragment found on
+            any redirect-chain ``Location`` header, on ``resp.url``, or on the
+            original url. The Location headers are checked FIRST because
+            ``resp.url`` frequently drops the fragment across a redirect;
+          * a page range ``(start, end)`` parsed from a DOI suffix such as
+            ``...-2026-9-2-203-210`` (=> pages 203-210) when the DOI ends
+            ``-<start>-<end>``.
+
+        Returns ``{"final_url", "is_pdf", "page_anchor", "page_end"}`` or
+        ``None`` on any error (fail-open: the caller then leaves the url
+        untouched and the pre-existing fetch path runs unchanged).
+
+        Faithfulness-neutral: this only decides WHICH url + page span is handed
+        to the extractor; no faithfulness gate is touched.
+        """
+        import aiohttp
+
+        try:
+            timeout = aiohttp.ClientTimeout(total=30)
+            async with aiohttp.ClientSession(timeout=timeout) as session:
+                async with session.get(url, allow_redirects=True) as resp:
+                    final_url = str(resp.url)
+                    content_type = (resp.headers.get("Content-Type") or "").lower()
+                    # Redirect-chain Location headers are the authoritative
+                    # fragment source (resp.url can drop `#page=N`); check them
+                    # first, then the final url, then the original url.
+                    frag_sources: list[str] = []
+                    for _hist in resp.history:
+                        _loc = _hist.headers.get("Location")
+                        if _loc:
+                            frag_sources.append(_loc)
+                    frag_sources.append(final_url)
+                    frag_sources.append(url)
+        except Exception as _exc:  # noqa: BLE001 — resolver must never break a fetch
+            logger.debug(
+                "[B1-DOI] doi->pdf resolve failed for %s: %s",
+                url[:60], str(_exc)[:100],
+            )
+            return None
+
+        final_path = urlparse(final_url).path.lower()
+        is_pdf = final_path.endswith(".pdf") or "application/pdf" in content_type
+
+        page_anchor: "Optional[int]" = None
+        for _s in frag_sources:
+            _n = _parse_pdf_page_fragment(_s)
+            if _n is not None:
+                page_anchor = _n
+                break
+
+        doi = self._extract_doi(url) or self._extract_doi(final_url)
+        doi_start, doi_end = _parse_doi_page_range(doi) if doi else (None, None)
+        # Fragment anchor wins; fall back to the DOI-suffix start page.
+        if page_anchor is None:
+            page_anchor = doi_start
+        page_end = doi_end
+
+        return {
+            "final_url": final_url,
+            "is_pdf": bool(is_pdf),
+            "page_anchor": page_anchor,
+            "page_end": page_end,
+        }
+
+    async def _extract_pdf_text(
+        self,
+        url: str,
+        page_anchor: "Optional[int]" = None,
+        page_end: "Optional[int]" = None,
+        out_meta: "Optional[Dict[str, Any]]" = None,
+    ) -> str:
         """FIX-CITE-3/GAP4: Download and extract text from academic PDF.
 
         Uses PyMuPDF (fitz) for extraction. Falls back to basic text
         extraction if PyMuPDF is not available.
+
+        I-deepfix-004 STEP B (gated by PG_PDF_CITED_WORK_SLICE, default ON;
+        OFF => byte-identical because all three new params stay None):
+          * ``page_anchor`` / ``page_end`` — thread a 1-indexed cited-work page
+            slice down to :meth:`_extract_pdf_text_from_bytes_impl` (B2);
+          * ``out_meta`` — when a dict is supplied, stamp ``fetched_blob_sha``
+            (sha256 of the fetched PDF bytes) + ``content_source_url`` (the
+            final resolved url that produced those bytes) so the caller can put
+            them on the evidence row's ``AccessResult.metadata`` (B4). When
+            ``out_meta`` is None nothing is computed and the path is unchanged.
         """
         import aiohttp
 
@@ -4499,10 +4723,33 @@ class AccessBypass:
                 pdf_bytes = await resp.read()
                 if len(pdf_bytes) < 1000:
                     return ""
+                _final_source_url = str(resp.url)
+
+        # B4: stamp blob identity for the caller (only when an out_meta dict is
+        # supplied — i.e. the STEP-B branch with the flag ON). Best-effort:
+        # a hashing error must never break extraction.
+        if out_meta is not None:
+            try:
+                import hashlib
+                out_meta["fetched_blob_sha"] = hashlib.sha256(pdf_bytes).hexdigest()
+                out_meta["content_source_url"] = _final_source_url
+            except Exception as _sha_exc:  # noqa: BLE001 — stamp is best-effort
+                logger.debug(
+                    "[B4-BLOB] blob sha stamp skipped for %s: %s",
+                    url[:60], str(_sha_exc)[:80],
+                )
 
-        return await self._extract_pdf_text_from_bytes(url, pdf_bytes)
+        return await self._extract_pdf_text_from_bytes(
+            url, pdf_bytes, page_anchor=page_anchor, page_end=page_end
+        )
 
-    async def _extract_pdf_text_from_bytes(self, url: str, pdf_bytes: bytes) -> str:
+    async def _extract_pdf_text_from_bytes(
+        self,
+        url: str,
+        pdf_bytes: bytes,
+        page_anchor: "Optional[int]" = None,
+        page_end: "Optional[int]" = None,
+    ) -> str:
         """I-deepfix-001 B1 (wave-2, 2026-07-08) — extraction-time FURNITURE screen.
 
         Delegates to the UNCHANGED extractor selector
@@ -4518,8 +4765,22 @@ class AccessBypass:
         Both flags default OFF => this returns the impl output unchanged =>
         BYTE-IDENTICAL. Faithfulness engine untouched — only WHICH extractor's
         verbatim text is returned can change.
+
+        I-deepfix-004 STEP B2: ``page_anchor`` / ``page_end`` (default None =>
+        byte-identical) thread the cited-work page slice to the impl's fitz
+        path. The furniture screen below is UNCHANGED and runs on whatever body
+        (whole-doc or sliced) the impl returns.
         """
-        body = await self._extract_pdf_text_from_bytes_impl(url, pdf_bytes)
+        # Byte-identical when no slice is requested: call the impl EXACTLY as
+        # before (positional only) so pre-existing callers / stubs that use the
+        # old 2-arg signature are unaffected. Only thread the page-slice kwargs
+        # when an anchor was actually resolved (STEP B1).
+        if page_anchor is None and page_end is None:
+            body = await self._extract_pdf_text_from_bytes_impl(url, pdf_bytes)
+        else:
+            body = await self._extract_pdf_text_from_bytes_impl(
+                url, pdf_bytes, page_anchor=page_anchor, page_end=page_end
+            )
         try:
             from src.polaris_graph.retrieval import shell_detector as _sd
         except Exception:  # noqa: BLE001 — detector import must never break extraction
@@ -4632,7 +4893,13 @@ class AccessBypass:
                 return _cand
         return ""
 
-    async def _extract_pdf_text_from_bytes_impl(self, url: str, pdf_bytes: bytes) -> str:
+    async def _extract_pdf_text_from_bytes_impl(
+        self,
+        url: str,
+        pdf_bytes: bytes,
+        page_anchor: "Optional[int]" = None,
+        page_end: "Optional[int]" = None,
+    ) -> str:
         """Extract text from already-fetched PDF bytes (offline-testable).
 
         Split out of :meth:`_extract_pdf_text` (which owns the network fetch)
@@ -4642,6 +4909,18 @@ class AccessBypass:
         Faithfulness-neutral: this only decides WHICH extractor produces the
         verbatim text that strict_verify later grounds — no faithfulness gate
         (strict_verify / NLI / 4-role / provenance) is touched.
+
+        I-deepfix-004 STEP B2 (gated upstream by PG_PDF_CITED_WORK_SLICE;
+        ``page_anchor`` default None => byte-identical): when ``page_anchor`` is
+        set on a multi-page doc, the PyMuPDF (fitz) fallback path below extracts
+        the cited work as a page SLICE starting at page ``page_anchor`` (1-indexed
+        -> ``doc[page_anchor-1]``) forward — stopping at ``page_end`` when known,
+        else accumulating under the EXISTING char budget (the caller's 50 000-char
+        cap, surfaced as ``_PDF_EXTRACT_CHAR_CAP``; no new page-count window). If
+        ``page_anchor`` exceeds the page count the whole-doc extraction runs
+        (fail-open). ``strip_pdf_frontmatter`` still runs on the slice (in the
+        caller's PDF branch). The docling / mineru paths are unchanged — for the
+        big combined-issue PDFs this targets they are OOM-gated to this fitz path.
         """
         import tempfile
 
@@ -4798,8 +5077,38 @@ class AccessBypass:
 
             doc = fitz.open(tmp_path)
             pages_text = []
-            for page in doc:
-                pages_text.append(page.get_text())
+            _page_count = doc.page_count
+            # I-deepfix-004 STEP B2: cited-work page slice. Fires ONLY when a
+            # page anchor was resolved (STEP B1) AND the doc is multi-page AND
+            # the anchor is within range; otherwise the whole-doc extraction
+            # below runs byte-identically (also the fail-open path when
+            # page_anchor > page_count).
+            if (
+                page_anchor is not None
+                and _page_count > 1
+                and 1 <= page_anchor <= _page_count
+            ):
+                start_idx = page_anchor - 1  # 1-indexed anchor -> 0-indexed page
+                _end_valid = page_end is not None and page_end >= page_anchor
+                # page_end is 1-indexed INCLUSIVE; clamp to the real page count.
+                stop_idx = min(page_end, _page_count) if _end_valid else _page_count
+                _acc_chars = 0
+                for _pi in range(start_idx, stop_idx):
+                    _ptext = doc[_pi].get_text()
+                    pages_text.append(_ptext)
+                    _acc_chars += len(_ptext)
+                    # No explicit end page: accumulate forward only until the
+                    # existing char budget (NOT a new page-count window).
+                    if not _end_valid and _acc_chars >= _PDF_EXTRACT_CHAR_CAP:
+                        break
+                logger.info(
+                    "[B2-SLICE] cited-work page slice pages %d..%d of %d (%d chars) url=%s",
+                    page_anchor, min(stop_idx, _page_count), _page_count,
+                    _acc_chars, url[:60],
+                )
+            else:
+                for page in doc:
+                    pages_text.append(page.get_text())
             doc.close()
 
             import os as _os
diff --git a/tests/fixtures/i_deepfix_004/real_masthead_spans.json b/tests/fixtures/i_deepfix_004/real_masthead_spans.json
new file mode 100644
index 00000000..51cc0c80
--- /dev/null
+++ b/tests/fixtures/i_deepfix_004/real_masthead_spans.json
@@ -0,0 +1,76 @@
+{
+ "_README": "I-deepfix-004 PR-1 offline test fixture. REAL captured spans copied verbatim from banked corpus_snapshot.json (gitignored outputs/.codex) so the offline test is self-contained + CI-runnable. Provenance per span in _provenance (LAW II auditable).",
+ "spans": {
+  "toc_dot_leader_masthead": "Industrial IoT Artificial Intelligence Framework 2022-02-22 Authors Wael William Diab, Alex Ferraro, Brad Klenz, Shi-Wan Lin, Edy Liongosari, Wadih Elie Tannous, Bassam Zarkout. Industrial IoT Artificial Intelligence Framework IIC:PUB:IIAIF:V0.10:ID:2022 ii CONTENTS 1 Industrial Artificial Intelligence .......................................................................................... 6 1.1 Industrial Internet of Things ................................................................................................. 6 1.2 Industrial Artificial Intelligence ............................................................................................ 6 1.3 Architecture Viewpoints ...................................................................................................... 7 2 Business Viewpoint ........................................................................................................... 8 2.1 Uncover Valuable Insights From Data Intensive Environments .............................................. 9 2.2 Enable Digital Transformation .............................................................................................. 9 2.3 Agent for Future-Proofing the Organization ........................................................................ 11 2.4 AI Adoption Readiness ....................................................................................................... 11 3 Usage Viewpoint ......................................................\n\n[...]\n\nIndustrial IoT Artificial Intelligence Framework 2022-02-22 Authors Wael William Diab, Alex Ferraro, Brad Klenz, Shi-Wan Lin, Edy Liongosari, Wadih Elie Tannous, Bassam Zarkout. Industrial IoT Artificial Intelligence Framework IIC:PUB:IIAIF:V0.10:ID:2022 ii CONTENTS 1 Industrial Artificial Intelligence .......................................................................................... 6 1.1 Industrial Internet of Things ................................................................................................. 6 1.2 Industrial Artificial Intelligence ............................................................................................ 6 1.3 Architecture Viewpoints ...................................................................................................... 7 2 Business Viewpoint ........................................................................................................... 8 2.1 Uncover Valuable Insights From Data Intensive Environments .............................................. 9 2.2 Enable Digital Transformation .............................................................................................. 9 2.3 Agent for Future-Proofing the Organization ........................................................................ 11 2.4 AI Adoption Readiness ....................................................................................................... 11 3 Usage Viewpoint ............................................................................................................. 12 3.1 Industrial AI Market........................................................................................................... 12 3.2 Usage Considerations ........................................................................................................ 13 3.3 Trustworthiness ................................................................................................................ 15 3.3.1 Security ............................................................................................................................. 16 3.3.2 Privacy ............................................................................................................................... 19 3.3.3 Confidentiality ................................................................................................................... 20 3.3.4 Explainability ..................................................................................................................... 21 3.3.5 Controllability ................................................................................................................... 21 3.4 Ethical and Societal Concerns ............................................................................................. 22 3.4.1 Ethics ................................................................................................................................. 22 3.4.2 Bias .................................................................................................................................... 23 3.4.3 Safety ................................................................................................................................ 24 3.5 Impact on Labor Force ....................................................................................................... 25 3.6 Regional and Industry-Specific Considerations .................................................................... 27 3.7 AI as a Force for Good ........................................................................................................ 27 4 Functional Viewpoint ...................................................................................................... 28 4.1 Architecture Objectives and Constraints ............................................................................. 28 4.2 Data Concerns ................................................................................................................... 29 4.3 Learning Techniques .......................................................................................................... 30 4.4 General Industrial AI Functional Architecture ..................................................................... 32 4.5 System of Systems Issues ................................................................................................... 34 4.6 Application Horizon of Industrial AI .................................................................................... 35 5 Implementation Viewpoint ............................................................................................. 36 5.1 Implementation Guidance ................................................................................................. 36 5.2 Implementation Considerations ......................................................................................... 37 5.2.1 Scope ................................................................................................................................. 37 5.2.2 Response Time .................................................................................................................. 37 5.2.3 Reliability .......................................................................................................................... 38 5.2.4 Bandwidth and Latency .................................................................................................... 38 5.2.5 Capacity ............................................................................................................................. 39 5.2.6 Security ............................................................................................................................. 39 5.2.7 Data Properties ................................................................................................................. 39 Industrial IoT Artificial Intelligence Framework IIC:PUB:IIAIF:V0.10:ID:2022 iii 5.2.8 Temporal Data Correlation ............................................................................................... 40 5.2.9 Interoperability ................................................................................................................. 40 5.2.10 Running Systems In Parallel .............................................................................................. 40 5.2.11 Dealing With Technical Debt............................................................................................. 41 5.2.12 Portability and Reusability of AI Systems ......................................................................... 41 6 The Future of the Industrial AI ......................................................................................... 42 6.1 Far-Reaching Benefits of AI Despite the Risks ..................................................................... 42 6.2 Convergence with Other Transformative Technologies ....................................................... 42 6.3 Standards Ecosystem ......................................................................................................... 44 6.3.1 Enabling intelligent insights .............................................................................................. 45 6.3.2 Ecosystem approach ......................................................................................................... 46 6.3.3 Program of work and role in enabling DX across industries ............................................. 46 6.3.4 Summary ........................................................................................................................... 48 6.4 Final Thoughts and Takeaways ........................................................................................... 48 Annex A Artificial Intelligence Background .................................................................. 50 A.1 Brief \n\n[...]\n\n........................................................................................................... 50 A.2 Why Now? ........................................................................................................................ 51 A.2.1 Cheap and Powerful Compute Infrastructure .................................................................. 51 A.2.2 Availability of Large Amounts of Data .............................................................................. 52 A.2.3 Improvements in Algorithms ............................................................................................ 52 Annex B Exemplary Use Cases of AI in Industry ........................................................... 52 B.1 Manufacturing\n\n[...]\n\nFuture of the Workforce. Source: McKinsey. ......................... 26 Figure 4-1. Industrial AI Framework Functional Viewpoint and Its Stakeholders. Source: IIC. .................. 28 Industrial IoT Artificial Intelligence Framework IIC:PUB:IIAIF:V0.10:ID:2022 iv Figure 4-2. AI/Machine Learning Model Process. ....................................................................................... 29 Figure 4-3. Data Processing for AI Modeling. .......................................................\n\n[...]\n\n14 Table 3-2. Securing Industrial AI Across the IIoT Security Function Building Blocks. ................................. 18 Table 3-3. Core Principles of the AI Ethics Framework. Source: Department of Industry, Australia. ........ 23 IIC:PUB:IIAIF:V0.10:ID:2022 5 Industrial Artificial Intelligence (AI) is the use of AI in applications in industry1 and a major contributor to value creation in the fourth industrial revolution. AI is being embedded in a wide range of applications, helping ",
+  "issn_editorial_masthead": "Loading... # OPEN ACCESS - PUBLICATIONS a b c d e f g h i j k l m n o p q r s t u v w x y z #### Advances in Computer Sciences ISSN: 2517-5718 # [View Journal](https://www.boffinaccess.com/advances-in-computer-sciences) ### [Editorial Board](https://www.boffinaccess.com/advances-in-computer-sciences/editorial-board) ### [Current Issue](https://www.boffinaccess.com/advances-in-computer-sciences/current-issue) ### [Submit Manuscript](https://www.boffinaccess.com/advances-in-computer-sciences/submit-manuscript) #### Agronomy and Agricultural Techniques # [View Journal](https://www.boffinaccess.com/agronomy-and-agricultural-techniques) ### [Editorial Board](https://www.boffinaccess.com/agronomy-and-agricultural-techniques/editorial-board) ### [Current Issue](https://www.boffinaccess.com/agronomy-and-agricultural-techniques/current-issue) ### [Submit Manuscript](https://www.boffinaccess.com/agronomy-and-agricultural-techniques/submit-manuscript) #### Artificial Intelligence Vanguard Journal # [View Journal](https://www.boffinaccess.com/artificial-intelligence-vanguard) ### [Editorial Board](https://www.boffinaccess.com/artificial-intelligence-vanguard/editorial-board) ### [Current Issue](https://www.boffinaccess.com/artificial-intelligence-vanguard/current-issue) ### [Submit Manuscript](https://www.boffinaccess.com/artificial-intelligence-vanguard/submit-manuscript) #### Biomedical Research and Reviews ISSN: 2631-3944 # [View Journal](https://www.boffinaccess.com/biomedical-resear",
+  "article_head_false": "Journal of \u2014Spring 2019\u2014Pages 3\u201330 \n\n# The implications of technological change for employment and wages are a source of controversy. Some see the ongoing process of automation\u2014as exemplified by computer numerical control machinery, industrial robots, and artificial intelligence\u2014as the harbinger of widespread joblessness. Others reason that current automation, like previous waves of technologies, will ultimately increase labor demand, and thus employment and wages. This paper presents a task-based framework, building on Acemoglu and Restrepo (2018a, 2018b) as well as Acemoglu and Autor (2011), Autor, Levy, and Murnane (2003), and Zeira (1998), for thinking through the implications of tech-nology for labor demand and productivity. Production requires tasks, which are allocated to capital or labor. New technologies not only increase the productivity of capital and labor at tasks they currently perform, but also impact the allocation of tasks to these factors of production\u2014what we call the task content of production . Shifts in the task content of production can have major effects for how labor demand changes as well as for productivity. Automation corresponds to the development and adoption of new technolo-gies that enable capital to be substituted for labor in a range of tasks. Automation changes the task content of production adversely for labor because of a displacement effect \u2014as capital takes over tasks previously performed by labor. The displacement \n\n# Automation and New Tasks: How Technology Displaces and Reinstates Labor \n\n> \u25a0\n\nDaron Acemoglu is Elizabeth and James Killian Professor of Economics, Massachusetts Institute of Technology, Cambridge, Massachusetts. Pascual Restrepo is Assistant Professor of Economics, Boston University, Boston, Massachusetts. Their emails are daron@mit.edu and pascual@bu.edu. \n\n> \u2020For supplementary materials such as appendices, datasets, and author disclosure statements, see the article page at https://doi.org/10.1257/jep.33.2.3 doi=10.1257/jep.33.2.3\n\n# Daron Acemoglu and Pascual Restrepo 4 Journal of Economic Perspectives \n\neffect implies that automation reduces the labor share of value added. Historical examples of automation are aplenty. Many early innovations of the Industrial Revo-lution automated tasks performed by artisans in spinning and weaving (Mantoux 1928), which led to widespread displacement, triggering the Luddite riots (Mokyr 1990). The mechanization of agriculture, which picked up speed with horse-powered reapers, harvesters, and plows in the second half of the 19th century and with trac-tors and combine harvesters in the 20th century, displaced agricultural workers in large numbers (Rasmussen 1982; Olmstead and Rhode 2001). Today too we are witnessing a period of rapid automation. The jobs of production workers are being disrupted with the rise of industrial robots and other automated machinery (Graetz and Michaels 2018; Acemoglu and Restrepo 2018b), while white-collar workers in accounting, sales, logistics, trading, and some managerial occupations are seeing some of the tasks they used to perform being replaced by specialized software and artificial intelligence. By allowing a more flexible allocation of tasks to factors, automation technology also increases productivity, and via this channel, which we call the productivity effect ,it contributes to the demand for labor in non-automated tasks. The net impact of automation on labor demand thus depends on how the displacement and produc-tivity effects weigh against each other. The history of technology is not only about the displacement of human labor by automation technologies. If it were, we would be confined to a shrinking set of old tasks and jobs, with a steadily declining labor share in national income. Instead, the displacement effect of automation has been counterbalanced by tech-nologies that create new tasks in which labor has a comparative advantage. Such new tasks generate not only a positive productivity effect, but also a reinstatement effect \u2014they reinstate labor into a broader range of tasks and thus change the task content of production in favor of labor. 1 The reinstatement effect is the polar opposite of the displacement effect and directly increases the labor share as well as labor demand. History is also replete with examples of the creation of new tasks and the rein-statement effect. In the 19th century, as automation of some tasks was ongoing, other technological developments generated employment opportunities in new occu-pations. These included jobs for line workers, engineers, machinists, repairmen, conductors, managers, and financiers (Chandler 1977; Mokyr 1990). New occu-pations and jobs in new industries also played a pivotal role in generating labor demand during the decades of rapid agricultural mechanization in the United States, especially in factories (Rasmussen 1982; Olmsted and Rhode 2001) and in clerical occupations, both in services and manufacturing (Goldin and Katz 2008; Michaels 2007). Although software and computers have replaced labor in some white-collar tasks, they have simultaneously created many new tasks. These include tasks related 1 There are also new tasks in which capital has a comparative advantage (for example, automated detec-tion). Throughout our focus is on \u201clabor-intensive\u201d new tasks, and for brevity, we will simply refer to these as \u201cnew tasks.\u201d Daron Acemoglu and Pascual Restrepo 5\n\nto programming, design, and maintenance of high tech equipment, such as software and app development, database design and analysis, and computer-security-related tasks, as well as tasks related to more specialized functions in existing occupations, including administrative assistants, analysts for loan applications, and medical equip-ment technicians (Lin 2011). In Acemoglu and Restrepo (2018a, using data from Lin 2011), we show that about half of employment growth over 1980\u20132015 took place in occupations in which job titles or tasks performed by workers changed. Our conceptual framework offers several lessons. First, the presumption that all \n\ntechnologies increase (aggregate) labor demand simply because they raise produc-tivity is wrong. Some automation technologies may in fact reduce labor demand because they bring sizable displacement effects but modest productivity gains (especially when substituted workers were cheap to begin with and the automated technology is only marginally better than them). Second, because of the displacement effect, we should not expect automation to create wage increases commensurate with productivity growth. In fact, as we noted already, automation by itself always reduces the labor share in industry value added and tends to reduce the overall labor share in the economy (meaning that it leads to slower wage growth than productivity growth). The reason why we have had rapid wage growth and stable labor shares in the past is a consequence of other technological changes that generated new tasks for labor and counterbalanced the effects of automation on the task content of production. Some technologies displaced labor from automated tasks while others reinstated labor into new tasks. On net, labor retained a key role in production. By the same token, our framework suggests that the future of work depends on the mixture of new technolo-gies and how these change the task content of production. In the second part of the paper, we use our framework to study the evolution of labor demand in the United States since World War II and explain how industry data can be used to infer the behavior of the task content of production and the displacement and reinstatement effects. We start by showing that there has been a slowdown in the growth of labor demand over the last three decades and an almost complete stagnation over the last two. We establish this by studying the evolution of the economy-wide wage bill, which combines information on average wages and total employment and is thus informative about changes in overall labor demand. We then use industry data to decompose changes in the economy-wide wage bill into productivity, composition and substitution effects, and changes in the task content of production. All technologies create productivity effects that contribute to labor demand. The composition effect arises from the reallocation of activity across sectors with different labor intensities. The substitution effect captures the substitution between labor- and capital-intensive tasks within an industry in response to a change in task prices (for instance, caused by factor-augmenting tech-nologies making labor or capital more productive at tasks they currently perform). We estimate changes in the task content of production from residual changes in industry-level labor shares (beyond what can be explained by substitution effects). We further decompose changes in the task content of production into displace-ment effects caused by automation and reinstatement effects driven by new tasks. 6 Journal of Economic Perspectives \n\nWe provide external support for this decomposition by relating estimated changes in the task content of production to a battery of measures of automation and intro-duction of new tasks across sectors. Our decomposition suggests that the evolution of the US wage bill, especially over the last 20 years, cannot be understood without factoring in changes in the task content of production. In particular, we find that the sharp slowdown of US wage bill growth over the last three decades is a consequence of weaker-than-usual productivity growth and significant shifts in the task content of production against labor. By decomposing the change in the task content of production, we estimate stronger displacement effects and considerably weaker reinstatement effects during the last 30 years than the decades before. These patterns hint at an acceleration of automation and a deceleration in the creation of new tasks. They also raise the question of why productivity growth has been so anemic while auto-mation has accelerated during recent years. We use our framework to shed light on this critical question. An online Appendix available with this paper at the journal website contains a more detailed exposition of our framework, proofs, additional empirical results, and details on the construction of our data. \n\n## Conceptual Framework \n\nProduction requires the completion of a range of tasks. The production of a shirt, for example, starts with a design, then requires the completion of a variety of production tasks, such as the extraction of fibers, spinning them to produce yarn, weaving, knitting, dyeing, and processing, as well as additional nonproduction tasks, including accounting, marketing, transportation, and sales. Each one of these tasks can be performed by human labor or by capital (including both machines and software). The allocation of tasks to factors determines the task content of production. Automation enables some of the tasks previously performed by labor to be produced by capital. As a recent example, advances in robotics technologies since the 1980s have allowed firms to automate a wide range of production tasks in manufacturing, such as machining, welding, painting, and assembling, that were performed manually (Ayres and Miller 1983; Groover, Weiss, Nagel, and Odrey 1986; Acemoglu and Restrepo 2018b). The set of tasks involved in producing a product is not constant over time, and the introduction of new tasks can be a major source of labor demand as well as productivity. In textiles, examples of new labor-intensive tasks include computerized designs, new methods of market research, and various managerial activities for better targeting of demand and cost saving. By changing the allocation of tasks to factors, both automation and the introduction of new tasks affect the task content of production. Tasks are thus the fundamental unit of production, and the factors of produc-tion contribute to output by performing these tasks. In contrast, the canonical Automation and New Tasks: How Technology Displaces and Reinstates Labor 7\n\napproach in economics bypasses tasks and directly posits a production function of the form Y = F (A K K, A LL), which additionally imposes that all technological change takes a factor-augmenting form. There are three related reasons we prefer our conceptual framework. First, the canonical approach lacks descriptive realism. Advances in robotics, for example, do not make capital or labor more productive, but expand the set of tasks that can be produced by capital. Second, capital-augmenting technological change (an increase in A K ) or labor-augmenting technological change (an increase in A L) corresponds to the relevant factor becoming uniformly more produc-tive in all tasks , which, we will show, ignores potentially important changes in the task content of production. Third, and most importantly, we will also see that the quan-titative and qualitative implications of factor-augmenting technological advances are different from those of technologies that change the task content of produc-tion. Focusing just on factor-augmenting technologies can force us into misleading conclusions. \n\nTasks and Production \n\nWe present our task-based framework by first describing the production process in a single-sector economy. 2 Suppose that production combines the output of a range of tasks, and that the tasks are indexed by z and normalized to lie between N \u2212 1 and \n\nN, as shown in Figure 1.3 Tasks can be produced using capital or labor. Tasks with \n\nz > I are not automated, and can only be produced with labor, which has a wage rate \n\nW. Tasks z \u2264 I are automated and can be produced with capital, which has a rental rate R, as well as labor. We assume that labor has both a comparative and an absolute advantage in higher indexed tasks. An increase in I therefore represents the introduc-tion of an automation technology, or automation for short. An increase in N , on the other hand, corresponds to the introduction of new labor-intensive tasks or new tasks \n\nfor short. In addition to automation ( I) and introduction of new tasks ( N) , the state of technology for this sector depends on A L (labor-augmenting technology) and A K\n\n(capital-augmenting technology), which increase the productivities of these factors in all tasks. Let us assume that it is cost-minimizing for firms to use capital in all tasks that are automated (all z \u2264 I) and to adopt all new tasks immediately. This implies an allocation of tasks to factors as summarized in Figure 1, which also shows how auto-mation and new tasks impact this allocation. 2 This also describes the production process in a sector situated in a multisector economy, with the only difference being that, in that case, changes in technology impact relative prices and induce reallocation of capital and labor across sectors. We discuss these relative price and reallocation effects below. 3 Namely, the production function takes the form Y = (\u222bN\u22121 \n\n> NY ( z)\u03c3\u2212 1____\n> \u03c3)\n> \u03c3____\n> \u03c3\u2212 1\n> , where Y(z) is the output of task\n> z. The assumption that tasks lie between N\u2212 1 and Nis adopted to simplify the exposition. Nothing major changes if we instead allow tasks to lie on the interval between 0 and N. The online Appendix presents more detail on underlying assumptions and on derivations of results that follow throughout the discussion.\n\n8 Journal of Economic Perspectives \n\nFollowing the same steps as in Acemoglu and Restrepo (2018a), output can be represented as a constant elasticity of substitution (CES) function of capital and labor: \n\nY = \u03a0(I, N )(\u0393 ( I, N )1__ \n\n> \u03c3\n\n( A LL)\u03c3\u2212 1____ \n\n> \u03c3\n\n+ (1 \u2013 \u0393 ( I, N )) 1__ \n\n> \u03c3\n\n(A KK)\u03c3\u2212 1____ \n\n> \u03c3\n\n)\n\n> \u03c3____\n> \u03c3\u2212 1\n\n.As in the canonical model, we have production as a function of the quantities of labor and capital, L and K. The labor-augmenting technology term A L and the capital-augmenting term A K increase the productivity of labor and capital in all tasks they currently produce. The elasticity of substitution between tasks, \u03c3, determines how easy it is to substitute one task for another, and is also the (derived) elasticity of substitution between capital and labor. The crucial difference from the canonical model is that the share parameters of this constant-elasticity-of-substitution function depend on automation and new tasks. The share parameter for labor, \u0393(I, N ), is the labor task content of production, which represents the share of tasks performed by labor relative to capital (adjusted for differences in labor and capital productivity across these tasks). Conversely, 1 \u2212 \u0393(I, N ) is the capital task content of production. Hence, an increase in \u0393(I, N ) \n\n> Source: Authors.\n> Note: The figure summarizes the allocation of tasks to capital and labor. Production requires the completion of a range of tasks, normalized to lie between N\u2013 1 and N. Tasks above Iare not automated, and can only be produced with labor. Tasks below Iare automated and will be produced with capital. An increase in Irepresents the introduction of automation technology or automation for short. An increase in Ncorresponds to the introduction of new labor-intensive tasks or new tasks for short.\n\nFigure 1 \n\nThe Allocation of Capital and Labor to the Production of Tasks and the Impact of Automation and the Creation of New Tasks Daron Acemoglu and Pascual Restrepo 9\n\nshifts the task content of production in favor of labor and against capital. In the special case where \u03c3 = 1, \u0393(I, N ) = N \u2212 I. More generally, \u0393(I, N ) is always increasing in N and decreasing in I. This, in particular, implies that automation (greater I)shifts the task content of production against labor because it entails capital taking over tasks previously performed by labor. In contrast, new labor-intensive tasks shift the task content of production in favor of labor. 4 Finally, automation and new tasks not only change the task content of production but also generate productivity gains by allowing the allocation of (some) tasks to cheaper factors. The term \u03a0( I, N ), which shows up as total factor productivity, represents these productivity gains. The labor share, given by wage bill ( WL ) divided by value added ( Y), can be derived as: \n\nsL = 1________________________ \n\n1 + 1 \u2212 \u0393(I, N )___________ \n\n\u0393(I, N ) (\n\nR/ A K\n\n> _____\n\nW/ A L) \n\n> 1\u2212\u03c3\n\n.This relationship, which will be relied upon extensively in the rest of the paper, clarifies the two distinct forces shaping the labor share (in an industry or the entire economy). As is standard, the labor share depends on the ratio of effective factor prices, W/A L and R/A K. Intuitively, as effective wages rise relative to effective rental rates of capital, the price of tasks produced by labor increases relative to the price of tasks produced by capital, and this generates a substitution effect across tasks. This is the only force influencing the labor share in the canonical model. Its magnitude and size depend on whether \u03c3 is greater than or less than 1. For example, when tasks are complements ( \u03c3 < 1), an increase in the effective wage raises the cost share of tasks produced by labor. The opposite happens when \u03c3 > 1. When \u03c3 = 1, we obtain a Cobb\u2013Douglas production function and the substitution effect vanishes because the share of each task in value added is fixed. More novel are the effects of the task content of production, \u0393(I, N ), on the labor share. Intuitively, as more tasks are allocated to capital instead of labor, the task content shifts against labor and the labor share will decline unambiguously. Our model thus predicts that, independently from the elasticity of substitution \n\n\u03c3, automation (which changes the task content of production against labor) will reduce the labor share in the industry, while new tasks (which alter the task content of production in favor of labor) will increase it. 4 Our exposition assumes that the task content of production does not depend on factor-augmenting technologies or the supply of capital or labor. This will be the case when it is cost-minimizing for firms in this sector to use capital in all tasks that are automated (all z \u2264 I) and use all new tasks immediately. The online Appendix presents the underlying assumptions on technology and factor supplies that ensures this is the case. When this assumption does not hold (for example, because of very large changes in factor-augmenting technologies or factor supplies), the allocation of tasks to factors will change with factor supplies and factor-augmenting technologies. Even in this case, the impact of factor-augmenting technologies on the task content will be small relative to the productivity gains from these technologies. 10 Journal of Economic Perspectives \n\nTechnology and Labor Demand \n\nWe now investigate how technology changes labor demand. We focus on the behavior of the wage bill, WL , which captures the total amount employers pay for labor. Recall that Wage bill = Value added \u00d7 Labor share .\n\nChanges in the wage bill will translate into some combination of changes in employ-ment and wages, and the exact division will be affected by the elasticity of labor supply and labor market imperfections, neither of which we model explicitly in this paper (for discussion, see Acemoglu and Restrepo 2018a, 2018b). We use this relationship to think about how three classes of technologies impact labor demand: automation, new tasks, and factor-augmenting advances. Consider the introduction of new automation technologies (an increase in I in Figure 1). The impact on labor demand can be represented as: Effect of automation on labor demand = Productivity effect \n\n+ Displacement effect. The productivity effect arises from the fact that automation increases value added, and this raises the demand for labor from non-automated tasks. If nothing else happened, labor demand of the industry would increase at the same rate as value added, and the labor share would remain constant. However, automation also generates a displace-ment effect \u2014it displaces labor from the tasks previously allocated to it\u2014which shifts the task content of production against labor and always reduces the labor share. Automation therefore increases the size of the pie, but labor gets a smaller slice. There is no guarantee that the productivity effect is greater than the displacement effect; some automation technologies can reduce labor demand even as they raise productivity. 5Hence, contrary to a common presumption in popular debates, it is not the \u201cbrilliant\u201d automation technologies that threaten employment and wages, but \u201cso-so technologies\u201d that generate small productivity improvements. This is because the posi-tive productivity effect of so-so technologies is not sufficient to offset the decline in labor demand due to displacement. To understand when this is likely to be the case, let us first consider where the productivity gains from automation are coming from. These are not a consequence of the fact that capital and labor are becoming more productive in the tasks they are performing, but follow from the ability of firms to use cheaper capital in tasks previously performed by labor. The productivity effect of 5 Indeed, in Acemoglu and Restrepo (2018b), we show that industrial robots, a leading example of auto-mation technology, are associated with lower labor share and labor demand at the industry level and lower labor demand in local labor markets exposed to this technology. This result is consistent with a powerful displacement effect that has dominated the productivity effect from this class of automation technologies. Automation and New Tasks: How Technology Displaces and Reinstates Labor 11 \n\nautomation is therefore proportional to cost-savings obtained from such substitution. The greater is the productivity of labor in tasks being automated relative to its wage and the smaller is the productivity of capital in these tasks relative to the rental rate of capital, the more limited the productivity gains from automation will be. Examples of so-so technologies include automated customer service, which has displaced human service representatives but is generally deemed to be low quality and thus unlikely to have generated large productivity gains. They may also include several of the applica-tions of artificial intelligence technology to tasks that are currently challenging for machines. Different technologies are accompanied by productivity effects of varying magnitudes, and hence, we cannot presume that one set of automation technolo-gies will impact labor demand in the same way as others. Likewise, because the productivity gains of automation depend on the wage, the net impact of automa-tion on labor demand will depend on the broader labor market context. When wages are high and labor is scarce, automation will generate a strong produc-tivity effect and will tend to raise labor demand. When wages are low and labor is ab",
+  "issn_in_prose_false": "Journal of Economic Perspectives ISSN 0895-3309 (Print) | ISSN 1944-7965 (Online) Artificial Intelligence: The Ambiguous Labor Market Impact of Automating Prediction Journal of Economic Perspectives (pp. 31\u201350) [Download Full Text PDF](/articles/pdf/doi/10.1257/jep.33.2.31) (Complimentary) (Complimentary) Abstract Recent advances in artificial intelligence are primarily driven by machine learning, a prediction technology. Prediction is useful because it is an input into decision-making. In order to appreciate the impact of artificial intelligence on jobs, it is important to understand the relative roles of prediction and decision tasks. We describe and provide examples of how artificial intelligence will affect labor, emphasizing differences between when the automation of prediction leads to automating decisions versus enhancing decision-making by humans.Citation Agrawal, Ajay, Joshua S. Gans, and Avi Goldfarb. 2019. \"Artificial Intelligence: The Ambiguous Labor Market Impact of Automating Prediction.\" Journal of Economic Perspectives 33 (2): 31\u201350. DOI: 10.1257/jep.33.2.31Additional Materials JEL Classification - C63 Computational Techniques; Simulation Modeling - J23 Labor Demand - J24 Human Capital; Skills; Occupational Choice; Labor Productivity - L23 Organization of Production - M11 Production Management",
+  "incidental_contents_false": "Title: Artificial Intelligence and Labor Productivity Paradox: The Economic Impact of AI in China, India, Japan, and Singapore URL Source: https://doi.org/10.32996/jefas.2021.3.2.13 Markdown Content: Article contents Research Article ## Authors ## Abstract Artificial intelligence is designed to generate technologies that potentially increase productivity and economic welfare. This study analyzes the relationship between GDP and high-technology exports, GDP per person employed, and unemployment rate in China, India, Japan, and Singapore. Recent concerns on technological unemployment claim that artificial intelligence disrupts the labor market which decreases employment over time. Using the multiple regression analysis, this study proved that Japan comparatively has better utilization of AI and labor productivity as all independent variables show significance to the GDP. Labor productivity in all countries is positively related to GDP. However, China and India showed signs of improper AI utilization as technological unemployment occurred. The unemployment rate in China is insignificant to its GDP, while India's unemployment rate is positively related to GDP, hence the jobless growth. In Singapore, the insignificance of high-tech exports to GDP is due to its lack of R&amp;D investments these recent years. The results suggest that AI escalates growth through proper utilization trade liberalization, as exercised by Japan, as it helps the economy to be open and flexible to various \n\n[...]\n\n direct investments that will cater technology transfer, creation of new jobs, and economic growth. ## Article information ### Journal ### Journal of Economics, Finance and Accounting Studies ### Volume (Issue) ### 3 (2) ### DOI ### [https://doi.org/10.32996/jefas.2021.3.2.13](https://doi.org/10.32996/jefas.2021.3.2.13) ### Pages ### 120-139 ### Published 2021-11-19 ## Copyright Copyright (c) 2021 Journal of Economics, Finance and Accounting Studies ## Open access ## Downloads * [PDF](https://al-kindipublisher.com/index.php/jefas/article/view/2350/2087) Views ### "
+ },
+ "_provenance": {
+  "toc_dot_leader_masthead": {
+   "source_snapshot": ".codex/I-deepfix-001/autopsy/autopsy_43262935/outputs/preflight_a100_v3/workforce/drb_72_ai_labor/corpus_snapshot.json",
+   "evidence_id": "ev_149",
+   "source_url": "https://odondebuenr.com.mx/wp-content/uploads/2025/12/Industrial-AI-Framework-Final-2022-02-21.pdf",
+   "doi": null,
+   "tier": "T6",
+   "dot_leaders": 77,
+   "issn": false,
+   "contents_vocab": false,
+   "len": 11201,
+   "note": "real captured issue TOC head; signal-1 dot-leader density"
+  },
+  "issn_editorial_masthead": {
+   "source_snapshot": "outputs/corpus_backups/extracted/drb_76_gut_microbiota_crc/corpus_snapshot.json",
+   "evidence_id": "ev_529",
+   "source_url": "https://doi.org/10.31021/jddm.20181119",
+   "doi": null,
+   "tier": "T1",
+   "dot_leaders": 0,
+   "issn": true,
+   "contents_vocab": true,
+   "len": 1500,
+   "note": "real captured journal masthead; signal-2 ISSN + editorial-board vocab"
+  },
+  "article_head_false": {
+   "source_snapshot": ".codex/I-deepfix-001/autopsy/autopsy_43262935/outputs/preflight_a100_v3/workforce/drb_72_ai_labor/corpus_snapshot.json",
+   "evidence_id": "acemoglu_restrepo_automation_tasks",
+   "source_url": "https://www.aeaweb.org/articles/pdf/doi/10.1257/jep.33.2.3",
+   "doi": "10.1257/jep.33.2.3",
+   "tier": "T1",
+   "dot_leaders": 0,
+   "issn": false,
+   "contents_vocab": false,
+   "len": 25000,
+   "note": "real T1 article head; zero front-matter signals"
+  },
+  "issn_in_prose_false": {
+   "source_snapshot": "outputs/corpus_backups/extracted/drb_72_ai_labor/corpus_snapshot.json",
+   "evidence_id": "ev_038",
+   "source_url": "https://pubs.aeaweb.org/doi/abs/10.1257/jep.33.2.31",
+   "doi": null,
+   "tier": "T4",
+   "dot_leaders": 0,
+   "issn": true,
+   "contents_vocab": false,
+   "len": 1330,
+   "note": "real span: ISSN present, contents-vocab ABSENT; proves signal-2 requires BOTH"
+  },
+  "incidental_contents_false": {
+   "source_snapshot": "outputs/corpus_backups/extracted/drb_72_ai_labor/corpus_snapshot.json",
+   "evidence_id": "ev_195",
+   "source_url": "https://doi.org/10.32996/jefas.2021.3.2.13",
+   "doi": null,
+   "tier": "T1",
+   "dot_leaders": 0,
+   "issn": false,
+   "contents_vocab": false,
+   "len": 2079,
+   "note": "real span: incidental \"contents\", no ISSN; proves co-occurrence needed"
+  }
+ },
+ "_notes": {
+  "dgpu_cyrillic_masthead": "The dgpu reb-t-9-2-2026.pdf Cyrillic masthead (31x collision class) was NOT on disk in any banked corpus_snapshot (all drb_* snapshots: masthead-vocab count 0). signal-2 is proven with a REAL captured ISSN+editorial-board masthead (issn_editorial_masthead). A real-shaped Cyrillic dgpu masthead is built inline in the test to exercise the \u0421\u041e\u0414\u0415\u0420\u0416\u0410\u041d\u0418\u0415/\u0420\u0415\u0414\u0410\u041a\u0426\u0418\u041e\u041d\u041d\u0410\u042f \u041a\u041e\u041b\u041b\u0415\u0413\u0418\u042f path.",
+  "identical_span_collision": "No banked rows share an identical blob/span across different DOIs (on-disk snapshots predate B4 fetched_blob_sha stamping; each row stores its own windowed quote). The collision test reuses REAL masthead span text with constructed DOIs to reproduce the 31x-dgpu container shape."
+ }
+}
\ No newline at end of file
diff --git a/tests/polaris_graph/test_i_deepfix_004_frontmatter.py b/tests/polaris_graph/test_i_deepfix_004_frontmatter.py
new file mode 100644
index 00000000..135b6f14
--- /dev/null
+++ b/tests/polaris_graph/test_i_deepfix_004_frontmatter.py
@@ -0,0 +1,506 @@
+# -*- coding: utf-8 -*-
+"""I-deepfix-004 (#1375) PR-1 — OFFLINE tests for the wrong-content citable-span fix
+(steps A + B + C + D).
+
+Covers, per the Fable root-cause plan (.codex/I-deepfix-004/fable_root_cause_plan.md):
+
+  D  shell_detector.is_issue_front_matter — TRUE on a REAL masthead/TOC span (dot-leader
+     density) + a REAL ISSN+editorial-board masthead + a real-shaped Cyrillic dgpu
+     masthead; FALSE on a real article head, a real ISSN-bearing non-masthead span, and a
+     real incidental "contents" mention. Fail-open on a short stub. OFF flag byte-identical.
+  D  shell_detector.identical_span_collision — 2 rows identical span + DIFFERENT works =>
+     both flagged; identical span + SAME work => not flagged; unique spans => none;
+     fetched_blob_sha key path.
+  A  live_retriever.refetch_for_extraction_with_diagnostics — PG_REFETCH_FULL_BODY ON =>
+     the fetch cap passed to _fetch_content is the large body cap (DEFAULT_CONTENT_MAX_CHARS)
+     and the quote is still capped at max_chars (a deep decimal is recovered); OFF => the
+     old max_chars fetch cap (byte-identical, deep decimal lost).
+  B  access_bypass._parse_pdf_page_fragment / _parse_doi_page_range (pure);
+     _resolve_doi_pdf_target captures the final URL + #page=N anchor from a redirect
+     Location header (mocked aiohttp); a fitz page-slice on a real-shaped multi-article PDF
+     returns the target article and NOT the ISSN/TOC page. OFF flag byte-identical.
+  D wiring A15 recovery rejects a masthead span as wrong_content_front_matter (screen ON);
+     OFF => the screen never fires (byte-identical).
+
+REAL captured data: front-matter spans are pulled verbatim from banked corpus_snapshot.json
+files (gitignored outputs/.codex) and copied into
+tests/fixtures/i_deepfix_004/real_masthead_spans.json so the test is self-contained + CI-
+runnable. Provenance per span is recorded in that fixture's _provenance block (LAW II).
+The dgpu Cyrillic masthead was NOT on disk (all drb_* snapshots carry masthead-vocab count
+0), so signal-2 is proven with a REAL captured ISSN+editorial masthead and the Cyrillic
+СОДЕРЖАНИЕ/РЕДАКЦИОННАЯ КОЛЛЕГИЯ path is exercised with a real-shaped inline fixture
+(DGPU_CYRILLIC_MASTHEAD_REAL_SHAPED). identical_span_collision reuses real masthead span
+text with constructed DOIs because no banked rows share an identical blob across DOIs (the
+on-disk snapshots predate B4 fetched_blob_sha stamping).
+"""
+
+from __future__ import annotations
+
+import asyncio
+import json
+import os
+from pathlib import Path
+
+import aiohttp
+
+from src.polaris_graph.retrieval import shell_detector
+import src.polaris_graph.retrieval.live_retriever as lr
+from src.tools import access_bypass as ab
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# Real captured spans (banked into a committed fixture from gitignored snapshots).
+# ─────────────────────────────────────────────────────────────────────────────
+
+_FIXTURE_PATH = (
+    Path(__file__).resolve().parents[1]
+    / "fixtures"
+    / "i_deepfix_004"
+    / "real_masthead_spans.json"
+)
+
+
+def _load_spans() -> dict:
+    with open(_FIXTURE_PATH, encoding="utf-8") as fh:
+        data = json.load(fh)
+    return data["spans"]
+
+
+SPANS = _load_spans()
+
+# A real-shaped Cyrillic dgpu-class journal masthead (822 chars). Built to match the
+# dgpu reb-t-9-2-2026.pdf masthead described in the root-cause plan because that exact
+# span was not present in any banked snapshot on disk. Exercises signal-2's Cyrillic
+# vocabulary (СОДЕРЖАНИЕ = contents, РЕДАКЦИОННАЯ КОЛЛЕГИЯ = editorial board) + ISSN.
+DGPU_CYRILLIC_MASTHEAD_REAL_SHAPED = (
+    "Дагестанский государственный педагогический университет имени Р. Гамзатова\n"
+    "Известия ДГПУ. Психолого-педагогические науки. Том 9. № 2. 2026\n"
+    "ISSN 2500-2953 (Print)  ISSN 2687-0770 (Online)\n"
+    "DOI: 10.31161/1995-0659-2026-9-2\n"
+    "\n"
+    "РЕДАКЦИОННАЯ КОЛЛЕГИЯ\n"
+    "Главный редактор: доктор педагогических наук, профессор.\n"
+    "Заместитель главного редактора. Ответственный секретарь.\n"
+    "Члены редакционной коллегии: доктор психологических наук; "
+    "доктор педагогических наук; кандидат философских наук.\n"
+    "\n"
+    "СОДЕРЖАНИЕ\n"
+    "Раздел 1. Общая педагогика, история педагогики и образования\n"
+    "Цифровизация и искусственный интеллект в образовании\n"
+    "Раздел 2. Теория и методика обучения и воспитания\n"
+    "Раздел 3. Коррекционная педагогика\n"
+    "Учредитель: ФГБОУ ВО «Дагестанский государственный педагогический университет».\n"
+    "Адрес редакции: издательство, редакционно-издательский отдел.\n"
+)
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# D — is_issue_front_matter
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def test_front_matter_true_on_real_dot_leader_toc():
+    """Signal 1: a REAL captured issue TOC head (77 dot-leader runs) is front-matter."""
+    span = SPANS["toc_dot_leader_masthead"]
+    assert shell_detector.is_issue_front_matter(span) is True
+
+
+def test_front_matter_true_on_real_issn_editorial_masthead():
+    """Signal 2: a REAL captured masthead (ISSN + editorial-board vocab) is front-matter."""
+    span = SPANS["issn_editorial_masthead"]
+    assert shell_detector.is_issue_front_matter(span) is True
+
+
+def test_front_matter_true_on_real_shaped_cyrillic_dgpu_masthead():
+    """Signal 2, Cyrillic path: ISSN + СОДЕРЖАНИЕ/РЕДАКЦИОННАЯ КОЛЛЕГИЯ is front-matter."""
+    assert shell_detector.is_issue_front_matter(DGPU_CYRILLIC_MASTHEAD_REAL_SHAPED) is True
+
+
+def test_front_matter_false_on_real_article_head():
+    """FALSE: a real T1 article head carries zero front-matter signals (fail-open KEEP)."""
+    span = SPANS["article_head_false"]
+    assert shell_detector.is_issue_front_matter(span) is False
+
+
+def test_front_matter_false_on_real_issn_bearing_non_masthead():
+    """FALSE: a real span with an ISSN but NO contents/editorial vocab — proves signal 2
+    requires BOTH the ISSN marker AND the contents vocabulary (a reference-list / prose
+    ISSN citation must never trip the masthead screen)."""
+    span = SPANS["issn_in_prose_false"]
+    # Precondition on the real span: ISSN present, contents-vocab absent.
+    assert shell_detector._FRONT_MATTER_ISSN_RE.search(span)
+    assert shell_detector.is_issue_front_matter(span) is False
+
+
+def test_front_matter_false_on_real_incidental_contents_mention():
+    """FALSE: a real article span that mentions the word "contents" incidentally (no ISSN,
+    no masthead vocabulary) — the co-occurrence requirement holds the other way too."""
+    span = SPANS["incidental_contents_false"]
+    assert "contents" in span.lower()
+    assert shell_detector.is_issue_front_matter(span) is False
+
+
+def test_front_matter_fail_open_on_short_stub():
+    """A body below the min-body floor is too short to read a structural verdict => KEEP."""
+    assert shell_detector.is_issue_front_matter("ISSN 2500-2953 СОДЕРЖАНИЕ") is False
+    assert shell_detector.is_issue_front_matter("") is False
+
+
+def test_front_matter_screen_flag_off_is_byte_identical(monkeypatch):
+    """The default-ON gate: OFF => the screen wrapper never fires => byte-identical KEEP,
+    even on the real dot-leader masthead. The pure detector itself is flag-agnostic (still
+    reports the structural truth); only the live wrapper honours the flag."""
+    span = SPANS["toc_dot_leader_masthead"]
+    monkeypatch.setenv("PG_SPAN_CITED_WORK_SCREEN", "0")
+    assert shell_detector.span_cited_work_screen_enabled() is False
+    # The live fail-open wrapper must skip the screen when OFF.
+    assert lr._span_is_issue_front_matter(span) is False
+    monkeypatch.setenv("PG_SPAN_CITED_WORK_SCREEN", "1")
+    assert shell_detector.span_cited_work_screen_enabled() is True
+    assert lr._span_is_issue_front_matter(span) is True
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# D — identical_span_collision
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def _row(eid: str, span: str, doi: str = "", url: str = "", blob_sha: str = "") -> dict:
+    r = {"evidence_id": eid, "direct_quote": span}
+    if doi:
+        r["doi"] = doi
+    if url:
+        r["source_url"] = url
+    if blob_sha:
+        r["fetched_blob_sha"] = blob_sha
+    return r
+
+
+def test_collision_identical_span_different_dois_both_flagged():
+    """The 31x-dgpu shape reproduced with REAL masthead span text: two rows carry the
+    IDENTICAL span but DIFFERENT DOIs => a multi-work container => BOTH flagged."""
+    masthead = SPANS["toc_dot_leader_masthead"]
+    rows = [
+        _row("ev_a", masthead, doi="10.34142/x-2026-9-2-203-210"),
+        _row("ev_b", masthead, doi="10.34142/x-2026-9-2-211-219"),
+    ]
+    flagged = shell_detector.identical_span_collision(rows)
+    assert flagged == {"ev_a", "ev_b"}
+
+
+def test_collision_identical_span_same_doi_not_flagged():
+    """Identical span + SAME cited work is a legitimate duplicate (CONSOLIDATE, step E) —
+    NOT a container collision => not flagged."""
+    masthead = SPANS["toc_dot_leader_masthead"]
+    rows = [
+        _row("ev_a", masthead, doi="10.34142/x-2026-9-2-203-210"),
+        _row("ev_b", masthead, doi="10.34142/x-2026-9-2-203-210"),
+    ]
+    assert shell_detector.identical_span_collision(rows) == set()
+
+
+def test_collision_unique_spans_none_flagged():
+    """Distinct spans can never be a container collision."""
+    rows = [
+        _row("ev_a", SPANS["article_head_false"], doi="10.1/aaa"),
+        _row("ev_b", SPANS["issn_in_prose_false"], doi="10.2/bbb"),
+    ]
+    assert shell_detector.identical_span_collision(rows) == set()
+
+
+def test_collision_blob_sha_key_different_dois_flagged():
+    """The content-identity key prefers fetched_blob_sha (B4 stamp): two rows sharing one
+    blob sha but citing different works => container => both flagged, even if the stored
+    direct_quote strings differ (a windowed slice of the same blob)."""
+    rows = [
+        _row("ev_a", "windowed slice one", doi="10.1/aaa", blob_sha="deadbeef" * 8),
+        _row("ev_b", "a different window", doi="10.2/bbb", blob_sha="deadbeef" * 8),
+    ]
+    assert shell_detector.identical_span_collision(rows) == {"ev_a", "ev_b"}
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# A — full-body refetch (fetch cap separated from quote cap)
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def _install_truncating_fetch(monkeypatch, body: str, recorder: dict):
+    """Stub _fetch_content that emulates the real `content = _stripped_body[:max_chars]`
+    truncation and records the fetch cap it was called with."""
+
+    def _stub(url, cap):  # signature: (url, max_chars) -> (content, ok, title, body_type, jsonld)
+        recorder["cap"] = cap
+        return (body[:cap], True, "", "full_text", None)
+
+    monkeypatch.setattr(lr, "_fetch_content", _stub)
+    lr.reset_refetch_cache()
+
+
+def _build_deep_decimal_body() -> tuple[str, str]:
+    head = "Employment and wage prose sentence. " * 40         # ~1480 chars head
+    mid = "neutral filler body content here. " * 80            # push the decimal past 3000
+    decimal = " the measured coefficient was 42.577 across cohorts. "
+    tail = "tail prose here. " * 300
+    body = head + mid + decimal + tail
+    return body, "42.577"
+
+
+def test_step_a_full_body_on_uses_large_fetch_cap_quote_capped(monkeypatch):
+    """PG_REFETCH_FULL_BODY ON => _fetch_content is called with the large body cap
+    (DEFAULT_CONTENT_MAX_CHARS), the quote stays capped at max_chars, and a decimal DEEP
+    in the body (beyond max_chars) is recovered into the quote."""
+    body, decimal = _build_deep_decimal_body()
+    assert body.find(decimal) > 3000  # the decimal lives beyond the OFF fetch cap
+    rec: dict = {}
+    _install_truncating_fetch(monkeypatch, body, rec)
+    monkeypatch.setenv("PG_REFETCH_FULL_BODY", "1")
+
+    quote, diag = lr.refetch_for_extraction_with_diagnostics(
+        "http://combined.test/on", max_chars=3000
+    )
+
+    assert rec["cap"] == lr.DEFAULT_CONTENT_MAX_CHARS  # full body fetched, not 3000
+    assert diag["eligible"] is True
+    assert len(quote) <= 3000  # quote still capped at max_chars
+    assert decimal in quote     # deep decimal recovered by the decimal-window design
+
+
+def test_step_a_full_body_off_is_byte_identical_head_truncated(monkeypatch):
+    """PG_REFETCH_FULL_BODY OFF => _fetch_content is called with the OLD max_chars fetch
+    cap (byte-identical to the prior head-truncating path); the deep decimal is thrown
+    away with the truncated body."""
+    body, decimal = _build_deep_decimal_body()
+    rec: dict = {}
+    _install_truncating_fetch(monkeypatch, body, rec)
+    monkeypatch.setenv("PG_REFETCH_FULL_BODY", "0")
+
+    quote, diag = lr.refetch_for_extraction_with_diagnostics(
+        "http://combined.test/off", max_chars=3000
+    )
+
+    assert rec["cap"] == 3000     # old behaviour: fetch capped at max_chars
+    assert diag["eligible"] is True
+    assert len(quote) <= 3000
+    assert decimal not in quote   # truncated away before the quote was built
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# B — page-anchor parsing (pure)
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def test_parse_pdf_page_fragment_hash_form():
+    assert ab._parse_pdf_page_fragment("https://x/y.pdf#page=207") == 207
+    assert ab._parse_pdf_page_fragment("#page=1") == 1
+
+
+def test_parse_pdf_page_fragment_query_form_and_misses():
+    assert ab._parse_pdf_page_fragment("https://x/y.pdf?page=42") == 42
+    assert ab._parse_pdf_page_fragment("https://x/y.pdf") is None
+    assert ab._parse_pdf_page_fragment("") is None
+    assert ab._parse_pdf_page_fragment("#page=0") is None  # 1-indexed; 0 rejected
+
+
+def test_parse_doi_page_range_from_suffix():
+    assert ab._parse_doi_page_range("10.34142/2312-2919-2026-9-2-203-210") == (203, 210)
+
+
+def test_parse_doi_page_range_rejects_inconsistent_and_missing():
+    assert ab._parse_doi_page_range("10.34142/2312-2919-2026-9-2-210-203") == (None, None)
+    assert ab._parse_doi_page_range("10.1000/plainjournal") == (None, None)
+    assert ab._parse_doi_page_range(None) == (None, None)
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# B — doi.org -> .pdf#page=N redirect resolution (mocked aiohttp)
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+class _FakeHeaders(dict):
+    def get(self, key, default=None):
+        for k, v in self.items():
+            if k.lower() == key.lower():
+                return v
+        return default
+
+
+class _FakeHist:
+    def __init__(self, location: str):
+        self.headers = _FakeHeaders({"Location": location})
+
+
+class _FakeResp:
+    def __init__(self, final_url: str, content_type: str, history: list):
+        self.url = final_url
+        self.headers = _FakeHeaders({"Content-Type": content_type})
+        self.history = history
+
+    async def __aenter__(self):
+        return self
+
+    async def __aexit__(self, *exc):
+        return False
+
+
+class _FakeSession:
+    def __init__(self, resp: _FakeResp):
+        self._resp = resp
+
+    async def __aenter__(self):
+        return self
+
+    async def __aexit__(self, *exc):
+        return False
+
+    def get(self, url, allow_redirects=True):
+        return self._resp
+
+
+def test_resolve_doi_pdf_target_captures_final_url_and_location_anchor(monkeypatch):
+    """STEP B1: a doi.org URL redirects to a publisher .pdf; the #page=207 anchor lives
+    ONLY on a redirect Location header (deliberately absent from the final url, which the
+    code comments say resp.url frequently drops). The resolver must still capture the final
+    resolved url AND page_anchor=207, plus page_end=210 from the DOI suffix."""
+    orig = "https://doi.org/10.34142/2312-2919-2026-9-2-203-210"
+    final = "https://journals.example.org/vol9/reb-t-9-2-2026.pdf"  # no fragment here
+    history = [
+        _FakeHist("https://journals.example.org/redirect?to=reb-t-9-2-2026.pdf#page=207")
+    ]
+    resp = _FakeResp(final, "application/pdf", history)
+    # _resolve_doi_pdf_target does a local `import aiohttp; aiohttp.ClientSession(...)`,
+    # so patching the real module's ClientSession intercepts the fetch offline.
+    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: _FakeSession(resp))
+
+    result = asyncio.run(ab.AccessBypass()._resolve_doi_pdf_target(orig))
+
+    assert result is not None
+    assert result["final_url"] == final
+    assert result["is_pdf"] is True
+    assert result["page_anchor"] == 207   # captured from the redirect Location header
+    assert result["page_end"] == 210      # from the DOI suffix -203-210
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# B — fitz page-slice on a real-shaped multi-article combined PDF
+# ─────────────────────────────────────────────────────────────────────────────
+
+_PAGE_TEXTS = [
+    # page 1: journal-issue cover / ISSN masthead / table of contents (front matter)
+    "ISSN 2500-2953  СОДЕРЖАНИЕ  РЕДАКЦИОННАЯ КОЛЛЕГИЯ  Table of Contents  "
+    "cover page 1 masthead front matter of the whole combined issue.",
+    # pages 2-3: the CITED article (alpha)
+    "ARTICLE_ALPHA_MARKER Automation and employment: an alpha study. "
+    "Abstract methods results the measured effect was 42.577 percent.",
+    "ARTICLE_ALPHA_MARKER continued: alpha discussion, conclusion and references.",
+    # pages 4-5: a DIFFERENT article (beta) in the same combined PDF
+    "ARTICLE_BETA_MARKER A second unrelated article beta. Introduction to a different topic.",
+    "ARTICLE_BETA_MARKER continued: beta results, discussion and references.",
+]
+
+
+def _build_multi_article_pdf() -> bytes:
+    import fitz
+
+    doc = fitz.open()
+    for text in _PAGE_TEXTS:
+        page = doc.new_page()
+        page.insert_text((72, 100), text, fontsize=11)
+    data = doc.tobytes()
+    doc.close()
+    return data
+
+
+def _extract_impl(pdf_bytes: bytes, **kwargs) -> str:
+    inst = ab.AccessBypass()
+    # Belt-and-suspenders with the env skip below: never let docling win the tiny fixture
+    # (docling returns the WHOLE doc and early-returns before the PyMuPDF slice path).
+    inst._docling_extract = lambda _b: ""
+    return asyncio.run(
+        inst._extract_pdf_text_from_bytes_impl("http://x/combined.pdf", pdf_bytes, **kwargs)
+    )
+
+
+def test_fitz_page_slice_returns_cited_article_not_toc(monkeypatch):
+    """STEP B2: with page_anchor=2, page_end=3 the fitz path extracts ONLY the cited
+    article (pages 2-3), NOT the page-1 ISSN/TOC masthead and NOT the other article
+    (pages 4-5) that shares the combined PDF."""
+    # Force the PyMuPDF slice path (docling is skipped for docs > 1 page); the slice logic
+    # lives only in the PyMuPDF fallback.
+    monkeypatch.setenv("PG_MAX_DOCLING_PDF_PAGES", "1")
+    pdf = _build_multi_article_pdf()
+
+    sliced = _extract_impl(pdf, page_anchor=2, page_end=3)
+
+    assert "ARTICLE_ALPHA_MARKER" in sliced
+    assert "ISSN 2500-2953" not in sliced
+    assert "СОДЕРЖАНИЕ" not in sliced
+    assert "ARTICLE_BETA_MARKER" not in sliced
+
+
+def test_fitz_no_anchor_off_path_extracts_whole_doc(monkeypatch):
+    """STEP B OFF / no anchor (page_anchor=None) => byte-identical whole-doc extraction,
+    which includes the masthead AND both articles."""
+    monkeypatch.setenv("PG_MAX_DOCLING_PDF_PAGES", "1")
+    pdf = _build_multi_article_pdf()
+
+    whole = _extract_impl(pdf)  # no page kwargs => old 2-arg path
+
+    assert "ISSN 2500-2953" in whole
+    assert "ARTICLE_ALPHA_MARKER" in whole
+    assert "ARTICLE_BETA_MARKER" in whole
+
+
+def test_pdf_cited_work_slice_flag_default_on_and_off():
+    """The default-ON gate + its explicit-OFF values."""
+    orig = os.environ.pop("PG_PDF_CITED_WORK_SLICE", None)
+    try:
+        assert ab.pdf_cited_work_slice_enabled() is True  # unset => default ON
+        for off in ("0", "false", "no", "off"):
+            os.environ["PG_PDF_CITED_WORK_SLICE"] = off
+            assert ab.pdf_cited_work_slice_enabled() is False
+        for on in ("1", "true", "yes", "on"):
+            os.environ["PG_PDF_CITED_WORK_SLICE"] = on
+            assert ab.pdf_cited_work_slice_enabled() is True
+    finally:
+        os.environ.pop("PG_PDF_CITED_WORK_SLICE", None)
+        if orig is not None:
+            os.environ["PG_PDF_CITED_WORK_SLICE"] = orig
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# D wiring — A15 recovery refetch rejects a masthead span as wrong_content_front_matter
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def test_refetch_rejects_masthead_span_wrong_content_front_matter(monkeypatch):
+    """Screen ON (default): when the re-fetch returns a REAL journal-issue masthead body,
+    the A15 recovery must route it to the not-extractable branch with
+    failure_mode == 'wrong_content_front_matter' (never adopt a cover/TOC span as the
+    cited article; recover->degrade->disclose, source kept)."""
+    masthead = SPANS["toc_dot_leader_masthead"]
+    rec: dict = {}
+    _install_truncating_fetch(monkeypatch, masthead, rec)
+    monkeypatch.setenv("PG_SPAN_CITED_WORK_SCREEN", "1")
+
+    quote, diag = lr.refetch_for_extraction_with_diagnostics(
+        "http://combined.test/masthead-on", max_chars=4000
+    )
+
+    assert quote == ""
+    assert diag["failure_mode"] == "wrong_content_front_matter"
+
+
+def test_refetch_masthead_screen_off_is_byte_identical(monkeypatch):
+    """Screen OFF => the front-matter screen never fires (byte-identical); the masthead
+    body is NOT rejected as wrong_content_front_matter (the OFF path adopts whatever the
+    pre-existing gates allow, exactly as before this fix)."""
+    masthead = SPANS["toc_dot_leader_masthead"]
+    rec: dict = {}
+    _install_truncating_fetch(monkeypatch, masthead, rec)
+    monkeypatch.setenv("PG_SPAN_CITED_WORK_SCREEN", "0")
+
+    _quote, diag = lr.refetch_for_extraction_with_diagnostics(
+        "http://combined.test/masthead-off", max_chars=4000
+    )
+
+    assert diag["failure_mode"] != "wrong_content_front_matter"

```

END OF DIFF. Return the schema block with your verdict as the final block.
