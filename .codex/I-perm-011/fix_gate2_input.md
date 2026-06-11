# Codex diff-gate — I-perm-011 (#1205): subquery relevance-floor fix (source-starvation). iter 1 of 5.
HARD CAP 5 iters. Front-load findings. APPROVE iff zero NOVEL P0 AND zero P1. Emit §8.3.9 schema; final line EXACTLY 'verdict: APPROVE' or 'verdict: REQUEST_CHANGES'.

## Problem (measured on the live drb_76 run)
evidence_selector relevance-floor _row_relevance normalizes lexical overlap by the WHOLE ~73-token
research question+protocol, so the 0.30 floor demands >=22 exact content-word matches -> it DROPPED
74 on-topic T1 clinical papers (Nature/Cell/Gut/PMC CRC-microbiota) on vocabulary mismatch. 597->53.

## Fix (verify against the diff below)
- evidence_selector.py: score each row vs its BEST-MATCHING sub-query (small per-facet denominators),
  floor uses max(whole-question, best-facet). New helpers _subquery_floor_enabled (flag
  PG_SELECT_SUBQUERY_FLOOR default OFF) / _subquery_token_sets / _row_relevance_facet; new optional
  sub_queries param. CONFINED to the relevance_floor!=None path where it is MONOTONIC-UP (keeps a
  SUPERSET, can only OPEN never tighten); tier-balanced truncating path forces empty subquery sets ->
  byte-identical. Flag OFF / slate-absent -> byte-identical.
- run_honest_sweep_r3.py: assemble sub_queries from decomposed + research-planner facets, thread to
  the 2 floor-path select sites; flag-gated extraction_yield.total_extracted_rows + selected_to_generator_initial telemetry.
- run_gate_b.py: PG_SELECT_SUBQUERY_FLOOR=1 force-on in the slate. DELIBERATELY did NOT lower
  PG_LIVE_MAX_EV_TO_GEN (kept 1500) — respects the operator 2026-06-10 decision; per-section cap 40 is
  the binding per-prompt guard; post-fix pool 597 < 1500 so non-binding by construction.

## RED-TEAM CHECKLIST
(a) Is it truly SUPERSET-only on the floor path (can only ADD rows, never drop a previously-kept row)?
(b) Flag OFF / tier-balanced path byte-identical?
(c) Faithfulness gates (strict_verify/4-role/D8) untouched? (only WHICH rows reach the generator changes;
    the same per-claim verification still runs on every row.)
(d) Does declining the cap-lowering leave any flood risk? (pool 597 < 1500, per-section cap 40 binds.)
(e) telemetry now reports the true pre-select (597) + post-select (53) counts?
Claude already ran: test_subquery_floor_relevance (9) + source_funnel_telemetry (8) + rerank (8) = 25 green;
build agent reported 179 total green, faithfulness untouched.

