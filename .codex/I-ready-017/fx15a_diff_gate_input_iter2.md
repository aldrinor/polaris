# FX-15a (#1118) diff-gate — ITER 2 of 5

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
Telemetry-correctness ONLY — no retrieval-selection / grounding / strict_verify / 4-role change.
Diff: `.codex/I-ready-017/fx15a_codex_diff.patch` (vs FX-11 verified tip `55d07534`).

## Your iter-1 verdict (addressed)
**P1:** "Deepener seed URLs remain on the default `primary_trial_doi` / `primary_trial_doi_seed`.
Citation-snowball URLs are primary-trial-derived but not direct primary-trial DOI seeds, so future
deep_retrieval traces can still pollute `backend=='primary_trial_doi'` telemetry. Relabel them,
e.g. `deepener_seed`, and add that label to both the reserved seed source set and sentinel origins
to preserve behavior."

## What iter-2 changed (exactly your P1)
1. `_SEED_SOURCE_LABELS` (live_retriever) → `{primary_trial_doi, agentic_seed, deepener_seed}` — so
   deepener seeds stay in the reserved/undroppable/unranked lane (no selection change).
2. `plan_sufficiency_gate.SENTINEL_ORIGINS` → adds `'deepener_seed'` (fallback-eligibility
   preserved, identical to the old `primary_trial_doi_seed` it carried before).
3. The deepener caller (`run_honest_sweep_r3.py`, `deep_retrieval` with `seed_urls=_deep_urls`)
   now passes `seed_source='deepener_seed', seed_query_origin='deepener_seed'`.

This is the SAME behavior-preserving pattern used for `agentic_seed` in iter-1.

## Evidence
- **Offline smoke — `test_fx15a_agentic_seed_label_iready017.py` → 6 passed** (added a deepener
  injection-label test + the seed-split now reserves all 3 classes + both new labels are sentinels).
- **Regression**: `test_live_retriever_rerank` (8) + `test_bug776_layer4_doi_seeds` (5) +
  `test_plan_sufficiency_phase3` (26) all pass.
- §-1.1: `outputs/audits/I-ready-017/fx15a_s11_audit.md` (updated for the deepener relabel).

## Remaining caller audit (complete)
Of all `run_live_retrieval(seed_urls=...)` callers: off-mode DOI keeps the default
`primary_trial_doi` (correct — those ARE DOI seeds); agentic → `agentic_seed`; deepener →
`deepener_seed`; gap (`seed_urls=[]`) and exp (no seeds) inject nothing. No seed lane is left
mislabeled.

## Question
Is the deepener relabel correct + behavior-preserving (reserved lane + sentinel both updated), and
are all seed lanes now truthfully labeled? Anything blocking APPROVE?

