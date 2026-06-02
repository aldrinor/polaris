# DUAL RE-AUDIT iter2 — I-meta-008 #1034 (P1s addressed)

In iter1 the two independent auditors converged on 3 P1s. Confirm each is resolved in the v4 diff.

P1-a (both): "flag only changed source selection; Step 2b still scraped + could hit Sci-Hub."
  FIX: narrative entities under prefer-abstract now SKIP Step 2b entirely (oa_locator and
  entity_prefers_abstract -> log skipped:prefer_abstract, no _fetch_url_pattern call). Live-verified:
  Acemoglu (economic_report) 3x identical, quote_source=crossref_abstract, scrape_skipped=True.

P1-b (Codex): "Sci-Hub PDF text (clean, not HTML) could become oa_full_text."
  FIX: _fetch_url_pattern rejects content when result.access_method contains 'scihub'/'sci-hub'
  (HTML AND PDF, on BOTH narrative-skip and clinical paths). Test test_scihub_access_method_rejected.

P1-c (Claude): "run_gate_b set flag benchmark-global incl. clinical questions whose Gate-B Lane-2
  coverage needs full-text tables."
  FIX: _FULLTEXT_ENTITY_TYPES (pivotal_trial,clinical_trial,rct,systematic_review,meta_analysis)
  KEEP the full-text path even under the flag; entity_prefers_abstract is False for them. Only
  narrative types (economic_report,...) prefer the abstract. Test test_clinical_entity_type_keeps_fulltext_under_flag.

Residual: access_bypass still ISSUES the Sci-Hub request on the clinical full-text path (the flag/
reject only discards the result). Filed as URGENT follow-up Issue #1035 (gate PG_SCIHUB_ENABLED
default off) per both auditors' "out of scope for this diff". Confirm that scoping is acceptable.

Tests: 63/63 frame_fetcher + 94/94 consumers pass. Confirm the P1 resolutions and whether you APPROVE.
End with: verdict: APPROVE|REQUEST_CHANGES + p1: [...] (remaining only).

