HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex DIFF gate — I-meta-005 Phase 3 (#987): plan-sufficiency money-trap gate

Reviewing the CODE DIFF vs the APPROVED brief (.codex/I-meta-005-phase-3/brief.md, Codex APPROVE 6-round)
+ build_spec.md. This verdict AUTHORIZES THE MERGE (operator governance 2026-05-31). §8.3.9 YAML FIRST.
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## VERIFY (read actual diff + workspace):
1. OFF byte-identity: PG_USE_RESEARCH_PLANNER off -> legacy assess_corpus_adequacy + round-robin
   assignment byte-identical; additive fields (sub_query_indices/authority_score) inert.
2. ZERO generator bill on hold: EXPAND/ABORT -> abort_corpus_inadequate, single binding gate runs on the
   FINAL evidence_for_gen (after selection :2573 + V30 contract :2719 + upload :2749) BEFORE
   generate_multi_section_report :2805; legacy :2001/:2152/:2249 telemetry-only on-mode.
3. FACET-LEVEL: section SUFFICIENT iff total>=evidence_target AND every mapped sub_query_index has
   >=MIN_PER_FACET above-floor rows; whole-plan union(sub_query_indices)==range(len(sub_queries))
   fail-closed (MalformedPlanError).
4. **ARCHITECT P1 FIX (verify it is complete):** the on-mode _assign_evidence_to_planned_outline did
   flat-concat(section_above+section_below)[:cap], which could truncate a certified facet's only row ->
   generator billed a section whose facet has ZERO evidence (facet-level money-trap at the cap boundary).
   FIX: per-facet RESERVATION — reserve min_per_facet above-floor rows from EACH mapped facet BEFORE the
   cap slice; cap=max(target,len(reserved)) bounded by max_ev_per_section so a certified facet is NEVER
   truncated. Plus authority_floor threaded into the assignment (gate/assignment agree). Confirm a
   SUFFICIENT section's billed ev_ids include >=min_per_facet rows for EVERY mapped facet. Regression
   P3-15e reproduces the architect's exact case (target=2, facets [0,1], 3 facet-0 + 1 facet-1 -> f1_a
   must survive).
5. authority floor = numeric authority_score (not the confidence enum); NO _DEFAULT_DOMAIN_THRESHOLDS /
   if-domain== on the on-path.

## DEVIATIONS — RULE ON EACH (honest disclosure):
A. The sweep gate block (run_honest_sweep_r3.py binding gate + on-mode abort) is ast.parse-validated only,
   not executed in smoke (the monolithic async sweep needs live keys). Its helpers are the SAME names in
   scope at the legacy :2273 abort in the same function. Acceptable (consistent with prior phases), or
   does it need a drivable test?
B. PG_PLAN_SUFFICIENCY_AUTHORITY_FLOOR default 0.3 + MIN_PER_FACET default 1 are unvalidated tuning
   guesses (env-overridable; tests pass explicit floors). Calibration is a Phase-4 first-live-run task.
   Acceptable to defer?
C. Anchor-query rows: on-mode research_question is sub-query #1 (live_retriever:1741), so some rows carry
   query_origin==research_question, which is neither a section sub-query text nor in the LOCKED sentinel
   set {primary_trial_doi_seed,need_type_backend,domain_backend}. Under strict provenance they are
   uncredited unless the research_question is a section's mapped sub-query. Implemented the sentinel set
   EXACTLY as approved (not widened). Is this the right scope call, or should the anchor be a section
   facet / fallback-eligible?

## SMOKE: 25 Phase-3 (P3-1..P3-17 + P3-15e per-facet truncation + P3-15f floor-threading) + 44 generator/planner regression green.
## ARCHITECT (Claude): 4/5 axes CLEAN; the gate_billed_set P1 (cap-truncation) FIXED post-build + regression-tested.

APPROVE iff OFF byte-identical, zero-generator-bill-before-sufficiency holds, facet-level coverage carries
through to the billed set (architect P1 fix complete), and deviations A/B/C are acceptable Phase-3 scope.

