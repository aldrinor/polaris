# FX-15b (#1119) diff-gate — ITER 1 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
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
Quality/precision fix. **Faithfulness-safety hinges on precision** (must NOT drop a real article)
AND on the seed-exclusion (must NOT drop the entire agentic seed lane). No grounding /
strict_verify / 4-role-decision change. Depends on FX-15a (#1118, DONE). Diff:
`.codex/I-ready-017/fx15b_codex_diff.patch` (vs FX-15a verified tip `83e7ebfd`).

## Bug (RB-02b)
Agentic lane: `enable_prefetch_filter=False` + no structural filter → aeaweb nav/SERP/conference
pages enter the merge (now-droppable after FX-15a) adding ~0 evidence (held drb_72: 69 merged → 14
selectable).

## CRITICAL grounding finding that shaped the fix (please scrutinize)
Step-3 (`live_retriever.py` `if enable_prefetch_filter and candidates:`) ran `filter_search_results`
on ALL candidates INCLUDING the injected empty-snippet seeds. Agentic seeds are URL-only (no
snippet) → the embedder scores them ~0 similarity → would REJECT every agentic seed if
`enable_prefetch_filter=True` were passed naively. So the plan's "enable the semantic filter" is
only safe once Step-3 excludes seeds.

## Fix
1. **Structural filter** `_is_low_content_host_or_page(url, title='')` (pure, live_retriever):
   reject `/search`, `/browse`, `/conference`, `/annual-meeting`, `/issues/`, `/forum/`, `/toc/`;
   SERP `search-results` / `per-page=`; reuse `tier_classifier._detect_conference_abstract`.
   PRECISION-FIRST — `/issue/` (singular) is NOT rejected (can prefix a real article); conference
   programs caught by the heuristic. Applied to `_ag_urls` on the agentic lane
   (`run_honest_sweep_r3.py`), flag-gated `PG_AGENTIC_HOST_FILTER` (default on). `urls_selectable`
   telemetry added (post-filter count).
2. **Seed-safe Step-3** — split seeds out via `_SEED_SOURCE_LABELS`, filter only non-seeds,
   re-prepend seeds. Then `enable_prefetch_filter=True` on the agentic call (inert for the URL-only
   seed_only set — no non-seed candidates to score — but fixes the latent seed-drop for ANY caller).

## Evidence
- **§-1.1 on REAL held trace** (`outputs/audits/I-ready-017/fx15b_s11_audit.md`): 41 agentic rows →
  DROP 13 / KEEP 28, **0 real articles dropped**. The single URL a loose heuristic flagged
  (`oup.com/.../article/3/Supplement_1/i906/...`) is a CONFERENCE SUPPLEMENT abstract, correctly
  caught by `_detect_conference_abstract` (a correct drop). Real working-paper PDFs (NBER/MIT/Oxford)
  + journal articles all KEPT.
- **Offline smoke — `test_fx15b_host_filter_iready017.py` → 4 passed**: structural reject table;
  precision gate (6 real articles, ZERO dropped); empty-URL kept; seed-exclusion repro (with
  `enable_prefetch_filter=True` + a reject-ALL embedder stub, the empty-snippet agentic seed STILL
  survives and produces an evidence row — pre-fix it would be dropped).
- **Regression**: FX-15a (6) + `test_live_retriever_rerank` (8) + `test_bug776_layer4_doi_seeds`
  (5) + `test_retrieval_trace` (7) + `test_plan_sufficiency_phase3` (26) all pass.

## Known recall gap (deferred — not a precision issue)
3 atypical citation-stub / news pages survive the structural floor (`/news/cnn`, `scirp.org/
reference/referencespapers?referenceid=`, `socqa.../bibcite/reference/`). Caught downstream by tier
classifier + `is_content_starved` + the (now seed-safe) semantic filter. `/news/` deliberately NOT
rejected (a news URL can be a legitimate citation — precision over recall).

## Questions for you
1. Is the precision boundary right — i.e. is rejecting `/conference/` programs + `_detect_conference_abstract`
   supplement abstracts on the agentic lane correct, and is excluding `/issue/` (singular) + `/news/`
   from the reject set the right precision call?
2. Is the Step-3 seed-exclusion correct + complete (seeds never off-topic-dropped; non-seeds still
   filtered; re-prepend order fine)?
3. Anything blocking APPROVE?

## THE DIFF UNDER REVIEW (vs FX-15a verified tip 83e7ebfd)
```diff
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index 9ec7aa19..d749286e 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -157,6 +157,7 @@ from src.polaris_graph.retrieval.contradiction_detector import (  # noqa: E402
     extract_numeric_claims,
 )
 from src.polaris_graph.retrieval.live_retriever import (  # noqa: E402
+    _is_low_content_host_or_page,
     run_live_retrieval,
 )
 
@@ -1602,7 +1603,7 @@ async def run_one_query(
         enabled=_storm_enabled, firing_status="enabled_not_reached" if _storm_enabled else "not_enabled",
     )
     _agentic_telemetry = make_feature_telemetry(
-        "agentic_search", urls_discovered=0,
+        "agentic_search", urls_discovered=0, urls_selectable=0,  # FX-15b (#1119): post-filter count
         enabled=_agentic_enabled, firing_status="enabled_not_reached" if _agentic_enabled else "not_enabled",
     )
     # I-ready-005 (#1076) iter-4 P1-2: the ContextVar publish is GATED on at least one forced-ON
@@ -2904,6 +2905,22 @@ async def run_one_query(
                 except Exception:  # noqa: BLE001
                     pass
 
+            # FX-15b (#1119): STRUCTURAL host-class filter — drop nav/SERP/conference-program URLs
+            # (which add ~0 evidence) from the agentic seed set BEFORE fetch. Cheap deterministic
+            # floor; faithfulness-safe (precision-first: never drops a real article). Flag-gated
+            # (PG_AGENTIC_HOST_FILTER, default ON) so it is reversible. urls_selectable telemetry =
+            # the post-filter count (vs urls_discovered = pre-filter).
+            if _ag_urls and os.getenv("PG_AGENTIC_HOST_FILTER", "1") != "0":
+                _ag_kept = [u for u in _ag_urls if not _is_low_content_host_or_page(u, "")]
+                _ag_dropped = len(_ag_urls) - len(_ag_kept)
+                if _ag_dropped:
+                    _log(
+                        f"[agentic]     host-class filter dropped {_ag_dropped} low-content urls "
+                        f"-> {len(_ag_kept)} selectable"
+                    )
+                _ag_urls = _ag_kept
+            _agentic_telemetry["urls_selectable"] = len(_ag_urls)
+
             if _ag_urls:
                 try:
                     agentic_retrieval = run_live_retrieval(
@@ -2912,7 +2929,12 @@ async def run_one_query(
                         protocol=protocol,
                         fetch_cap=min(len(_ag_urls), _ag_url_cap),
                         enable_openalex_enrich=True,
-                        enable_prefetch_filter=False,
+                        # FX-15b (#1119): semantic off-topic filter ON for this lane. Now seed-safe —
+                        # Step-3 excludes injected seeds from filter_search_results (empty-snippet
+                        # seeds would otherwise be off-topic-dropped). Inert for the URL-only seed_only
+                        # set (no non-seed candidates to score); the structural filter above is the
+                        # real defense for URL-only agentic seeds.
+                        enable_prefetch_filter=True,
                         seed_urls=_ag_urls,
                         seed_only=True,   # ONLY the agentic URLs — no Serper/S2/domain fan-out
                         # FX-15a (#1118): truthful source/origin labels — these are agentic web
diff --git a/src/polaris_graph/retrieval/live_retriever.py b/src/polaris_graph/retrieval/live_retriever.py
index 93b62863..dad55bb7 100644
--- a/src/polaris_graph/retrieval/live_retriever.py
+++ b/src/polaris_graph/retrieval/live_retriever.py
@@ -50,6 +50,7 @@ from src.polaris_graph.authority.authority_model import score_source_authority
 from src.polaris_graph.authority.source_class import AuthoritySignals
 from src.polaris_graph.retrieval.tier_classifier import (
     ClassificationSignals,
+    _detect_conference_abstract,
     classify_source_tier,
 )
 
@@ -2102,6 +2103,41 @@ _SEED_SOURCE_LABELS: frozenset[str] = frozenset(
 )
 
 
+# FX-15b (#1119): path/route markers that unambiguously denote a NAV / SERP / conference-program
+# page carrying ~0 extractable evidence. Matched as lowercase substrings of the URL. Chosen
+# PRECISION-FIRST from the held drb_72 trace: every one of these appears only on listing/program
+# pages, NEVER on a real article URL (`/articles?id=...`, `pubs.*/doi/...`, arxiv `/abs/...`).
+# Note: `/issues/` (plural journal-TOC listing, e.g. `/issues/381`) is rejected, but `/issue/`
+# (singular) is NOT — it can prefix a real article path; conference programs are caught by the
+# reused `_detect_conference_abstract` heuristic instead.
+_LOW_CONTENT_PATH_MARKERS: tuple[str, ...] = (
+    "/search", "/browse", "/conference", "/annual-meeting", "/issues/", "/forum/",
+    "/toc/",  # journal table-of-contents listing (e.g. /toc/jpe/current) — never a real article
+)
+
+
+def _is_low_content_host_or_page(url: str, title: str = "") -> bool:
+    """FX-15b (#1119): structural reject of nav / SERP / conference-program URLs, applied to
+    agentic-discovered seed URLs BEFORE fetch (a cheap deterministic floor layered before the
+    semantic / tier filters). PRECISION-FIRST — must NEVER reject a real article/abstract page.
+    Pure + no network. Returns True iff the URL should be dropped as low-content.
+    """
+    if not url:
+        return False
+    u = url.lower()
+    if any(marker in u for marker in _LOW_CONTENT_PATH_MARKERS):
+        return True
+    # Paginated SERP / search-result listing pages (not an article).
+    if "search-results" in u or "per-page=" in u:
+        return True
+    # Conference-abstract / supplement program pages (reuse the tier-classifier heuristic so the
+    # two layers stay consistent). title is usually empty for URL-only agentic seeds; URL-only
+    # signals (/Supplement_, /abstract/, abstract-id prefixes) still fire.
+    if _detect_conference_abstract(title or "", url):
+        return True
+    return False
+
+
 def _rerank_and_reserve(
     candidates: list["SearchCandidate"],
     *,
@@ -2437,15 +2473,27 @@ def run_live_retrieval(
 
     # ── Step 3: prefetch off-topic filter ──────────────────────────
     if enable_prefetch_filter and candidates:
-        _pre_offtopic_urls = {c.url for c in candidates}
-        filt = filter_search_results(candidates, research_question)
-        candidates = filt.kept
-        for _dropped_url in _pre_offtopic_urls - {c.url for c in candidates}:
-            _trace_drop(_dropped_url, "offtopic")
-        notes.append(
-            f"prefetch_offtopic: {filt.total_kept} kept / "
-            f"{filt.total_rejected} rejected (threshold={filt.threshold_used:.2f})"
-        )
+        # FX-15b (#1119): EXCLUDE the injected seeds (empty title/snippet, source in
+        # _SEED_SOURCE_LABELS) from the semantic off-topic filter. They have no snippet to embed,
+        # so `filter_search_results` would score them ~0 similarity and REJECT the entire reserved
+        # seed lane (e.g. all agentic seeds). Filter only the non-seed search candidates; re-prepend
+        # the seeds untouched (mirrors the seed split in `_rerank_and_reserve`). Seeds are never
+        # off-topic-dropped — exactly as before this lane could enable the filter.
+        _seed_cands = [c for c in candidates if getattr(c, "source", "") in _SEED_SOURCE_LABELS]
+        _nonseed_cands = [
+            c for c in candidates if getattr(c, "source", "") not in _SEED_SOURCE_LABELS
+        ]
+        if _nonseed_cands:
+            _pre_offtopic_urls = {c.url for c in _nonseed_cands}
+            filt = filter_search_results(_nonseed_cands, research_question)
+            candidates = _seed_cands + filt.kept
+            for _dropped_url in _pre_offtopic_urls - {c.url for c in filt.kept}:
+                _trace_drop(_dropped_url, "offtopic")
+            notes.append(
+                f"prefetch_offtopic: {filt.total_kept} kept / "
+                f"{filt.total_rejected} rejected (threshold={filt.threshold_used:.2f})"
+            )
+        # else: only seeds present (e.g. seed_only mode) — nothing to off-topic filter.
     kept_by_offtopic = len(candidates)
 
     # ── Step 4: fetch-time relevance rerank + per-sub-query reservation, then cap ──
diff --git a/tests/polaris_graph/test_fx15b_host_filter_iready017.py b/tests/polaris_graph/test_fx15b_host_filter_iready017.py
new file mode 100644
index 00000000..840d40ca
--- /dev/null
+++ b/tests/polaris_graph/test_fx15b_host_filter_iready017.py
@@ -0,0 +1,90 @@
+"""FX-15b (I-ready-017 #1119): host-class junk filter + seed-safe semantic prefetch.
+
+(1) `_is_low_content_host_or_page` — a precision-first structural reject of nav/SERP/conference
+    pages, applied to agentic-discovered seed URLs before fetch. MUST never drop a real article.
+(2) Step-3 prefetch off-topic filter now EXCLUDES injected seeds (empty-snippet, source in
+    _SEED_SOURCE_LABELS) so enabling `enable_prefetch_filter=True` on the agentic seed lane can no
+    longer drop every URL-only seed as ~0-similarity off-topic.
+
+Quality/precision fix — no grounding/strict_verify/4-role change. Offline, no network.
+"""
+from __future__ import annotations
+
+import src.polaris_graph.retrieval.live_retriever as lr
+from src.polaris_graph.retrieval.live_retriever import _is_low_content_host_or_page
+from src.polaris_graph.retrieval.prefetch_offtopic_filter import FilterResult
+
+# (url, expected_reject) — held drb_72 trace shapes + real-article controls.
+_REJECT = [
+    "https://www.aeaweb.org/conference/2009/retrieve.php?pdfid=139",
+    "https://www.aeaweb.org/conference/2019/preliminary/paper/Ri8niS2D",
+    "https://www.aeaweb.org/conference/2023/program/paper/8A8RRTQY",
+    "https://www.aeaweb.org/journals/search-results?from=a&page=156&per-page=21",
+    "https://www.aeaweb.org/journals/search-results?from=a&page=216&per-page=21",
+    "https://www.aeaweb.org/forum/232/ba-wanting-to-gain-exposure",
+    "https://www.aeaweb.org/issues/381",
+    "https://www.google.com/search?q=labor+economics",
+    "https://example.org/browse/all",
+    "https://soc.org/annual-meeting/2024/schedule",
+    "https://www.journals.uchicago.edu/toc/jpe/2020/128/6",
+    "https://www.journals.uchicago.edu/toc/jpe/current",
+]
+_KEEP = [
+    "https://www.aeaweb.org/articles?id=10.1257/jep.29.3.3",
+    "https://www.aeaweb.org/articles?id=10.1257/aer.104.8.2509",
+    "https://pubs.aeaweb.org/doi/10.1257/aer.104.8.2509",
+    "https://arxiv.org/abs/2401.00001",
+    "https://www.nber.org/papers/w12345",
+    "https://doi.org/10.1056/NEJMoa1107039",
+]
+
+
+def test_low_content_filter_rejects_nav_serp_conference():
+    for u in _REJECT:
+        assert _is_low_content_host_or_page(u, "") is True, f"should REJECT low-content: {u}"
+
+
+def test_low_content_filter_keeps_real_articles_precision():
+    """PRECISION GATE: not a single real article/abstract URL may be dropped."""
+    for u in _KEEP:
+        assert _is_low_content_host_or_page(u, "") is False, f"must KEEP real source: {u}"
+
+
+def test_low_content_filter_empty_url_is_kept():
+    assert _is_low_content_host_or_page("", "") is False
+
+
+def _stub_fetch(url, max_chars, **kwargs):
+    return (
+        "Apixaban reduced stroke versus warfarin in atrial fibrillation patients. " * 8,
+        True, "Stub Title", "html", "",
+    )
+
+
+def _reject_all_filter(candidates, research_question, threshold=None):
+    """Simulate an embedder that rejects EVERY candidate (worst case for seeds)."""
+    return FilterResult(
+        kept=[], rejected=list(candidates), threshold_used=0.99,
+        total_in=len(candidates), total_kept=0, total_rejected=len(candidates),
+    )
+
+
+def test_step3_excludes_seeds_from_offtopic_filter(monkeypatch):
+    """The latent bug FX-15b fixes: with enable_prefetch_filter=True and a reject-all embedder, an
+    empty-snippet injected seed must STILL survive (it is excluded from the off-topic filter).
+    Pre-fix, the seed would be dropped as ~0-similarity off-topic and produce no evidence row."""
+    monkeypatch.setattr(lr, "_fetch_content", _stub_fetch)
+    monkeypatch.setattr(lr, "filter_search_results", _reject_all_filter)
+    res = lr.run_live_retrieval(
+        research_question="anticoagulation in atrial fibrillation",
+        seed_urls=["https://www.aeaweb.org/articles?id=10.1257/y"],
+        seed_only=True,
+        seed_source="agentic_seed",
+        seed_query_origin="agentic_seed",
+        enable_prefetch_filter=True,   # ON — but seeds are excluded from the filter
+        enable_openalex_enrich=False,
+        fetch_cap=5,
+    )
+    rows = [r for r in res.evidence_rows if r["source_url"] == "https://www.aeaweb.org/articles?id=10.1257/y"]
+    assert rows, "the agentic seed must survive the off-topic filter (seed-exclusion), not be dropped"
+    assert rows[0]["source"] == "agentic_seed"
```