## DIFF
```diff
diff --git a/scripts/dr_benchmark/run_gate_b.py b/scripts/dr_benchmark/run_gate_b.py
index b40c6d44..05259e9f 100644
--- a/scripts/dr_benchmark/run_gate_b.py
+++ b/scripts/dr_benchmark/run_gate_b.py
@@ -538,6 +538,23 @@ _FULL_CAPABILITY_BENCHMARK_SLATE: dict[str, str] = {
     "PG_USE_FINDING_DEDUP": "1",
     "PG_CAPPED_FINDING_DEDUP": "1",
     "PG_RELEVANCE_FLOOR": "0.30",
+    # I-perm-011 (#1205): max-over-subqueries relevance floor. `_row_relevance`
+    # normalizes overlap by the WHOLE multi-part question token set, so a ~73-token
+    # research question makes the 0.30 floor demand >=22 exact-word matches — which
+    # over-drops on-topic top-tier papers whose domain vocabulary doesn't lexically
+    # match the question's exact words (drb_76: 597->53 pre-select; 74 on-topic T1
+    # shed). ON => each row is scored against the BEST-MATCHING decomposed sub-query
+    # (q1d + planner facets, small per-facet denominators) and the floor uses
+    # max(whole-question, best-facet) — MONOTONIC-UP, so it can only OPEN the
+    # throttle (keeps a SUPERSET), never tighten it. PG_LIVE_MAX_EV_TO_GEN stays
+    # 1500 (DELIBERATELY UNCHANGED): the post-fix surviving pool is <= the
+    # pre-select total (597 for drb_76) which is < 1500, so the global pool cap is
+    # non-binding by construction; the BINDING per-prompt guard is
+    # PG_MAX_EV_PER_SECTION=40 (line 490). Lowering the pool cap would re-impose the
+    # niche-section starvation the 2026-06-10 operator decision (lines 475-482)
+    # explicitly removed — so the diagnosis's secondary "lower to 200" is NOT
+    # applied here. Default OFF in code => slate-absent runs are byte-identical.
+    "PG_SELECT_SUBQUERY_FLOOR": "1",
     # I-ready-017 FX-03 (#1107): the 4-role seam MUST judge each claim against the cited [start:end]
     # BOUNDED window, not the whole source doc (BUG-02 confirmed out-of-span false-accept, claim
     # 06-004). OFF feeds whole-record evidence to Sentinel/Judge so a claim can be VERIFIED on support
@@ -786,6 +803,18 @@ _BENCHMARK_FORCE_ON_FLAGS = frozenset({
     "PG_SWEEP_NUMERIC_SANITIZER",
     "PG_SWEEP_SEMANTIC_CONTRAINDICATION",
     "PG_SPAN_RESOLVER",
+    # I-perm-011 (#1205): force-on the max-over-subqueries relevance floor (exact
+    # "1", not the numeric-floor path which would mangle a non-"1" string the same
+    # way it would PG_RELEVANCE_FLOOR). The lift is CONFINED to the relevance-floor
+    # selection path (the Gate-B path: PG_USE_FINDING_DEDUP + PG_RELEVANCE_FLOOR are
+    # both on here), where it is MONOTONIC-UP (keeps a SUPERSET; faithfulness gates
+    # untouched), so forcing it on can only OPEN the over-aggressive floor that shed
+    # 74 on-topic T1 rows on drb_76 — never tighten it. (It does NOT apply to the
+    # tier-balanced truncating path, where a score lift could reorder top-N.) NOT
+    # added to _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS (no fail-closed gate): a newly
+    # introduced selection fix, kept active-by-slate but not yet a mandatory paid-
+    # run precondition (the I-perm-003 selection-scale stance).
+    "PG_SELECT_SUBQUERY_FLOOR",
 })
 
 # Flags/modes that the benchmark slate force-sets to a specific value that is
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index dffbbd71..2a3bab77 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -1143,6 +1143,21 @@ def _retrieval_manifest_section(retrieval) -> dict:
         "extraction_yield": {
             "fetched": getattr(retrieval, "candidates_fetched", 0),
             "finding_rows": getattr(retrieval, "extraction_finding_rows", 0),
+            # I-perm-011 (#1205): the frozen `finding_rows` above is a MAIN-LANE
+            # snapshot (counted at run_live_retrieval return, BEFORE the additive
+            # agentic/STORM merges), so it is neither the true pre-select pool nor
+            # the final generator count. `total_extracted_rows` is the TRUE
+            # post-merge pre-selection pool (`len(retrieval.evidence_rows)` after
+            # all lanes). Added only when PG_SELECT_SUBQUERY_FLOOR is on so a
+            # flag-OFF / slate-absent run keeps a byte-identical `extraction_yield`
+            # dict (the existing exact-shape telemetry tests stay green).
+            **(
+                {"total_extracted_rows": len(
+                    getattr(retrieval, "evidence_rows", []) or []
+                )}
+                if _env_flag("PG_SELECT_SUBQUERY_FLOOR", default=False)
+                else {}
+            ),
         },
     }
 
@@ -4579,6 +4594,20 @@ async def run_one_query(
             _relevance_floor = parse_relevance_floor(
                 os.getenv("PG_RELEVANCE_FLOOR")
             )
+        # I-perm-011 (#1205): collect the decomposed sub-query TEXT (q1d +
+        # research-planner facets) so the selector can score each row against the
+        # BEST-MATCHING sub-query (small per-facet denominator) instead of the
+        # whole multi-part question (whose long denominator over-cuts on-topic
+        # T1 papers at the 0.30 floor). The selector itself is gated on
+        # PG_SELECT_SUBQUERY_FLOOR (default OFF -> the list is ignored and scoring
+        # is byte-identical), so building it unconditionally is safe + side-effect
+        # free. `_research_plan` is None when the planner is OFF; `_decomposed`
+        # defaults to [].
+        _subquery_texts: list[str] = list(_decomposed or [])
+        if _research_plan is not None:
+            _subquery_texts += [
+                str(sq) for sq in (getattr(_research_plan, "sub_queries", []) or [])
+            ]
         # M-42e (2026-04-22): pass primary_trial_anchors to the
         # selector so it can reserve T1 slots for named-trial
         # primary papers. Anchors come from the loaded scope
@@ -4655,6 +4684,7 @@ async def run_one_query(
             max_rows=max_ev,
             primary_trial_anchors=_primary_anchors,
             relevance_floor=_relevance_floor,   # Phase 5: None OFF -> 20-cap path
+            sub_queries=_subquery_texts,        # I-perm-011: flag-gated facet floor
         )
         evidence_for_gen = evidence_selection.selected_rows
         # I-ready-004 (#1078): CAPPED finding-dedup for Gate-B. The relevance-floor selection above is
@@ -5245,6 +5275,7 @@ async def run_one_query(
                         max_rows=max_ev,
                         primary_trial_anchors=_primary_anchors,
                         relevance_floor=_relevance_floor,   # Phase 5 (#989)
+                        sub_queries=_subquery_texts,        # I-perm-011: facet floor
                     )
                     # I-ready-004 (#1078) Codex diff-gate iter-1 P1-1: the gap-round reselect uses the
                     # NO-CAP relevance-floor selector too — without this, a saturation-expansion run
@@ -6823,6 +6854,25 @@ async def run_one_query(
             "evaluator_gate": eval_gate.to_dict(),
             # BUG-M-201: generator-visible evidence provenance.
             "evidence_selection": evidence_selection.to_dict(),
+            # I-perm-011 (#1205): the post-floor extraction funnel endpoint —
+            # rows that survived the relevance floor + capped-dedup and form the
+            # generator BASE (pre-prepend; the contract/upload prepends are added
+            # later, and the post-floor base is the inflation-free count). This is
+            # the honest counterpart to extraction_yield.total_extracted_rows (the
+            # pre-select pool). It is read from the SAME `evidence_selection` object
+            # the manifest already exposes above (the round-0 post-floor/dedup
+            # selection — NOT reassigned by the saturation loop, which tracks its
+            # rounds via `evidence_for_gen`/`_resel`), so the two keys are always
+            # consistent. This is exactly the drb_76 `selected=53 of 597` endpoint.
+            # Gated on PG_SELECT_SUBQUERY_FLOOR so a flag-OFF / slate-absent run
+            # keeps a byte-identical manifest.
+            **(
+                {"selected_to_generator_initial": len(
+                    evidence_selection.selected_rows
+                )}
+                if _env_flag("PG_SELECT_SUBQUERY_FLOOR", default=False)
+                else {}
+            ),
             "protocol_sha256": scope.protocol_sha256,
             # #958 (S2): use the shared retrieval-section writer so the
             # corpus-truncation flag + counts land on the SUCCESS path too
diff --git a/src/polaris_graph/retrieval/evidence_selector.py b/src/polaris_graph/retrieval/evidence_selector.py
index 940687ce..af3e73ba 100644
--- a/src/polaris_graph/retrieval/evidence_selector.py
+++ b/src/polaris_graph/retrieval/evidence_selector.py
@@ -423,6 +423,75 @@ def _row_relevance(
     return len(overlap) / max(1, len(anchors))
 
 
+# ── I-perm-011 (#1205): max-over-subqueries relevance (default OFF) ──────────
+# `_row_relevance` normalizes overlap by the WHOLE question+protocol token set.
+# That denominator scales with question LENGTH: a ~73-content-token multi-part
+# research question makes the 0.30 floor demand >=22 exact-word matches, so an
+# excellent on-topic top-tier paper whose domain vocabulary (Fusobacterium,
+# butyrate, tumorigenesis) doesn't lexically overlap the question's exact words
+# (predominant, mitigate, retard) is dropped (drb_76: 597->53; 74 on-topic T1
+# shed). The run already decomposes the question into focused sub-queries
+# (q1d + STORM). Scoring each row against the BEST-MATCHING sub-query (each with
+# a SMALL denominator) lets a row matching ONE facet clear the floor instead of
+# being diluted by the other ~60 paragraph tokens.
+#
+# This is MONOTONIC-UP: it returns max(whole_question_score, best_subquery_score)
+# so a row NEVER scores lower than today. Flag-ON therefore keeps a SUPERSET of
+# flag-OFF rows — it can only OPEN the throttle, never tighten it.
+#
+# Flag `PG_SELECT_SUBQUERY_FLOOR` (default OFF). OFF, or no sub-query token sets,
+# => the score equals `_row_relevance` exactly (byte-identical selection).
+
+
+def _subquery_floor_enabled() -> bool:
+    """Kill-switch `PG_SELECT_SUBQUERY_FLOOR` (default OFF). OFF => the
+    whole-question `_row_relevance` score is used unchanged (byte-identical)."""
+    raw = os.environ.get("PG_SELECT_SUBQUERY_FLOOR", "0").strip().lower()
+    return raw not in ("0", "false", "no", "off", "")
+
+
+def _subquery_token_sets(sub_queries: list[str] | None) -> list[set[str]]:
+    """Per-sub-query content-token sets, dropping empties. Returns [] when the
+    feature is disabled OR no usable sub-queries are supplied — the empty list
+    makes `_row_relevance_facet` fall back to the whole-question score."""
+    if not sub_queries or not _subquery_floor_enabled():
+        return []
+    sets: list[set[str]] = []
+    for sq in sub_queries:
+        toks = _content_tokens(str(sq or ""))
+        if toks:
+            sets.append(toks)
+    return sets
+
+
+def _row_relevance_facet(
+    row: dict[str, Any],
+    question_tokens: set[str],
+    protocol_tokens: set[str],
+    subquery_token_sets: list[set[str]],
+) -> float:
+    """Relevance score that takes the MAX of the whole-question score and the
+    best per-sub-query score. `subquery_token_sets` empty => identical to
+    `_row_relevance` (the only caller-visible difference is the max-up lift when
+    the flag is on AND sub-queries are present). Result clamped to [0, 1]."""
+    base = _row_relevance(row, question_tokens, protocol_tokens)
+    if not subquery_token_sets:
+        return base
+    text = " ".join(
+        str(row.get(k, "") or "") for k in ("statement", "direct_quote")
+    )
+    ev_toks = _content_tokens(text)
+    best = base
+    for subq_toks in subquery_token_sets:
+        denom = len(subq_toks)
+        if denom <= 0:
+            continue
+        score = len(ev_toks & subq_toks) / denom
+        if score > best:
+            best = score
+    return min(1.0, best)
+
+
 # ── #955 (S2, 2026-05-30): within-tier-band recency tiebreaker ──────────────
 # Semantic Scholar `year` is fetched (live_retriever.py) and lands on the row
 # (row["year"] or row["metadata"]["year"]) but the selector never used it, so a
@@ -1078,6 +1147,7 @@ def select_evidence_for_generation(
     max_rows: int,
     primary_trial_anchors: list[str] | None = None,
     relevance_floor: float | None = None,
+    sub_queries: list[str] | None = None,
 ) -> EvidenceSelection:
     """Pick up to max_rows evidence rows, tier-balanced + relevance-ranked.
 
@@ -1138,11 +1208,27 @@ def select_evidence_for_generation(
             if v:
                 protocol_tokens |= _content_tokens(str(v))
 
+    # I-perm-011 (#1205): per-sub-query token sets for the max-over-subqueries
+    # floor (default OFF). CONFINED TO THE RELEVANCE-FLOOR PATH (`relevance_floor
+    # is not None`): the lift is MONOTONIC-UP, so on the keep-everything-above-floor
+    # path it only OPENS the floor (keeps a SUPERSET) — a true "can only open, never
+    # tighten" guarantee. On the tier-balanced TRUNCATING path it must NOT apply:
+    # lifting a row's score there reorders the top-N and could DISPLACE a
+    # previously-kept row (a tighten). So for the tier-balanced path the sets stay
+    # empty and `_row_relevance_facet` == `_row_relevance` exactly (byte-identical
+    # regardless of the flag). `_subquery_token_sets` also returns [] when the flag
+    # is OFF or no usable sub-queries are supplied.
+    _subq_token_sets = (
+        _subquery_token_sets(sub_queries) if relevance_floor is not None else []
+    )
+
     # Score every row and tag with tier + original index.
     scored: list[tuple[int, float, str, dict[str, Any]]] = []
     for idx, row in enumerate(evidence_rows):
         tier = _row_tier(row, url_to_tier)
