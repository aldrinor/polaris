# FX-13 (#1125) diff-gate — ITER 1 of 5

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
P2 telemetry/diversity correctness — pure string fix; no grounding/strict_verify/4-role change. Diff:
`.codex/I-ready-017/fx13_codex_diff.patch` (vs FL-05 verified tip `b43939d5`).

## Bug — confirmed §-1.1 on the REAL held trace
`_domain_of` did `netloc.lower().lstrip("www.")`. `str.lstrip` strips any leading char in the SET
{w, .}, NOT the literal prefix. Over the held drb_72 trace's 145 URLs, **2 domains corrupted**:
`wol.iza.org → ol.iza.org` (a REAL labor-economics source, and not even a www. host) and
`www.weforum.org → eforum.org`. The domain feeds `_domain_of(cand.url)` (`:2757`) source-diversity
dedup, so two real sources were mis-bucketed. Full §-1.1: `outputs/audits/I-ready-017/fx13_s11_audit.md`.

## Fix
`lstrip("www.")` → `removeprefix("www.")` (Python 3.9+; repo 3.13) in ALL 3 identical instances:
`live_retriever.py:1901` (production), `scripts/compare_live_vs_pg_lb_sa_02.py:32`,
`scripts/run_honest_on_prerebuild_corpus.py:81`.

## Evidence
- §-1.1 on REAL held trace: 2/145 corrupted (wol.iza.org, weforum) — above.
- Offline smoke `test_fx13_domain_of_iready017.py` → 4 passed: who.int/washington.edu un-corrupted;
  `wwwhost.example.com` NOT over-stripped; subdomains/plain hosts unchanged; bad URL → ''.
- Regression: `test_live_retriever_rerank` (8) + `test_fx15b_host_filter` (5) green.

## Also checked (clean)
Other retrieval `lstrip(...)`: `qualitative_conflict_detector.py:279` (`lstrip(" :,")`),
`tier_classifier.py:624` (`lstrip("\"'([ ")`) are LEGITIMATE leading-punctuation char-set strips —
not prefix bugs, left as-is.

## Question
Is the removeprefix fix correct + complete across all 3 instances, and the other lstrip calls
correctly left alone? Anything blocking APPROVE?

## THE DIFF UNDER REVIEW (vs FL-05 verified tip b43939d5)
```diff
diff --git a/scripts/compare_live_vs_pg_lb_sa_02.py b/scripts/compare_live_vs_pg_lb_sa_02.py
index 791a9843..59a890aa 100644
--- a/scripts/compare_live_vs_pg_lb_sa_02.py
+++ b/scripts/compare_live_vs_pg_lb_sa_02.py
@@ -29,7 +29,7 @@ from src.polaris_graph.retrieval.tier_classifier import (  # noqa: E402
 
 def _domain(url: str) -> str:
     try:
-        return (urlparse(url).netloc or "").lower().lstrip("www.")
+        return (urlparse(url).netloc or "").lower().removeprefix("www.")  # FX-13 (#1125): not lstrip (char-set bug)
     except Exception:
         return ""
 
diff --git a/scripts/run_honest_on_prerebuild_corpus.py b/scripts/run_honest_on_prerebuild_corpus.py
index 512e10c0..0da6ad84 100644
--- a/scripts/run_honest_on_prerebuild_corpus.py
+++ b/scripts/run_honest_on_prerebuild_corpus.py
@@ -78,7 +78,7 @@ from src.polaris_graph.retrieval.tier_classifier import (  # noqa: E402
 def _domain_of(url: str) -> str:
     from urllib.parse import urlparse
     try:
-        return (urlparse(url).netloc or "").lower().lstrip("www.")
+        return (urlparse(url).netloc or "").lower().removeprefix("www.")  # FX-13 (#1125): not lstrip (char-set bug)
     except Exception:
         return ""
 
diff --git a/src/polaris_graph/retrieval/live_retriever.py b/src/polaris_graph/retrieval/live_retriever.py
index e68f7dc1..ffb1bddb 100644
--- a/src/polaris_graph/retrieval/live_retriever.py
+++ b/src/polaris_graph/retrieval/live_retriever.py
@@ -1898,7 +1898,10 @@ def _fetch_content(
 
 def _domain_of(url: str) -> str:
     try:
-        return (urlparse(url).netloc or "").lower().lstrip("www.")
+        # FX-13 (#1125): removeprefix, NOT lstrip — `lstrip("www.")` strips any leading char in the
+        # SET {w, .}, corrupting domains like www.who.int -> "ho.int" / www.washington.edu ->
+        # "ashington.edu". removeprefix removes only the literal "www." prefix.
+        return (urlparse(url).netloc or "").lower().removeprefix("www.")
     except Exception:
         return ""
 
diff --git a/tests/polaris_graph/test_fx13_domain_of_iready017.py b/tests/polaris_graph/test_fx13_domain_of_iready017.py
new file mode 100644
index 00000000..43f934d5
--- /dev/null
+++ b/tests/polaris_graph/test_fx13_domain_of_iready017.py
@@ -0,0 +1,35 @@
+"""FX-13 (I-ready-017 #1125): _domain_of must use removeprefix, not lstrip.
+
+`netloc.lower().lstrip("www.")` strips any leading char in the SET {w, .}, corrupting domains whose
+name starts with w/. (www.who.int -> "ho.int", www.washington.edu -> "ashington.edu"). The fix uses
+`removeprefix("www.")` (literal prefix). The domain feeds source-diversity dedup, so a corrupted
+label mis-buckets sources. Offline, no network.
+"""
+from __future__ import annotations
+
+from src.polaris_graph.retrieval.live_retriever import _domain_of
+
+
+def test_www_prefix_stripped_literally_not_charset():
+    # the exact cases the old lstrip bug corrupted:
+    assert _domain_of("https://www.who.int/data") == "who.int"            # was "ho.int"
+    assert _domain_of("https://www.washington.edu/x") == "washington.edu"  # was "ashington.edu"
+    assert _domain_of("https://www.aeaweb.org/articles?id=1") == "aeaweb.org"
+    assert _domain_of("https://www.nature.com/articles/x") == "nature.com"
+
+
+def test_non_www_host_not_over_stripped():
+    # a host whose name starts with 'w'/'www' but is NOT a literal www. prefix must be left intact.
+    assert _domain_of("https://wwwhost.example.com/x") == "wwwhost.example.com"  # was "host.example.com"
+    assert _domain_of("https://web.mit.edu/x") == "web.mit.edu"                  # 'w'+'e' — lstrip kept 'eb...'? prefix-safe now
+
+
+def test_plain_host_and_subdomain_unchanged():
+    assert _domain_of("https://pubs.aeaweb.org/doi/10.1257/x") == "pubs.aeaweb.org"
+    assert _domain_of("https://arxiv.org/abs/2401.00001") == "arxiv.org"
+    assert _domain_of("https://nber.org/papers/w12345") == "nber.org"
+
+
+def test_bad_url_returns_empty():
+    assert _domain_of("") == ""
+    assert _domain_of("not a url") == ""  # no netloc
```