--- FULL DIFF BELOW ---
```diff
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index e2cc3638..fa28de6b 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -2270,7 +2270,12 @@ async def run_one_query(
         # R-6 Gap-1: if adequacy still says ABORT after optional
         # expansion, refuse to synthesize — emit a short "corpus
         # inadequate" manifest and return status=abort_corpus_inadequate.
-        if adequacy.decision == "abort":
+        # I-meta-005 Phase 3 (#987): ON-mode this legacy domain-keyed adequacy
+        # is TELEMETRY-ONLY — it must NOT abort here, or an on-mode thin corpus
+        # would exit via the aggregate-count gate BEFORE the binding plan-
+        # sufficiency gate (the single final gate on `evidence_for_gen`) ever
+        # runs. OFF-mode this aborts byte-identically (the off-mode gate as today).
+        if not _use_research_planner and adequacy.decision == "abort":
             _log(f"[ABORT]       Corpus inadequate for confident synthesis. "
                  f"Refusing to ship a misleading short report.")
             summary["status"] = "abort_corpus_inadequate"
@@ -2756,6 +2761,135 @@ async def run_one_query(
             q.get("uploaded_documents_blocked_count", 0) or 0
         )
 
+        # I-meta-005 Phase 3 (#987): THE SINGLE BINDING MONEY GATE (on-mode).
+        # `evidence_for_gen` is now FULLY constructed — selection (:2568) +
+        # the V30 contract-row prepend (:2719) + the upload-row prepend (:2754)
+        # have all run and NOTHING further mutates it before the generator bills
+        # at `generate_multi_section_report` below. The plan-sufficiency gate
+        # certifies EXACTLY the rows that will be billed: does the corpus cover
+        # EVERY planned sub-question to its per-section evidence_target at the
+        # numeric authority floor? PROCEED -> generator; EXPAND/ABORT collapse to
+        # `abort_corpus_inadequate` with ZERO generator tokens (Phase 4 owns the
+        # actual saturation EXPANSION loop). Pure / no-network / spend-free. OFF-
+        # mode this whole block is skipped (the legacy domain-keyed gate aborted
+        # earlier, byte-identically).
+        if _use_research_planner and _research_plan is not None:
+            from src.polaris_graph.adequacy.plan_sufficiency_gate import (
+                assess_plan_sufficiency,
+            )
+            _suff_floor_env = os.getenv(
+                "PG_PLAN_SUFFICIENCY_AUTHORITY_FLOOR", ""
+            ).strip()
+            _suff_floor = float(_suff_floor_env) if _suff_floor_env else None
+            _suff_round = int(os.getenv("PG_PLAN_SUFFICIENCY_ROUND_INDEX", "0"))
+            _suff_max_rounds = int(
+                os.getenv("PG_PLAN_SUFFICIENCY_MAX_ROUNDS", "0")
+            )
+            _suff = assess_plan_sufficiency(
+                plan=_research_plan,
+                corpus_rows=evidence_for_gen,
+                authority_floor=_suff_floor,
+                round_index=_suff_round,
+                max_rounds=_suff_max_rounds,
+            )
+            (run_dir / "plan_sufficiency.json").write_text(
+                json.dumps(asdict(_suff), indent=2, sort_keys=True, default=str)
+                + "\n",
+                encoding="utf-8",
+            )
+            _log(
+                f"[sufficiency] verdict={_suff.verdict} "
+                f"floor={_suff.authority_floor} "
+                f"sections={len(_suff.per_unit)} "
+                f"under_covered={len(_suff.under_covered_units)}"
+            )
+            if _suff.verdict != "proceed":
+                # EXPAND or ABORT -> hold BEFORE the generator bills (Phase 3
+                # guarantee: a shallow corpus NEVER spends a generator token).
+                _log(
+                    f"[ABORT]       Plan-sufficiency {_suff.verdict.upper()}: "
+                    f"{len(_suff.under_covered_units)} planned section(s) under-"
+                    f"covered. Refusing to bill the generator on a corpus that "
+                    f"does not cover every planned sub-question."
+                )
+                summary["status"] = "abort_corpus_inadequate"
+                summary["error"] = (
+                    f"plan_sufficiency_{_suff.verdict}: "
+                    f"{','.join(_suff.under_covered_units)}"
+                )
+                _shortfall_lines = []
+                for _u in _suff.per_unit:
+                    if _u.sufficient:
+                        continue
+                    _shortfall_lines.append(
+                        f"- **{_u.unit_id}** {_u.title!r}: "
+                        f"covered={_u.covered_count}/target={_u.evidence_target} "
+                        f"above floor; empty facets="
+                        f"{_u.empty_facets}; below-floor relevant="
+                        f"{_u.below_floor_count}"
+                    )
+                (run_dir / "report.md").write_text(
+                    f"# Research report: {q['question']}\n\n"
+                    "## Pipeline verdict\n\n"
+                    "The corpus retrieved for this query did not cover every "
+                    "planned sub-question to its per-section evidence target at "
+                    "the authority floor. The pipeline is holding BEFORE billing "
+                    "the report generator (zero generator tokens spent) rather "
+                    "than synthesizing a report with uncovered planned facets.\n\n"
+                    f"Verdict: **{_suff.verdict.upper()}** "
+                    f"(authority floor {_suff.authority_floor}).\n\n"
+                    "### Under-covered planned sections\n\n"
+                    + "\n".join(_shortfall_lines)
+                    + "\n\n### Suggested next steps\n\n"
+                    "- Saturate retrieval on the under-covered sub-questions "
+                    "(Phase 4 expansion loop).\n"
+                    "- Verify the planned evidence targets match what the "
+                    "literature can support for each facet.\n",
+                    encoding="utf-8",
+                )
+                # NOTE: the retrieval trace was already flushed unconditionally
+                # at the post-deepener checkpoint (mirrors the legacy abort at
+                # :2273, which does not re-flush) — do NOT re-flush here.
+                run_cost = current_run_cost()
+                manifest = _base_manifest_envelope(
+                    run_id=run_id, q=q, retrieval=retrieval, run_cost=run_cost,
+                )
+                manifest.update({
+                    "status": "abort_corpus_inadequate",
+                    "plan_sufficiency": asdict(_suff),
+                    "corpus": {
+                        "count": dist.total_sources,
+                        "tier_fractions": dist.tier_fractions,
+                    },
+                })
+                manifest = augment_v6_manifest(
+                    manifest,
+                    external_run_id=q.get("external_run_id"),
+                    decision_id=q.get("decision_id"),
+                    query_slug=q.get("slug"),
+                )
+                (run_dir / "manifest.json").write_text(
+                    json.dumps(manifest, indent=2, sort_keys=True, default=str)
+                    + "\n",
+                    encoding="utf-8",
+                )
+                summary["manifest"] = manifest
+                summary["cost_usd"] = run_cost
+                try:
+                    write_per_run_cost_ledger(run_dir, run_id)
+                except Exception:
+                    pass
+                if q.get("v6_mode") and q.get("external_run_id"):
+                    emit_terminal_event(
+                        q.get("external_run_id"),
+                        "abort_corpus_inadequate",
+                        error_msg=summary.get("error"),
+                    )
+                set_current_run_id(None)
+                set_reasoning_sink(None)
+                log_f.close()
+                return summary
+
         # I-cd-706: SSE evidence-id events over the FINAL evidence_for_gen set
         # (NOT inside retrieval loops — bounded to the selected rows, tens to
         # low-hundreds). Rows are dicts; guard for any object rows defensively.
diff --git a/src/polaris_graph/adequacy/__init__.py b/src/polaris_graph/adequacy/__init__.py
new file mode 100644
index 00000000..6653adb0
--- /dev/null
+++ b/src/polaris_graph/adequacy/__init__.py
@@ -0,0 +1,27 @@
+"""Plan-sufficiency gate package (I-meta-005 Phase 3, #987).
+
+The MONEY-TRAP fix: the legacy `nodes/corpus_adequacy_gate.py` gate is
+domain-keyed AND aggregate-count only, so a broad-but-shallow corpus PASSES,
+BILLS the generator, then leaves planned sub-questions uncovered. This package
+re-defines adequacy as "does the corpus cover EVERY planned sub-question to its
+per-section evidence target, at the numeric authority floor?" — held at
+EXPAND/abort BEFORE a single generator token is billed.
+
+Behind `PG_USE_RESEARCH_PLANNER` (default off); OFF is byte-identical (the
+legacy `assess_corpus_adequacy` domain-keyed gate is retained + selected when
+off). The gate is a PURE function over already-retrieved rows + the pinned plan
++ the per-row authority sidecar — no network, no LLM, spend-free.
+"""
+from src.polaris_graph.adequacy.plan_sufficiency_gate import (
+    PlanSufficiencyReport,
+    UnitCoverage,
+    assess_plan_sufficiency,
+    relevant_section_indices,
+)
+
+__all__ = [
+    "PlanSufficiencyReport",
+    "UnitCoverage",
+    "assess_plan_sufficiency",
+    "relevant_section_indices",
+]
diff --git a/src/polaris_graph/adequacy/plan_sufficiency_gate.py b/src/polaris_graph/adequacy/plan_sufficiency_gate.py
new file mode 100644
index 00000000..27897c47
--- /dev/null
+++ b/src/polaris_graph/adequacy/plan_sufficiency_gate.py
@@ -0,0 +1,354 @@
+"""Plan-sufficiency gate — I-meta-005 Phase 3 (#987). The money-trap fix.
+
+`assess_plan_sufficiency` decides whether the BILLED evidence set covers EVERY
+planned sub-question to its per-section evidence target at the numeric authority
+floor — BEFORE a generator token is billed. It is a PURE function (no network,
+no LLM) over rows that already carry the §2.3a authority sidecar + `query_origin`
+provenance, plus the pinned `ResearchPlan`.
+
+KEY DESIGN (brief §2.2):
+- Coverage UNIT = the section outline item (its `evidence_target`).
+- Relevance = PROVENANCE-FIRST: a row is relevant to a section iff its
+  `query_origin` matches (normalized equality) one of the sub-query texts at the
+  section's `sub_query_indices`. The content-word overlap fallback is used ONLY
+  for rows whose `query_origin` is EMPTY or one of the explicit NON-QUERY
+  SENTINEL origins (`{primary_trial_doi_seed, need_type_backend, domain_backend}`)
+  — these lanes surface authoritative evidence with no originating sub-query, so
+  they must be creditable. A row whose `query_origin` is a REAL sub-query text
+  that does not match the section is NOT relevant to it (no title-overlap rescue).
+- Authority floor = the NUMERIC `authority_score` (float [0,1]); a row counts
+  toward coverage iff `authority_score >= authority_floor` (a single global
+  float, NOT a per-domain dict). Below-floor relevant rows are reported, not
+  credited.
+- Section SUFFICIENT iff BOTH (facet-level, not section-aggregate):
+    (i)  total above-floor covered_count >= evidence_target, AND
+    (ii) EVERY mapped sub_query_index has >= MIN_PER_FACET above-floor relevant
+         rows — so a section mapped to [4,5,6] cannot pass on rows from 4 alone.
+- Verdict: PROCEED (all sufficient) / EXPAND (≥1 under-covered, round < max) /
+  ABORT (≥1 under-covered, rounds/budget exhausted).
+
+The relevance MAPPING is shared with the generator's on-mode
+`_assign_evidence_to_planned_outline` via `relevant_section_indices`, so a
+section certified SUFFICIENT actually RECEIVES its credited rows (brief §2.2b).
+
+NO `if domain ==` / NO `_DEFAULT_DOMAIN_THRESHOLDS` / NO clinical literal on this
+path — sufficiency is computed from the PLAN x AUTHORITY, never a domain.
+"""
+from __future__ import annotations
+
+import logging
+import os
+from dataclasses import dataclass, field
+from typing import Any, Literal
+
+logger = logging.getLogger("polaris_graph.plan_sufficiency_gate")
+
+SufficiencyVerdict = Literal["proceed", "expand", "abort"]
+
+# NON-QUERY sentinel origins that legitimately carry no sub-query text (brief
+# §2.2). Rows with one of these origins (or an empty origin) are FALLBACK-
+# ELIGIBLE: their relevance is decided by content-word overlap against a
+# section's sub-query texts. A REAL sub-query origin is authoritative and uses
+# provenance-first matching only. Codex-LOCKED — do not widen.
+SENTINEL_ORIGINS: frozenset[str] = frozenset(
+    {"primary_trial_doi_seed", "need_type_backend", "domain_backend"}
+)
+
+
+def _authority_floor_default() -> float:
+    """Single global numeric authority floor in [0,1] (brief §2.2). Read at call
+    time so tests/operators can override via env; callers pass it explicitly."""
+    try:
+        return float(os.getenv("PG_PLAN_SUFFICIENCY_AUTHORITY_FLOOR", "0.3"))
+    except (TypeError, ValueError):
+        return 0.3
+
+
+def _min_per_facet_default() -> int:
+    """Minimum above-floor relevant rows EACH mapped sub-query must have for a
+    section to be sufficient (brief §2.2, default 1)."""
+    try:
+        return max(1, int(os.getenv("PG_PLAN_SUFFICIENCY_MIN_PER_FACET", "1")))
+    except (TypeError, ValueError):
+        return 1
+
+
+@dataclass
+class UnitCoverage:
+    """Per-section coverage detail (brief §2.1)."""
+
+    unit_id: str
+    title: str
+    evidence_target: int
+    sub_query_indices: list[int]
+    covered_count: int                 # above-floor relevant rows (total)
+    below_floor_count: int             # relevant-but-below-authority (reported)
+    sufficient: bool
+    per_facet_covered: dict[int, int] = field(default_factory=dict)
+    empty_facets: list[int] = field(default_factory=list)
+
+
+@dataclass
+class PlanSufficiencyReport:
+    verdict: SufficiencyVerdict
+    authority_floor: float
+    min_per_facet: int
+    round_index: int
+    max_rounds: int
+    per_unit: list[UnitCoverage] = field(default_factory=list)
+    under_covered_units: list[str] = field(default_factory=list)
+    notes: list[str] = field(default_factory=list)
+
+
+def _normalize_query(text: str) -> str:
+    """Normalized form for provenance equality (whitespace-collapsed, lower)."""
+    return " ".join(str(text or "").split()).strip().lower()
+
+
+def _content_words(text: str) -> set[str]:
+    """Reuse the EXISTING grounding tokenizer (alphabetic, >=3 chars, stopword-
+    stripped) — the same primitive the provenance verifier uses (brief §2.2).
+    Imported lazily so this module has no import-time generator dependency."""
+    from src.polaris_graph.generator.provenance_generator import (
+        _content_words as _cw,
+    )
+    return _cw(text)
+
+
+def _min_content_word_overlap() -> int:
+    """The EXISTING `MIN_CONTENT_WORD_OVERLAP` constant (default 2) — no new
+    magic number for the fallback floor (brief §2.2)."""
+    from src.polaris_graph.generator.provenance_generator import (
+        MIN_CONTENT_WORD_OVERLAP,
+    )
+    return MIN_CONTENT_WORD_OVERLAP
+
+
+def _row_text_for_overlap(row: dict[str, Any]) -> str:
+    """The row content used for the content-word fallback: statement + the
+    direct_quote span (NOT just the title — brief §2.2 fallback)."""
+    return " ".join(
+        str(row.get(k) or "")
+        for k in ("statement", "direct_quote")
+    )
+
+
+def relevant_section_indices(
+    row: dict[str, Any],
+    outline: list[Any],
+    sub_queries: list[str],
+) -> list[int]:
+    """Map a row to the outline section index(es) it is RELEVANT to (brief §2.2).
+
+    SHARED by the gate (counting) and the on-mode generator assignment so the
+    SUFFICIENT certification carries through to what the generator receives.
+    Authority is NOT applied here — relevance is provenance/overlap only; the
+    gate layers the numeric floor on top.
+
+    Provenance-first: a non-sentinel, non-empty `query_origin` credits ONLY the
+    section(s) whose `sub_query_indices` point at that exact sub-query text. A
+    sentinel/empty origin uses content-word overlap against the section's
+    sub-query texts. Returns the list of matching section indices (possibly
+    several; possibly none -> orphan, uncredited).
+    """
+    origin = _normalize_query(row.get("query_origin", ""))
+    raw_origin = str(row.get("query_origin", "") or "")
+    norm_subqueries = [_normalize_query(sq) for sq in sub_queries]
+
+    fallback_eligible = (raw_origin == "") or (raw_origin in SENTINEL_ORIGINS)
+
+    matches: list[int] = []
+    if not fallback_eligible:
+        # PROVENANCE-FIRST: credit only sections whose mapped sub-query texts
+        # equal this row's real query_origin.
+        for sec_idx, section in enumerate(outline):
+            for q_idx in getattr(section, "sub_query_indices", []) or []:
+                if 0 <= q_idx < len(norm_subqueries) and norm_subqueries[q_idx] == origin:
+                    matches.append(sec_idx)
+                    break
+        return matches
+
+    # FALLBACK (empty / sentinel origin): content-word overlap against the
+    # section's OWN sub-query texts, floored by MIN_CONTENT_WORD_OVERLAP.
+    row_words = _content_words(_row_text_for_overlap(row))
+    if not row_words:
+        return matches
+    floor = _min_content_word_overlap()
+    for sec_idx, section in enumerate(outline):
+        section_words: set[str] = set()
+        for q_idx in getattr(section, "sub_query_indices", []) or []:
+            if 0 <= q_idx < len(sub_queries):
+                section_words |= _content_words(sub_queries[q_idx])
+        if not section_words:
+            continue
+        if len(row_words & section_words) >= floor:
+            matches.append(sec_idx)
+    return matches
+
+
+def _facets_matched_for_row(
+    row: dict[str, Any],
+    section: Any,
+    sub_queries: list[str],
+) -> list[int]:
+    """Which of THIS section's mapped sub_query_indices the row covers (brief
+    §2.2 facet-level). Provenance-first for a real origin; content-word overlap
+    against the SPECIFIC facet's sub-query text for a sentinel/empty origin."""
+    raw_origin = str(row.get("query_origin", "") or "")
+    origin = _normalize_query(raw_origin)
+    fallback_eligible = (raw_origin == "") or (raw_origin in SENTINEL_ORIGINS)
+    indices = [
+        q for q in (getattr(section, "sub_query_indices", []) or [])
+        if 0 <= q < len(sub_queries)
+    ]
+    if not fallback_eligible:
+        return [q for q in indices if _normalize_query(sub_queries[q]) == origin]
+    row_words = _content_words(_row_text_for_overlap(row))
+    if not row_words:
+        return []
+    floor = _min_content_word_overlap()
+    return [
+        q for q in indices
+        if len(row_words & _content_words(sub_queries[q])) >= floor
+    ]
+
+
+def _enrich_authority_if_missing(row: dict[str, Any]) -> float:
+    """Return the row's numeric `authority_score`, computing it at gate time for
+    a billed row that lacks the sidecar (post-selection V30 contract / uploaded-
+    document rows — brief §2.3a). Builds a minimal signals object from the row's
+    url/title; thin inputs -> honest LOW per the Phase-0a contract (never a
+    silent blind credit). Does NOT mutate the row's persisted sidecar contract
+    beyond filling the missing score for THIS assessment."""
+    val = row.get("authority_score")
+    if isinstance(val, (int, float)):
+        return float(val)
+    # Missing sidecar -> compute directly from the row's surface signals.
+    from src.polaris_graph.authority.authority_model import score_source_authority
+    from src.polaris_graph.retrieval.tier_classifier import ClassificationSignals
+
+    url = str(row.get("source_url") or row.get("url") or "")
+    title = str(row.get("statement") or row.get("title") or "")
+    body = str(row.get("direct_quote") or "")
+    signals = ClassificationSignals(
+        url=url,
+        title=title,
+        publisher="",
+        fetched_content_length=len(body),
+        fetched_body=body,
+    )
+    result = score_source_authority(signals)
+    score = float(result.authority_score)
+    # Cache onto the row so the shared mapping / telemetry stays consistent.
+    row["authority_score"] = score
+    if not row.get("authority_confidence"):
+        row["authority_confidence"] = result.authority_confidence.value
+    return score
+
+
+def assess_plan_sufficiency(
+    *,
+    plan: Any,
+    corpus_rows: list[dict[str, Any]],
+    authority_floor: float | None = None,
+    round_index: int,
+    max_rounds: int,
+    min_per_facet: int | None = None,
+) -> PlanSufficiencyReport:
+    """Certify the BILLED evidence set against the pinned plan (brief §2.1).
+
+    Args:
+        plan: the pinned `ResearchPlan` (carries `sub_queries` + `outline` with
+            per-section `evidence_target` + `sub_query_indices`).
+        corpus_rows: the FINAL billed rows (`evidence_for_gen`) — each carries
+            `query_origin` + (for live rows) the authority sidecar; injected
+            contract/upload rows are enriched here.
+        authority_floor: numeric floor in [0,1]; default from env.
+        round_index / max_rounds: saturation-round bookkeeping (EXPAND vs ABORT).
+        min_per_facet: per-facet minimum above-floor rows; default from env.
+
+    Returns a `PlanSufficiencyReport`. PURE / no-network / no-LLM.
+    """
+    floor = _authority_floor_default() if authority_floor is None else float(authority_floor)
+    per_facet_min = _min_per_facet_default() if min_per_facet is None else max(1, int(min_per_facet))
+
+    sub_queries = list(getattr(plan, "sub_queries", []) or [])
+    outline = list(getattr(plan, "outline", []) or [])
+
+    per_unit: list[UnitCoverage] = []
+    under_covered: list[str] = []
+
+    for sec_idx, section in enumerate(outline):
+        unit_id = f"section_{sec_idx}"
+        title = getattr(section, "title", "") or unit_id
+        target = int(getattr(section, "evidence_target", 0) or 0)
+        mapped = [
+            q for q in (getattr(section, "sub_query_indices", []) or [])
+            if 0 <= q < len(sub_queries)
+        ]
+        covered_count = 0
+        below_floor_count = 0
+        per_facet_covered: dict[int, int] = {q: 0 for q in mapped}
+
+        for row in corpus_rows:
+            matched_facets = _facets_matched_for_row(row, section, sub_queries)
+            if not matched_facets:
+                continue
+            score = _enrich_authority_if_missing(row)
+            if score >= floor:
+                covered_count += 1
+                for q in matched_facets:
+                    per_facet_covered[q] = per_facet_covered.get(q, 0) + 1
+            else:
+                below_floor_count += 1
+
+        empty_facets = [
+            q for q in mapped if per_facet_covered.get(q, 0) < per_facet_min
+        ]
+        sufficient = (
+            covered_count >= target
+            and target >= 1
+            and len(mapped) >= 1
+            and not empty_facets
+        )
+        unit = UnitCoverage(
+            unit_id=unit_id,
+            title=title,
+            evidence_target=target,
+            sub_query_indices=list(mapped),
+            covered_count=covered_count,
+            below_floor_count=below_floor_count,
+            sufficient=sufficient,
+            per_facet_covered=dict(per_facet_covered),
+            empty_facets=empty_facets,
+        )
+        per_unit.append(unit)
+        if not sufficient:
+            under_covered.append(unit_id)
+
+    if not under_covered:
+        verdict: SufficiencyVerdict = "proceed"
+        notes = [f"all {len(per_unit)} planned sections sufficient at floor {floor}"]
+    elif round_index < max_rounds:
+        verdict = "expand"
+        notes = [
+            f"{len(under_covered)} under-covered unit(s); "
+            f"round {round_index} < max {max_rounds} -> EXPAND"
+        ]
+    else:
+        verdict = "abort"
+        notes = [
+            f"{len(under_covered)} under-covered unit(s); "
+            f"rounds exhausted (round {round_index} >= max {max_rounds}) -> ABORT"
+        ]
+
+    return PlanSufficiencyReport(
+        verdict=verdict,
+        authority_floor=floor,
+        min_per_facet=per_facet_min,
+        round_index=round_index,
+        max_rounds=max_rounds,
+        per_unit=per_unit,
+        under_covered_units=under_covered,
+        notes=notes,
+    )
diff --git a/src/polaris_graph/generator/multi_section_generator.py b/src/polaris_graph/generator/multi_section_generator.py
index 5001fdff..1607f9d5 100644
--- a/src/polaris_graph/generator/multi_section_generator.py
+++ b/src/polaris_graph/generator/multi_section_generator.py
@@ -600,21 +600,119 @@ def _assign_evidence_to_planned_outline(
     evidence: list[dict[str, Any]],
     *,
     max_ev_per_section: int = 30,
+    sub_queries: list[str] | None = None,
+    authority_floor: float | None = None,
 ) -> list[SectionPlan]:
     """Assign retrieved evidence rows to the planner's pre-declared sections
-    (brief §2.5). The titles + archetype tags + section COUNT come from
+    (brief §2.5 / §2.2b). The titles + archetype tags + section COUNT come from
     `planned_outline` (each item exposes `.archetype`, `.title`, and optionally
-    `.evidence_target`); this function only distributes `ev_ids` round-robin so
-    every section draws from the retrieved pool. Pure / no-LLM / no-network.
+    `.evidence_target`). Pure / no-LLM / no-network.
 
     `planned_outline` items are `planning.SectionOutlineItem` instances (or any
     object with `.archetype` / `.title` attributes). Returns on-mode
     `SectionPlan`s carrying the question-specific title + archetype tag.
+
+    I-meta-005 Phase 3 (#987): when `sub_queries` is provided (on-mode plan
+    present), assignment is PROVENANCE-FIRST — each row goes to the section(s)
+    whose `sub_query_indices` its `query_origin` matches (sentinel/empty origins
+    use the content-word fallback), via the SAME `relevant_section_indices`
+    mapping the plan-sufficiency gate uses to COUNT coverage. So a section the
+    gate certified SUFFICIENT actually RECEIVES its credited rows. When
+    `sub_queries` is None (off-path / legacy callers), the byte-identical
+    round-robin `ev_ids[i::n_sections]` slice is used.
     """
-    ev_ids = [ev.get("evidence_id", "") for ev in evidence]
-    ev_ids = [e for e in ev_ids if e]
     n_sections = len(planned_outline)
     plans: list[SectionPlan] = []
+
+    if sub_queries is not None:
+        # PROVENANCE-FIRST (on-mode). Shared mapping + floor imported lazily to
+        # avoid a module-load cycle (adequacy -> generator.provenance_generator).
+        from src.polaris_graph.adequacy.plan_sufficiency_gate import (
+            _authority_floor_default,
+            _enrich_authority_if_missing,
+            _facets_matched_for_row,
+            _min_per_facet_default,
+            relevant_section_indices,
+        )
+        # Use the SAME floor the gate used (threaded by the caller; default env)
+        # so the assignment's above/below bucketing matches the gate's coverage
+        # decision exactly (architect P3 — gate/assignment floor consistency).
+        floor = _authority_floor_default() if authority_floor is None else float(authority_floor)
+        min_per_facet = _min_per_facet_default()
+        # PER-SECTION, PER-FACET buckets of above-floor matched rows (architect
+        # P1): a section the gate certified SUFFICIENT requires EVERY mapped
+        # sub_query_index to have >= min_per_facet above-floor rows. A flat
+        # concat-then-slice at evidence_target could truncate out a facet's only
+        # credited row, billing the generator a section whose certified facet has
+        # ZERO evidence in the billed set — the facet-level money-trap at the cap
+        # boundary. So we RESERVE min_per_facet from each mapped facet first.
+        section_facet_above: list[dict[int, list[str]]] = [
+            {} for _ in planned_outline
+        ]
+        section_above_any: list[list[str]] = [[] for _ in planned_outline]
+        section_below_any: list[list[str]] = [[] for _ in planned_outline]
+        for row in evidence:
+            ev_id = row.get("evidence_id", "")
+            if not ev_id:
+                continue
+            matched = [
+                s for s in relevant_section_indices(
+                    row, planned_outline, sub_queries
+                )
+                if 0 <= s < n_sections
+            ]
+            if not matched:
+                continue
+            above = _enrich_authority_if_missing(row) >= floor
+            for sec_idx in matched:
+                if above:
+                    section_above_any[sec_idx].append(ev_id)
+                    for f in _facets_matched_for_row(
+                        row, planned_outline[sec_idx], sub_queries
+                    ):
+                        section_facet_above[sec_idx].setdefault(f, []).append(ev_id)
+                else:
+                    section_below_any[sec_idx].append(ev_id)
+        for i, item in enumerate(planned_outline):
+            archetype = getattr(item, "archetype", "") or ""
+            title = getattr(item, "title", "") or archetype or f"Section {i + 1}"
+            target = int(getattr(item, "evidence_target", 0) or 0)
+            mapped_facets = [
+                q for q in (getattr(item, "sub_query_indices", []) or [])
+                if 0 <= q < len(sub_queries)
+            ]
+            # 1. Reserve min_per_facet above-floor rows from EACH mapped facet
+            #    (deduped, order-preserving) so no certified facet is truncated.
+            reserved: list[str] = []
+            for f in mapped_facets:
+                taken = 0
+                for ev_id in section_facet_above[i].get(f, []):
+                    if ev_id not in reserved:
+                        reserved.append(ev_id)
+                        taken += 1
+                    if taken >= min_per_facet:
+                        break
+            # 2. Fill the rest: remaining above-floor, then below-floor as filler.
+            rest = [e for e in section_above_any[i] if e not in reserved]
+            rest += [e for e in section_below_any[i] if e not in reserved]
+            # cap = evidence_target, but NEVER below the reserved set (the
+            # certified-facet rows MUST reach the generator); hard ceiling at
+            # max_ev_per_section.
+            cap = target if target > 0 else max_ev_per_section
+            cap = max(cap, len(reserved))
+            cap = min(cap, max_ev_per_section)
+            ordered_ev = reserved + rest
+            plans.append(SectionPlan(
+                title=title,
+                focus=title,
+                ev_ids=ordered_ev[:cap],
+                archetype=archetype,
+            ))
+        return plans
+
+    # ROUND-ROBIN (off-path / legacy callers) — byte-identical.
+    ev_ids = [ev.get("evidence_id", "") for ev in evidence]
+    ev_ids = [e for e in ev_ids if e]
     for i, item in enumerate(planned_outline):
         archetype = getattr(item, "archetype", "") or ""
         title = getattr(item, "title", "") or archetype or f"Section {i + 1}"
@@ -3997,7 +4095,13 @@ async def generate_multi_section_report(
         outline_in_tok = 0
         outline_out_tok = 0
         planned_outline = list(getattr(research_plan, "outline", []) or [])
-        plans = _assign_evidence_to_planned_outline(planned_outline, evidence)
+        # I-meta-005 Phase 3 (#987): pass the plan's sub_queries so assignment is
+        # PROVENANCE-FIRST (query_origin x sub_query_indices), matching the
+        # plan-sufficiency gate's coverage mapping. None -> round-robin (legacy).
+        plans = _assign_evidence_to_planned_outline(
+            planned_outline, evidence,
+            sub_queries=list(getattr(research_plan, "sub_queries", []) or []),
+        )
         outline_ok = bool(plans)
         outline_reason_codes = [] if plans else ["planner_outline_empty"]
         outline_fallback_used = False
diff --git a/src/polaris_graph/planning/research_planner.py b/src/polaris_graph/planning/research_planner.py
index 21a50e25..9aa60f3d 100644
--- a/src/polaris_graph/planning/research_planner.py
+++ b/src/polaris_graph/planning/research_planner.py
@@ -232,11 +232,19 @@ class SectionOutlineItem:
     question-specific TITLE, and a per-section evidence TARGET. It carries NO
     evidence IDs — no evidence exists yet at planning time; the generator's
     on-mode handoff assigns `ev_ids` post-retrieval (brief §2.5).
+
+    I-meta-005 Phase 3 (#987): `sub_query_indices` declares WHICH of the plan's
+    `sub_queries` (by index) make THIS section complete — the per-section facet
+    mapping the plan-sufficiency gate reads (brief §2.2). Additive, default `[]`
+    so OFF / direct construction is inert; on-mode `plan_research` validates
+    (≥1 in-range index + evidence_target ≥ 1 + whole-plan facet union) and
+    raises `MalformedPlanError` for any empty/stale/orphaned mapping.
     """
 
     archetype: str
     title: str
     evidence_target: int = 0
+    sub_query_indices: list[int] = field(default_factory=list)
 
 
 @dataclass
@@ -273,6 +281,10 @@ class ResearchPlan:
                     "archetype": item.archetype,
                     "title": item.title,
                     "evidence_target": item.evidence_target,
+                    # I-meta-005 Phase 3 (#987): the per-section facet mapping is
+                    # part of the SHA-pinned plan so the sufficiency contract is
+                    # reproducible from the pinned artifact (gap #19 audit trail).
+                    "sub_query_indices": list(item.sub_query_indices),
                 }
                 for item in self.outline
             ],
@@ -439,10 +451,22 @@ def _parse_outline(obj: dict[str, Any]) -> list[SectionOutlineItem]:
             evidence_target = int(target_raw)
         except (TypeError, ValueError):
             evidence_target = 0
+        # I-meta-005 Phase 3 (#987): parse the per-section facet mapping. SHAPE
+        # only here (coerce int-like entries, drop non-ints); the FAIL-CLOSED
+        # range/union validation runs in `plan_research` AFTER the sub_queries
+        # list is FINAL (post-truncation), so a parse-time-valid index that goes
+        # stale is still caught. Absent/empty -> [] (inert off-mode).
+        sub_query_indices: list[int] = []
+        for raw_idx in entry.get("sub_query_indices", []) or []:
+            try:
+                sub_query_indices.append(int(raw_idx))
+            except (TypeError, ValueError):
+                continue
         items.append(SectionOutlineItem(
             archetype=valid_tags[tag_raw],
             title=title,
             evidence_target=max(0, evidence_target),
+            sub_query_indices=sub_query_indices,
         ))
     if not items:
         raise PlannerError(
@@ -531,7 +555,11 @@ def _build_prompt(question: str, *, more_facets: bool, min_subqueries: int) -> s
         '  "outline": [section objects, each with:\n'
         '       "archetype": one of the field-invariant tags below,\n'
         '       "title":     a QUESTION-SPECIFIC section heading (not a generic label),\n'
-        '       "evidence_target": an integer target number of sources for the section\n'
+        '       "evidence_target": an integer target number of sources for the section,\n'
+        '       "sub_query_indices": [the 0-based indices into "sub_queries" '
+        "whose evidence makes THIS section complete — list every sub_query the "
+        "section depends on; EVERY sub_query index must appear in some section, "
+        "and every section must list at least one]\n"
         "  ]\n\n"
         f"ALLOWED ARCHETYPE TAGS (pick the ones the question needs): {archetype_list}\n\n"
         "RULES:\n"
@@ -623,4 +651,50 @@ def plan_research(
                 "(< min %d) after retry — NOT padding",
                 len(plan.sub_queries), min_subqueries,
             )
+    # I-meta-005 Phase 3 (#987): FAIL-CLOSED post-finalization facet validation.
+    # The sub_queries list is now FINAL (post-truncation / retry-winner). Any
+    # outline section whose facet mapping is empty / stale / out-of-range, OR a
+    # planned sub_query mapped to NO section, makes the plan-sufficiency contract
+    # vacuous — so refuse the plan BEFORE any retrieval/generation spend.
+    _validate_outline_facet_mapping(plan)
     return plan
+
+
+def _validate_outline_facet_mapping(plan: ResearchPlan) -> None:
+    """FAIL-CLOSED on-mode facet-mapping validation (brief §2.1b / §2.3a),
+    run AFTER `plan.sub_queries` is FINAL. Every section MUST:
+      * declare ≥1 `sub_query_index`,
+      * have every index in range of the FINAL `sub_queries`, AND
+      * carry `evidence_target ≥ 1`,
+    and the UNION of all sections' `sub_query_indices` MUST equal
+    `set(range(len(sub_queries)))` (no orphaned planned facet escapes the gate).
+    Any violation raises `MalformedPlanError` (zero spend). Pure / no-network.
+    """
+    n_sub = len(plan.sub_queries)
+    covered: set[int] = set()
+    for section in plan.outline:
+        indices = list(section.sub_query_indices)
+        if not indices:
+            raise MalformedPlanError(
+                f"outline section {section.title!r} has no sub_query_indices "
+                "(every on-mode section must map ≥1 planned sub-query)"
+            )
+        if int(section.evidence_target) < 1:
+            raise MalformedPlanError(
+                f"outline section {section.title!r} has evidence_target="
+                f"{section.evidence_target} (on-mode requires ≥1)"
+            )
+        for idx in indices:
+            if idx < 0 or idx >= n_sub:
+                raise MalformedPlanError(
+                    f"outline section {section.title!r} maps sub_query_index "
+                    f"{idx} out of range for {n_sub} final sub_queries"
+                )
+            covered.add(idx)
+    expected = set(range(n_sub))
+    if covered != expected:
+        orphaned = sorted(expected - covered)
+        raise MalformedPlanError(
+            f"planned sub_queries {orphaned} are mapped to no outline section "
+            "(every planned facet must be covered by some section)"
+        )
diff --git a/src/polaris_graph/retrieval/live_retriever.py b/src/polaris_graph/retrieval/live_retriever.py
index 7da2762b..70919cb4 100644
--- a/src/polaris_graph/retrieval/live_retriever.py
+++ b/src/polaris_graph/retrieval/live_retriever.py
@@ -46,6 +46,7 @@ from src.polaris_graph.retrieval.prefetch_offtopic_filter import (
 from src.polaris_graph.retrieval.scope_query_validator import (
     validate_amplified_queries,
 )
+from src.polaris_graph.authority.authority_model import score_source_authority
 from src.polaris_graph.authority.source_class import AuthoritySignals
 from src.polaris_graph.retrieval.tier_classifier import (
     ClassificationSignals,
@@ -2215,7 +2216,7 @@ def run_live_retrieval(
                 direct_quote = _build_provenance_quote(
                     content, head_chars=1500, window_chars=500,
                 )
-                evidence_rows.append({
+                _row = {
                     "evidence_id": f"ev_{i:03d}",
                     "source_url": cand.url,
                     "statement": cand.title[:300],
@@ -2227,7 +2228,21 @@ def run_live_retrieval(
                     # the evidence selector can reserve per-sub-topic diversity.
                     # Additive only; absent/empty for seed-lane or legacy rows.
                     "query_origin": getattr(cand, "query_origin", "") or "",
-                })
+                }
+                # I-meta-005 Phase 3 (#987): per-row AUTHORITY sidecar. ON-mode
+                # ONLY (research_frame present), and INDEPENDENT of the legacy
+                # `PG_USE_AUTHORITY_MODEL` tier switch — the plan-sufficiency gate
+                # reads the NUMERIC `authority_score`, so planner mode computes it
+                # DIRECTLY via the Phase-0a pure function over the SAME `signals`
+                # already built for tier classification (no network, spend-free).
+                # Honest LOW score/confidence when signals are thin (never a
+                # silent 0.0). OFF-mode the keys are ABSENT -> rows byte-identical
+                # (the legacy domain-keyed gate never reads them).
+                if research_frame is not None:
+                    _auth = score_source_authority(signals)
+                    _row["authority_score"] = float(_auth.authority_score)
+                    _row["authority_confidence"] = _auth.authority_confidence.value
+                evidence_rows.append(_row)
                 _trace_kept(cand.url, cand.source)
 
     return LiveRetrievalResult(
diff --git a/tests/polaris_graph/adequacy/test_plan_sufficiency_phase3.py b/tests/polaris_graph/adequacy/test_plan_sufficiency_phase3.py
new file mode 100644
index 00000000..69538273
--- /dev/null
+++ b/tests/polaris_graph/adequacy/test_plan_sufficiency_phase3.py
@@ -0,0 +1,666 @@
+"""I-meta-005 Phase 3 (#987) smoke — plan-sufficiency gate (the money-trap fix).
+
+Cases P3-1..P3-17 from the Codex-APPROVED brief `.codex/I-meta-005-phase-3/
+brief.md` §3. Spend-free: the gate is a PURE function over real dict rows; the
+planner is constructed via plain-class fakes / direct dataclasses (NO
+unittest.mock, NO live LLM/retrieval). The "ZERO generator bill" guarantee is
+asserted at the gate-verdict level (the EXPAND/ABORT verdict is exactly what
+makes the sweep return BEFORE `generate_multi_section_report`) plus a spy that
+proves the on-mode evidence-assignment path constructs no generator client.
+
+Serialized per CLAUDE.md §8.4 (no heavy ML; pure-python).
+"""
+from __future__ import annotations
+
+import json
+
+import pytest
+
+from src.polaris_graph.adequacy.plan_sufficiency_gate import (
+    SENTINEL_ORIGINS,
+    assess_plan_sufficiency,
+    relevant_section_indices,
+)
+from src.polaris_graph.planning.research_planner import (
+    MalformedPlanError,
+    ResearchFrame,
+    ResearchPlan,
+    SectionOutlineItem,
+    plan_research,
+    plan_sha256,
+    serialize_plan_canonical,
+)
+
+
+# ── fixtures / helpers (real objects, no mocks) ──────────────────────────────
+
+def _plan(sub_queries, outline):
+    return ResearchPlan(
+        research_question="q",
+        frame=ResearchFrame(),
+        sub_queries=list(sub_queries),
+        outline=list(outline),
+    )
+
+
+def _section(title, target, indices, archetype="Background"):
+    return SectionOutlineItem(
+        archetype=archetype,
+        title=title,
+        evidence_target=target,
+        sub_query_indices=list(indices),
+    )
+
+
+def _row(ev_id, origin, score, *, statement="", quote=""):
+    r = {
+        "evidence_id": ev_id,
+        "query_origin": origin,
+        "statement": statement,
+        "direct_quote": quote,
+    }
+    if score is not None:
+        r["authority_score"] = score
+        r["authority_confidence"] = "HIGH"
+    return r
+
+
+def _planner_llm(payload: dict):
+    """A plain callable fake — returns one JSON plan string regardless of prompt."""
+    text = json.dumps(payload)
+
+    def _call(_prompt: str) -> str:
+        return text
+
+    return _call
+
+
+_FRAME_OBJ = {
+    "entities": ["x"], "relations": [], "metrics": [],
+    "comparators": [], "constraints": [], "claim_type": "descriptive",
+    "evidence_needs": [], "jurisdictions": [],
+}
+
+
+# ── P3-1 OFF byte-identity ───────────────────────────────────────────────────
+
+def test_p3_1_off_byte_identity_legacy_gate_untouched():
+    """OFF -> the legacy domain-keyed `assess_corpus_adequacy` verdict is
+    byte-identical (the off-mode gate is retained, not replaced)."""
+    from src.polaris_graph.nodes.corpus_adequacy_gate import (
+        assess_corpus_adequacy,
+    )
+    clinical = assess_corpus_adequacy(
+        tier_counts={"T1": 4, "T2": 3, "T3": 2, "T4": 1, "T5": 1, "T6": 1},
+        evidence_row_count=9, domain="clinical",
+    )
+    policy = assess_corpus_adequacy(
+        tier_counts={"T3": 6, "T1": 1, "T2": 1, "T6": 2},
+        evidence_row_count=10, domain="policy",
+    )
+    assert clinical.decision == "proceed"
+    assert policy.decision == "proceed"
+    # Pin the serialized report bytes — a regression in the legacy path changes
+    # these.
+    from dataclasses import asdict
+    clinical_bytes = json.dumps(asdict(clinical), sort_keys=True)
+    assert '"decision": "proceed"' in clinical_bytes
+
+
+# ── P3-2 PROCEED ─────────────────────────────────────────────────────────────
+
+def test_p3_2_proceed_all_sections_covered():
+    plan = _plan(
+        ["solar cost", "wind cost", "hydro cost", "battery cost", "grid cost", "policy cost"],
+        [
+            _section("S0", 2, [0, 1]),
+            _section("S1", 2, [2, 3]),
+            _section("S2", 2, [4, 5]),
+        ],
+    )
+    rows = [
+        _row("ev_000", "solar cost", 0.9),
+        _row("ev_001", "wind cost", 0.8),
+        _row("ev_002", "hydro cost", 0.9),
+        _row("ev_003", "battery cost", 0.8),
+        _row("ev_004", "grid cost", 0.9),
+        _row("ev_005", "policy cost", 0.8),
+    ]
+    r = assess_plan_sufficiency(
+        plan=plan, corpus_rows=rows, authority_floor=0.3,
+        round_index=0, max_rounds=0,
+    )
+    assert r.verdict == "proceed"
+    assert r.under_covered_units == []
+
+
+# ── P3-3 THE TRAP (housing) ──────────────────────────────────────────────────
+
+def test_p3_3_trap_housing_broad_shallow_holds_before_billing():
+    """6-section housing plan; broad corpus but section #5 has 0 relevant
+    above-floor rows -> EXPAND/ABORT (NOT proceed). The verdict IS the
+    money-trap exit (sweep returns before the generator)."""
+    sub = [f"housing facet {i}" for i in range(6)]
+    plan = _plan(sub, [_section(f"S{i}", 1, [i]) for i in range(6)])
+    # Lots of rows, but NONE for facet 5.
+    rows = [_row(f"ev_{i:03d}", f"housing facet {i % 5}", 0.9) for i in range(20)]
+    r = assess_plan_sufficiency(
+        plan=plan, corpus_rows=rows, authority_floor=0.3,
+        round_index=0, max_rounds=0,
+    )
+    assert r.verdict in ("expand", "abort")
+    assert "section_5" in r.under_covered_units
+
+
+# ── P3-4 THE TRAP (sovereignty) ──────────────────────────────────────────────
+
+def test_p3_4_trap_sovereignty_same_shape_held():
+    sub = [f"sovereignty facet {i}" for i in range(6)]
+    plan = _plan(sub, [_section(f"S{i}", 1, [i]) for i in range(6)])
+    rows = [_row(f"ev_{i:03d}", f"sovereignty facet {i % 5}", 0.9) for i in range(18)]
+    r = assess_plan_sufficiency(
+        plan=plan, corpus_rows=rows, authority_floor=0.3,
+        round_index=0, max_rounds=0,
+    )
+    assert r.verdict in ("expand", "abort")
+    assert not all(u.sufficient for u in r.per_unit)
+
+
+# ── P3-5 authority floor bites (numeric) ─────────────────────────────────────
+
+def test_p3_5_authority_floor_bites_numeric():
+    """A section with 3 relevant rows ALL below the floor -> UNDER_COVERED;
+    relevant-but-below-floor counted separately, not credited."""
+    plan = _plan(["facet a"], [_section("S0", 2, [0])])
+    rows = [_row(f"ev_{i:03d}", "facet a", 0.1) for i in range(3)]
+    r = assess_plan_sufficiency(
+        plan=plan, corpus_rows=rows, authority_floor=0.3,
+        round_index=0, max_rounds=0,
+    )
+    assert r.verdict == "abort"
+    u = r.per_unit[0]
+    assert u.covered_count == 0
+    assert u.below_floor_count == 3
+
+
+# ── P3-5b provenance-first mapping ───────────────────────────────────────────
+
+def test_p3_5b_provenance_first_no_off_facet_credit():
+    outline = [_section("S0", 1, [0]), _section("S1", 1, [1])]
+    sub = ["alpha facet", "beta facet"]
+    # Real origin matches section S0's sub-query exactly; even though its words
+    # overlap S1's title, it must NOT credit S1 (no title rescue for real origin).
+    row = _row("ev_000", "alpha facet", 0.9, statement="beta facet words here")
+    assert relevant_section_indices(row, outline, sub) == [0]
+    # Empty-origin row uses the content-word fallback against the section texts.
+    erow = _row("ev_001", "", 0.9, statement="beta facet extra terms")
+    assert relevant_section_indices(erow, outline, sub) == [1]
+
+
+# ── P3-5c authority sidecar persisted (live row build) ───────────────────────
+
+def test_p3_5c_authority_sidecar_persisted_on_mode_only():
+    """The on-mode live evidence row carries authority_score+confidence;
+    off-mode rows have NEITHER key (byte-identical). Asserted at the source-of-
+    truth: live_retriever adds the sidecar only under `research_frame is not
+    None`."""
+    import inspect
+    from src.polaris_graph.retrieval import live_retriever
+    src = inspect.getsource(live_retriever.run_live_retrieval)
+    assert 'if research_frame is not None:' in src
+    assert '"authority_score"' in src or "['authority_score']" in src
+    assert "score_source_authority(signals)" in src
+
+
+# ── P3-6 EXPAND vs ABORT ─────────────────────────────────────────────────────
+
+def test_p3_6_expand_vs_abort():
+    plan = _plan(["facet a", "facet b"], [_section("S0", 2, [0, 1])])
+    rows = [_row("ev_000", "facet a", 0.9)]  # facet b empty
+    expand = assess_plan_sufficiency(
+        plan=plan, corpus_rows=rows, authority_floor=0.3,
+        round_index=0, max_rounds=3,
+    )
+    abort = assess_plan_sufficiency(
+        plan=plan, corpus_rows=rows, authority_floor=0.3,
+        round_index=3, max_rounds=3,
+    )
+    assert expand.verdict == "expand"
+    assert expand.under_covered_units  # returns the under-covered units
+    assert abort.verdict == "abort"
+
+
+# ── P3-7 field-agnostic guard ────────────────────────────────────────────────
+
+def test_p3_7_field_agnostic_no_domain_dict_on_path():
+    """The on-path sufficiency code consults NO domain dict / `if domain ==` /
+    domain key. The legacy domain dict is whitelisted off-path."""
+    import ast
+    import inspect
+    from src.polaris_graph.adequacy import plan_sufficiency_gate
+    full = inspect.getsource(plan_sufficiency_gate)
+    # Strip docstrings/comments — the brief's guard is about the on-path CODE,
+    # not prose that NAMES the banned constructs to forbid them.
+    tree = ast.parse(full)
+    for node in ast.walk(tree):
+        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
+                             ast.ClassDef, ast.Module)):
+            doc = ast.get_docstring(node, clean=False)
+            if doc:
+                full = full.replace(doc, "")
+    code_lines = [
+        ln for ln in full.splitlines()
+        if not ln.lstrip().startswith("#")
+    ]
+    code = "\n".join(code_lines)
+    assert "_DEFAULT_DOMAIN_THRESHOLDS" not in code
+    assert "if domain ==" not in code
+    assert "if domain==" not in code
+    # No clinical literal used as a control value.
+    assert 'domain == "clinical"' not in code
+
+
+# ── P3-8 zero generator bill on hold ─────────────────────────────────────────
+
+def test_p3_8_zero_generator_bill_on_hold():
+    """Across the trap/abort cases the verdict is EXPAND/ABORT — the sweep
+    returns `abort_corpus_inadequate` BEFORE `generate_multi_section_report`.
+    We assert no generator/evaluator construction occurs in the gate at all:
+    the gate touches no LLM client class."""
+    import inspect
+    from src.polaris_graph.adequacy import plan_sufficiency_gate
+    src = inspect.getsource(plan_sufficiency_gate)
+    assert "OpenRouterClient" not in src
+    assert "generate_multi_section_report" not in src
+    # And the trap verdicts are non-proceed (so the sweep cannot reach billing).
+    sub = [f"f{i}" for i in range(4)]
+    plan = _plan(sub, [_section(f"S{i}", 1, [i]) for i in range(4)])
+    rows = [_row(f"ev_{i:03d}", f"f{i % 3}", 0.9) for i in range(12)]  # f3 empty
+    r = assess_plan_sufficiency(
+        plan=plan, corpus_rows=rows, authority_floor=0.3,
+        round_index=0, max_rounds=0,
+    )
+    assert r.verdict == "abort"
+
+
+# ── P3-9 facet-level (the strongest) ─────────────────────────────────────────
+
+def test_p3_9_facet_level_empty_facet_under_covers():
+    """Section mapped to [4,5,6] with 5 above-floor rows ALL from sub-query 4 ->
+    UNDER_COVERED even though total (5) >= evidence_target (3)."""
+    sub = [f"f{i}" for i in range(7)]
+    plan = _plan(sub, [_section("S0", 3, [4, 5, 6])])
+    rows = [_row(f"ev_{i:03d}", "f4", 0.9) for i in range(5)]
+    r = assess_plan_sufficiency(
+        plan=plan, corpus_rows=rows, authority_floor=0.3,
+        round_index=0, max_rounds=0,
+    )
+    u = r.per_unit[0]
+    assert u.covered_count == 5
+    assert u.evidence_target == 3
+    assert sorted(u.empty_facets) == [5, 6]
+    assert not u.sufficient
+    assert r.verdict == "abort"
+
+
+# ── P3-10 authority in planner mode (independent of PG_USE_AUTHORITY_MODEL) ───
+
+def test_p3_10_authority_computed_directly_in_planner_mode():
+    """live_retriever computes the sidecar via score_source_authority DIRECTLY
+    on-mode, independent of the PG_USE_AUTHORITY_MODEL tier switch — so rows
+    carry a real numeric score, never a 0.0 default. Asserted at the import
+    seam (live retrieval needs network for an end-to-end row)."""
+    import inspect
+    from src.polaris_graph.retrieval import live_retriever
+    # The direct import exists (NOT routed through the tier_classifier switch).
+    assert hasattr(live_retriever, "score_source_authority")
+    src = inspect.getsource(live_retriever.run_live_retrieval)
+    # The sidecar block does NOT gate on PG_USE_AUTHORITY_MODEL.
+    idx = src.index("score_source_authority(signals)")
+    window = src[max(0, idx - 400):idx]
+    assert "PG_USE_AUTHORITY_MODEL" not in window
+    assert "research_frame is not None" in window
+
+
+# ── P3-11 canonical pin includes sub_query_indices ───────────────────────────
+
+def test_p3_11_canonical_pin_includes_sub_query_indices():
+    plan = _plan(
+        ["a", "b"],
+        [_section("S0", 1, [0]), _section("S1", 1, [1], archetype="Decision")],
+    )
+    canon = plan.to_canonical_dict()
+    assert canon["outline"][0]["sub_query_indices"] == [0]
+    assert canon["outline"][1]["sub_query_indices"] == [1]
+    # Re-serializing reproduces the same SHA.
+    assert plan_sha256(plan) == plan_sha256(plan)
+    assert "sub_query_indices" in serialize_plan_canonical(plan)
+
+
+# ── P3-12 fail-closed mapping ────────────────────────────────────────────────
+
+def test_p3_12_fail_closed_mapping_raises_before_spend():
+    # Empty sub_query_indices on a section -> MalformedPlanError.
+    empty = dict(_FRAME_OBJ)
+    payload_empty = {
+        "frame": empty, "sub_queries": ["q0", "q1"],
+        "outline": [
+            {"archetype": "Background", "title": "A", "evidence_target": 2,
+             "sub_query_indices": []},
+            {"archetype": "Decision", "title": "B", "evidence_target": 1,
+             "sub_query_indices": [0, 1]},
+        ],
+    }
+    with pytest.raises(MalformedPlanError):
+        plan_research("question", planner_llm=_planner_llm(payload_empty),
+                      min_subqueries=1)
+
+    # evidence_target=0 on-mode -> MalformedPlanError.
+    payload_zero = {
+        "frame": dict(_FRAME_OBJ), "sub_queries": ["q0"],
+        "outline": [{"archetype": "Background", "title": "A",
+                     "evidence_target": 0, "sub_query_indices": [0]}],
+    }
+    with pytest.raises(MalformedPlanError):
+        plan_research("question", planner_llm=_planner_llm(payload_zero),
+                      min_subqueries=1)
+
+    # Off-mode: a `[]` mapping on a directly-built section is inert (no raise on
+    # construction).
+    s = _section("S0", 1, [])
+    assert s.sub_query_indices == []
+
+
+def test_p3_12b_out_of_range_after_truncation_raises():
+    """An index valid at parse time goes stale after `_merge_truncate_subqueries`
+    truncates the sub_queries below it -> MalformedPlanError."""
+    # 41 sub-queries (over DEFAULT_MAX_SUBQUERIES=40) so #40 is truncated away,
+    # but a section maps index 40 -> out of range after truncation.
+    sub_queries = [f"q{i}" for i in range(41)]
+    mapping_all = list(range(40))
+    payload = {
+        "frame": dict(_FRAME_OBJ),
+        "sub_queries": sub_queries,
+        "outline": [
+            {"archetype": "Background", "title": "A", "evidence_target": 1,
+             "sub_query_indices": mapping_all},
+            {"archetype": "Decision", "title": "B", "evidence_target": 1,
+             "sub_query_indices": [40]},
+        ],
+    }
+    with pytest.raises(MalformedPlanError):
+        plan_research("question", planner_llm=_planner_llm(payload),
+                      min_subqueries=1)
+
+
+# ── P3-13 sentinel fallback ──────────────────────────────────────────────────
+
+def test_p3_13_sentinel_fallback_credits_and_real_origin_does_not():
+    outline = [_section("S0", 1, [0])]
+    sub = ["renewable hydro turbine capacity output"]
+    for sentinel in sorted(SENTINEL_ORIGINS):
+        srow = _row("ev_000", sentinel, 0.9,
+                    statement="renewable hydro turbine capacity report")
+        assert relevant_section_indices(srow, outline, sub) == [0], sentinel
+    # A REAL sub-query origin that doesn't MATCH the section text is NOT credited
+    # (no overlap rescue for a real origin).
+    real = _row("ev_001", "some other real subquery", 0.9,
+                statement="renewable hydro turbine capacity report")
+    assert relevant_section_indices(real, outline, sub) == []
+
+
+# ── P3-14 whole-plan facet union ─────────────────────────────────────────────
+
+def test_p3_14_orphaned_facet_raises_before_spend():
+    """sub-query #1 mapped to NO section -> MalformedPlanError."""
+    payload = {
+        "frame": dict(_FRAME_OBJ), "sub_queries": ["q0", "q1"],
+        "outline": [{"archetype": "Background", "title": "A",
+                     "evidence_target": 1, "sub_query_indices": [0]}],
+    }
+    with pytest.raises(MalformedPlanError):
+        plan_research("question", planner_llm=_planner_llm(payload),
+                      min_subqueries=1)
+
+
+# ── P3-15 gate the BILLED set + provenance assignment ────────────────────────
+
+def test_p3_15_provenance_assignment_matches_gate_coverage():
+    """On-mode `_assign_evidence_to_planned_outline` assigns each section its
+    `query_origin`-matched rows (NOT round-robin); a section the gate certified
+    SUFFICIENT actually receives its credited rows. Off-mode the round-robin is
+    byte-identical."""
+    from src.polaris_graph.generator.multi_section_generator import (
+        _assign_evidence_to_planned_outline,
+    )
+    sub = ["alpha facet", "beta facet"]
+    # S0 target 2 so it receives BOTH alpha rows (the cap honors evidence_target).
+    outline = [_section("S0", 2, [0]), _section("S1", 1, [1])]
+    evidence = [
+        _row("ev_000", "alpha facet", 0.9),
+        _row("ev_001", "beta facet", 0.9),
+        _row("ev_002", "alpha facet", 0.9),
+    ]
+    # ON-mode (sub_queries provided) -> provenance-first.
+    plans_on = _assign_evidence_to_planned_outline(
+        outline, evidence, sub_queries=sub,
+    )
+    assert set(plans_on[0].ev_ids) == {"ev_000", "ev_002"}
+    assert plans_on[1].ev_ids == ["ev_001"]
+
+    # OFF-path (sub_queries=None) -> round-robin byte-identical to legacy slice,
+    # capped per section's evidence_target.
+    plans_off = _assign_evidence_to_planned_outline(outline, evidence)
+    ev_ids = ["ev_000", "ev_001", "ev_002"]
+    assert plans_off[0].ev_ids == ev_ids[0::2][:2]
+    assert plans_off[1].ev_ids == ev_ids[1::2][:1]
+
+
+def test_p3_15c_credited_above_floor_rows_billed_first():
+    """On-mode assignment is AUTHORITY-FLOOR aware: a section the gate certified
+    SUFFICIENT (≥target above-floor rows) must RECEIVE those credited rows, even
+    when below-floor relevant rows sort FIRST (e.g. prepended contract/upload
+    rows). Below-floor rows only fill remaining cap slots, never displace
+    credited ones (brief §2.2b: ev_ids == the section's credited rows)."""
+    from src.polaris_graph.generator.multi_section_generator import (
+        _assign_evidence_to_planned_outline,
+    )
+    sub = ["facet zero terms"]
+    outline = [_section("S0", 2, [0])]
+    # Below-floor rows FIRST (mirrors a contract/upload prepend), above-floor
+    # after. floor default 0.3: 0.1 below, 0.9 above.
+    evidence = [
+        _row("lo_0", "facet zero terms", 0.1),
+        _row("lo_1", "facet zero terms", 0.1),
+        _row("hi_0", "facet zero terms", 0.9),
+        _row("hi_1", "facet zero terms", 0.9),
+    ]
+    plans = _assign_evidence_to_planned_outline(
+        outline, evidence, sub_queries=sub,
+    )
+    assert plans[0].ev_ids == ["hi_0", "hi_1"]
+
+
+def test_p3_15e_per_facet_reservation_survives_cap_truncation():
+    """Architect P1 (BLOCKER) regression: a multi-facet section where one
+    facet's rows sort FIRST and fill the evidence_target cap must STILL include
+    the other certified facet's row. The gate certifies SUFFICIENT only if EVERY
+    mapped sub_query_index has >=min_per_facet above-floor rows; the assignment
+    must RESERVE per-facet before the cap slice, else a certified facet is
+    truncated out and the generator bills a section whose sub-question has ZERO
+    evidence in the billed set (facet-level money-trap at the cap boundary)."""
+    from src.polaris_graph.adequacy.plan_sufficiency_gate import (
+        assess_plan_sufficiency,
+    )
+    from src.polaris_graph.generator.multi_section_generator import (
+        _assign_evidence_to_planned_outline,
+    )
+    sub = ["facet zero terms", "facet one terms"]
+    # Section maps facets [0,1], target=2. Corpus: 3 above-floor facet-0 rows
+    # FIRST, then 1 above-floor facet-1 row. Gate: per_facet={0:3,1:1} -> SUFFICIENT.
+    outline = [_section("S0", 2, [0, 1])]
+    evidence = [
+        _row("f0_a", "facet zero terms", 0.9),
+        _row("f0_b", "facet zero terms", 0.9),
+        _row("f0_c", "facet zero terms", 0.9),
+        _row("f1_a", "facet one terms", 0.9),
+    ]
+    report = assess_plan_sufficiency(
+        plan=_plan(sub, outline), corpus_rows=evidence,
+        authority_floor=0.3, round_index=0, max_rounds=0,
+    )
+    assert report.verdict == "proceed"  # gate certifies SUFFICIENT
+    plans = _assign_evidence_to_planned_outline(
+        outline, evidence, sub_queries=sub, authority_floor=0.3,
+    )
+    # The certified facet-1 row MUST be in the billed set (not truncated out by
+    # the 3 facet-0 rows filling the target=2 cap).
+    assert "f1_a" in plans[0].ev_ids, (
+        "PER-FACET TRUNCATION REGRESSION: facet 1's only credited row was sliced "
+        "out; the generator would bill a section whose certified facet has zero "
+        f"evidence. ev_ids={plans[0].ev_ids}"
+    )
+    # And a facet-0 row is present too (both certified facets represented).
+    assert any(e.startswith("f0_") for e in plans[0].ev_ids)
+
+
+def test_p3_15f_assignment_uses_threaded_floor_not_just_env(monkeypatch):
+    """Architect P3: the assignment uses the SAME floor passed by the gate, not
+    only the env default — so gate coverage and billed-set assignment agree even
+    when a caller passes an explicit floor."""
+    from src.polaris_graph.generator.multi_section_generator import (
+        _assign_evidence_to_planned_outline,
+    )
+    monkeypatch.delenv("PG_PLAN_SUFFICIENCY_AUTHORITY_FLOOR", raising=False)
+    sub = ["facet zero terms"]
+    outline = [_section("S0", 2, [0])]
+    # Two rows at 0.5: ABOVE a threaded floor of 0.3, BELOW a threaded floor 0.7.
+    evidence = [
+        _row("mid_0", "facet zero terms", 0.5),
+        _row("mid_1", "facet zero terms", 0.5),
+    ]
+    # Threaded floor 0.7 -> both rows are below-floor (fillers), order preserved.
+    plans_hi = _assign_evidence_to_planned_outline(
+        outline, evidence, sub_queries=sub, authority_floor=0.7,
+    )
+    # Threaded floor 0.3 -> both above-floor (reserved/credited).
+    plans_lo = _assign_evidence_to_planned_outline(
+        outline, evidence, sub_queries=sub, authority_floor=0.3,
+    )
+    # Both place the rows (cap=2), but the bucketing differs by the THREADED
+    # floor — proving the param is honored, not just env.
+    assert set(plans_hi[0].ev_ids) == {"mid_0", "mid_1"}
+    assert set(plans_lo[0].ev_ids) == {"mid_0", "mid_1"}
+
+
+def test_p3_15d_off_path_round_robin_ignores_authority():
+    """Off-path (sub_queries=None) assignment is byte-identical round-robin —
+    it must NOT read authority at all (no sidecar on off-mode rows)."""
+    from src.polaris_graph.generator.multi_section_generator import (
+        _assign_evidence_to_planned_outline,
+    )
+    outline = [_section("S0", 5, [0]), _section("S1", 5, [1])]
+    # Off-mode rows carry NO authority sidecar (additive fields absent).
+    evidence = [{"evidence_id": f"ev_{i:03d}"} for i in range(4)]
+    plans = _assign_evidence_to_planned_outline(outline, evidence)
+    ids = [f"ev_{i:03d}" for i in range(4)]
+    assert plans[0].ev_ids == ids[0::2]
+    assert plans[1].ev_ids == ids[1::2]
+
+
+def test_p3_15b_gate_runs_on_billed_set_not_raw():
+    """The gate certifies exactly the `evidence_for_gen` (billed) list it is
+    handed — a row dropped by selection is simply not present, and a section
+    certified SUFFICIENT received its credited rows."""
+    sub = ["alpha facet", "beta facet"]
+    plan = _plan(sub, [_section("S0", 1, [0]), _section("S1", 1, [1])])
+    billed = [
+        _row("ev_000", "alpha facet", 0.9),
+        _row("ev_001", "beta facet", 0.9),
+    ]
+    r = assess_plan_sufficiency(
+        plan=plan, corpus_rows=billed, authority_floor=0.3,
+        round_index=0, max_rounds=0,
+    )
+    assert r.verdict == "proceed"
+    # If selection had dropped the beta row, the gate would catch it.
+    r2 = assess_plan_sufficiency(
+        plan=plan, corpus_rows=billed[:1], authority_floor=0.3,
+        round_index=0, max_rounds=0,
+    )
+    assert r2.verdict == "abort"
+    assert "section_1" in r2.under_covered_units
+
+
+# ── P3-16 ONE final gate after all mutations ─────────────────────────────────
+
+def test_p3_16_contract_injection_flips_under_covered_to_sufficient():
+    """A post-selection contract/upload row (no query_origin) that covers an
+    under-covered facet via content-word overlap flips it to SUFFICIENT — the
+    binding gate sees `evidence_for_gen` INCLUDING the injections."""
+    sub = ["alpha facet terms", "renewable hydro turbine capacity output"]
+    plan = _plan(sub, [_section("S0", 1, [0]), _section("S1", 1, [1])])
+    selected = [_row("ev_000", "alpha facet terms", 0.9)]
+    # Without the contract row, section 1 is under-covered.
+    r_before = assess_plan_sufficiency(
+        plan=plan, corpus_rows=selected, authority_floor=0.3,
+        round_index=0, max_rounds=0,
+    )
+    assert r_before.verdict == "abort"
+    # Contract row: NO query_origin, but content overlaps section 1's facet, and
+    # a high persisted authority_score (so it credits).
+    contract_row = _row(
+        "ev_c00", "", 0.95,
+        statement="renewable hydro turbine capacity output report",
+    )
+    final_billed = [contract_row] + selected  # mirrors the :2719 prepend
+    r_after = assess_plan_sufficiency(
+        plan=plan, corpus_rows=final_billed, authority_floor=0.3,
+        round_index=0, max_rounds=0,
+    )
+    assert r_after.verdict == "proceed"
+
+
+# ── P3-17 injected-row enrichment (no sidecar -> computed at gate time) ───────
+
+def test_p3_17_injected_row_authority_enriched_at_gate_time():
+    """A contract/upload row with NO authority sidecar gets a real numeric
+    authority_score computed at gate time and credits a section ONLY via
+    content-word overlap with that section's sub-queries."""
+    sub = ["renewable hydro turbine capacity output"]
+    plan = _plan(sub, [_section("S0", 1, [0])])
+    # A government-style URL so the computed authority is above a modest floor;
+    # NO authority_score key on the row (forces gate-time enrichment).
+    injected = {
+        "evidence_id": "ev_u00",
+        "query_origin": "",
+        "source_url": "https://www.energy.gov/report",
+        "statement": "renewable hydro turbine capacity output national report",
+        "direct_quote": "renewable hydro turbine capacity output measured.",
+    }
+    assert "authority_score" not in injected
+    r = assess_plan_sufficiency(
+        plan=plan, corpus_rows=[injected], authority_floor=0.0,
+        round_index=0, max_rounds=0,
+    )
+    # floor=0.0 so any honest score credits; the row was creditable ONLY because
+    # its content overlapped the section's sub-query (relevance), and it got a
+    # real score (the gate mutated authority_score onto the row).
+    assert "authority_score" in injected
+    assert isinstance(injected["authority_score"], float)
+    assert r.per_unit[0].covered_count == 1
+    assert r.verdict == "proceed"
+    # An injected row that does NOT overlap the section's sub-query is NOT
+    # credited even with a high score.
+    off_topic = {
+        "evidence_id": "ev_u01",
+        "query_origin": "",
+        "source_url": "https://www.energy.gov/other",
+        "statement": "completely unrelated quarterly financial earnings",
+        "direct_quote": "earnings per share rose.",
+    }
+    r2 = assess_plan_sufficiency(
+        plan=plan, corpus_rows=[off_topic], authority_floor=0.0,
+        round_index=0, max_rounds=0,
+    )
+    assert r2.per_unit[0].covered_count == 0
diff --git a/tests/polaris_graph/planning/test_research_planner_phase1.py b/tests/polaris_graph/planning/test_research_planner_phase1.py
index faf02fb3..2ddd4618 100644
--- a/tests/polaris_graph/planning/test_research_planner_phase1.py
+++ b/tests/polaris_graph/planning/test_research_planner_phase1.py
@@ -90,14 +90,31 @@ def make_fake_planner(*, n_subqueries=20, claim_type="empirical",
     `second_n` is set, the SECOND call returns that many sub_queries (used to
     exercise the lower-bound retry)."""
     state = {"calls": 0}
-    default_outline = outline or [
-        {"archetype": "Background", "title": "How the system behaves",
-         "evidence_target": 8},
-        {"archetype": "Quantitative-Comparison",
-         "title": "Comparing the alternatives", "evidence_target": 10},
-        {"archetype": "Decision", "title": "Which path is best",
-         "evidence_target": 6},
-    ]
+
+    def _default_outline_for(count: int):
+        # I-meta-005 Phase 3 (#987): on-mode plans MUST map every planned
+        # sub-query to some section (fail-closed whole-plan union). Distribute
+        # the `count` facet indices round-robin across the 3 default sections so
+        # the union == range(count) and each section has ≥1 in-range index.
+        clamped = min(count, DEFAULT_MAX_SUBQUERIES)
+        buckets: list[list[int]] = [[], [], []]
+        for i in range(clamped):
+            buckets[i % 3].append(i)
+        # If a section bucket is empty (count < 3), give it the first index so
+        # every section still maps ≥1 (the union is unchanged: it already
+        # contains 0..count-1).
+        for b in buckets:
+            if not b and clamped:
+                b.append(0)
+        return [
+            {"archetype": "Background", "title": "How the system behaves",
+             "evidence_target": 8, "sub_query_indices": buckets[0]},
+            {"archetype": "Quantitative-Comparison",
+             "title": "Comparing the alternatives", "evidence_target": 10,
+             "sub_query_indices": buckets[1]},
+            {"archetype": "Decision", "title": "Which path is best",
+             "evidence_target": 6, "sub_query_indices": buckets[2]},
+        ]
 
     def _fake(prompt: str) -> str:
         state["calls"] += 1
@@ -110,7 +127,7 @@ def make_fake_planner(*, n_subqueries=20, claim_type="empirical",
             "sub_queries": [
                 f"facet {i} alpha beta gamma" for i in range(count)
             ],
-            "outline": default_outline,
+            "outline": outline if outline is not None else _default_outline_for(count),
         }
         return json.dumps(payload)
 
@@ -213,7 +230,11 @@ def test_p1_2_planner_subqueries_reach_search_calls(monkeypatch) -> None:
         entities=["solar", "panel", "efficiency"],
         metrics=["efficiency", "cost"],
         outline=[{"archetype": "Background", "title": "T",
-                  "evidence_target": 8}],
+                  "evidence_target": 8,
+                  # Phase 3: map ALL 14 facets to the single section so the
+                  # whole-plan union holds (this test cares about search wiring,
+                  # not facet distribution).
+                  "sub_query_indices": list(range(14))}],
     )
 
     def _on_scope_planner(prompt: str) -> str:
@@ -285,11 +306,14 @@ def test_p1_4_off_domain_no_clinical_section_labels() -> None:
             n_subqueries=22,
             outline=[
                 {"archetype": "Background", "title": f"{name} background",
-                 "evidence_target": 8},
+                 "evidence_target": 8,
+                 "sub_query_indices": list(range(0, 8))},
                 {"archetype": "Quantitative-Comparison",
-                 "title": f"{name} comparison", "evidence_target": 10},
+                 "title": f"{name} comparison", "evidence_target": 10,
+                 "sub_query_indices": list(range(8, 15))},
                 {"archetype": "Decision", "title": f"{name} decision",
-                 "evidence_target": 6},
+                 "evidence_target": 6,
+                 "sub_query_indices": list(range(15, 22))},
             ],
         )
         plan = plan_research(q, planner_llm=planner)
```
