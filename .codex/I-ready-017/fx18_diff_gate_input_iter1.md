# FX-18 (#1122) diff-gate — ITER 1 of 5

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
**Discovery-breadth — faithfulness-SAFE** (ADDS candidates; every new source passes the SAME
fetch/tier/strict_verify/4-role gates; no grounding/verification change). Diff:
`.codex/I-ready-017/fx18_codex_diff.patch` (vs FX-06 verified tip `5d7fd51e`).

## Bug — confirmed §-1.1 on the REAL held retrieval_trace
Per-backend search `return_count` across the 5 effective queries (held drb_72):
- **`semantic_scholar` (S2): [0, 0, 0, 0, 4]** — 4/5 NL queries returned ZERO (S2 is a keyword index;
  the sweep fed it 40-70-word NL queries).
- `serper`: [10×5] = 50.
- **`openalex_search`: absent** — the NL-friendly OpenAlex backend (already built, fail-open) was
  never wired into the search lane.
Full §-1.1: `outputs/audits/I-ready-017/fx18_s11_audit.md`.

## Fix
1. **S2 short-keyword:** new `query_decomposer.distill_keywords(q, max_terms=8)` (content tokens via
   the existing `_content_tokens`, stopword-filtered, deduped first-seen, capped, pure). The per-query
   S2 call sends the distilled phrase instead of NL `q`. Flag `PG_S2_KEYWORD_DISTILL` (default on);
   empty distillation → NL fallback. The candidate `query_origin` STAYS the NL `q` (rerank
   reservation + plan-sufficiency unchanged).
2. **Wire OpenAlex:** `openalex_search(q)` in the per-query loop as a PARALLEL academic backend
   (ADD/union, NOT replace S2 — my Q8 call), union+dedup via the shared `seen_urls`; candidates carry
   `source="openalex_search"`, default `query_origin=q`. Flag `PG_OPENALEX_SEARCH` (default on);
   fail-open (lazy import inside try/except — a fault adds 0 hits).

## Evidence
- **§-1.1 on REAL held trace**: S2 [0,0,0,0,4]; OpenAlex absent (above).
- **Offline smoke — `test_fx18_s2_keyword_openalex_iready017.py` → 3 passed**: `distill_keywords`
  (≤8 terms, stopwords dropped, deduped, shorter; all-stopword → '' fallback); integration (mocked
  serper/s2/openalex/fetch) — **S2 receives the distilled phrase** (not NL), **OpenAlex's new URL
  merged** (source=openalex_search), a URL shared with serper **deduped** (kept once as serper).
- **Regression**: query_decomposer (14) + FX-15a (6) + FX-15b (5) + live_retriever_rerank (8) +
  retrieval_trace (7) + research_planner phase1 — 68 passed.

