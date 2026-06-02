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


## ==== DIFF ====
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
index a7443113..c91e61e5 100644
--- a/src/polaris_graph/retrieval/frame_fetcher.py
+++ b/src/polaris_graph/retrieval/frame_fetcher.py
@@ -209,6 +209,18 @@ _OPENALEX_FRAME_FALLBACK_ENABLED = (
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
 
 _DEFAULT_TIMEOUT = float(os.getenv("PG_FRAME_FETCHER_TIMEOUT", "15"))
 _MAX_RETRIES = int(os.getenv("PG_FRAME_FETCHER_MAX_RETRIES", "3"))
@@ -766,6 +778,37 @@ def _call_openalex(
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
@@ -1151,7 +1194,7 @@ def _fetch_frame_entity_inner(
         and doi
         and not abstract_crossref
         and not abstract_pubmed
-        and (not oa_full_text or len(oa_full_text) < _OA_FULLTEXT_MIN_CHARS)
+        and (not _is_usable_full_text(oa_full_text) or _FRAME_PREFER_ABSTRACT)
     ):
         oa_meta, oa_attempts, oa_timings = _call_openalex(client, doi)
         attempts.extend(oa_attempts)
@@ -1191,22 +1234,38 @@ def _fetch_frame_entity_inner(
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
+    if _FRAME_PREFER_ABSTRACT and abstract_text:
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
index 5ec023db..36439aad 100644
--- a/tests/polaris_graph/test_m56_frame_fetcher.py
+++ b/tests/polaris_graph/test_m56_frame_fetcher.py
@@ -1490,3 +1490,105 @@ class TestOpenAlexThinStubRichest:
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
+    def test_prefer_abstract_flag_uses_abstract_over_clean_fulltext(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        """With PG_FRAME_PREFER_ABSTRACT on (run_gate_b sets it), the clean
+        deterministic abstract is preferred over even a clean long OA scrape
+        — eliminating the non-deterministic-scrape dependency."""
+        monkeypatch.setattr(
+            "src.polaris_graph.retrieval.frame_fetcher._FRAME_PREFER_ABSTRACT",
+            True,
+        )
+        clean_full = "Clean genuine full text. " * 120  # >=1200, clean
+        monkeypatch.setattr(
+            "src.polaris_graph.retrieval.frame_fetcher._fetch_url_pattern",
+            lambda url: (clean_full, url),
+        )
+        transport = _Transport([
+            ("api.crossref.org", 200, _crossref_response()),  # has abstract
+            ("api.unpaywall.org", 200, _unpaywall_response(
+                is_oa=True, pdf_url="https://oa.example/x.pdf")),
+        ])
+        with _client_with_transport(transport) as client:
+            row = fetch_frame_entity(_binding(), client=client)
+        assert row.quote_source == "crossref_abstract"  # NOT oa_full_text
+        assert "tirzepatide" in row.direct_quote.lower()
+        assert "Clean genuine full text" not in row.direct_quote
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
End with the YAML schema.