-        score = _row_relevance(row, question_tokens, protocol_tokens)
+        score = _row_relevance_facet(
+            row, question_tokens, protocol_tokens, _subq_token_sets,
+        )
         scored.append((idx, score, tier, row))
 
     # Full tier counts (FROM evidence_rows, the selectable universe).
```
## NEW TEST
```python
"""I-perm-011 (#1205): max-over-subqueries relevance floor.

`_row_relevance` normalizes lexical overlap by the WHOLE question+protocol token
set, so a long multi-part research question makes the 0.30 floor demand many exact
matches — over-dropping an on-topic paper whose domain vocabulary matches ONE
facet but not the whole paragraph (drb_76: 597->53 pre-select; 74 on-topic T1
shed). The fix scores each row against the BEST-MATCHING decomposed sub-query
(small per-facet denominator), gated on PG_SELECT_SUBQUERY_FLOOR (default OFF).

These tests prove the two contract guarantees:
  1. THROTTLE OPENS: a row matching ONE facet strongly but scoring < floor against
     the whole question is DROPPED when off, KEPT when on (more rows reach gen).
  2. BEHAVIOR-SAFE WHEN OFF: flag off (or no sub-queries) => selection is
     byte-identical to the prior whole-question floor, and the on-mode result is a
     SUPERSET of the off-mode result (monotonic-up; never tightens).
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.evidence_selector import (
    select_evidence_for_generation,
    _row_relevance,
    _row_relevance_facet,
    _subquery_token_sets,
    _content_tokens,
)


# A long multi-part research question (the drb_76 denominator pathology, in
# miniature): many distinct content tokens, so a row matching only a niche facet
# scores far below the 0.30 floor against the whole paragraph.
_LONG_QUESTION = (
    "Considering the predominant dietary choices that shape and influence the "
    "delicate equilibrium of the intestinal environment, what mechanisms might "
    "mitigate, retard, or otherwise modulate the downstream physiological "
    "consequences across multiple distinct organ systems and metabolic pathways?"
)

# A focused facet sub-query (q1d/STORM decomposition) with a SMALL token set.
_FACET = "gut microbiota dysbiosis colorectal cancer tumorigenesis"

# A target row whose vocabulary matches the FACET strongly but barely overlaps the
# long question's exact words. Off-mode score is < 0.30; facet score is >> 0.30.
_TARGET_ROW = {
    "evidence_id": "ev_facet",
    "url": "https://www.nature.com/articles/microbiota-crc",
    "tier": "T1",
    "title": "Microbiota dysbiosis and colorectal tumorigenesis",
    "statement": (
        "Gut microbiota dysbiosis promotes colorectal cancer tumorigenesis "
        "through pathogenic bacteria and toxic metabolites."
    ),
    "direct_quote": "dysbiosis drives colorectal tumorigenesis",
}

_FLOOR = 0.30


def _classified(url: str, tier: str):
    return {"url": url, "tier": tier}


def test_target_row_scores_below_floor_against_whole_question() -> None:
    """Precondition: with the whole-question score (off mode) the target row is
    UNDER the 0.30 floor — i.e. today's behaviour drops this genuinely on-topic
    row. (If this ever stops holding the fixture is stale, not the fix.)"""
    q_toks = _content_tokens(_LONG_QUESTION)
    base = _row_relevance(_TARGET_ROW, q_toks, set())
    assert base < _FLOOR, f"fixture stale: base score {base} not below floor"


def test_target_row_scores_above_floor_against_best_facet() -> None:
    """The max-over-subqueries score clears the floor because the row matches the
    small-denominator facet strongly."""
    q_toks = _content_tokens(_LONG_QUESTION)
    sets = [_content_tokens(_FACET)]
    facet = _row_relevance_facet(_TARGET_ROW, q_toks, set(), sets)
    assert facet >= _FLOOR, f"facet score {facet} did not clear floor"
    # And it is never LOWER than the whole-question base (monotonic-up).
    assert facet >= _row_relevance(_TARGET_ROW, q_toks, set())


def test_floor_drops_target_when_flag_off(monkeypatch) -> None:
    """OFF: the over-aggressive whole-question floor drops the on-topic row."""
    monkeypatch.delenv("PG_SELECT_SUBQUERY_FLOOR", raising=False)
    sel = select_evidence_for_generation(
        research_question=_LONG_QUESTION,
        protocol=None,
        classified_sources=[_classified(_TARGET_ROW["url"], "T1")],
        evidence_rows=[dict(_TARGET_ROW)],
        max_rows=0,                       # floor mode replaces the cap
        relevance_floor=_FLOOR,
        sub_queries=[_FACET],             # provided, but flag OFF => ignored
    )
    kept_urls = {r["url"] for r in sel.selected_rows}
    assert _TARGET_ROW["url"] not in kept_urls
    assert sel.dropped_count == 1


def test_floor_keeps_target_when_flag_on(monkeypatch) -> None:
    """ON: the throttle OPENS — the row matching one facet strongly is kept."""
    monkeypatch.setenv("PG_SELECT_SUBQUERY_FLOOR", "1")
    sel = select_evidence_for_generation(
        research_question=_LONG_QUESTION,
        protocol=None,
        classified_sources=[_classified(_TARGET_ROW["url"], "T1")],
        evidence_rows=[dict(_TARGET_ROW)],
        max_rows=0,
        relevance_floor=_FLOOR,
        sub_queries=[_FACET],
    )
    kept_urls = {r["url"] for r in sel.selected_rows}
    assert _TARGET_ROW["url"] in kept_urls
    assert sel.dropped_count == 0


def test_on_mode_is_superset_of_off_mode(monkeypatch) -> None:
    """Monotonic-up: every row kept OFF is also kept ON (never tightens), and ON
    keeps at least as many rows. Mixed pool: one facet-matching niche row + one
    row that clears the whole-question floor outright."""
    on_topic_general = {
        "evidence_id": "ev_general",
        "url": "https://example.org/general",
        "tier": "T2",
        "title": "dietary choices and intestinal equilibrium",
        # Overlaps the whole question heavily -> clears the floor in BOTH modes.
        "statement": (
            "predominant dietary choices shape the intestinal equilibrium and "
            "mitigate downstream physiological consequences across organ systems "
            "and metabolic pathways"
        ),
        "direct_quote": "dietary choices modulate intestinal equilibrium",
    }
    rows = [dict(_TARGET_ROW), dict(on_topic_general)]
    classified = [
        _classified(_TARGET_ROW["url"], "T1"),
        _classified(on_topic_general["url"], "T2"),
    ]

    monkeypatch.delenv("PG_SELECT_SUBQUERY_FLOOR", raising=False)
    off = select_evidence_for_generation(
        research_question=_LONG_QUESTION, protocol=None,
        classified_sources=classified, evidence_rows=[dict(r) for r in rows],
        max_rows=0, relevance_floor=_FLOOR, sub_queries=[_FACET],
    )
    off_urls = {r["url"] for r in off.selected_rows}

    monkeypatch.setenv("PG_SELECT_SUBQUERY_FLOOR", "1")
    on = select_evidence_for_generation(
        research_question=_LONG_QUESTION, protocol=None,
        classified_sources=classified, evidence_rows=[dict(r) for r in rows],
        max_rows=0, relevance_floor=_FLOOR, sub_queries=[_FACET],
    )
    on_urls = {r["url"] for r in on.selected_rows}

    assert off_urls.issubset(on_urls), "on mode dropped a row that off kept"
    assert len(on_urls) > len(off_urls), "on mode did not open the throttle"
    assert on_topic_general["url"] in off_urls  # general row clears floor in both


def test_no_subqueries_is_byte_identical(monkeypatch) -> None:
    """Flag ON but NO sub-queries supplied => `_subquery_token_sets` is empty =>
    scoring falls back to the whole-question floor exactly (byte-identical)."""
    monkeypatch.setenv("PG_SELECT_SUBQUERY_FLOOR", "1")
    assert _subquery_token_sets(None) == []
    assert _subquery_token_sets([]) == []
    sel = select_evidence_for_generation(
        research_question=_LONG_QUESTION,
        protocol=None,
        classified_sources=[_classified(_TARGET_ROW["url"], "T1")],
        evidence_rows=[dict(_TARGET_ROW)],
        max_rows=0,
        relevance_floor=_FLOOR,
        sub_queries=None,                 # no facets => fall back
    )
    assert _TARGET_ROW["url"] not in {r["url"] for r in sel.selected_rows}


def test_tier_balanced_truncating_path_unchanged_when_flag_on(monkeypatch) -> None:
    """The lift is CONFINED to the relevance-floor path. On the tier-balanced
    TRUNCATING path (relevance_floor=None, max_rows < pool), lifting scores would
    reorder the top-N and could DISPLACE a previously-kept row — a tighten. So the
    facet lift must NOT apply there: the selection is byte-identical regardless of
    the flag, even with sub_queries supplied."""
    rows = [dict(_TARGET_ROW)]
    for i in range(6):
        rows.append({
            "evidence_id": f"ev_{i}",
            "url": f"https://example.org/row{i}",
            "tier": "T2",
            "title": f"intestinal equilibrium dietary choices {i}",
            "statement": (
                "predominant dietary choices shape intestinal equilibrium and "
                f"modulate downstream physiological consequences {i}"
            ),
            "direct_quote": "",
        })
    classified = [{"url": r["url"], "tier": r["tier"]} for r in rows]

    def _run() -> list[str]:
        sel = select_evidence_for_generation(
            research_question=_LONG_QUESTION,
            protocol=None,
            classified_sources=classified,
            evidence_rows=[dict(r) for r in rows],
            max_rows=3,                    # truncating tier-balanced path
            relevance_floor=None,          # NOT the floor path
            sub_queries=[_FACET],
        )
        return [r["url"] for r in sel.selected_rows]

    monkeypatch.delenv("PG_SELECT_SUBQUERY_FLOOR", raising=False)
    off = _run()
    monkeypatch.setenv("PG_SELECT_SUBQUERY_FLOOR", "1")
    on = _run()
    assert on == off, "facet lift leaked into the tier-balanced truncating path"


def test_facet_helper_clamps_to_unit_interval() -> None:
    """A row that contains every facet token still scores <= 1.0."""
    q_toks = _content_tokens(_LONG_QUESTION)
    sets = [_content_tokens("alpha beta")]
    row = {"statement": "alpha beta alpha beta", "direct_quote": "alpha beta"}
    assert _row_relevance_facet(row, q_toks, set(), sets) == pytest.approx(1.0)


def test_subquery_token_sets_drops_empty_and_respects_flag(monkeypatch) -> None:
    """Empty/whitespace sub-queries are dropped; flag OFF returns []."""
    monkeypatch.setenv("PG_SELECT_SUBQUERY_FLOOR", "1")
    sets = _subquery_token_sets([_FACET, "", "   ", "the a an"])
    assert len(sets) == 1                 # only the real facet survives
    assert sets[0] == _content_tokens(_FACET)
    monkeypatch.setenv("PG_SELECT_SUBQUERY_FLOOR", "0")
    assert _subquery_token_sets([_FACET]) == []
```