## Decisions made (please confirm)
- **Q8 ADD vs REPLACE:** chose ADD (union OpenAlex with S2's NL path), per the plan's lean — S2's
  keyword path now also fires (distilled), and OpenAlex covers NL. Confirm ADD is right.
- **Keyword distillation = first-≤8 content tokens** (leading terms = the topic). Bounded
  over-generalization (keeps the same content words, drops stopwords + caps length); downstream
  semantic prefetch (now seed-safe) + tier classifier still filter. Acceptable, or do you want a
  different distillation (e.g. salience-ranked)?

## Question
Is the S2 distillation + OpenAlex wiring correct, dedup sound (shared `seen_urls`), and the
query_origin tagging consistent (NL `q` for S2; `q` default for OpenAlex)? Anything blocking APPROVE?

## THE DIFF UNDER REVIEW (vs FX-06 verified tip 5d7fd51e)
```diff
diff --git a/src/polaris_graph/retrieval/live_retriever.py b/src/polaris_graph/retrieval/live_retriever.py
index 315205eb..e68f7dc1 100644
--- a/src/polaris_graph/retrieval/live_retriever.py
+++ b/src/polaris_graph/retrieval/live_retriever.py
@@ -46,6 +46,7 @@ from src.polaris_graph.retrieval.prefetch_offtopic_filter import (
 from src.polaris_graph.retrieval.scope_query_validator import (
     validate_amplified_queries,
 )
+from src.polaris_graph.retrieval.query_decomposer import distill_keywords  # FX-18 (#1122)
 from src.polaris_graph.authority.authority_model import score_source_authority
 from src.polaris_graph.authority.source_class import AuthoritySignals
 from src.polaris_graph.retrieval.tier_classifier import (
@@ -2372,8 +2373,18 @@ def run_live_retrieval(
                 query_origin=q,
             ))
 
-        logger.info("[live_retriever] S2 q=%r", q[:80])
-        s2_hits = _s2_bulk_search(q, limit=max_s2)
+        # FX-18 (#1122): S2 bulk is a KEYWORD index — feeding it the 40-70-word NL query returned ~0
+        # for 4/5 golden questions. Send a SHORT content-keyword distillation of `q` instead (pure,
+        # stopword-filtered, capped). Flag-gated PG_S2_KEYWORD_DISTILL (default on); an empty
+        # distillation falls back to the NL `q` (never an empty search). The candidate's `query_origin`
+        # stays the NL `q` so the per-sub-query rerank reservation + plan-sufficiency are unchanged.
+        _s2_query = q
+        if os.getenv("PG_S2_KEYWORD_DISTILL", "1") != "0":
+            _kw = distill_keywords(q, max_terms=int(os.getenv("PG_S2_KEYWORD_MAX_TERMS", "8")))
+            if _kw:
+                _s2_query = _kw
+        logger.info("[live_retriever] S2 q=%r", _s2_query[:80])
+        s2_hits = _s2_bulk_search(_s2_query, limit=max_s2)
         api_calls["s2"] += 1
         for hit in s2_hits:
             url = hit.get("url", "")
@@ -2389,6 +2400,32 @@ def run_live_retrieval(
                 query_origin=q,
             ))
 
+        # FX-18 (#1122): OpenAlex /works?search handles NL queries that the S2 keyword index does not,
+        # and is already built (domain_backends.openalex_search, fail-open). Wire it as a PARALLEL
+        # academic backend — ADD (union), not replace S2 (Codex Q8) — sending the NL `q`; union+dedup
+        # via the shared `seen_urls`. Candidates carry source="openalex_search"; default query_origin
+        # to `q`. Flag-gated PG_OPENALEX_SEARCH (default on). Fail-open: a backend fault adds 0 hits.
+        if os.getenv("PG_OPENALEX_SEARCH", "1") != "0":
+            try:
+                from src.polaris_graph.retrieval.domain_backends import (  # noqa: E402
+                    openalex_search,
+                )
+                _oa_hits = openalex_search(q, limit=max_s2)
+                api_calls["openalex_search"] = api_calls.get("openalex_search", 0) + 1
+                for cand in _oa_hits:
+                    url = getattr(cand, "url", "")
+                    if not url or url in seen_urls:
+                        continue
+                    seen_urls.add(url)
+                    if not getattr(cand, "query_origin", ""):
+                        cand.query_origin = q
+                    candidates.append(cand)
+            except Exception as exc:
+                logger.warning(
+                    "[live_retriever] openalex_search failed for %r (fail-open): %s",
+                    q[:60], exc,
+                )
+
     # ── Step 2a: specialized issuer-class backends ──────────────────
     # I-meta-005 Phase 2 (#986) DUAL PATH:
     #   ON-mode (research_frame present): the field-agnostic NEED-TYPE registry
diff --git a/src/polaris_graph/retrieval/query_decomposer.py b/src/polaris_graph/retrieval/query_decomposer.py
index 1d738497..3d15a2d3 100644
--- a/src/polaris_graph/retrieval/query_decomposer.py
+++ b/src/polaris_graph/retrieval/query_decomposer.py
@@ -151,6 +151,25 @@ def decompose_question(question: str, *, max_subqueries: int = DEFAULT_MAX_SUBQU
     return out
 
 
+def distill_keywords(question: str, *, max_terms: int = 8) -> str:
+    """FX-18 (#1122): distill an NL question to a SHORT space-joined keyword phrase for a KEYWORD
+    index (Semantic Scholar bulk returned ~0 for the 40-70-word NL golden questions). Content tokens
+    only (stopword-filtered, 3+ chars — reuses `_content_tokens`), de-duplicated in first-seen order,
+    capped at `max_terms`. Pure / no-network / no-LLM. Returns '' when the question has no content
+    tokens so the caller falls back to the full query (never sends an empty search).
+    """
+    out: list[str] = []
+    seen: set[str] = set()
+    for tok in _content_tokens(question):
+        if tok in seen:
+            continue
+        seen.add(tok)
+        out.append(tok)
+        if len(out) >= max_terms:
+            break
+    return " ".join(out)
+
+
 def build_amplified_query_list(
     *,
     hand_authored: list[str],
diff --git a/tests/polaris_graph/test_fx18_s2_keyword_openalex_iready017.py b/tests/polaris_graph/test_fx18_s2_keyword_openalex_iready017.py
new file mode 100644
index 00000000..66aa9d04
--- /dev/null
+++ b/tests/polaris_graph/test_fx18_s2_keyword_openalex_iready017.py
@@ -0,0 +1,82 @@
+"""FX-18 (I-ready-017 #1122): S2 short-keyword lane + wire OpenAlex into the sweep search lane.
+
+S2 bulk is a keyword index — the 40-70-word NL golden queries returned ~0. FX-18 (1) distills `q`
+to a short content-keyword phrase for S2 (`distill_keywords`), and (2) wires
+`domain_backends.openalex_search` (NL-friendly, fail-open) as a parallel academic backend,
+union+deduped via the shared `seen_urls`. Discovery-breadth only — every new source passes the SAME
+fetch/tier/strict_verify/4-role gates. Offline, no network.
+"""
+from __future__ import annotations
+
+import src.polaris_graph.retrieval.domain_backends as _db
+import src.polaris_graph.retrieval.live_retriever as lr
+from src.polaris_graph.retrieval.prefetch_offtopic_filter import SearchCandidate
+from src.polaris_graph.retrieval.query_decomposer import distill_keywords
+
+_NL = (
+    "To what extent will artificial intelligence and automation technologies displace or transform "
+    "jobs across the labor market over the next decade, and what does the empirical economics "
+    "literature conclude about net employment effects?"
+)
+
+
+def test_distill_keywords_short_stopword_filtered_capped():
+    kw = distill_keywords(_NL, max_terms=8)
+    toks = kw.split()
+    assert 0 < len(toks) <= 8                       # non-empty + capped
+    assert len(toks) < len(_NL.split())             # strictly shorter than the NL query
+    assert "the" not in toks and "and" not in toks  # stopwords dropped
+    assert len(toks) == len(set(toks))              # de-duplicated
+    # content terms preserved
+    assert "artificial" in toks and "intelligence" in toks
+
+
+def test_distill_keywords_empty_when_no_content_tokens():
+    # all-stopword question -> '' so the caller falls back to the full NL query (never empty search).
+    assert distill_keywords("what is the of and to", max_terms=8) == ""
+
+
+def _stub_fetch(url, max_chars, **kwargs):
+    return ("Automation displaced manufacturing jobs in the labor market. " * 8, True, "T", "html", "")
+
+
+def test_s2_gets_distilled_query_and_openalex_merged_deduped(monkeypatch):
+    captured_s2: dict = {}
+    monkeypatch.setattr(lr, "_serper_search", lambda q, num=10: [
+        {"url": "https://dup.org/a", "title": "Serper A", "snippet": "labor"}
+    ])
+
+    def _fake_s2(query, limit=20):
+        captured_s2["q"] = query
+        return []
+    monkeypatch.setattr(lr, "_s2_bulk_search", _fake_s2)
+
+    def _fake_openalex(query, limit=20):
+        return [
+            SearchCandidate(url="https://dup.org/a", title="OA dup", snippet="", source="openalex_search"),
+            SearchCandidate(url="https://oa.org/b", title="OA new", snippet="", source="openalex_search"),
+        ]
+    monkeypatch.setattr(_db, "openalex_search", _fake_openalex)
+    monkeypatch.setattr(lr, "_fetch_content", _stub_fetch)
+
+    res = lr.run_live_retrieval(
+        research_question=_NL,
+        protocol=None,            # no scope validation -> effective_queries = [the NL question]
+        anchor_seed=True,
+        enable_openalex_enrich=False,
+        enable_prefetch_filter=False,
+        fetch_cap=10,
+    )
+
+    # (1) S2 received the DISTILLED keyword phrase, not the 33-word NL query.
+    assert captured_s2["q"] == distill_keywords(_NL, max_terms=8)
+    assert len(captured_s2["q"].split()) <= 8
+
+    rows = {r["source_url"]: r for r in res.evidence_rows}
+    # (2) OpenAlex's NEW url merged.
+    assert "https://oa.org/b" in rows
+    assert rows["https://oa.org/b"]["source"] == "openalex_search"
+    # (3) The url OpenAlex shared with serper is deduped — present exactly once, kept as the serper row.
+    dup_rows = [r for r in res.evidence_rows if r["source_url"] == "https://dup.org/a"]
+    assert len(dup_rows) == 1
+    assert dup_rows[0]["source"] == "serper"
```