## ==== v4 DIFF ====
```diff
diff --git a/scripts/dr_benchmark/run_gate_b.py b/scripts/dr_benchmark/run_gate_b.py
index 530a5bdb..fbde5a78 100644
--- a/scripts/dr_benchmark/run_gate_b.py
+++ b/scripts/dr_benchmark/run_gate_b.py
@@ -451,6 +451,12 @@ async def run_gate_b_query(
     # span-verifiable abstract yield. `setdefault` so an explicit operator override still wins (LAW VI).
     os.environ.setdefault("PG_UNPAYWALL_ENABLED", "1")
     os.environ.setdefault("PG_TRAFILATURA_ENABLED", "1")
+    # #1034: paywalled-journal OA fetches are non-deterministic + noisy (Sci-Hub HTML / Jina
+    # landing-page markdown / intermittent CrossRef abstract). For frame-contract grounding the
+    # clean, deterministic abstract (CrossRef/OpenAlex) is the correct source — contract fields
+    # are abstract-level claims. Prefer it over the scrape; setdefault keeps the operator override.
+    os.environ.setdefault("PG_FRAME_PREFER_ABSTRACT", "1")
+    os.environ.setdefault("PG_OPENALEX_FRAME_FALLBACK", "1")
     if transport is not None:
         active_transport = transport               # offline/test: injected fake
     else:
diff --git a/src/polaris_graph/retrieval/frame_fetcher.py b/src/polaris_graph/retrieval/frame_fetcher.py
index a7443113..7ec7abf0 100644
--- a/src/polaris_graph/retrieval/frame_fetcher.py
+++ b/src/polaris_graph/retrieval/frame_fetcher.py
@@ -209,6 +209,32 @@ _OPENALEX_FRAME_FALLBACK_ENABLED = (
 # fall below this -> they must not block the abstract fallbacks and
 # must lose to a real abstract (e.g. OpenAlex 1331 chars).
 _OA_FULLTEXT_MIN_CHARS = int(os.getenv("PG_OA_FULLTEXT_MIN_CHARS", "1200"))
+# Prefer the clean, deterministic abstract (CrossRef/OpenAlex/PubMed) over a
+# scraped OA "full text" for frame-contract grounding (#1034). Ground-truthed:
+# paywalled-journal OA fetches are NON-DETERMINISTIC (Sci-Hub HTML one call,
+# Jina landing-page markdown the next, clean CrossRef abstract a third) and
+# noisy, while the abstract is clean and stable — and contract fields
+# (thesis/mechanism/effect) are abstract-level claims. Default OFF preserves
+# the M-66b-T clinical full-text path (multi-field trial rosters live in
+# tables, not abstracts); run_gate_b sets it ON for the benchmark.
+_FRAME_PREFER_ABSTRACT = (
+    os.getenv("PG_FRAME_PREFER_ABSTRACT", "0").strip().lower()
+    in ("1", "true", "yes", "on")
+)
+# Entity types whose contract fields live in full-text TABLES (clinical trial
+# 9-field rosters etc.) KEEP the OA full-text path even under prefer-abstract,
+# so Gate-B gold-rubric coverage for clinical questions is preserved (dual-audit
+# #1034 P1). Narrative entity types (economic_report, ...) prefer the clean
+# abstract AND skip the scrape entirely (no non-deterministic fetch, no Sci-Hub
+# request).
+_FULLTEXT_ENTITY_TYPES = frozenset(
+    t.strip().lower()
+    for t in os.getenv(
+        "PG_FRAME_FULLTEXT_ENTITY_TYPES",
+        "pivotal_trial,clinical_trial,rct,systematic_review,meta_analysis",
+    ).split(",")
+    if t.strip()
+)
 
 _DEFAULT_TIMEOUT = float(os.getenv("PG_FRAME_FETCHER_TIMEOUT", "15"))
 _MAX_RETRIES = int(os.getenv("PG_FRAME_FETCHER_MAX_RETRIES", "3"))
@@ -766,6 +792,37 @@ def _call_openalex(
     return data, attempts, timings
 
 
+def _looks_like_html_junk(text: str) -> bool:
+    """True when a fetched 'full text' is actually raw HTML markup or a
+    Sci-Hub wrapper page rather than clean extracted prose (#1034
+    follow-up). Ground-truthed: aeaweb paywalled econ papers (e.g.
+    Acemoglu 10.1257/jep.33.2.3) come back as a ~25K-char Sci-Hub HTML
+    viewer page that passes any length threshold but is useless for M-58
+    extraction. Inspects the head of the content for HTML structural
+    markers or Sci-Hub branding (case-insensitive)."""
+    head = text[:600].lower()
+    return (
+        "<!doctype" in head
+        or "<html" in head
+        or "<head>" in head
+        or "<head " in head
+        or "<body" in head
+        or "sci-hub" in head
+    )
+
+
+def _is_usable_full_text(text: str | None) -> bool:
+    """A fetched OA full text is usable as the rich `direct_quote` source
+    only if it is SUBSTANTIAL (>= _OA_FULLTEXT_MIN_CHARS) AND clean prose
+    (not HTML / Sci-Hub junk). Otherwise the abstract fallbacks
+    (CrossRef / OpenAlex / PubMed) must take over (#1034)."""
+    return bool(
+        text
+        and len(text) >= _OA_FULLTEXT_MIN_CHARS
+        and not _looks_like_html_junk(text)
+    )
+
+
 def _pick_richest_abstract(
     *,
     crossref: str | None,
@@ -858,6 +915,13 @@ def _fetch_url_pattern(url: str) -> tuple[str, str]:
                 return "", ""
             content = getattr(result, "content", "") or ""
             final_url = getattr(result, "url", "") or url
+            method = (getattr(result, "access_method", "") or "").lower()
+            # Never use pirate-source (Sci-Hub) content in a research /
+            # clinical product — legal + provenance (#1034 dual-audit P1).
+            # Rejects BOTH the Sci-Hub HTML viewer page AND clean Sci-Hub
+            # PDF text (which _looks_like_html_junk cannot detect).
+            if "scihub" in method or "sci-hub" in method:
+                return "", ""
             if not content:
                 return "", ""
             return content[:_M66_CONTENT_CAP], final_url
@@ -1037,6 +1101,15 @@ def _fetch_frame_entity_inner(
     abstract_crossref: str | None = None
     doi = identifiers.get("doi")
     pmid = identifiers.get("pmid")
+    # Entity-scoped prefer-abstract (#1034 dual-audit P1): a narrative
+    # frame entity (economic_report, ...) under the flag prefers the clean
+    # abstract AND skips the OA scrape entirely; a full-text entity type
+    # (clinical trial rosters) keeps the full-text path so Gate-B coverage
+    # is preserved.
+    entity_prefers_abstract = (
+        _FRAME_PREFER_ABSTRACT
+        and binding.entity_type.strip().lower() not in _FULLTEXT_ENTITY_TYPES
+    )
 
     # Step 1: CrossRef for metadata + abstract when DOI present
     if doi:
@@ -1071,7 +1144,18 @@ def _fetch_frame_entity_inner(
     # full text, giving M-58 enough surface to extract SURPASS
     # 9-field rosters. Falls back to abstract on fetch failure.
     oa_locator = oa_pdf_url or oa_html_url
-    if oa_locator:
+    if oa_locator and entity_prefers_abstract:
+        # Narrative frame entity under prefer-abstract: SKIP the OA scrape
+        # entirely — no non-deterministic AccessBypass call, no Sci-Hub
+        # request (#1034 dual-audit P1). The clean abstract is the source.
+        attempts.append(RetrievalAttempt(
+            source="access_bypass",
+            url=f"oa_full_text_skipped:{oa_locator}",
+            attempt_index=1,
+            http_status=None,
+            outcome="skipped:prefer_abstract",
+        ))
+    elif oa_locator:
         full_text, final_url = _fetch_url_pattern(oa_locator)
         if full_text:
             oa_full_text = full_text
@@ -1151,7 +1235,7 @@ def _fetch_frame_entity_inner(
         and doi
         and not abstract_crossref
         and not abstract_pubmed
-        and (not oa_full_text or len(oa_full_text) < _OA_FULLTEXT_MIN_CHARS)
+        and (not _is_usable_full_text(oa_full_text) or entity_prefers_abstract)
     ):
         oa_meta, oa_attempts, oa_timings = _call_openalex(client, doi)
         attempts.extend(oa_attempts)
@@ -1191,22 +1275,38 @@ def _fetch_frame_entity_inner(
     # (e.g. aeaweb returns ~540 chars via Jina) is NOT usable full text
     # (issue #1034). Only treat oa_full_text as real full text above the
     # threshold; otherwise it competes as a last-priority partial.
-    real_full_text = (
-        oa_full_text
-        if (oa_full_text and len(oa_full_text) >= _OA_FULLTEXT_MIN_CHARS)
-        else None
-    )
-    # Richest abstract across CrossRef/OpenAlex/PubMed (+ a thin
-    # oa_full_text stub as last resort), longest wins (#1033/#1034).
+    real_full_text = oa_full_text if _is_usable_full_text(oa_full_text) else None
+    # Richest abstract across CrossRef/OpenAlex/PubMed (+ a thin but CLEAN
+    # oa_full_text stub as last resort), longest wins (#1033/#1034). HTML /
+    # Sci-Hub junk is never admitted as a partial — it would poison the span.
     abstract_text, abstract_quote_source = _pick_richest_abstract(
         crossref=abstract_crossref,
         openalex=abstract_openalex,
         pubmed=abstract_pubmed,
-        partial_full_text=(oa_full_text if not real_full_text else None),
+        partial_full_text=(
+            oa_full_text
+            if (
+                oa_full_text
+                and not real_full_text
+                and not _looks_like_html_junk(oa_full_text)
+            )
+            else None
+        ),
     )
-    if real_full_text:
+    if entity_prefers_abstract and abstract_text:
+        # Frame-contract grounding (#1034): the clean, deterministic
+        # abstract is preferred over a non-deterministic / noisy OA scrape.
+        # Contract fields (thesis/mechanism/effect) are abstract-level claims.
+        direct_quote = abstract_text
+        quote_source = abstract_quote_source
+        provenance = (
+            ProvenanceClass.OPEN_ACCESS if any_oa_url
+            else ProvenanceClass.ABSTRACT_ONLY
+        )
+        failure_reason = None
+    elif real_full_text:
         # V30 Phase-2 M-66b-T: real OA full text — rich source for
-        # M-58's multi-field extractions.
+        # M-58's multi-field extractions (default path; clinical rosters).
         direct_quote = real_full_text
         quote_source = "oa_full_text"
         provenance = ProvenanceClass.OPEN_ACCESS
diff --git a/tests/polaris_graph/test_m56_frame_fetcher.py b/tests/polaris_graph/test_m56_frame_fetcher.py
index 5ec023db..62c67a5c 100644
--- a/tests/polaris_graph/test_m56_frame_fetcher.py
+++ b/tests/polaris_graph/test_m56_frame_fetcher.py
@@ -1490,3 +1490,170 @@ class TestOpenAlexThinStubRichest:
             )
         assert row.provenance_class == ProvenanceClass.METADATA_ONLY
         assert row.direct_quote == ""
+
+
+# ─────────────────────────────────────────────────────────────────────
+# (10) HTML/Sci-Hub junk full-text + prefer-abstract flag (issue #1034)
+# ─────────────────────────────────────────────────────────────────────
+_SCIHUB_HTML = (
+    '<!DOCTYPE html>\n<html>\n<head><title>Sci-Hub. Automation and New '
+    'Tasks</title></head>\n<body>' + ("nav " * 6000) + '</body></html>'
+)  # ~25K chars, looks_html True
+
+
+class TestHtmlJunkAndPreferAbstract:
+    def test_looks_like_html_junk_and_usable_helpers(self) -> None:
+        from src.polaris_graph.retrieval.frame_fetcher import (
+            _looks_like_html_junk, _is_usable_full_text,
+        )
+        assert _looks_like_html_junk(_SCIHUB_HTML) is True
+        assert _looks_like_html_junk("<html><body>x</body></html>") is True
+        assert _looks_like_html_junk("Sci-Hub viewer page " * 50) is True
+        assert _looks_like_html_junk("Clean prose about automation." * 50) is False
+        assert _is_usable_full_text("Clean prose. " * 200) is True   # long+clean
+        assert _is_usable_full_text(_SCIHUB_HTML) is False           # junk
+        assert _is_usable_full_text("short") is False               # < threshold
+        assert _is_usable_full_text(None) is False
+
+    def test_scihub_html_fulltext_rejected_openalex_wins(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        """THE real run-6 bug: the OA fetch returns a 25K-char Sci-Hub HTML
+        page (passes any length check). It must be rejected as junk and the
+        clean OpenAlex abstract used instead. (flag OFF — junk rejection is
+        unconditional.)"""
+        monkeypatch.setattr(
+            "src.polaris_graph.retrieval.frame_fetcher._fetch_url_pattern",
+            lambda url: (_SCIHUB_HTML, url),
+        )
+        cr_no_abs = _crossref_response(abstract=None)
+        transport = _Transport([
+            ("api.crossref.org", 200, cr_no_abs),
+            ("api.unpaywall.org", 200, _unpaywall_response(
+                is_oa=True,
+                pdf_url="https://www.aeaweb.org/articles/pdf/x.pdf")),
+            ("api.openalex.org", 200,
+             _openalex_response(sentence=_LONG_OPENALEX_SENTENCE)),
+        ])
+        with _client_with_transport(transport) as client:
+            row = fetch_frame_entity(
+                _binding(
+                    primary="doi:10.1056/NEJMoa2107519", secondaries=()
+                ),
+                client=client,
+            )
+        assert row.quote_source == "openalex_abstract"  # NOT the HTML junk
+        assert "<!DOCTYPE" not in row.direct_quote
+        assert "Sci-Hub" not in row.direct_quote
+        assert "finding200" in row.direct_quote
+
+    def test_prefer_abstract_narrative_skips_scrape_uses_abstract(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        """Flag on + NARRATIVE entity type (economic_report): the OA scrape
+        is SKIPPED entirely (no AccessBypass / Sci-Hub request — #1034 P1)
+        and the clean abstract is used. _fetch_url_pattern must NOT be
+        called."""
+        monkeypatch.setattr(
+            "src.polaris_graph.retrieval.frame_fetcher._FRAME_PREFER_ABSTRACT",
+            True,
+        )
+
+        def _boom(url):  # pragma: no cover - asserts non-invocation
+            raise AssertionError("scrape must be skipped under prefer-abstract")
+        monkeypatch.setattr(
+            "src.polaris_graph.retrieval.frame_fetcher._fetch_url_pattern",
+            _boom,
+        )
+        transport = _Transport([
+            ("api.crossref.org", 200, _crossref_response()),  # has abstract
+            ("api.unpaywall.org", 200, _unpaywall_response(
+                is_oa=True, pdf_url="https://oa.example/x.pdf")),
+        ])
+        with _client_with_transport(transport) as client:
+            row = fetch_frame_entity(
+                _binding(entity_type="economic_report"), client=client
+            )
+        assert row.quote_source == "crossref_abstract"  # NOT oa_full_text
+        assert any(
+            a.outcome == "skipped:prefer_abstract"
+            for a in row.retrieval_attempts
+        )
+
+    def test_clinical_entity_type_keeps_fulltext_under_flag(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        """Flag on + CLINICAL entity type (pivotal_trial): full-text path is
+        PRESERVED (clinical 9-field rosters live in tables) — Gate-B coverage
+        protected (#1034 P1)."""
+        monkeypatch.setattr(
+            "src.polaris_graph.retrieval.frame_fetcher._FRAME_PREFER_ABSTRACT",
+            True,
+        )
+        clean_full = "Clean genuine full text with trial roster. " * 60
+        monkeypatch.setattr(
+            "src.polaris_graph.retrieval.frame_fetcher._fetch_url_pattern",
+            lambda url: (clean_full, url),
+        )
+        transport = _Transport([
+            ("api.crossref.org", 200, _crossref_response()),
+            ("api.unpaywall.org", 200, _unpaywall_response(
+                is_oa=True, pdf_url="https://oa.example/x.pdf")),
+        ])
+        with _client_with_transport(transport) as client:
+            row = fetch_frame_entity(
+                _binding(entity_type="pivotal_trial"), client=client
+            )
+        assert row.quote_source == "oa_full_text"  # clinical keeps full text
+        assert "trial roster" in row.direct_quote
+
+    def test_scihub_access_method_rejected_in_fetch_url_pattern(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        """A Sci-Hub source (even clean PDF text) is rejected at the
+        _fetch_url_pattern boundary by access_method — legal/provenance
+        (#1034 dual-audit P1). _looks_like_html_junk cannot see PDF
+        provenance, so this guard is the one that stops Sci-Hub PDF text."""
+        from src.polaris_graph.retrieval import frame_fetcher as ff
+        from src.tools.access_bypass import AccessResult
+
+        class _SciHubAB:
+            def __init__(self, *_a, **_kw) -> None:
+                pass
+
+            async def fetch_with_bypass(
+                self, url: str, prefer_legal: bool = True,
+            ) -> AccessResult:
+                return AccessResult(
+                    url=url,
+                    content="Clean paper body text from a pirate PDF." * 50,
+                    access_method="scihub_pdf",
+                    legal_alternative=None,
+                    success=True, metadata={},
+                )
+        monkeypatch.setattr(
+            "src.tools.access_bypass.AccessBypass", _SciHubAB,
+        )
+        content, final_url = ff._fetch_url_pattern("https://example.com/x.pdf")
+        assert content == ""  # Sci-Hub content rejected outright
+        assert final_url == ""
+
+    def test_prefer_abstract_off_keeps_fulltext(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        """Flag OFF (default): clean OA full text is still preferred —
+        preserves the M-66b-T clinical full-text path."""
+        clean_full = "Clean genuine full text. " * 120
+        monkeypatch.setattr(
+            "src.polaris_graph.retrieval.frame_fetcher._fetch_url_pattern",
+            lambda url: (clean_full, url),
+        )
+        transport = _Transport([
+            ("api.crossref.org", 200, _crossref_response()),
+            ("api.unpaywall.org", 200, _unpaywall_response(
+                is_oa=True, pdf_url="https://oa.example/x.pdf")),
+        ])
+        with _client_with_transport(transport) as client:
+            row = fetch_frame_entity(_binding(), client=client)
+        assert row.quote_source == "oa_full_text"
+        assert "Clean genuine full text" in row.direct_quote

```
End with the verdict schema.
