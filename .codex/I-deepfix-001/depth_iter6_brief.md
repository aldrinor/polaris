HARD ITERATION CAP: reset for a NEW P0 production blocker (per §-1.2 rule 6 — a real production blocker is NOT force-approvable). This is a focused re-gate of the P0+P1 fixes. Verdict APPROVE iff zero P0 AND zero P1.

# Gate: I-deepfix-001 DEPTH build — Fable's iter-5 P0 (NameError) + P1 (double-locator over-drop) FIXED

Fable iter-5 caught a P0 that Codex + 62 tests all missed (Codex can't run the code; no test hit the layer-ON path):

1. **P0 (LAUNCH BLOCKER, FIXED):** analyst_synthesis.py:589 emitter guard called `_promote_grounded_active()`
   — a function that DOES NOT EXIST. Real name: `_promote_mode_active()` (line 445). With the slate posture
   (layer ON), generate_analyst_synthesis raised NameError; the caller (multi_section_generator.py:10423)
   swallowed it as "non-fatal" -> the analyst-synthesis DEPTH layer silently vanished -> shallow report.
   FIX: `_promote_grounded_active()` -> `_promote_mode_active()` (one token). NEW regression test
   test_p0_emitter_failclosed_calls_real_promote_fn_no_nameerror: with layer ON + PROMOTE OFF,
   generate_analyst_synthesis returns ('',0,0) fail-closed WITHOUT NameError (proven — the test exercises the
   exact layer-ON emitter path that had zero coverage). Direction is fail-closed (safe), not a fabrication path.

2. **P1 (over-drop, FIXED):** narration rule flagged "Job displacement was concentrated in clerical roles
   (see Table 2) and manufacturing (see Figure 3)." as chrome — two bare "see X" locators tripped the >=2
   chain. FIX: split the signal — _NAV_VERB_STRUCTURE_RE (description verb DIRECTLY governing a structure
   noun, "presents Figure 4.1") counts fully; _NAV_LOCATOR_RE (bare "see figure|table|page" / "as a
   schematic") counts AT MOST ONCE combined. Chain = verb_structure_count + min(1, locator_count); flag if
   chain>=2 OR structure-dominates. Proven KEPT: Fable's double-locator, "present evidence that", single "see
   Figure 2 and Table 3". Proven FLAGGED: box-2 "presents Figure 4.1 ... includes Figure 6.1 as a schematic".
   NEW regression case added.

Fable ALSO confirmed clean (unchanged): preflight refuses ungated launch; topical gate demote-not-drop (never
loses a row); regroup 0.85 no over-merge; frozen faithfulness engine byte-untouched; the 5 omitted files
(numeric_comparator, cross_source_synthesis, verified_compose, boundary_conditions, key_findings) all
faithfulness-safe. 63 tests pass.

## Output schema
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]

## THE FIX DIFF (full cumulative depth build; the 2 new fixes are analyst_synthesis.py + weighted_enrichment.py + tests)
```diff
diff --git a/scripts/dr_benchmark/run_gate_b.py b/scripts/dr_benchmark/run_gate_b.py
index e15b6abf..edaac23b 100644
--- a/scripts/dr_benchmark/run_gate_b.py
+++ b/scripts/dr_benchmark/run_gate_b.py
@@ -864,11 +864,22 @@ _FULL_CAPABILITY_BENCHMARK_SLATE: dict[str, str] = {
     # PG_RELEVANCE_FLOOR gotcha). Code default 0.0 => slate-absent runs are byte-identical; the slate
     # ACTIVATES it for the cert run (the PG_LIVE_MAX_EV_TO_GEN "built-it-then-left-it-off" lesson).
     "PG_MIN_VERIFIED_SECTION_FRACTION": "0.4",
-    # I-ready-013 (#1080): benchmark report.md must be a verified-only surface.
-    # The legacy Analyst Synthesis layer is interpretive and not span-verified /
-    # 4-role gated, so Gate-B force-disables it instead of turning on the planner
-    # or changing the verifier machinery.
-    "PG_SWEEP_ANALYST_SYNTHESIS": "0",
+    # I-deepfix-001 (#1369) DEPTH: re-enable the Analyst Synthesis interpretive layer, but ONLY
+    # under the D3 fail-closed PROMOTE gate (PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED) — every synthesis
+    # sentence is verify-AFTER-compose-DROP: it must pass the frozen-engine provenance re-pass, the
+    # >=2 content-word span-grounding overlap, AND the second-family Sentinel groundedness judge, or it
+    # is DROPPED from the scored body (never label-and-keep). Judge/engine fault -> fail-closed DROP.
+    # Operator-authorized grounded-depth posture (2026-07-07): STRICTER than the ungated legacy layer
+    # banned under I-ready-013 (#1080), not looser — this layer's prose is the report's ONLY
+    # multi-paragraph mechanism/implication/comparison ARGUMENT. A launch with
+    # PG_SWEEP_ANALYST_SYNTHESIS=1 while PROMOTE resolves falsey is BLOCKED by the fail-closed preflight
+    # assert (_assert_analyst_synthesis_gated) — that combination would ship UNGATED synthesis.
+    "PG_SWEEP_ANALYST_SYNTHESIS": "1",
+    # D3 fail-closed drop gate (code default-OFF): pin ON so re-enabled synthesis is ALWAYS gated.
+    "PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED": "1",
+    # The per-sentence deviation screen (code default-ON): pin ON so a stray .env=0 cannot disable the
+    # gate while the layer is on.
+    "PG_ANALYST_SYNTHESIS_DEVIATION_CHECK": "1",
     # I-ready-004 (#1078): finding-dedup. Collapse near-duplicate findings to one corroboration-counted
     # representative + apply a relevance floor. The legacy PG_USE_FINDING_DEDUP mode CONSOLIDATES (keeps
     # ALL sources per claim, multi-citation) — §-1.3 CONSOLIDATE-DON'T-DROP. PG_RELEVANCE_FLOOR is a FLOAT
@@ -1595,6 +1606,11 @@ _FULL_CAPABILITY_BENCHMARK_SLATE: dict[str, str] = {
     # span-grounding chokepoint; the FROZEN faithfulness engine is byte-untouched).
     "PG_CROSS_SOURCE_BODY": "1",              # plan-driven candidate pairing (cross_source_synthesis)
     "PG_NUMERIC_COMPARATOR": "1",             # upgrade fully-comparable NEUTRAL pair -> comparison connective
+    # I-deepfix-001 (#1369) STEP 3: construct-level numeric comparison — lets DIFFERENT-subject numbers that
+    # share a unit + known construct (Frey-Osborne vs Eloundou vs ILO exposure %) pair for the "; for
+    # comparison, " connective. Fail-closed (unknown construct/unit never pairs); each clause keeps its own
+    # [#ev] token; non-directional (§-1.3). Was the reason 892 extracted numbers rendered zero comparison.
+    "PG_NUMERIC_CONSTRUCT_COMPARISON": "1",
     "PG_PROVENANCE_REANCHOR": "1",            # re-anchor wrongly-cited claim to best ENTAILING span (argmax)
     "PG_SYNTH_PRIMARY": "1",                  # compose-then-verify PRIMARY body for corroborated baskets
     "PG_FINDING_DEDUP_NLI": "1",              # directional bidirectional-entailment same-claim grouping (Wave-1b)
@@ -2470,6 +2486,12 @@ _BENCHMARK_FORCE_ON_FLAGS = frozenset({
 # around capability-enabling flags keep their original meaning.
 _BENCHMARK_FORCE_EXACT_FLAGS = frozenset({
     "PG_SWEEP_ANALYST_SYNTHESIS",
+    # I-deepfix-001 (#1369) DEPTH: pin the two D3 gate flags to their slate value so a stray
+    # operator/.env cannot re-enable the interpretive layer UNGATED (promote off) or disable the
+    # per-sentence deviation screen while the layer is on. The fail-closed preflight assert below
+    # (_assert_analyst_synthesis_gated) is the hard backstop; these force-EXACT pins are belt-and-braces.
+    "PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED",
+    "PG_ANALYST_SYNTHESIS_DEVIATION_CHECK",
     # I-beatboth-011 KEYSTONE (#1289): force-EXACT the STRING-valued span-gate companions so a stray
     # operator/.env value cannot survive the slate. PG_HTML_EXTRACTOR=trafilatura_precision selects the
     # precision profile (the int-FLOOR path would crash on float('trafilatura_precision')) — also
@@ -2657,12 +2679,14 @@ _BENCHMARK_SPAN_WINDOW_MAX_BYTES = 2000
 # fails CLOSED if ANY of these is truthy (a stray operator/.env value re-arming a killed loser). STORM
 # core + ingest + agentic are the live-discovery losers; the three query-gen entries (legacy decompose /
 # IterResearch / research-planner) are the superseded query-gen modules (FS-Researcher W2 is the sole
-# adaptive qgen winner). PG_SWEEP_ANALYST_SYNTHESIS stays (the un-span-verified synthesis layer). Each is
-# ALSO force-EXACT "0" (slate de-arm) — REQUIRED_OFF is the fail-closed assert.
+# adaptive qgen winner). Each is ALSO force-EXACT "0" (slate de-arm) — REQUIRED_OFF is the fail-closed assert.
 # R1_deepener_enable: PG_SWEEP_EVIDENCE_DEEPENER is REMOVED from this REQUIRED_OFF set — the citation-
 # snowball deepener is now the recall lever (setdefault-ON, widen-only), NOT a killed loser.
+# I-deepfix-001 (#1369) DEPTH: PG_SWEEP_ANALYST_SYNTHESIS is REMOVED from this REQUIRED_OFF set — the
+# interpretive layer is now re-enabled UNDER the D3 fail-closed PROMOTE gate (slate "1"), so it is a
+# gated winner, not a killed loser. Its safety is enforced instead by _assert_analyst_synthesis_gated
+# in preflight (a launch with the layer ON but PROMOTE OFF fails CLOSED — ungated synthesis is blocked).
 _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS = (
-    "PG_SWEEP_ANALYST_SYNTHESIS",
     "PG_STORM_ENABLED_IN_BENCHMARK",   # K1 STORM core (the loser the operator saw fire)
     "PG_STORM_ENABLED",                # K1 storm_interviews module flag (dual-arm kill)
     "PG_STORM_INGEST_WEB_RESULTS",     # K3 STORM seed-URL ingest lane
@@ -3830,6 +3854,16 @@ _WINNER_FLAG_ALLOWLIST: frozenset[str] = frozenset({
     "PG_ABSTRACTIVE_WRITER",                 # W12 abstractive writer (per-basket prose producer)
     "PG_BASKET_CORROBORATION_RENDER",        # W12/W14 keep-all basket render
     "PG_SYNTHESIS_ABSTRACT_CONCLUSION",      # W14 render=det (abstract/conclusion sandwich)
+    # ── I-deepfix-001 (#1369) DEPTH build winners — conscious winner decision (operator-authorized,
+    #    dual-gated Codex+Fable). GATED grounded-synthesis (verify-after-compose-DROP) + construct-level
+    #    numeric comparison. These are force-EXACT "1" in the slate; allowlisting them is the deliberate
+    #    "winner-or-infra" acknowledgement the SLATE-PURITY gate requires. The fail-closed preflight
+    #    assert (a run with PG_SWEEP_ANALYST_SYNTHESIS on but PROMOTE off is REFUSED) keeps the ungated
+    #    posture that was banned; the frozen faithfulness engine is untouched. ─────────────────────────
+    "PG_SWEEP_ANALYST_SYNTHESIS",            # depth: gated analyst-synthesis argument-arc writer
+    "PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED", # depth: D3 PROMOTE drop-if-ungrounded gate (fail-closed)
+    "PG_ANALYST_SYNTHESIS_DEVIATION_CHECK",  # depth: per-sentence groundedness deviation screen
+    "PG_NUMERIC_CONSTRUCT_COMPARISON",       # depth: construct-level cross-source numeric comparison
     # ── FROZEN faithfulness engine + the verified-compose / breadth surfaces (NOT losers) ───────────
     "PG_STRICT_VERIFY_ENTAILMENT",           # W13 binding entailment leg (frozen engine, enforce mode)
     "PG_MAX_JUDGE_ERROR_RATE",               # judge error-rate wall (faithfulness transport)
@@ -3955,6 +3989,15 @@ _WINNER_FLAG_ALLOWLIST: frozenset[str] = frozenset({
     # loser still fails CLOSED. §-1.3 weight-and-consolidate; FAITHFULNESS-NEUTRAL.
     "PG_CROSS_SOURCE_BODY",                  # plan-driven candidate pairing (cross_source_synthesis)
     "PG_NUMERIC_COMPARATOR",                 # NEUTRAL -> comparison connective upgrade
+    # ── I-deepfix-001 (#1369) DEPTH winners — conscious 'winner or infra?' decision, allowlisted
+    # deliberately so the depth slate PASSES SLATE-PURITY (they are force-EXACT "1" above). The analyst
+    # layer is the grounded-synthesis argument writer under the D3 fail-closed PROMOTE drop gate; the
+    # construct comparator surfaces cross-subject numeric comparisons. FAITHFULNESS-NEUTRAL (verify-after-
+    # compose-DROP / engine-licensed connective); the frozen strict_verify/NLI/4-role engine is untouched.
+    "PG_SWEEP_ANALYST_SYNTHESIS",            # grounded analyst-synthesis argument layer (gated)
+    "PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED", # D3 fail-closed drop-if-ungrounded PROMOTE gate
+    "PG_ANALYST_SYNTHESIS_DEVIATION_CHECK",  # per-sentence deviation screen (keeps the gate live)
+    "PG_NUMERIC_CONSTRUCT_COMPARISON",       # construct-level cross-source numeric comparison
     "PG_PROVENANCE_REANCHOR",                # re-anchor wrongly-cited claim to best ENTAILING span (argmax)
     "PG_SYNTH_PRIMARY",                      # compose-then-verify PRIMARY body for corroborated baskets
     "PG_FINDING_DEDUP_NLI",                  # directional bidirectional-entailment same-claim grouping
@@ -4640,6 +4683,24 @@ def preflight_full_capability(smoke_scale: bool = False, offline: bool = False)
             _assert_aw_preconditions()
         except RuntimeError as _awe:
             raise RuntimeError(f"benchmark preflight FAILED: {_awe}") from _awe
+    # I-deepfix-001 (#1369) DEPTH fail-closed: the Analyst Synthesis interpretive layer is re-enabled
+    # (slate PG_SWEEP_ANALYST_SYNTHESIS=1) but may ONLY ship under the D3 fail-closed PROMOTE gate — every
+    # synthesis sentence is verify-AFTER-compose-DROP. A launch with the layer ON while PROMOTE resolves
+    # falsey would ship UNGATED interpretive prose (the I-ready-013 ban reason). REFUSE the paid run in
+    # that state. promote_grounded_enabled() is the authoritative probe (it requires BOTH the deviation
+    # check ON AND the promote flag ON). Faithfulness gate — runs on smoke + full alike; only asserts when
+    # the layer is actually ON (an operator may legitimately run verbatim-only with the layer off).
+    if os.getenv("PG_SWEEP_ANALYST_SYNTHESIS", "0").strip().lower() not in ("", "0", "false", "off", "no"):
+        from src.polaris_graph.generator.analyst_synthesis_deviation_check import (  # noqa: PLC0415
+            promote_grounded_enabled as _promote_gate_on,
+        )
+        if not _promote_gate_on():
+            raise RuntimeError(
+                "benchmark preflight FAILED: PG_SWEEP_ANALYST_SYNTHESIS is ON but the D3 PROMOTE gate "
+                "(PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED + PG_ANALYST_SYNTHESIS_DEVIATION_CHECK) is NOT "
+                "active — that ships UNGATED interpretive synthesis (the I-ready-013 ban reason). The slate "
+                "pins PROMOTE ON; a stray .env=0 disabled it. Re-enable the gate or disable the layer."
+            )
     # F03 (A3): the verified-section-FRACTION coverage-honesty floor must be ACTIVE (a float in (0, 1])
     # for the cert run — a 0/absent value disables the gate and lets a mostly-gap clinical report ship
     # GREEN (the "built-it-then-left-it-off" failure). Checked FIRST (fail-fast on a faithfulness gate;
diff --git a/src/polaris_graph/generator/analyst_synthesis.py b/src/polaris_graph/generator/analyst_synthesis.py
index ce52f51f..5682bc97 100644
--- a/src/polaris_graph/generator/analyst_synthesis.py
+++ b/src/polaris_graph/generator/analyst_synthesis.py
@@ -578,6 +578,21 @@ async def generate_analyst_synthesis(
         )
         return "", 0, 0
 
+    # I-deepfix-001 (#1369) iter2 (Codex P0): EMITTER-level fail-closed. The Gate-B preflight refuses an
+    # ungated launch, but the RESUME-render / direct-sweep path SKIPS that preflight — so the same guard
+    # must bind HERE at the emitter. If the layer is ON while the D3 PROMOTE (drop-if-ungrounded) gate is
+    # NOT active, shipping would emit legacy KEEP-and-LABEL (un-dropped) synthesis — the exact ungated
+    # posture that was banned. Refuse it: ship the span-verified core ONLY. Default-ON kill-switch so only
+    # an explicit operator opt-out disables the guard. The frozen faithfulness engine is untouched.
+    if os.environ.get(
+        "PG_ANALYST_SYNTHESIS_EMITTER_FAILCLOSED", "1"
+    ).strip().lower() not in ("0", "false", "off", "no") and not _promote_mode_active():
+        logger.warning(
+            "[analyst_synthesis] EMITTER fail-CLOSED: layer ON but D3 PROMOTE gate is OFF — refusing "
+            "UNGATED synthesis (verified core only). Set PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED=1 to ship it."
+        )
+        return "", 0, 0
+
     from src.polaris_graph.llm.openrouter_client import (
         OpenRouterClient,
         set_reasoning_call_context,
diff --git a/src/polaris_graph/generator/summary_table.py b/src/polaris_graph/generator/summary_table.py
index f7e71a13..056fa98a 100644
--- a/src/polaris_graph/generator/summary_table.py
+++ b/src/polaris_graph/generator/summary_table.py
@@ -716,6 +716,25 @@ def _union_terms(term_lists: Iterable[list[str]]) -> list[str]:
     return out[:_MAX_TERMS_PER_CELL]
 
 
+# I-deepfix-001 (#1369) FIX 1 — summary-table duplicate rows (10/36 rows in box-2 were dups of 3 docs:
+# SERBE×6, Deloitte [10][11], laweconcenter [25][26]). Root cause (Fable): (a) doc_key splits the SAME
+# document across a URL-keyed row and title-keyed rows (blank-URL bibliography entries), so they never
+# unite; (b) _same_finding's Jaccard>=0.6 bar rejects the composer's synonym-swap paraphrases (0.53-0.56).
+# A SECOND additive pass groups the FINAL rows by their VISIBLE source label (Literature minus trailing
+# [N] citations) and merges, within a label, rows with an identical non-empty salient-number set OR high
+# claim-token CONTAINMENT — catching URL-vs-title splits and paraphrases without lowering the primary bar.
+# CONSOLIDATE-KEEP-ALL: every citation survives on the merged row. Default-ON PG_SUMMARY_TABLE_LABEL_REGROUP.
+_LABEL_CITE_SUFFIX_RE = re.compile(r"(?:\s*\[\d+\])+\s*$")
+_ENV_LABEL_REGROUP = "PG_SUMMARY_TABLE_LABEL_REGROUP"
+_REGROUP_CONTAINMENT_WITH_NUMBERS = 0.60  # even with an identical number set, require real token overlap
+# I-deepfix-001 (#1369) iter2 (Codex + Fable P2): a NUMBERLESS pair has no numeric discriminator, so the
+# label-regroup second pass must clear the SAME strict bar as the first-pass numberless Jaccard (0.85),
+# not 0.60 — else two DISTINCT same-label qualitative findings at 60% containment over-merge and a real
+# second finding is lost from the table (§-1.3 no-drop). Number-matched pairs keep the 0.60 bar (the
+# identical salient-number set is the real discriminator there).
+_REGROUP_CONTAINMENT_NUMBERLESS = 0.85
+
+
 def _merge_cluster(cluster: list[_RowData]) -> _RowData:
     """Collapse a >=2-member same-document same-finding cluster into ONE multi-citation row.
     ``num`` = min member num (stable sort anchor); ``cite_nums`` = sorted union of ALL members'
@@ -731,8 +750,10 @@ def _merge_cluster(cluster: list[_RowData]) -> _RowData:
         if _clean_claim_text(m.claim) == best_claim:
             rep = m
             break
-    suffix = f" [{min_row.num}]"
-    base = min_row.literature[:-len(suffix)] if min_row.literature.endswith(suffix) else min_row.literature
+    # I-deepfix-001 (#1369) FIX 1: strip ALL trailing [N] citations (robust to an already-consolidated
+    # multi-cite row entering the label-regroup second pass), then re-append the full keep-all set. For a
+    # single-cite row "X [8]" this is byte-identical to the prior single-suffix strip.
+    base = _LABEL_CITE_SUFFIX_RE.sub("", min_row.literature).rstrip()
     literature = base + "".join(f"[{n}]" for n in cite_nums)
     return _RowData(
         num=min_row.num,
@@ -792,6 +813,92 @@ def _consolidate_rows_by_source(rows: list[_RowData]) -> list[_RowData]:
     return out
 
 
+def _label_regroup_enabled() -> bool:
+    """LAW VI kill-switch ``PG_SUMMARY_TABLE_LABEL_REGROUP`` (default ON). OFF => the second pass is a
+    no-op and rows pass through byte-identically."""
+    return os.environ.get(_ENV_LABEL_REGROUP, "1").strip().lower() not in _OFF_VALUES
+
+
+def _row_label_key(r: "_RowData") -> str:
+    """The row's VISIBLE-source grouping key: the Literature cell with its trailing ``[N]`` citations
+    stripped, whitespace-normalized and lowercased. Groups a document that split across a URL-keyed row
+    and title-keyed rows (which ``doc_key`` kept apart). PURE."""
+    lit = _LABEL_CITE_SUFFIX_RE.sub("", r.literature or "")
+    return _WS_RE.sub(" ", lit).strip().lower()
+
+
+def _same_finding_regroup(a: str, b: str) -> bool:
+    """Relaxed same-finding test for the SAME-LABEL second pass: a DIFFERENT salient-number set is never
+    merged (different quantitative result); an identical number set (or both numberless) merges when the
+    claim-token CONTAINMENT (|A∩B|/min(|A|,|B|)) clears the bar — a lower bar when an identical NON-EMPTY
+    number set already anchors the pair, the stricter bar when there is no numeric discriminator. Uses
+    containment (not Jaccard) so synonym swaps + length asymmetry do not defeat it. PURE."""
+    sa, sb = _salient_numbers(a), _salient_numbers(b)
+    if sa != sb:
+        return False
+    ta, tb = _claim_tokens(a), _claim_tokens(b)
+    if not ta and not tb:
+        return True
+    if not ta or not tb:
+        return False
+    containment = len(ta & tb) / min(len(ta), len(tb))
+    bar = _REGROUP_CONTAINMENT_WITH_NUMBERS if sa else _REGROUP_CONTAINMENT_NUMBERLESS
+    return containment >= bar
+
+
+def _regroup_rows_by_label(rows: list["_RowData"]) -> list["_RowData"]:
+    """SECOND additive consolidation pass (FIX 1): group by VISIBLE source label and merge same-label
+    rows that state the same finding under the relaxed :func:`_same_finding_regroup` test. Empty/`source`
+    labels and singletons pass through unchanged; merge is CONSOLIDATE-KEEP-ALL via ``_merge_cluster``.
+    Emits the realized-effect ``[activation]`` marker (anti-dark). Order-stable. PURE apart from the log."""
+    if not _label_regroup_enabled():
+        return rows
+    rows_in = len(rows)
+    by_label: dict[str, list[_RowData]] = {}
+    order: list[str] = []
+    passthrough: list[_RowData] = []
+    for r in rows:
+        key = _row_label_key(r)
+        if not key or key == "source":
+            passthrough.append(r)  # no identifiable label => never regrouped (fail-closed)
+            continue
+        if key not in by_label:
+            by_label[key] = []
+            order.append(key)
+        by_label[key].append(r)
+    out: list[_RowData] = []
+    groups = 0
+    for key in order:
+        group = by_label[key]
+        if len(group) < 2:
+            out.append(group[0])
+            continue
+        ordered = sorted(group, key=lambda r: r.num)
+        used = [False] * len(ordered)
+        for i, seed in enumerate(ordered):
+            if used[i]:
+                continue
+            cluster = [seed]
+            used[i] = True
+            for j in range(i + 1, len(ordered)):
+                if used[j]:
+                    continue
+                if _same_finding_regroup(seed.claim, ordered[j].claim):
+                    cluster.append(ordered[j])
+                    used[j] = True
+            if len(cluster) >= 2:
+                out.append(_merge_cluster(cluster))
+                groups += 1
+            else:
+                out.append(cluster[0])
+    out.extend(passthrough)
+    logger.info(
+        "[activation] summary_table_label_regroup: groups=%d rows_in=%d rows_out=%d",
+        groups, rows_in, len(out),
+    )
+    return out
+
+
 def _word_boundary_search(needle_regex_body: str, text: str, *, ignore_case: bool) -> bool:
     """True iff ``needle_regex_body`` matches ``text`` bounded on BOTH sides by a NON-word
     character (or a string edge) — i.e. as a WHOLE token, never as a substring inside a
@@ -1031,6 +1138,11 @@ def _build_rows(
     # so the collapsed multi-citation rows and the untouched singletons order together by ``num``.
     if _source_consolidate_enabled():
         rows = _consolidate_rows_by_source(rows)
+        # I-deepfix-001 (#1369) FIX 1: SECOND label-regroup pass catches the URL-vs-title splits and
+        # synonym-swap paraphrases the first (doc_key + Jaccard) pass leaves as duplicate rows. Kept
+        # UNDER the same master consolidation gate so PG_SUMMARY_TABLE_SOURCE_CONSOLIDATE=0 stays
+        # byte-identical to the one-row-per-eid legacy output.
+        rows = _regroup_rows_by_label(rows)
     rows.sort(key=lambda r: r.num)
     return rows
 
@@ -1133,6 +1245,67 @@ def _insert_before_appendix(report_md: str, table_md: str, appendix_boundary_mar
     return report_md.rstrip() + block
 
 
+# I-deepfix-001 (#1369) FIX 3 (iter3) — off-topic summary-table rows. Root cause (Fable): the promotion
+# topical gate is wired ONLY to the CWF single-source promotion partition, never to summary-table row
+# building, so an off-topic-but-span-verified source (materials-science MWCNT row [28] in a Gen-AI-and-jobs
+# report) rows-ifies unchecked. WEIGHT-NOT-FILTER / no-drop (Codex+Fable P1): a row whose claim shares EXACTLY
+# ZERO content-word overlap with the research question is DEMOTED to the bottom of the table — NEVER dropped
+# (lexical overlap is not a reliable off-topic signal; an on-topic synonym row has zero literal overlap too).
+# Every verified row survives; skips (no demotion) when the question yields no tokens. Default-ON
+# PG_SUMMARY_TABLE_TOPICAL_GATE.
+_ENV_TOPICAL_GATE = "PG_SUMMARY_TABLE_TOPICAL_GATE"
+
+
+def _topical_gate_enabled() -> bool:
+    """LAW VI kill-switch (default ON). OFF => rows pass through byte-identically."""
+    return os.environ.get(_ENV_TOPICAL_GATE, "1").strip().lower() not in _OFF_VALUES
+
+
+def _topical_tokens(text: str) -> frozenset[str]:
+    """Content-word tokens for the topical-overlap test, splitting on whitespace AND hyphens/slashes so a
+    compound like "employment-to-population" contributes "employment" (else an on-topic row that never
+    uses the question's exact surface form would be wrongly dropped). Stopword-stripped. PURE."""
+    out: set[str] = set()
+    for raw in re.split(r"[\s\-/]+", (text or "").lower()):
+        tok = raw.strip(".,;:!?()[]{}\"'`—–…%")
+        if not tok or tok in _CONSOLIDATE_STOPWORDS:
+            continue
+        out.add(tok)
+    return frozenset(out)
+
+
+def _topical_gate_rows(rows: list["_RowData"], research_question: str) -> list["_RowData"]:
+    """WEIGHT-NOT-FILTER / no-drop (Codex + Fable P1, §-1.3): NEVER drop a verified summary-table row on
+    topical grounds — a vocabulary-mismatch on-topic row ('Automation exposure is highest in clerical
+    occupations' vs a 'generative AI employment effects' question) has zero LITERAL question-token overlap
+    yet is genuinely on-topic, and lexical overlap is not a reliable off-topic signal. Instead DEMOTE: keep
+    EVERY row, but order the zero-overlap rows AFTER the overlapping ones (stable within each group) so
+    on-topic findings surface first without deleting any content. Emits the realized-effect marker. PURE
+    apart from the log."""
+    if not _topical_gate_enabled():
+        return rows
+    qtokens = _topical_tokens(research_question or "")
+    if not qtokens:
+        logger.info(
+            "[activation] summary_table_topical_gate: demoted=0 kept=%d (no question tokens -> skip)",
+            len(rows),
+        )
+        return rows
+    on_topic: list[_RowData] = []
+    off_topic: list[_RowData] = []
+    for r in rows:
+        ctoks = _topical_tokens(r.claim or "")
+        if ctoks and not (ctoks & qtokens):
+            off_topic.append(r)  # zero literal overlap -> DEMOTE to the bottom, never drop
+        else:
+            on_topic.append(r)
+    logger.info(
+        "[activation] summary_table_topical_gate: demoted=%d kept=%d (no-drop, on-topic-first)",
+        len(off_topic), len(on_topic) + len(off_topic),
+    )
+    return on_topic + off_topic
+
+
 def render_requested_summary_table(
     *,
     research_question: str,
@@ -1157,6 +1330,9 @@ def render_requested_summary_table(
     if len(headers) < 2:
         return SummaryTableResult(text=existing_report_md, changed=False, canary="no_table_requested")
     rows = _build_rows(bibliography or [], section_claims, chrome_screen)
+    # I-deepfix-001 (#1369) FIX 3 (iter3): DEMOTE off-topic table rows (literal zero question-overlap) to the
+    # bottom — never drop (weight-not-filter / §-1.3 no-drop). Every verified row survives.
+    rows = _topical_gate_rows(rows, research_question)
     if not rows:
         return SummaryTableResult(
             text=existing_report_md, changed=False, canary="no_verified_rows", headers=headers
diff --git a/src/polaris_graph/generator/weighted_enrichment.py b/src/polaris_graph/generator/weighted_enrichment.py
index 4abacd07..ba4af963 100644
--- a/src/polaris_graph/generator/weighted_enrichment.py
+++ b/src/polaris_graph/generator/weighted_enrichment.py
@@ -2872,11 +2872,107 @@ def _base_junk(text: str) -> bool:
         return _is_web_chrome(text) or _is_captcha_stub(text)
 
 
+# I-deepfix-001 (#1369) FIX 4 — chrome TYPES the existing screens structurally cannot match (Fable,
+# code-verified on box-2 report): (a) GENERATED document-navigation NARRATION ("...on page 46, presents
+# Figure 4.1 on page 61, includes Figure 6.1 as a schematic") — span-grounded so strict_verify passes it,
+# but it is document-structure furniture, not a research finding; (b) an author MASTHEAD carrying NO
+# ORCID/ISSN (so _ORCID_RE + the ISSN masthead rule both miss it: "Alexandra Shajek 1. Institut für ...,
+# GmbH, Berlin, Germany 2."). Default-ON kill-switch PG_RENDER_CHROME_NARRATION. Precision-first: the
+# narration rule needs >=2 distinct structure references so a real claim mentioning ONE figure is safe.
+_STRUCTURE_REF_RE = re.compile(
+    r"\b(?:on\s+)?page\s+\d+\b|\bFig(?:ure|\.)?\s*\d+(?:\.\d+)?\b|\bTable\s+\d+(?:\.\d+)?\b"
+    r"|\bas\s+a\s+schematic\b|\bchapter\s+\d+\b|\bsection\s+\d+(?:\.\d+)?\b",
+    re.I,
+)
+_MASTHEAD_NO_ORCID_RE = re.compile(
+    r"\b\d\s*\.?\s*(?:Institut|Institute|Universit|GmbH|Department|Laborator|Faculty|Ministry|Centre|Center)\b"
+    r".{0,90}?\b(?:Germany|Deutschland|USA|United\s+States|France|Italy|Spain|Netherlands|Austria|"
+    r"Switzerland|Sweden|Norway|Denmark|Finland|Belgium|Poland|Portugal|Greece|China|Japan|Korea|India|"
+    r"Canada|Australia|Kingdom)\b",
+    re.I,
+)
+
+
+def _render_chrome_narration_enabled() -> bool:
+    """Kill-switch ``PG_RENDER_CHROME_NARRATION`` (default ON). Only an explicit 0/false/off/no
+    disables; an EMPTY string stays ON."""
+    return os.environ.get("PG_RENDER_CHROME_NARRATION", "1").strip().lower() not in ("0", "false", "off", "no")
+
+
+# I-deepfix-001 (#1369) iter2/iter3 (Codex + Fable P1, WEIGHT-NOT-FILTER / no-drop): a REAL finding that
+# merely cites figure/table LOCATIONS is NOT chrome. TWO keep-signals, both computed on the residual after
+# stripping the structure references, so "Figure 4.1"'s "4.1" / "page 61"'s "61" never read as findings:
+#   (a) a finding metric survives — a %, "percent/pp", a decimal, OR a plain/comma integer of >=2 digits
+#       ("job losses of 1,200 and 900 workers"); OR
+#   (b) SUBSTANTIVE content dominates — the structure references are a MINORITY of the text (< 45% of chars),
+#       so a qualitative finding ("Table 2 and Table 3 show automation displaces routine work") is KEPT.
+# Only text that is BOTH metric-free AND dominated by document-navigation refs ("...page 46, presents
+# Figure 4.1 on page 61, includes Figure 6.1 as a schematic") is flagged as chrome. Err toward KEEP (§-1.3).
+_FINDING_METRIC_RE = re.compile(
+    r"\d+(?:\.\d+)?\s*%|\bpercent(?:age\s+points?)?\b|\bpp\b|\d{1,3}(?:,\d{3})+|\d+\.\d+|\b\d{2,}\b"
+)
+# Document-DESCRIPTION verb that DIRECTLY GOVERNS a structure noun — the writer narrating a document's own
+# apparatus ("presents Figure 4.1", "includes Figure 6.1", "reproduces Table 2 as a schematic"). Codex iter-3
+# P1: the verb ALONE is not enough — "present/illustrate/depict/include" are REAL finding verbs when they
+# govern CONTENT ("present evidence that automation displaces work", "illustrate that ...", "depict a shift").
+# So we require the description verb to be IMMEDIATELY followed by a structure noun (Figure/Table/Chart/...),
+# OR the standalone "as a schematic" tail. This catches the box-2 navigation chrome without touching a real
+# qualitative finding that merely uses "present/illustrate/depict".
+# STRONG navigation signal: a description verb DIRECTLY governing a structure noun ("presents Figure 4.1").
+# Each occurrence counts fully toward the narration chain.
+_NAV_VERB_STRUCTURE_RE = re.compile(
+    r"\b(?:outlines?|presents?|depicts?|illustrates?|includes?|reproduces?|shows?|contains?|summariz\w+)\s+"
+    r"(?:the\s+|a\s+|an\s+)?(?:Fig(?:ure|\.)?|Table|Chart|Schematic|Diagram|Panel|Exhibit|Appendix|Chapter)\b",
+    re.I,
+)
+# WEAK navigation signal: a bare "see Figure/Table/page" locator or an "as a schematic" tail. Codex iter-4 +
+# Fable iter-5 P1 (no-drop): a REAL finding routinely carries such parentheticals — "(see Table 2) and
+# manufacturing (see Figure 3)". So ALL of these together count AT MOST ONCE toward the chain.
+_NAV_LOCATOR_RE = re.compile(
+    r"\bas\s+a\s+schematic\b|\bsee\s+(?:figure|table|page)\b",
+    re.I,
+)
+
+
+def _is_generated_narration_or_masthead(text: str) -> bool:
+    """True iff ``text`` is generated document-navigation narration or an ORCID/ISSN-less author-
+    affiliation masthead. NARRATION = >=2 structure refs AND no finding metric AND (a document-DESCRIPTION
+    verb like outlines/presents/includes OR the structure refs DOMINATE the text). Weight-not-filter /
+    no-drop (Codex+Fable P1): a real finding citing a table/figure location — quantitative ('3.2% ... Table 4
+    on page 12.', 'job losses of 1,200 and 900 workers') OR qualitative ('Table 2 and Table 3 show automation
+    displaces routine work') — is CONTENT and is NEVER dropped (it has a metric, or an outcome verb rather
+    than a description verb, or low structure-share). PURE."""
+    # Masthead: an affiliation block carrying a finding metric is a numbered-list FINDING, not a masthead.
+    if _MASTHEAD_NO_ORCID_RE.search(text) and not _FINDING_METRIC_RE.search(text):
+        return True
+    refs = _STRUCTURE_REF_RE.findall(text)
+    if len(refs) >= 2:
+        residual = _STRUCTURE_REF_RE.sub(" ", text)
+        if _FINDING_METRIC_RE.search(residual):
+            return False  # a real finding metric survives the structure refs -> content, keep it
+        ref_chars = sum(len(m) for m in refs)
+        structure_dominates = ref_chars / (len(text.strip()) or 1) >= 0.45
+        # Codex iter-3/4 + Fable iter-5 P1 (no-drop): pure document narration walks the reader through
+        # MULTIPLE exhibits ("presents Figure 4.1 ... includes Figure 6.1 as a schematic"); a REAL finding
+        # cites locations in passing ("...(see Table 2) and manufacturing (see Figure 3)", "present evidence
+        # that ..."). So the chain = (every strong description-verb-governs-structure phrase) + (all the weak
+        # bare "see X"/"as a schematic" locators counted AT MOST ONCE combined). Flag only when the chain
+        # reaches 2 OR the structure refs outright dominate. A real finding never chains 2+ STRONG nav clauses.
+        nav_chain = len(_NAV_VERB_STRUCTURE_RE.findall(text)) + min(1, len(_NAV_LOCATOR_RE.findall(text)))
+        if nav_chain >= 2 or structure_dominates:
+            return True   # metric-free + (multi-clause document-navigation OR structure-dominated) -> chrome
+        return False      # metric-free finding with <=1 locator phrase and low structure-share -> keep it
+    return False
+
+
 def _is_new_chrome_category(text: str) -> bool:
     """The NEW I-wire-012 chrome categories (default-ON, high-precision) PLUS the I-wire-013 (#1327)
     CONTAINMENT forensic rules (a unit that CONTAINS glued page-furniture, not only IS junk)."""
     if _SHARED_RENDER_CHROME_RE.search(text):
         return True
+    # I-deepfix-001 (#1369) FIX 4: generated page/figure narration + ORCID-less masthead (default-ON).
+    if _render_chrome_narration_enabled() and _is_generated_narration_or_masthead(text):
+        return True
     if _SHARED_CLAIM_HEADER_CHROME_RE.search(text):
         return True
     if _SHARED_TOC_RE.search(text):
diff --git a/tests/dr_benchmark/test_verified_only_surface_iready013.py b/tests/dr_benchmark/test_verified_only_surface_iready013.py
index 9df4fb35..3eccae91 100644
--- a/tests/dr_benchmark/test_verified_only_surface_iready013.py
+++ b/tests/dr_benchmark/test_verified_only_surface_iready013.py
@@ -70,7 +70,11 @@ def _set_min_passing_gate_b_env(monkeypatch: pytest.MonkeyPatch) -> None:
     set_max_cost_per_run(25.0)
 
 
-def test_gate_b_slate_force_disables_unverified_analyst_synthesis(monkeypatch):
+def test_gate_b_slate_enables_gated_analyst_synthesis(monkeypatch):
+    """I-deepfix-001 (#1369): the analyst-synthesis layer is RE-ENABLED under the GATED D3 PROMOTE
+    (drop-if-ungrounded) posture — operator-authorized, dual-gated (Codex+Fable). The slate now forces
+    the layer ON with BOTH gate flags ON; the three flags are conscious WINNERS (allowlist + FORCE_EXACT)
+    and are NO LONGER in REQUIRED_OFF. This supersedes the old I-ready-013 hard-ban assertion."""
     from src.polaris_graph.llm.openrouter_client import (
         get_max_cost_per_run,
         set_max_cost_per_run,
@@ -78,49 +82,45 @@ def test_gate_b_slate_force_disables_unverified_analyst_synthesis(monkeypatch):
 
     old_cap = get_max_cost_per_run()
     try:
-        monkeypatch.setenv("PG_SWEEP_ANALYST_SYNTHESIS", "1")
         gate_b.apply_full_capability_benchmark_slate()
-        assert os.environ["PG_SWEEP_ANALYST_SYNTHESIS"] == "0"
-        assert gate_b._FULL_CAPABILITY_BENCHMARK_SLATE["PG_SWEEP_ANALYST_SYNTHESIS"] == "0"
-        assert "PG_SWEEP_ANALYST_SYNTHESIS" in gate_b._BENCHMARK_FORCE_EXACT_FLAGS
-        assert "PG_SWEEP_ANALYST_SYNTHESIS" in gate_b._BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS
+        assert gate_b._FULL_CAPABILITY_BENCHMARK_SLATE["PG_SWEEP_ANALYST_SYNTHESIS"] == "1"
+        assert gate_b._FULL_CAPABILITY_BENCHMARK_SLATE["PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED"] == "1"
+        assert gate_b._FULL_CAPABILITY_BENCHMARK_SLATE["PG_ANALYST_SYNTHESIS_DEVIATION_CHECK"] == "1"
+        assert os.environ["PG_SWEEP_ANALYST_SYNTHESIS"] == "1"
+        for _f in (
+            "PG_SWEEP_ANALYST_SYNTHESIS",
+            "PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED",
+            "PG_ANALYST_SYNTHESIS_DEVIATION_CHECK",
+        ):
+            assert _f in gate_b._BENCHMARK_FORCE_EXACT_FLAGS
+            assert _f in gate_b._WINNER_FLAG_ALLOWLIST
+            assert _f not in gate_b._BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS
     finally:
         set_max_cost_per_run(old_cap)
 
 
-def test_gate_b_preflight_fails_if_analyst_synthesis_enabled(monkeypatch):
+def test_gate_b_preflight_refuses_ungated_analyst_synthesis(monkeypatch):
+    """I-deepfix-001 (#1369): the layer may ONLY ship under the D3 fail-closed PROMOTE gate. A run with
+    PG_SWEEP_ANALYST_SYNTHESIS ON while PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED resolves falsey is the exact
+    ungated posture that was banned, so the preflight REFUSES it fail-closed."""
     from src.polaris_graph.llm.openrouter_client import (
         get_max_cost_per_run,
         set_max_cost_per_run,
     )
 
     old_cap = get_max_cost_per_run()
-    # _set_min_passing_gate_b_env applies the production slate, which mutates os.environ DIRECTLY (not via
-    # monkeypatch). Snapshot + restore the whole environment so the winners-only baseline (e.g. the W4
-    # PG_CLINICAL_PDF_EXTRACTOR=mineru25 pin) does not leak into sibling dr_benchmark tests in the same
-    # process — the env-leak class this suite is otherwise prone to.
+    # _set_min_passing_gate_b_env mutates os.environ DIRECTLY; snapshot + restore so the winners-only
+    # baseline does not leak into sibling dr_benchmark tests in the same process.
     env_snapshot = dict(os.environ)
     try:
         _set_min_passing_gate_b_env(monkeypatch)
-        # offline=True: this is a no-GPU / no-spend unit test, so skip ONLY the WINNER-FIRES GPU
-        # host-capability probes (W4 mineru25 torch.cuda, W5 reranker device) that would false-fail on a
-        # CPU host. The NO-LOSER gate + the killed-loser REQUIRED_OFF check (which is what protects the
-        # analyst-synthesis suppression) stay UNCONDITIONAL, so the perturbation below still binds.
-        gate_b.preflight_full_capability(offline=True)
-
-        # I-deepfix-001 (#1344): the legacy Analyst Synthesis layer is a killed un-span-verified loser —
-        # PG_SWEEP_ANALYST_SYNTHESIS is in _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS, so re-arming it trips
-        # the generic NO-LOSER/REQUIRED_OFF gate. The message names the flag (the dedicated "Analyst
-        # Synthesis" phrasing was consolidated into the generic killed-loser gate), so match the flag id.
+        # ungated posture: layer ON, D3 PROMOTE gate OFF => REFUSED fail-closed by the :4693 preflight assert.
         monkeypatch.setenv("PG_SWEEP_ANALYST_SYNTHESIS", "1")
-        with pytest.raises(RuntimeError, match="PG_SWEEP_ANALYST_SYNTHESIS"):
+        monkeypatch.setenv("PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED", "0")
+        with pytest.raises(RuntimeError, match="PROMOTE"):
             gate_b.preflight_full_capability(offline=True)
     finally:
         set_max_cost_per_run(old_cap)
-        # I-deepfix-001 (#1344) Codex P1: undo monkeypatch FIRST — _set_min_passing_gate_b_env recorded
-        # POST-slate env values via monkeypatch, and pytest's monkeypatch teardown runs AFTER this finally;
-        # without undo() it would re-inject them, defeating the snapshot restore. The snapshot restore then
-        # handles the slate's DIRECT os.environ mutations (untracked by monkeypatch). Both are required.
         monkeypatch.undo()
         os.environ.clear()
         os.environ.update(env_snapshot)
```
