# DUAL INDEPENDENT AUDIT — I-meta-008 #1034: thin oa_full_text stub blocks OpenAlex fallback

You are one of TWO independent auditors (Claude + Codex) running in parallel per the
POLARIS §-1.1 line-by-line standard. Audit claim-by-claim against the actual code + the
run-6 evidence. Do NOT rubber-stamp. Surface every real finding.

## The change under review (v2 fix, committed)
`src/polaris_graph/retrieval/frame_fetcher.py` + tests. The diff is in
`.codex/I-meta-008-thinstub/codex_diff.patch`.

Summary of the v2 logic:
- New `_OA_FULLTEXT_MIN_CHARS` (default 1200). An OA full-text fetch shorter than this is
  treated as a STUB, not real full text.
- Step 4 OpenAlex fallback now fires when `not abstract_crossref and not abstract_pubmed
  and (not oa_full_text or len(oa_full_text) < _OA_FULLTEXT_MIN_CHARS)`.
- `_pick_richest_abstract(crossref, openalex, pubmed, partial_full_text)` chooses the
  LONGEST text; ties keep priority order (CrossRef > OpenAlex > PubMed > thin-partial).
- Decision: real full text (>= threshold) wins; else the richest abstract; a 540-char
  stub loses to a 1331-char OpenAlex abstract. Provenance OPEN_ACCESS if an OA locator
  existed, else ABSTRACT_ONLY.

