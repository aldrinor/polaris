# FX-15b (#1119) diff-gate — ITER 2 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
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
Quality/precision fix; faithfulness-safety = precision (never drop a page that bears evidence) +
seed-exclusion (never drop the agentic seed lane). Diff: `.codex/I-ready-017/fx15b_codex_diff.patch`
(vs FX-15a verified tip `83e7ebfd`).

## Your iter-1 verdict (addressed)
- **P1:** blanket `/conference` reject false-dropped real papers — `evidence_pool.json` shows
  `/conference/2025/program/paper/S7SHZQ4n` + `/S25ktKkD` fetched real content; same shape as junk
  `8A8RRTQY`. "Narrow the filter; add regression fixtures for the held S7SHZQ4n/S25ktKkD URLs."
- **P2:** the precision smoke omitted the held program-paper URLs that yielded full evidence.

## What iter-2 changed (exactly your findings)
1. **Narrowed `_LOW_CONTENT_PATH_MARKERS`** to PURE-nav only: `/search`, `/browse`, `/issues/`,
   `/forum/`, `/toc/` + SERP query strings (`search-results`, `per-page=`). **REMOVED** `/conference`
   and `/annual-meeting` (can prefix real papers) AND the `_detect_conference_abstract` call from the
   pre-fetch path (supplement abstracts bear abstract-level evidence) — these are now decided by the
   POST-fetch tier classifier + content-starvation check, never pre-fetch dropped. (Removed the now
   unused `_detect_conference_abstract` import.)
2. **P2 regression**: added `test_held_conference_papers_not_dropped_regression` asserting the exact
   held URLs (S7SHZQ4n, S25ktKkD) are KEPT, plus those + 8A8RRTQY + the OUP supplement + a synthetic
   annual-meeting paper added to the precision KEEP set.

## Evidence — §-1.1 re-audit with evidence_pool.json cross-reference
`outputs/audits/I-ready-017/fx15b_s11_audit.md`: 41 agentic rows → **DROP 7 / KEEP 34, 0 false
drops**. All 7 dropped have **0 evidence** in evidence_pool (issues / forum / search-results×2 /
search-index / toc×2). Both real conference papers (S7SHZQ4n=50k, S25ktKkD=30k chars) now KEPT.
- **Offline smoke — `test_fx15b_host_filter_iready017.py` → 5 passed**: pure-nav reject table;
  precision gate (11 KEEP incl. the held conference papers + supplement + working-paper PDFs, ZERO
  dropped); the P1 regression; empty-URL kept; seed-exclusion repro (reject-ALL embedder + empty
  seed → seed survives).
- Regression: FX-15a (6) + `test_live_retriever_rerank` (8) + `test_retrieval_trace` (7) +
  `test_plan_sufficiency_phase3` (26) all pass.

## Division of labor (the precision principle now applied)
The pre-fetch STRUCTURAL floor drops ONLY pages that cannot contain a paper (SERP/TOC/browse/forum).
Conference papers, supplement abstracts, working-paper PDFs are KEPT and go to fetch; the existing
POST-fetch tier classifier + `is_content_starved` + the (now seed-safe) semantic filter handle their
tiering/dropping. The seed-exclusion in Step-3 is unchanged from iter-1.

## Question
Is the narrowed precision boundary correct (drop only pure-nav; keep anything that could fetch
evidence), and the seed-exclusion still sound? Anything blocking APPROVE?

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
index 93b62863..315205eb 100644
--- a/src/polaris_graph/retrieval/live_retriever.py
+++ b/src/polaris_graph/retrieval/live_retriever.py
@@ -2102,6 +2102,46 @@ _SEED_SOURCE_LABELS: frozenset[str] = frozenset(
 )
 
 