## THE DIFF UNDER REVIEW (vs FX-11 verified tip 55d07534)
```diff
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index d7b73237..9ec7aa19 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -2740,6 +2740,12 @@ async def run_one_query(
                         enable_prefetch_filter=False,
                         seed_urls=_deep_urls,
                         seed_only=True,     # ONLY the deepener URLs — no Serper/S2/domain fan-out
+                        # FX-15a (#1118, Codex iter-1 P1): citation-snowball deepener URLs are
+                        # primary-trial-DERIVED but NOT direct DOI seeds — label them truthfully so
+                        # they don't pollute primary_trial_doi telemetry. Stays in the reserved seed
+                        # lane (seed-split + SENTINEL_ORIGINS include deepener_seed); telemetry only.
+                        seed_source="deepener_seed",
+                        seed_query_origin="deepener_seed",
                     )
                     # ATOMIC merge (Codex diff-gate iter-1 P1): stage everything in LOCAL copies,
                     # recompute dist/completeness/adequacy over the staged corpus, and COMMIT all
@@ -2909,6 +2915,11 @@ async def run_one_query(
                         enable_prefetch_filter=False,
                         seed_urls=_ag_urls,
                         seed_only=True,   # ONLY the agentic URLs — no Serper/S2/domain fan-out
+                        # FX-15a (#1118): truthful source/origin labels — these are agentic web
+                        # discoveries, NOT primary-trial DOI seeds. Keeps the reserved seed lane
+                        # (seed-split splits on {primary_trial_doi, agentic_seed}); telemetry only.
+                        seed_source="agentic_seed",
+                        seed_query_origin="agentic_seed",
                     )
                     # ATOMIC merge via the pure helper (dedup by URL + global ev_### renumber), then
                     # recompute dist/completeness/adequacy over the staged corpus and COMMIT only after
diff --git a/src/polaris_graph/adequacy/plan_sufficiency_gate.py b/src/polaris_graph/adequacy/plan_sufficiency_gate.py
index 27897c47..02b05566 100644
--- a/src/polaris_graph/adequacy/plan_sufficiency_gate.py
+++ b/src/polaris_graph/adequacy/plan_sufficiency_gate.py
@@ -12,7 +12,7 @@ KEY DESIGN (brief §2.2):
   `query_origin` matches (normalized equality) one of the sub-query texts at the
   section's `sub_query_indices`. The content-word overlap fallback is used ONLY
   for rows whose `query_origin` is EMPTY or one of the explicit NON-QUERY
-  SENTINEL origins (`{primary_trial_doi_seed, need_type_backend, domain_backend}`)
+  SENTINEL origins (`{primary_trial_doi_seed, agentic_seed, deepener_seed, need_type_backend, domain_backend}`)
   — these lanes surface authoritative evidence with no originating sub-query, so
   they must be creditable. A row whose `query_origin` is a REAL sub-query text
   that does not match the section is NOT relevant to it (no title-overlap rescue).
@@ -51,7 +51,11 @@ SufficiencyVerdict = Literal["proceed", "expand", "abort"]
 # section's sub-query texts. A REAL sub-query origin is authoritative and uses
 # provenance-first matching only. Codex-LOCKED — do not widen.
 SENTINEL_ORIGINS: frozenset[str] = frozenset(
-    {"primary_trial_doi_seed", "need_type_backend", "domain_backend"}
+    # FX-15a (#1118): `agentic_seed` (agentic-discovered URLs) and `deepener_seed` (citation-
+    # snowball deepener URLs, Codex iter-1 P1) are non-query seed lanes, creditable via the overlap
+    # fallback exactly as the old mislabel `primary_trial_doi_seed` was — so the relabels preserve
+    # plan-sufficiency fallback-eligibility (no behavior change).
+    {"primary_trial_doi_seed", "agentic_seed", "deepener_seed", "need_type_backend", "domain_backend"}
 )
 
 
diff --git a/src/polaris_graph/retrieval/live_retriever.py b/src/polaris_graph/retrieval/live_retriever.py
index c80ab229..93b62863 100644
--- a/src/polaris_graph/retrieval/live_retriever.py
+++ b/src/polaris_graph/retrieval/live_retriever.py
@@ -2090,6 +2090,18 @@ def _lexical_relevance_score(candidate: "SearchCandidate", question_tokens: set[
     return len(cand_tokens & question_tokens) / float(len(question_tokens))
 
 
+# FX-15a (#1118): the injected-seed source classes that share the reserved/undroppable/unranked
+# lane. `primary_trial_doi` = #817 layer-4 direct primary-trial DOI seeds; `agentic_seed` =
+# agentic-discovered URLs; `deepener_seed` = citation-snowball deepener URLs (Codex iter-1 P1:
+# these are primary-trial-DERIVED but NOT direct DOI seeds, so they must not pollute
+# `primary_trial_doi` telemetry either). ALL are split out and prepended unranked; FX-15b later
+# makes the web-discovered classes droppable via the host-class filter (telemetry-correctness
+# here is the prerequisite).
+_SEED_SOURCE_LABELS: frozenset[str] = frozenset(
+    {"primary_trial_doi", "agentic_seed", "deepener_seed"}
+)
+
+
 def _rerank_and_reserve(
     candidates: list["SearchCandidate"],
     *,
@@ -2102,8 +2114,10 @@ def _rerank_and_reserve(
     iter-1 required-changes).
 
     Seed lane (I-bug-776 #817): primary-trial DOI seeds carry empty title/snippet, so
-    relevance scoring would drop them. They are SPLIT OUT by `source == "primary_trial_doi"`
-    and prepended AFTER ranking — never ranked, never dropped, exactly additive as before.
+    relevance scoring would drop them. They are SPLIT OUT by `source in _SEED_SOURCE_LABELS`
+    (FX-15a #1118: the set `{primary_trial_doi, agentic_seed}` — both injected seed classes keep
+    the additive/reserved lane) and prepended AFTER ranking — never ranked, never dropped, exactly
+    additive as before.
 
     Reservation: group non-seeds by `query_origin`; sort each group by (-score, index);
     take at most ONE reserved item per origin while capacity remains (origins with the best
@@ -2114,8 +2128,8 @@ def _rerank_and_reserve(
     `candidates[:fetch_cap + n_seed_injected]`.
     """
     try:
-        seeds = [c for c in candidates if getattr(c, "source", "") == "primary_trial_doi"]
-        non_seeds = [c for c in candidates if getattr(c, "source", "") != "primary_trial_doi"]
+        seeds = [c for c in candidates if getattr(c, "source", "") in _SEED_SOURCE_LABELS]
+        non_seeds = [c for c in candidates if getattr(c, "source", "") not in _SEED_SOURCE_LABELS]
         if fetch_cap <= 0 or not non_seeds:
             return seeds + non_seeds[:max(fetch_cap, 0)]
 
@@ -2183,6 +2197,8 @@ def run_live_retrieval(
     domain: Optional[str] = None,
     seed_urls: Optional[list[str]] = None,
     seed_only: bool = False,
+    seed_source: str = "primary_trial_doi",
+    seed_query_origin: str = "primary_trial_doi_seed",
     research_frame: Any = None,
     anchor_seed: bool = True,
 ) -> LiveRetrievalResult:
@@ -2282,15 +2298,18 @@ def run_live_retrieval(
     for _surl in seed_urls or []:
         if _surl and _surl not in seen_urls:
             seen_urls.add(_surl)
+            # FX-15a (#1118): the seed SOURCE/ORIGIN labels are now caller-supplied so the agentic
+            # lane (seed_source='agentic_seed') is no longer mislabeled as a primary-trial DOI seed.
+            # Defaults preserve the #817 layer-4 DOI-lane labels for every existing caller.
             candidates.append(SearchCandidate(
-                url=_surl, title="", snippet="", source="primary_trial_doi",
-                query_origin="primary_trial_doi_seed",
+                url=_surl, title="", snippet="", source=seed_source,
+                query_origin=seed_query_origin,
             ))
             _n_seed_injected += 1
     if _n_seed_injected:
         logger.info(
-            "[live_retriever] injected %d direct primary-trial DOI seed candidates",
-            _n_seed_injected,
+            "[live_retriever] injected %d direct seed candidates (source=%s, query_origin=%s)",
+            _n_seed_injected, seed_source, seed_query_origin,
         )
 
     # I-meta-002-q1d (#942-deepener, Codex diff-gate iter-2 P1): seed_only processes ONLY the injected
diff --git a/tests/polaris_graph/test_fx15a_agentic_seed_label_iready017.py b/tests/polaris_graph/test_fx15a_agentic_seed_label_iready017.py
new file mode 100644
index 00000000..1230ce59
--- /dev/null
+++ b/tests/polaris_graph/test_fx15a_agentic_seed_label_iready017.py
@@ -0,0 +1,129 @@
+"""FX-15a (I-ready-017 #1118): agentic seed source-label correctness.
+
+Agentic-discovered seed URLs were injected as `source='primary_trial_doi'`,
+`query_origin='primary_trial_doi_seed'` — mislabeling ordinary web discoveries as primary-trial
+DOI seeds. The fix threads caller-supplied `seed_source` / `seed_query_origin` through
+`run_live_retrieval`, splits the reserved seed lane on the SET {primary_trial_doi, agentic_seed}
+(so the relabel changes NO selection — both classes stay reserved/undroppable), and adds
+`agentic_seed` to `plan_sufficiency_gate.SENTINEL_ORIGINS` (so fallback-eligibility is preserved).
+
+Telemetry-correctness ONLY — no retrieval-selection, grounding, strict_verify or 4-role change.
+Offline, no network (seed_only + stubbed `_fetch_content`).
+"""
+from __future__ import annotations
+
+import src.polaris_graph.retrieval.live_retriever as lr
+from src.polaris_graph.adequacy.plan_sufficiency_gate import SENTINEL_ORIGINS
+from src.polaris_graph.retrieval.live_retriever import (
+    SearchCandidate,
+    _rerank_and_reserve,
+    _SEED_SOURCE_LABELS,
+)
+
+
+def test_seed_split_reserves_both_seed_classes_unranked():
+    """The relabel must NOT change selection: BOTH primary_trial_doi AND agentic_seed candidates
+    stay in the reserved lane (prepended, never ranked, never dropped) — only the label differs."""
+    doi_seed = SearchCandidate(
+        url="https://doi.org/10.1056/x", title="", snippet="", source="primary_trial_doi",
+        query_origin="primary_trial_doi_seed",
+    )
+    agentic_seed = SearchCandidate(
+        url="https://aeaweb.org/articles?id=10.1257/y", title="", snippet="",
+        source="agentic_seed", query_origin="agentic_seed",
+    )
+    deepener_seed = SearchCandidate(
+        url="https://example.org/cited-ref", title="", snippet="",
+        source="deepener_seed", query_origin="deepener_seed",
+    )
+    web = SearchCandidate(
+        url="https://example.org/web", title="W", snippet="w", source="serper",
+        query_origin="sub query text",
+    )
+    out = _rerank_and_reserve(
+        [web, doi_seed, agentic_seed, deepener_seed],
+        research_question="anticoagulation in atrial fibrillation",
+        fetch_cap=1,
+        n_seed_injected=3,
+    )
+    out_sources = [c.source for c in out]
+    # ALL three seed classes survive (reserved); none dropped despite fetch_cap=1
+    assert "primary_trial_doi" in out_sources
+    assert "agentic_seed" in out_sources
+    assert "deepener_seed" in out_sources
+    # seeds are PREPENDED before the (single) reserved web candidate
+    assert out_sources[:3] == ["primary_trial_doi", "agentic_seed", "deepener_seed"]
+    assert "serper" in out_sources  # the one non-seed slot
+
+
+def test_seed_source_labels_constant():
+    assert _SEED_SOURCE_LABELS == frozenset(
+        {"primary_trial_doi", "agentic_seed", "deepener_seed"}
+    )
+
+
+def test_seed_origins_are_sentinels():
+    """Preserves fallback-eligibility the old mislabel `primary_trial_doi_seed` (a sentinel) had."""
+    assert "agentic_seed" in SENTINEL_ORIGINS
+    assert "deepener_seed" in SENTINEL_ORIGINS  # Codex iter-1 P1
+    assert "primary_trial_doi_seed" in SENTINEL_ORIGINS  # unchanged
+
+
+def _stub_fetch(url, max_chars, **kwargs):
+    # (content, ok, title, body_type, jsonld) — non-starved content so the row is kept.
+    return (
+        "Apixaban reduced stroke versus warfarin in atrial fibrillation patients. " * 8,
+        True, "Stub Title", "html", "",
+    )
+
+
+def test_injection_uses_caller_label_agentic(monkeypatch):
+    monkeypatch.setattr(lr, "_fetch_content", _stub_fetch)
+    res = lr.run_live_retrieval(
+        research_question="anticoagulation in atrial fibrillation",
+        seed_urls=["https://aeaweb.org/articles?id=10.1257/y"],
+        seed_only=True,
+        seed_source="agentic_seed",
+        seed_query_origin="agentic_seed",
+        enable_openalex_enrich=False,
+        fetch_cap=5,
+    )
+    rows = [r for r in res.evidence_rows if r["source_url"] == "https://aeaweb.org/articles?id=10.1257/y"]
+    assert rows, "the stubbed agentic seed should produce one kept evidence row"
+    assert rows[0]["source"] == "agentic_seed"
+    assert rows[0]["query_origin"] == "agentic_seed"
+
+
+def test_injection_uses_caller_label_deepener(monkeypatch):
+    """Codex iter-1 P1: the citation-snowball deepener caller labels its URLs deepener_seed
+    (NOT primary_trial_doi), staying in the reserved lane."""
+    monkeypatch.setattr(lr, "_fetch_content", _stub_fetch)
+    res = lr.run_live_retrieval(
+        research_question="anticoagulation in atrial fibrillation",
+        seed_urls=["https://example.org/cited-ref"],
+        seed_only=True,
+        seed_source="deepener_seed",
+        seed_query_origin="deepener_seed",
+        enable_openalex_enrich=False,
+        fetch_cap=5,
+    )
+    rows = [r for r in res.evidence_rows if r["source_url"] == "https://example.org/cited-ref"]
+    assert rows, "the stubbed deepener seed should produce one kept evidence row"
+    assert rows[0]["source"] == "deepener_seed"
+    assert rows[0]["query_origin"] == "deepener_seed"
+
+
+def test_injection_default_label_is_doi_seed(monkeypatch):
+    """DOI-lane caller (defaults) is unchanged — no regression from the new params."""
+    monkeypatch.setattr(lr, "_fetch_content", _stub_fetch)
+    res = lr.run_live_retrieval(
+        research_question="anticoagulation in atrial fibrillation",
+        seed_urls=["https://doi.org/10.1056/NEJMoa1107039"],
+        seed_only=True,
+        enable_openalex_enrich=False,
+        fetch_cap=5,
+    )
+    rows = [r for r in res.evidence_rows if r["source_url"] == "https://doi.org/10.1056/NEJMoa1107039"]
+    assert rows, "the stubbed DOI seed should produce one kept evidence row"
+    assert rows[0]["source"] == "primary_trial_doi"
+    assert rows[0]["query_origin"] == "primary_trial_doi_seed"
```
