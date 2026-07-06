HARD ITERATION CAP: 5 per document. This is iter 1 of 5. APPROVE iff zero P0 and zero P1. Your shell is unavailable this session — this context is SELF-CONTAINED (full diff + a per-flag coherence table computed from the real file); verify from the inlined evidence, do NOT abstain on shell grounds.

# Wave-3a U4 diff review — ACTIVATE the core path: 14 flags into the gate-B QUAD slate (the payoff)

CONTEXT: POLARIS I-deepfix-001 (#1344). The routing proof found the new-core deep-research modules were DARK on the paid path (their flags absent from the gate-B slate → OLD modules silently built the report). U1 (routing), U2 (fire markers), U3 (activation canary) are committed. THIS unit (U4, Claude-authored, you are the independent gate) flips the flags ON by adding them to the gate-B QUAD: `_FULL_CAPABILITY_BENCHMARK_SLATE` (dict "1") + `_BENCHMARK_FORCE_ON_FLAGS` + `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` + `_WINNER_FLAG_ALLOWLIST`. The allowlist is MANDATORY: the SLATE-PURITY preflight RuntimeErrors on any force-on/force-exact ON-token NOT in `_WINNER_FLAG_ALLOWLIST`. This edits ONLY the slate constructs — no pipeline logic.

REVIEW for:
1. **QUAD COHERENCE (no preflight RuntimeError).** Each of the 14 flags must be in slate + FORCE_ON + PREFLIGHT_REQUIRED + ALLOWLIST (PG_LOG_LEVEL is force-EXACT "INFO" not force-on: slate + FORCE_EXACT + ALLOWLIST). Confirm from the diff that EACH flag is added to every list it needs, and — critically — that every force-on/force-exact ON-token added is ALSO in the allowlist (else the preflight fails closed before spend). The per-flag occurrence table (computed from the real post-edit file) is below.
2. **ALLOWLIST completeness** — the operator's repeated failure is a flag forced ON but not allowlisted → RuntimeError at benchmark start. Cross-check each of the 14 appears in the allowlist addition.
3. **PG_SUBENTITY_QUERY_EXPANSION promotion** — the executable `os.environ.setdefault("PG_SUBENTITY_QUERY_EXPANSION","1")` is REMOVED (the 1 deletion-ish) and the flag added to the QUAD (conscious LAW VI policy flip). Confirm the setdefault is gone and the flag is now force-on+allowlisted.
4. **DEAD ASSERTION FIX** — `_CROSS_SOURCE_SILENT_NOOP_MARKER` literal 'anchored' → 'candidate' (matches the producer's emitted "...candidate cross-source pair(s)..." at cross_source_synthesis.py:802). Confirm.
5. **OFF / NON-BENCHMARK BYTE-IDENTICAL** — these constants are only forced inside apply_full_capability_benchmark_slate; a non-benchmark invocation (unit tests, direct run) does not mutate env. Confirm no pipeline logic changed — only the slate/force/preflight/allowlist/force-exact constructs.
6. **PG_PRESENTATION_TABLES NOT added** (deferred, 2c-wiring unbuilt). Confirm it's absent (occurrence count 0).
7. Any P0/P1: a flag forced-on but NOT allowlisted (RuntimeError risk), a dependency flag missed (parent silently no-ops), a pipeline-logic change, or reformat (git diff -w == git diff = 11/11 del, 113 ins, byte-preserving splice on the mixed-CRLF file).

PER-FLAG OCCURRENCE COUNT in the post-edit run_gate_b.py (boolean flags appear 4+ across the QUAD; capability flags appear 5+ because U3's canary + preflight also reference them; deps exactly 4; PG_LOG_LEVEL slate+forceexact+allowlist; PG_PRESENTATION_TABLES=0 confirms deferred):
  PG_CROSS_SOURCE_BODY : 5
  PG_NUMERIC_COMPARATOR : 5
  PG_PROVENANCE_REANCHOR : 5
  PG_SYNTH_PRIMARY : 6
  PG_FINDING_DEDUP_NLI : 11
  PG_MIN_CITE_SET : 11
  PG_TWO_SIDED_DEBATE : 5
  PG_SHALLOW_REPORT_CANARY : 12
  PG_ACTIVATION_CANARY : 13
  PG_SUBENTITY_QUERY_EXPANSION : 8
  PG_CORROBORATION_LAYER2_CITE : 4
  PG_CITATION_TWO_LAYER_POLICY : 4
  PG_FINDING_DEDUP_QUALITATIVE : 4
  PG_CONSOLIDATION_NLI_QUALITATIVE : 4
  PG_LOG_LEVEL : 6
  PG_PRESENTATION_TABLES : 0

THE DIFF (run_gate_b.py, +113/-11):
```diff
diff --git a/scripts/dr_benchmark/run_gate_b.py b/scripts/dr_benchmark/run_gate_b.py
index 802990a0..333b0050 100644
--- a/scripts/dr_benchmark/run_gate_b.py
+++ b/scripts/dr_benchmark/run_gate_b.py
@@ -1584,6 +1584,43 @@ _FULL_CAPABILITY_BENCHMARK_SLATE: dict[str, str] = {
     # plumbing on the safe docling->PyMuPDF PDF path. mineru25 firing + its crash-isolation (subprocess/
     # hard-kill) is the queued fix before the paid run. Gate-B model-loading runs land on the GPU VM per
     # the VM-only run policy.
+    # I-deepfix-001 (#1344) WAVE-3a U4 — ACTIVATE the deep-research CORE path: turn the 7 dark capability
+    # modules + 2 fail-loud canaries + the promoted sub-entity expander + their 4 dependency flags ON for
+    # the paid Gate-B run. Each of the 14 is slate "1" HERE + _BENCHMARK_FORCE_ON_FLAGS (a stray operator/
+    # .env =0 cannot survive the setdefault slate) + _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS (fail-CLOSED pre-
+    # spend) + _WINNER_FLAG_ALLOWLIST (SLATE-PURITY). Each module already has its routing (U1), [activation]
+    # fire-marker (U2) and the activation canary (U3) committed; THIS unit flips the flags. §-1.3 DNA-ALIGNED
+    # (WEIGHT-and-CONSOLIDATE surfaces — NO cap/target/thinner); FAITHFULNESS-NEUTRAL (every surfaced / re-
+    # anchored / synthesized claim re-passes the UNCHANGED strict_verify / NLI / 4-role D8 / provenance /
+    # span-grounding chokepoint; the FROZEN faithfulness engine is byte-untouched).
+    "PG_CROSS_SOURCE_BODY": "1",              # plan-driven candidate pairing (cross_source_synthesis)
+    "PG_NUMERIC_COMPARATOR": "1",             # upgrade fully-comparable NEUTRAL pair -> comparison connective
+    "PG_PROVENANCE_REANCHOR": "1",            # re-anchor wrongly-cited claim to best ENTAILING span (argmax)
+    "PG_SYNTH_PRIMARY": "1",                  # compose-then-verify PRIMARY body for corroborated baskets
+    "PG_FINDING_DEDUP_NLI": "1",              # directional bidirectional-entailment same-claim grouping (Wave-1b)
+    "PG_MIN_CITE_SET": "1",                   # minimal INLINE cite set vs weight-channel demotion (keep-all)
+    "PG_TWO_SIDED_DEBATE": "1",               # two-leg debate disclosure + con-side retrieval guarantee
+    # PROMOTE: PG_SUBENTITY_QUERY_EXPANSION was an ad-hoc os.environ.setdefault in apply_full_capability_
+    # benchmark_slate (operator/.env =0 WON). CONSCIOUS LAW VI POLICY FLIP: it is now a FORCED winner like
+    # the other coverage levers (precedent: the FORCE_ON coverage-lever group). WIDEN-ONLY SUPERSET,
+    # FAITHFULNESS-NEUTRAL (§-1.3): only ADDS scope-anchored queries; every added query routes through the
+    # UNCHANGED fetch -> classify_source_tier -> strict_verify chokepoint. setdefault removed at call site.
+    "PG_SUBENTITY_QUERY_EXPANSION": "1",      # R2 sub-entity / STORM-perspective query expansion (PROMOTED)
+    # DEPENDENCY flags (each DEFAULT-ON in code) — pinned "1" so the parent capability never silently no-ops:
+    "PG_CORROBORATION_LAYER2_CITE": "1",      # dep of PG_MIN_CITE_SET (default-ON; explicit pin)
+    "PG_CITATION_TWO_LAYER_POLICY": "1",      # dep of PG_MIN_CITE_SET (two-layer citation render; default-ON)
+    "PG_FINDING_DEDUP_QUALITATIVE": "1",      # dep of PG_FINDING_DEDUP_NLI (qualitative-basket pass; default-ON)
+    "PG_CONSOLIDATION_NLI_QUALITATIVE": "1",  # dep of PG_FINDING_DEDUP_NLI (qualitative-NLI union; default-ON)
+    # fail-loud DETECTOR canaries (opt-in DEFAULT-OFF in code) — ARMED for the activation-validation run:
+    "PG_SHALLOW_REPORT_CANARY": "1",          # Wave-1d shallow-report fail-loud detector
+    "PG_ACTIVATION_CANARY": "1",              # Wave-3a activation fail-loud detector (parses [activation] markers)
+    # LOG-LEVEL SAFETY (Fable U3 P2): the activation canary reads module-logger [activation] markers, which
+    # run_honest_sweep_r3.py logs at INFO (logging.basicConfig level=os.environ.get("PG_LOG_LEVEL","INFO")).
+    # A stray operator PG_LOG_LEVEL=WARNING would SUPPRESS every info-level marker -> the canary would
+    # false-fail. Force-EXACT "INFO" (in _BENCHMARK_FORCE_EXACT_FLAGS + allowlisted) so markers are never
+    # suppressed on the benchmark run. Non-numeric string pin => SLATE-PURITY requires the allowlist entry.
+    # Observability-only; touches no faithfulness path.
+    "PG_LOG_LEVEL": "INFO",                   # pin log level so [activation] INFO markers are never suppressed
 }
 
 # Minimum effective values the run MUST meet — the preflight FAILS CLOSED if any is below these (i.e.
@@ -1817,6 +1854,25 @@ _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS = (
     "PG_CONTRADICTION_SUPPRESS_METRIC_MISMATCH",
     "PG_FACT_DEDUP_EXACT_INTRASECTION",
     "PG_RUN_VALIDITY_GATE",
+    # I-deepfix-001 (#1344) WAVE-3a U4 — fail-CLOSED before spend if any of the 14 ACTIVATED core-path
+    # flags is off: the 7 dark capability modules, the promoted sub-entity expander, the 4 default-ON
+    # dependency flags, and the 2 fail-loud canaries. Force-ON above, so a stray operator =0 fails the run
+    # CLOSED here. Booleans -> safe in this truthy-required tuple (os.getenv=="1"). Requiring the canaries
+    # truthy guarantees the validation run is ARMED. §-1.3 PIN-only; faithfulness engine UNTOUCHED.
+    "PG_CROSS_SOURCE_BODY",
+    "PG_NUMERIC_COMPARATOR",
+    "PG_PROVENANCE_REANCHOR",
+    "PG_SYNTH_PRIMARY",
+    "PG_FINDING_DEDUP_NLI",
+    "PG_MIN_CITE_SET",
+    "PG_TWO_SIDED_DEBATE",
+    "PG_SUBENTITY_QUERY_EXPANSION",
+    "PG_CORROBORATION_LAYER2_CITE",
+    "PG_CITATION_TWO_LAYER_POLICY",
+    "PG_FINDING_DEDUP_QUALITATIVE",
+    "PG_CONSOLIDATION_NLI_QUALITATIVE",
+    "PG_SHALLOW_REPORT_CANARY",
+    "PG_ACTIVATION_CANARY",
 )
 
 # Codex diff-gate I-cap-005 P1-2: the minimum EFFECTIVE per-run budget cap. PG_MAX_COST_PER_RUN is an
@@ -2045,6 +2101,26 @@ _BENCHMARK_FORCE_ON_FLAGS = frozenset({
     "PG_CONTRADICTION_SUPPRESS_METRIC_MISMATCH",
     "PG_FACT_DEDUP_EXACT_INTRASECTION",
     "PG_RUN_VALIDITY_GATE",
+    # I-deepfix-001 (#1344) WAVE-3a U4 — force-ON the 7 dark deep-research capability modules + the 2
+    # fail-loud canaries + the PROMOTED sub-entity expander + the 4 default-ON dependency flags so a stray
+    # operator/.env =0 cannot survive the setdefault slate and silently leave the ACTIVATED core path dark
+    # on the paid run. Each is a slate "1" member above + preflight-required below + allowlisted (SLATE-
+    # PURITY). §-1.3 DNA-ALIGNED (WEIGHT-and-CONSOLIDATE; NO cap/target/thinner); FAITHFULNESS-NEUTRAL
+    # (every surfaced / re-anchored / synthesized claim re-passes the UNCHANGED strict_verify chokepoint).
+    "PG_CROSS_SOURCE_BODY",
+    "PG_NUMERIC_COMPARATOR",
+    "PG_PROVENANCE_REANCHOR",
+    "PG_SYNTH_PRIMARY",
+    "PG_FINDING_DEDUP_NLI",
+    "PG_MIN_CITE_SET",
+    "PG_TWO_SIDED_DEBATE",
+    "PG_SUBENTITY_QUERY_EXPANSION",       # PROMOTED from ad-hoc setdefault (conscious LAW VI policy flip)
+    "PG_CORROBORATION_LAYER2_CITE",       # dep of PG_MIN_CITE_SET (default-ON; force so parent never no-ops)
+    "PG_CITATION_TWO_LAYER_POLICY",       # dep of PG_MIN_CITE_SET (default-ON)
+    "PG_FINDING_DEDUP_QUALITATIVE",       # dep of PG_FINDING_DEDUP_NLI (default-ON)
+    "PG_CONSOLIDATION_NLI_QUALITATIVE",   # dep of PG_FINDING_DEDUP_NLI (default-ON)
+    "PG_SHALLOW_REPORT_CANARY",           # Wave-1d shallow-report fail-loud detector (armed for validation)
+    "PG_ACTIVATION_CANARY",               # Wave-3a activation fail-loud detector (armed for validation)
 })
 
 # Flags/modes that the benchmark slate force-sets to a specific value that is
@@ -2200,6 +2276,13 @@ _BENCHMARK_FORCE_EXACT_FLAGS = frozenset({
     "PG_EMBED_MODEL",                     # K12 live relevance embedder id (= Qwen3-Embedding-8B)
     "PG_ENTAILMENT_MODEL",                # gemma-pin: live NLI / semantic-conflict judge (= glm-5.2)
     "PG_EVALUATOR_MODEL",                 # gemma-pin: external evaluator (= glm-5.2)
+    # I-deepfix-001 (#1344) WAVE-3a U4 LOG-LEVEL SAFETY (Fable U3 P2): the activation canary parses the
+    # module-logger [activation] markers, which run_honest_sweep_r3.py logs at INFO
+    # (logging.basicConfig level=os.environ.get("PG_LOG_LEVEL","INFO")). A stray operator PG_LOG_LEVEL=
+    # WARNING would SUPPRESS every info-level marker and the canary would false-fail. Force-EXACT "INFO"
+    # (non-numeric STRING => the numeric-FLOOR path would crash on float("INFO"); it is a slate-dict member
+    # so apply_slate hard-sets it) + allowlisted for SLATE-PURITY. Observability-only; faithfulness-neutral.
+    "PG_LOG_LEVEL",
 })
 
 # I-ready-017 FX-03 (#1107) Codex iter-2 P1: hard CEILING on the cited-span window (defense-in-depth on
@@ -2426,7 +2509,7 @@ def firing_marker_contract_substrings() -> dict[str, str]:
 # survived ..." when eligible pairs existed but nothing survived per-clause re-verify. The stems below
 # are the stable literals in those two producer lines.
 _CROSS_SOURCE_FIRED_MARKER = "[cross_source_synthesis] composed"
-_CROSS_SOURCE_SILENT_NOOP_MARKER = "anchored cross-source pair(s) but 0 analytical units survived"
+_CROSS_SOURCE_SILENT_NOOP_MARKER = "candidate cross-source pair(s) but 0 analytical units survived"
 
 
 def assert_cross_source_synthesis_fired(log_text: str) -> None:
@@ -3193,6 +3276,27 @@ _WINNER_FLAG_ALLOWLIST: frozenset[str] = frozenset({
     "PG_CONTRADICTION_SUPPRESS_METRIC_MISMATCH",   # metric-mismatch out of headline contradiction count
     "PG_FACT_DEDUP_EXACT_INTRASECTION",      # exact-duplicate intra-section consolidation (keep-all)
     "PG_RUN_VALIDITY_GATE",                  # validity: render-validity master gate (fail-closed do-not-ship)
+    # ── I-deepfix-001 (#1344) WAVE-3a U4 — the ACTIVATED deep-research core path (winner-or-infra: WINNERS) ──
+    # The 7 dark capability modules + the promoted sub-entity expander + their 4 dependency flags + the 2
+    # fail-loud detectors + the log-level observability pin, force-ON / force-EXACT above. Each is the DRB-II
+    # ACTIVATION machinery or its dependency / detector / observability pin — a conscious 'winner or infra?'
+    # decision, allowlisted deliberately so the clean slate PASSES SLATE-PURITY while a future re-introduced
+    # loser still fails CLOSED. §-1.3 weight-and-consolidate; FAITHFULNESS-NEUTRAL.
+    "PG_CROSS_SOURCE_BODY",                  # plan-driven candidate pairing (cross_source_synthesis)
+    "PG_NUMERIC_COMPARATOR",                 # NEUTRAL -> comparison connective upgrade
+    "PG_PROVENANCE_REANCHOR",                # re-anchor wrongly-cited claim to best ENTAILING span (argmax)
+    "PG_SYNTH_PRIMARY",                      # compose-then-verify PRIMARY body for corroborated baskets
+    "PG_FINDING_DEDUP_NLI",                  # directional bidirectional-entailment same-claim grouping
+    "PG_MIN_CITE_SET",                       # minimal INLINE cite set vs weight-channel demotion (keep-all)
+    "PG_TWO_SIDED_DEBATE",                   # two-leg debate disclosure + con-side retrieval guarantee
+    "PG_SUBENTITY_QUERY_EXPANSION",          # R2 sub-entity / STORM-perspective query expansion (promoted winner)
+    "PG_CORROBORATION_LAYER2_CITE",          # dep of PG_MIN_CITE_SET
+    "PG_CITATION_TWO_LAYER_POLICY",          # dep of PG_MIN_CITE_SET
+    "PG_FINDING_DEDUP_QUALITATIVE",          # dep of PG_FINDING_DEDUP_NLI
+    "PG_CONSOLIDATION_NLI_QUALITATIVE",      # dep of PG_FINDING_DEDUP_NLI
+    "PG_SHALLOW_REPORT_CANARY",              # Wave-1d shallow-report fail-loud detector (observability)
+    "PG_ACTIVATION_CANARY",                  # Wave-3a activation fail-loud detector (observability)
+    "PG_LOG_LEVEL",                          # log-level pin so [activation] INFO markers are never suppressed (observability)
 })
 
 # BB5-C06 (#1178): entity types that KEEP the OA full-text path even under PG_FRAME_PREFER_ABSTRACT.
@@ -3417,16 +3521,14 @@ def apply_full_capability_benchmark_slate(smoke_scale: bool = False) -> None:
     # for every other non-trigger reason. Config-only slate tests never call it, so they stay clean.
     # FAITHFULNESS-NEUTRAL: no faithfulness logic.
     # ─────────────────────────────────────────────────────────────────────────────────────────────
-    # ARM R2 (wiring audit — Codex+Fable, 2026-07-04): PG_SUBENTITY_QUERY_EXPANSION defaults "0"
-    # (sub_entity_query_expander.py:62) and was set NOWHERE in the effective run env, so the sub-entity +
-    # STORM-perspective query expansion was DEAD on the drb_72 run. Arm it here so
-    # sub_entity_expansion_enabled() -> True and widen_with_sub_entities fires
-    # (fs_researcher_query_gen.py:398-405). `setdefault` (NOT force) so an explicit operator/.env override
-    # still WINS (LAW VI). WIDEN-ONLY SUPERSET, FAITHFULNESS-NEUTRAL (§-1.3): it only ADDS scope-anchored
-    # queries to the frontier (a strict superset of the flag-OFF issued set) — no cap / target / thinner /
-    # drop; every added query routes through the UNCHANGED per_query_retrieve -> fetch ->
-    # classify_source_tier -> strict_verify chokepoint, and the FROZEN faithfulness engine is untouched.
-    os.environ.setdefault("PG_SUBENTITY_QUERY_EXPANSION", "1")
+    # ARM R2 PROMOTED to the QUAD — Wave-3a U4 (I-deepfix-001 #1344). The ad-hoc
+    # `os.environ.setdefault("PG_SUBENTITY_QUERY_EXPANSION", "1")` that lived HERE is REMOVED. The flag is
+    # now a FORCED winner: slate "1" + _BENCHMARK_FORCE_ON_FLAGS + _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS +
+    # _WINNER_FLAG_ALLOWLIST (see the Wave-3a slate block). CONSCIOUS LAW VI POLICY FLIP: previously an
+    # operator/.env PG_SUBENTITY_QUERY_EXPANSION=0 WON (setdefault); it is now force-on for the benchmark
+    # like the other coverage levers (precedent: the FORCE_ON coverage-lever group). WIDEN-ONLY SUPERSET,
+    # FAITHFULNESS-NEUTRAL (§-1.3): it only ADDS scope-anchored queries; every added query routes through
+    # the UNCHANGED per_query_retrieve -> fetch -> classify_source_tier -> strict_verify chokepoint.
     # ─────────────────────────────────────────────────────────────────────────────────────────────
     # ARM L2 (wiring audit — Codex+Fable, 2026-07-04): PG_SUBTOPIC_ADDITIVE_FACTS defaults "0"
     # (verified_compose.py:560-567) and was set NOWHERE, so the additive distinct-fact pass (commit
```

OUTPUT SCHEMA (return exactly):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
quad_coherent_no_preflight_error: true|false
all_14_allowlisted: true|false
subentity_promoted_setdefault_removed: true|false
dead_assertion_fixed: true|false
off_byte_identical: true|false
presentation_tables_not_added: true|false
convergence_call: continue | accept_remaining
notes: <short>
```
APPROVE iff QUAD coherent (no preflight RuntimeError), all 14 allowlisted, subentity promoted, dead assertion fixed, OFF byte-identical, PG_PRESENTATION_TABLES absent, zero P0/P1.