+# FX-15b (#1119): path/route markers for pages that CANNOT carry a single paper's content — pure
+# navigation / search-result / table-of-contents / discussion listings. Matched as lowercase
+# substrings of the URL. Chosen PRECISION-FIRST and EMPIRICALLY (Codex iter-1 P1 + evidence_pool.json
+# cross-reference on the held drb_72 trace): every one appears ONLY on listing/nav pages, never on a
+# page that fetched real evidence.
+#
+# DELIBERATELY EXCLUDED (Codex iter-1 P1 — these CAN bear evidence, so pre-fetch dropping is a
+# precision failure; the POST-fetch tier classifier + content-starvation check handle the empty ones):
+#   - `/conference/.../program/paper/<id>` — held S7SHZQ4n (50k chars) + S25ktKkD (30k chars) fetched
+#     as REAL papers; the junk 8A8RRTQY has the IDENTICAL shape, so URL cannot distinguish them.
+#   - `/annual-meeting/.../paper/...` — same ambiguity as conference papers.
+#   - conference SUPPLEMENT abstracts (`/Supplement_`) — bear abstract-level evidence; let the tier
+#     classifier DOWN-TIER them (it already does) rather than pre-fetch DROP them.
+# `/issue/` (singular) is NOT a marker (it prefixes real article paths); `/issues/` (plural TOC
+# listing) IS.
+_LOW_CONTENT_PATH_MARKERS: tuple[str, ...] = (
+    "/search", "/browse", "/issues/", "/forum/",
+    "/toc/",  # journal table-of-contents listing (e.g. /toc/jpe/current) — never a real article
+)
+
+
+def _is_low_content_host_or_page(url: str, title: str = "") -> bool:
+    """FX-15b (#1119): structural reject of pure NAV / SERP / table-of-contents / discussion URLs,
+    applied to agentic-discovered seed URLs BEFORE fetch (a cheap deterministic floor that skips a
+    wasted fetch on pages that cannot contain a paper). PRECISION-FIRST — must NEVER reject a page
+    that could fetch real evidence (conference papers, supplement abstracts, working-paper PDFs are
+    all KEPT and decided by the post-fetch tier classifier + content-starvation check). Pure + no
+    network. Returns True iff the URL is a pure listing/nav page that should be dropped.
+    """
+    if not url:
+        return False
+    u = url.lower()
+    if any(marker in u for marker in _LOW_CONTENT_PATH_MARKERS):
+        return True
+    # Paginated SERP / search-result listing pages (not an article).
+    if "search-results" in u or "per-page=" in u:
+        return True
+    return False
+
+
 def _rerank_and_reserve(
     candidates: list["SearchCandidate"],
     *,
@@ -2437,15 +2477,27 @@ def run_live_retrieval(
 
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
index 00000000..a03f1f22
--- /dev/null
+++ b/tests/polaris_graph/test_fx15b_host_filter_iready017.py
@@ -0,0 +1,112 @@
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
+# Pure NAV / SERP / TOC / discussion listing pages (held drb_72 trace shapes + synthetic) — REJECT.
+_REJECT = [
+    "https://www.aeaweb.org/journals/search-results?from=a&page=156&per-page=21",
+    "https://www.aeaweb.org/journals/search-results?from=a&page=216&per-page=21",
+    "https://www.aeaweb.org/search/index?jelcode=b1&type=&page=504",
+    "https://www.aeaweb.org/forum/232/ba-wanting-to-gain-exposure",
+    "https://www.aeaweb.org/issues/381",
+    "https://www.google.com/search?q=labor+economics",
+    "https://example.org/browse/all",
+    "https://www.journals.uchicago.edu/toc/jpe/2020/128/6",
+    "https://www.journals.uchicago.edu/toc/jpe/current",
+]
+# Real articles AND pages that CAN bear evidence (conference papers, supplement abstracts,
+# annual-meeting papers, working-paper PDFs) — KEEP (post-fetch tier classifier decides). Codex
+# iter-1 P1: the structural filter MUST NOT pre-fetch-drop these.
+_KEEP = [
+    "https://www.aeaweb.org/articles?id=10.1257/jep.29.3.3",
+    "https://www.aeaweb.org/articles?id=10.1257/aer.104.8.2509",
+    "https://pubs.aeaweb.org/doi/10.1257/aer.104.8.2509",
+    "https://arxiv.org/abs/2401.00001",
+    "https://www.nber.org/papers/w12345",
+    "https://doi.org/10.1056/NEJMoa1107039",
+    # Held drb_72 conference program-paper URLs that fetched REAL papers (evidence_pool.json):
+    "https://www.aeaweb.org/conference/2025/program/paper/S7SHZQ4n",  # 50k chars
+    "https://www.aeaweb.org/conference/2025/program/paper/S25ktKkD",  # 30k chars
+    # Same shape, junk in this run — but URL cannot distinguish, so KEEP (post-fetch drops it):
+    "https://www.aeaweb.org/conference/2023/program/paper/8A8RRTQY",
+    # Conference supplement abstract — bears abstract-level evidence; tier classifier down-tiers it:
+    "https://academic.oup.com/ooec/article/3/Supplement_1/i906/7708121",
+    "https://soc.org/annual-meeting/2024/program/paper/abc",
+]
+
+
+# Codex iter-1 P1 regression: the EXACT held URLs that fetched real evidence must NEVER be dropped.
+_HELD_FALSE_DROP_REGRESSION = [
+    "https://www.aeaweb.org/conference/2025/program/paper/S7SHZQ4n",
+    "https://www.aeaweb.org/conference/2025/program/paper/S25ktKkD",
+]
+
+
+def test_held_conference_papers_not_dropped_regression():
+    """Codex iter-1 P1: these held agentic URLs each fetched a real paper (50k / 30k chars in
+    evidence_pool.json). A blanket /conference reject false-dropped them — must stay KEPT."""
+    for u in _HELD_FALSE_DROP_REGRESSION:
+        assert _is_low_content_host_or_page(u, "") is False, f"P1 regression — must KEEP real paper: {u}"
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