## The diagnosis to verify (run-6 evidence in run6_frame_evidence.txt)
Claim: in run 6, `acemoglu_restrepo_automation_tasks` (the foundational "Automation and
New Tasks" JEP paper, DOI 10.1257/jep.33.2.3) came back provenance=open_access with
oa_full_text PRESENT but crossref_abstract ABSENT — i.e. the aeaweb PDF 403'd and Jina
returned a ~540-char STUB that was used as direct_quote, which the generator could not
extract fields from -> "not extractable". The old #1033 fallback was blocked because
oa_full_text was truthy. OpenAlex holds the real 1331-char abstract.

## What I need you to independently audit (line-by-line)
1. **Diff correctness**: is `_pick_richest_abstract` deterministic? (ties -> priority via
   strictly-greater while iterating; positions of equal length.) Any off-by-one / wrong
   branch / wrong provenance label?
2. **Threshold logic**: does the v2 change correctly let OpenAlex fire on a thin stub
   while still preferring a real long full text? Is 1200 a defensible boundary (a real
   full-text extraction is much longer; a paywall stub is ~540)? Any case where a
   legitimately short-but-real abstract is mishandled?
3. **Does v2 actually fix run-6's failures?** Walk EACH of the 7 entities in
   run6_frame_evidence.txt and state whether v2 grounds it, and with which source:
   - acemoglu_automation (oa_full_text stub, no crossref): does OpenAlex now fire + win?
   - acemoglu_robots (metadata_only): helped by #1033 already?
   - autor / frey_osborne (oa_full_text present, got real content run-6): unchanged?
   - brynjolfsson / eloundou (crossref_abstract present): NOT helped by OpenAlex — is that
     an honest residual (the effect number isn't in the abstract / generator-extraction
     issue), or does the diff need to also fire OpenAlex when crossref abstract is thin?
4. **Any OTHER bug** in the fetch path exposed by this change (determinism, the DOI guard,
   network discipline, the provenance downgrade when any_oa_url but empty quote)?
5. **Regression risk**: existing M-66b-T test uses full_text ~1650 chars (>=1200 -> still
   real full text). Confirm no existing behavior breaks.

## Output (required schema)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
p1: [...]
p2: [...]
per_entity_fix_assessment:
  acemoglu_automation: <fixed-by-openalex | still-broken | ...>
  acemoglu_robots: ...
  autor: ...
  frey_osborne: ...
  brynjolfsson: ...
  eloundou: ...
honest_residual: <what still reads as 'not extractable' after v2, and is that a fetch bug or a generator-extraction issue>
```
End with the schema as your final lines.


## ==== run6_frame_evidence.txt ====
```
=== run6 frame_coverage_report (the documented failure) ===
by_status: {"fail_min_fields": 1, "pass": 6}
  acemoglu_restrepo_automation_tasks         prov=open_access    oa_full_text=True crossref_abstract=False min_fields=3
  autor_why_still_jobs                       prov=open_access    oa_full_text=True crossref_abstract=False min_fields=2
  fourth_industrial_revolution_framing       prov=open_access    oa_full_text=False crossref_abstract=False min_fields=1
  acemoglu_restrepo_robots_jobs              prov=metadata_only  oa_full_text=False crossref_abstract=False min_fields=3
  frey_osborne_computerisation               prov=open_access    oa_full_text=True crossref_abstract=False min_fields=2
  brynjolfsson_genai_at_work                 prov=abstract_only  oa_full_text=False crossref_abstract=True min_fields=3
  eloundou_gpts_are_gpts                     prov=abstract_only  oa_full_text=False crossref_abstract=True min_fields=2

LIVE OpenAlex probe (verified this session, urllib direct):
  10.1257/jep.33.2.3 Acemoglu-Automation : 1331 chars  (was oa_full_text STUB -> not extractable)
  10.1086/705716     Acemoglu-Robots-JPE  : 688 chars   (was metadata_only)
  10.1257/jep.29.3.3 Autor-JEP            : 1530 chars
  10.1093/qje/qjae044 Brynjolfsson-QJE    : 1113 chars  (has crossref_abstract; not helped by OpenAlex)
  10.1126/science.adj0998 Eloundou-Science: 56 chars    (thin; has crossref_abstract)

```

## ==== DIFF UNDER REVIEW ====
```diff
diff --git a/src/polaris_graph/retrieval/frame_fetcher.py b/src/polaris_graph/retrieval/frame_fetcher.py
index ab39e260..33b9cca0 100644
--- a/src/polaris_graph/retrieval/frame_fetcher.py
+++ b/src/polaris_graph/retrieval/frame_fetcher.py
@@ -204,6 +204,11 @@ _OPENALEX_FRAME_FALLBACK_ENABLED = (
     os.getenv("PG_OPENALEX_FRAME_FALLBACK", "1").strip().lower()
     not in ("0", "false", "no", "off")
 )
+# Minimum chars for an OA full-text fetch to count as REAL full text
+# (issue #1034). Paywalled-PDF stubs (e.g. aeaweb via Jina ~540 chars)
+# fall below this -> they must not block the abstract fallbacks and
+# must lose to a real abstract (e.g. OpenAlex 1331 chars).
+_OA_FULLTEXT_MIN_CHARS = int(os.getenv("PG_OA_FULLTEXT_MIN_CHARS", "1200"))
 
 _DEFAULT_TIMEOUT = float(os.getenv("PG_FRAME_FETCHER_TIMEOUT", "15"))
 _MAX_RETRIES = int(os.getenv("PG_FRAME_FETCHER_MAX_RETRIES", "3"))
@@ -761,22 +766,38 @@ def _call_openalex(
     return data, attempts, timings
 
 
-def _pick_abstract(
+def _pick_richest_abstract(
+    *,
     crossref: str | None,
-    pubmed: str | None,
     openalex: str | None,
+    pubmed: str | None,
+    partial_full_text: str | None = None,
 ) -> tuple[str, str]:
-    """Choose the best available abstract text + its quote_source
-    label, in priority order: CrossRef (authoritative metadata
-    abstract) > PubMed (clinical) > OpenAlex (reconstructed fallback,
-    issue #1033). Returns ("", "none") when all are empty."""
+    """Choose the RICHEST (longest) available abstract text + its
+    quote_source label. Candidates in priority order CrossRef >
+    OpenAlex > PubMed > thin-OA-full-text partial; the LONGEST wins,
+    ties break toward the higher-priority source (deterministic —
+    strictly-greater comparison while iterating priority order).
+
+    A thin oa_full_text stub (paywalled-PDF Jina result, ~540 chars)
+    is admitted only as the last-priority `partial_full_text`
+    candidate, so a real abstract (e.g. OpenAlex 1331 chars) overrides
+    it rather than being blocked by it (issue #1034). Returns
+    ("", "none") when every candidate is empty."""
+    candidates: list[tuple[str, str]] = []
     if crossref:
-        return crossref, "crossref_abstract"
-    if pubmed:
-        return pubmed, "pubmed_abstract"
+        candidates.append((crossref, "crossref_abstract"))
     if openalex:
-        return openalex, "openalex_abstract"
-    return "", "none"
+        candidates.append((openalex, "openalex_abstract"))
+    if pubmed:
+        candidates.append((pubmed, "pubmed_abstract"))
+    if partial_full_text:
+        candidates.append((partial_full_text, "oa_full_text_partial"))
+    best: tuple[str, str] | None = None
+    for text, src in candidates:
+        if best is None or len(text) > len(best[0]):
+            best = (text, src)
+    return best if best is not None else ("", "none")
 
 
 def _urlsafe_doi(doi: str) -> str:
@@ -1126,7 +1147,7 @@ def _fetch_frame_entity_inner(
         and doi
         and not abstract_crossref
         and not abstract_pubmed
-        and not oa_full_text
+        and (not oa_full_text or len(oa_full_text) < _OA_FULLTEXT_MIN_CHARS)
     ):
         oa_meta, oa_attempts, oa_timings = _call_openalex(client, doi)
         attempts.extend(oa_attempts)
@@ -1162,28 +1183,39 @@ def _fetch_frame_entity_inner(
     # POLARIS content fetch infrastructure at M-57; the distinction
     # from ABSTRACT_ONLY is that a full-text source exists.
     any_oa_url = oa_pdf_url or oa_html_url
-    # Best available abstract across CrossRef/PubMed/OpenAlex (#1033),
-    # with its honest quote_source label.
-    abstract_text, abstract_quote_source = _pick_abstract(
-        abstract_crossref, abstract_pubmed, abstract_openalex
+    # A real OA full-text extraction is long; a paywalled-PDF stub
+    # (e.g. aeaweb returns ~540 chars via Jina) is NOT usable full text
+    # (issue #1034). Only treat oa_full_text as real full text above the
+    # threshold; otherwise it competes as a last-priority partial.
+    real_full_text = (
+        oa_full_text
+        if (oa_full_text and len(oa_full_text) >= _OA_FULLTEXT_MIN_CHARS)
+        else None
     )
-    if any_oa_url:
-        # V30 Phase-2 M-66b-T: when Step 2b succeeded in fetching
-        # OA full text, use it as direct_quote (rich source for
-        # M-58's 9-field SURPASS extractions). Else fall back to the
-        # best resolved abstract (CrossRef/PubMed/OpenAlex).
-        if oa_full_text:
-            direct_quote = oa_full_text
-            quote_source = "oa_full_text"
-        else:
-            direct_quote = abstract_text
-            quote_source = abstract_quote_source
+    # Richest abstract across CrossRef/OpenAlex/PubMed (+ a thin
+    # oa_full_text stub as last resort), longest wins (#1033/#1034).
+    abstract_text, abstract_quote_source = _pick_richest_abstract(
+        crossref=abstract_crossref,
+        openalex=abstract_openalex,
+        pubmed=abstract_pubmed,
+        partial_full_text=(oa_full_text if not real_full_text else None),
+    )
+    if real_full_text:
+        # V30 Phase-2 M-66b-T: real OA full text — rich source for
+        # M-58's multi-field extractions.
+        direct_quote = real_full_text
+        quote_source = "oa_full_text"
         provenance = ProvenanceClass.OPEN_ACCESS
         failure_reason = None
     elif abstract_text:
         direct_quote = abstract_text
         quote_source = abstract_quote_source
-        provenance = ProvenanceClass.ABSTRACT_ONLY
+        # OPEN_ACCESS when an OA locator existed (full text just wasn't
+        # extractable); else ABSTRACT_ONLY.
+        provenance = (
+            ProvenanceClass.OPEN_ACCESS if any_oa_url
+            else ProvenanceClass.ABSTRACT_ONLY
+        )
         failure_reason = None
     elif title:  # we have metadata but no abstract, no OA
         direct_quote = ""
diff --git a/tests/polaris_graph/test_m56_frame_fetcher.py b/tests/polaris_graph/test_m56_frame_fetcher.py
index 9eb5b9f7..a3ba3294 100644
--- a/tests/polaris_graph/test_m56_frame_fetcher.py
+++ b/tests/polaris_graph/test_m56_frame_fetcher.py
@@ -1332,3 +1332,105 @@ class TestOpenAlexFallback:
             )
         assert row.provenance_class == ProvenanceClass.METADATA_ONLY
         assert not any("openalex" in u for u in transport.call_log)
+
+
+# ─────────────────────────────────────────────────────────────────────
+# (9) Thin oa_full_text stub must not block OpenAlex (issue #1034)
+# ─────────────────────────────────────────────────────────────────────
+_LONG_OPENALEX_SENTENCE = "Tirzepatide " + " ".join(
+    f"finding{i}" for i in range(220)
+)  # ~2000 chars >> a 540-char stub and >> the 1200 full-text threshold
+
+
+class TestOpenAlexThinStubRichest:
+    def test_pick_richest_longest_wins_ties_keep_priority(self) -> None:
+        from src.polaris_graph.retrieval.frame_fetcher import (
+            _pick_richest_abstract,
+        )
+        # OpenAlex longest -> wins despite CrossRef higher priority.
+        t, s = _pick_richest_abstract(
+            crossref="short", openalex="x" * 50, pubmed=None,
+        )
+        assert s == "openalex_abstract" and t == "x" * 50
+        # Equal length -> CrossRef (higher priority) wins.
+        t, s = _pick_richest_abstract(
+            crossref="abcd", openalex="wxyz", pubmed=None,
+        )
+        assert s == "crossref_abstract"
+        # Only a thin partial full-text present -> it is used last-resort.
+        t, s = _pick_richest_abstract(
+            crossref=None, openalex=None, pubmed=None,
+            partial_full_text="stub",
+        )
+        assert s == "oa_full_text_partial"
+        # All empty.
+        assert _pick_richest_abstract(
+            crossref=None, openalex=None, pubmed=None,
+        ) == ("", "none")
+
+    def test_thin_oa_fulltext_stub_does_not_block_openalex(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        """THE #1034 BUG: aeaweb PDF 403s but Jina returns a ~540-char
+        stub. The stub must NOT block OpenAlex; the richer OpenAlex
+        abstract (>=1200) must win, not the stub."""
+        stub = "X" * 540  # below _OA_FULLTEXT_MIN_CHARS (1200)
+        monkeypatch.setattr(
+            "src.polaris_graph.retrieval.frame_fetcher._fetch_url_pattern",
+            lambda url: (stub, url),
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
+        assert row.provenance_class == ProvenanceClass.OPEN_ACCESS
+        assert row.quote_source == "openalex_abstract"  # NOT the stub
+        assert "finding200" in row.direct_quote
+        assert "XXXX" not in row.direct_quote  # the stub did not win
+        assert len(row.direct_quote) > 540
+        assert any(
+            "openalex" in a.source for a in row.retrieval_attempts
+        )
+
+    def test_real_long_fulltext_still_preferred_over_openalex(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        """A genuine long OA full text (>= threshold) still wins; the
+        thin-stub guard must not demote real full text."""
+        real = "Genuine full text. " * 120  # ~2280 chars >= 1200
+        monkeypatch.setattr(
+            "src.polaris_graph.retrieval.frame_fetcher._fetch_url_pattern",
+            lambda url: (real, url),
+        )
+        cr_no_abs = _crossref_response(abstract=None)
+        transport = _Transport([
+            ("api.crossref.org", 200, cr_no_abs),
+            ("api.unpaywall.org", 200, _unpaywall_response(
+                is_oa=True, pdf_url="https://oa.example/real.pdf")),
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
+        assert row.provenance_class == ProvenanceClass.OPEN_ACCESS
+        assert row.quote_source == "oa_full_text"
+        assert "Genuine full text" in row.direct_quote
+        # OpenAlex not even called (real full text resolved first).
+        assert not any("openalex" in u for u in transport.call_log)

```

## End with the YAML schema as your final lines.
