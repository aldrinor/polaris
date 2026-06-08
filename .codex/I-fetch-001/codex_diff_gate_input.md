HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Output schema (machine-parseable; loose prose is rejected):

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

Review this `sec_edgar` CIK-parse fix: the backend read CIK from `_id.split(':')[0]` (the accession number) and threw `ValueError` on every hit; the fix takes CIK from the `ciks` array. Verify: (a) the CIK now comes from the `ciks` field, (b) a missing/empty `ciks` hit is skipped not crashed, (c) the document-URL build still works, (d) the regression test actually reproduces the old failure shape and passes now, (e) no other backend touched. End with 'verdict: APPROVE' or 'verdict: REQUEST_CHANGES' then bullets.

---

## Staged diff (`git diff --cached -- src/polaris_graph/retrieval/domain_backends.py tests/polaris_graph/test_domain_backends_r6_gap2.py`)

```diff
diff --git a/src/polaris_graph/retrieval/domain_backends.py b/src/polaris_graph/retrieval/domain_backends.py
index 3185ed10..bdddb02b 100644
--- a/src/polaris_graph/retrieval/domain_backends.py
+++ b/src/polaris_graph/retrieval/domain_backends.py
@@ -304,16 +304,28 @@ def sec_edgar_search(
     for h in hits[:limit]:
         src = h.get("_source", {}) or {}
         adsh = src.get("adsh", "")
-        cik = (h.get("_id", "").split(":")[0]
-               if ":" in h.get("_id", "")
-               else src.get("ciks", [""])[0])
+        # I-fetch-001 (#1167): the EDGAR full-text `_id` is
+        # `<accession>:<primary_doc>` — splitting it on ":" yields the
+        # dash-bearing accession number, NOT the CIK, so `int(cik)` below
+        # raised ValueError on EVERY hit (zero SEC candidates returned).
+        # The CIK lives in the `ciks` array on `_source`; take it from
+        # there and skip (fail-loud per hit, not per backend) any hit
+        # whose CIK is missing or non-numeric.
+        ciks = src.get("ciks") or []
+        cik = (ciks[0] or "").strip() if ciks else ""
         form = src.get("form", "")
         display_name = src.get("display_names", [""])[0] or ""
         filed = src.get("file_date", "")
         if not adsh:
             continue
+        if not cik.isdigit():
+            logger.debug(
+                "sec_edgar_search: skipping hit %r with non-numeric "
+                "cik %r", h.get("_id", ""), cik,
+            )
+            continue
         # Construct a filing URL
-        cik_no_leading_zero = str(int(cik)) if cik else ""
+        cik_no_leading_zero = str(int(cik))
         adsh_no_dash = adsh.replace("-", "")
         url = (
             f"https://www.sec.gov/Archives/edgar/data/"
diff --git a/tests/polaris_graph/test_domain_backends_r6_gap2.py b/tests/polaris_graph/test_domain_backends_r6_gap2.py
index 89403f62..e82a031e 100644
--- a/tests/polaris_graph/test_domain_backends_r6_gap2.py
+++ b/tests/polaris_graph/test_domain_backends_r6_gap2.py
@@ -14,6 +14,7 @@ from src.polaris_graph.retrieval.domain_backends import (
     _parse_arxiv_feed,
     europe_pmc_search,
     run_domain_backends,
+    sec_edgar_search,
 )
 from src.polaris_graph.retrieval.prefetch_offtopic_filter import (
     SearchCandidate,
@@ -258,3 +259,110 @@ def test_europe_pmc_fails_open_on_empty_or_error() -> None:
         side_effect=RuntimeError("network down"),
     ):
         assert europe_pmc_search("q") == []
+
+
+# --- I-fetch-001 (#1167): SEC EDGAR full-text CIK comes from `ciks`, NOT `_id` -----------
+def _edgar_payload(*hits):
+    return {"hits": {"hits": list(hits)}}
+
+
+def _edgar_hit(_id, *, adsh, ciks, form="10-K",
+              display="Tesla, Inc.  (TSLA)", filed="2024-01-29"):
+    return {
+        "_id": _id,
+        "_source": {
+            "adsh": adsh,
+            "ciks": ciks,
+            "form": form,
+            "display_names": [display],
+            "file_date": filed,
+        },
+    }
+
+
+def test_sec_edgar_cik_from_ciks_array_not_id() -> None:
+    # The full-text `_id` is `<accession>:<primary_doc>`. The OLD code split
+    # `_id` on ":" and fed the dash-bearing accession to int() → ValueError
+    # on EVERY hit (zero SEC candidates). The CIK must come from `ciks`.
+    payload = _edgar_payload(_edgar_hit(
+        "0001234567-24-000123:tsla-10k.htm",
+        adsh="0001234567-24-000123",
+        ciks=["0001318605"],
+    ))
+    with patch(
+        "src.polaris_graph.retrieval.domain_backends._http_get_json",
+        return_value=payload,
+    ):
+        out = sec_edgar_search("Tesla 10-K")
+    assert len(out) >= 1
+    cand = out[0]
+    assert cand.source == "sec_edgar"
+    # CIK is the int-normalized (leading-zero-stripped) value from `ciks`.
+    assert cand.metadata["cik"] == "0001318605"
+    assert "/data/1318605/" in cand.url
+    assert "000123456724000123" in cand.url
+    assert cand.metadata["adsh"] == "0001234567-24-000123"
+
+
+def test_sec_edgar_does_not_raise_on_realistic_response() -> None:
+    # Regression guard: a realistic full-text response must NOT raise.
+    payload = _edgar_payload(_edgar_hit(
+        "0001234567-24-000123:tsla-10k.htm",
+        adsh="0001234567-24-000123",
+        ciks=["0001318605"],
+    ))
+    with patch(
+        "src.polaris_graph.retrieval.domain_backends._http_get_json",
+        return_value=payload,
+    ):
+        # Must not raise ValueError.
+        sec_edgar_search("Tesla 10-K")
+
+
+def test_sec_edgar_skips_hit_with_missing_cik_keeps_rest() -> None:
+    # A single bad hit (empty/missing ciks) is SKIPPED, not crash-the-backend;
+    # the good hit still contributes (fail-loud per hit, fail-open per backend).
+    payload = _edgar_payload(
+        _edgar_hit(
+            "0001234567-24-000123:bad.htm",
+            adsh="0001234567-24-000123",
+            ciks=[],  # missing CIK → skip this hit
+        ),
+        _edgar_hit(
+            "0007654321-24-000999:msft-10k.htm",
+            adsh="0007654321-24-000999",
+            ciks=["0000789019"],
+            display="MICROSOFT CORP  (MSFT)",
+        ),
+    )
+    with patch(
+        "src.polaris_graph.retrieval.domain_backends._http_get_json",
+        return_value=payload,
+    ):
+        out = sec_edgar_search("Microsoft 10-K")
+    assert len(out) == 1
+    assert out[0].metadata["cik"] == "0000789019"
+    assert "/data/789019/" in out[0].url
+
+
+def test_sec_edgar_skips_non_numeric_cik() -> None:
+    # A non-numeric CIK must be skipped (never reach int()).
+    payload = _edgar_payload(_edgar_hit(
+        "0001234567-24-000123:tsla-10k.htm",
+        adsh="0001234567-24-000123",
+        ciks=["not-a-number"],
+    ))
+    with patch(
+        "src.polaris_graph.retrieval.domain_backends._http_get_json",
+        return_value=payload,
+    ):
+        out = sec_edgar_search("q")
+    assert out == []
+
+
+def test_sec_edgar_fails_open_on_empty() -> None:
+    with patch(
+        "src.polaris_graph.retrieval.domain_backends._http_get_json",
+        return_value=None,
+    ):
+        assert sec_edgar_search("q") == []

```
