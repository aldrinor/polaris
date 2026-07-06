# Wave-3a build spec — the ACTIVATION contract (derived from the DUAL-APPROVED routing proof)

Source of truth: `.codex/I-deepfix-001/wave3_routing_proof.md` (Codex iter-2 APPROVE + Fable APPROVE, fix_plan_complete=true, any_fix_relaxes_faithfulness=false). This spec pins the exact marker literals + wiring so producers (modules) and consumer (activation canary) agree. Build order = markers → synth-primary routing → canary → wire → harden (safety machinery before activation). Every diff dual-gated (Codex inline + Fable file-access), OFF/non-slate byte-identical, faithfulness engine byte-untouched, commit EXACT files never -A.

## FIRE-MARKER CONTRACT (stable literals; canary parses `[activation] <module>:` lines)
Each module, when its flag is ON and it actually did its work, emits ONE stable log line via the run logger (the same `_log`/logger sink the existing D8/shallow markers use). Format: `[activation] <name>: <positive-count> <bool-fields>`. The canary asserts the positive marker PRESENT and the degrade/old marker ABSENT, plus the boolean not-degraded fields.

| module | flag | POSITIVE marker (emit on real work) | not-degraded fields | OLD/degrade marker (must be ABSENT / false) | producer site |
|---|---|---|---|---|---|
| synth-primary | PG_SYNTH_PRIMARY | `[activation] synth_primary: authored_prose kept=<N>` (emit ONLY when authored body non-empty; kept=count, per Fable R5 — do NOT emit on kept=[] pure-disclosure) | — | (canary also checks a corroborated basket was authored — see synth-primary routing) | verified_compose.py ~1462-1486 non-empty authored return |
| finding-dedup-NLI | PG_FINDING_DEDUP_NLI | `[activation] finding_dedup_nli: invoked directional_merges=<N>` | `degraded=<bool>` `wall_truncated=<bool>` | degraded=true (cross-encoder OOM/None → legacy fallback) | finding_dedup.py ~1479-1480 keystone + FindingDedupResult |
| basket-consume | PG_BASKET_CONSUME_FINDING_DEDUP | `[activation] basket_consume_finding_dedup: regrouped old_to_new=<N>` | `noop=<bool>` | noop=true (returned input unchanged, credibility_pass.py:738/:854) | credibility_pass.py _regroup_graph_by_finding_dedup |
| provenance-reanchor | PG_PROVENANCE_REANCHOR | `[activation] provenance_reanchor: accepted=<N> reanchored_argmax=<N>` | `build_ok=<bool>` | — (reanchor telemetry get_reanchor_telemetry) | provenance_generator.py reanchor argmax leg ~1583-1617 + run_honest_sweep_r3 telemetry snapshot |
| span-resolver | PG_SPAN_RESOLVER (via reanchor) | reuse `reanchored_argmax:` (provenance_generator.py:1614) as positive | — | INVERTED: `reanchored_local_window:` must be ABSENT (loophole stayed shut) | provenance_generator.py:1614 / :2892 |
| cross-source-body | PG_CROSS_SOURCE_BODY | `[activation] cross_source_body: plan_driven pairs=<N>` | `input_threaded=<bool>` (equiv_clusters+agree_map threaded) `degraded=<bool>` | anchor-equality path marker / degraded=true | cross_source_synthesis.py _plan_driven_candidate_pairs ~679; distinct anchor marker in _anchor_candidate_pairs ~722 |
| numeric-comparator | PG_NUMERIC_COMPARATOR | `[activation] numeric_comparator: upgraded=<N>` | `build_ok=<bool>` (lookup build did not swallow) | build_ok=false (silent swallow multi_section_generator.py:5180 → make fail-loud) | cross_source_synthesis.py ~650-661 comp set |
| two-sided-debate | PG_TWO_SIDED_DEBATE | `[activation] two_sided_debate: leg2_inspected=<N> con_disclosed=<N>` | — | leg2 skipped route trace | multi_section_generator.py ~4885/:5308 |
| min-cite-set | PG_MIN_CITE_SET | `[activation] min_cite_set: minimized=<N> demoted_to_weight=<N>` | `build_ok=<bool>` | — (keep-all: demoted → weight channel, none dropped) | citation_set_minimizer.py ~81 / run_honest_sweep_r3.py:3583-3604 |
| expert-facet-planner | PG_EXPERT_FACET_PLANNER | `[activation] expert_facet_planner: facets=<N>` | — | — (already safe; marker is the only gap) | expert_facet_planner.py ~56 / fs_researcher_query_gen.py:493 |
| sub-entity-expansion | PG_SUBENTITY_QUERY_EXPANSION | `[activation] subentity_query_expansion: expanded_queries=<N>` | — | — | sub_entity_query_expander.py ~62 / fs_researcher_query_gen.py:382 |

Rule: markers are STRUCTURAL presence/boolean, NEVER a count THRESHOLD (§-1.3). A count of 0 with the flag ON on an eligible input = the canary's eligible-yet-zero contradiction (like Wave-1d), not a "must be >= K" target.

## 3a-synthprimary — the routing DESIGN decision (R2, faithfulness-critical)
PROBLEM: gate-B force-ON + preflight-REQUIRED PG_VERIFIED_COMPOSE_MULTICITED (run_gate_b.py:1282/:1629) → verified_compose.py:2320 routes every ≥2-source basket to compose_basket_multicited_sentence, which never enters _compose_one_basket_synth_primary. So corroborated baskets (the §-1.3 core body) bypass synth-primary.
DECISION (pre-committed, preferred): **route corroborated (≥2-source) baskets THROUGH synth-primary** when PG_SYNTH_PRIMARY is ON — i.e. synth-primary's group writer composes the corroborated basket, and the stricter per-sentence writer verify wrapper `_verify_all_sentences_synth` (verified_compose.py:1357-1384; SAME verify_fn, own-region gate, chrome screen) runs unchanged. Preserve all-corroborator multi-citation surfacing (every corroborating source cited — §-1.3 consolidate-keep-all). NON-NEGOTIABLE: strict_verify / provenance / span grounding byte-untouched; multi-citation of every corroborator preserved. This is its own dual-gated diff; if the preferred route proves infeasible, fall back to documenting synth-primary as single-source-only + reconcile the canary (do NOT silently ship corroborated baskets on the old path).

## 3a-wire — the QUAD activation (run_gate_b.py only)
Add EACH of these to ALL FOUR: `_FULL_CAPABILITY_BENCHMARK_SLATE` (value "1") + `_BENCHMARK_FORCE_ON_FLAGS` + `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` + `_WINNER_FLAG_ALLOWLIST` (allowlist MANDATORY — slate-purity RuntimeError run_gate_b.py:3999 on any un-allowlisted ON-token):
- 7 dark capability flags: PG_CROSS_SOURCE_BODY, PG_NUMERIC_COMPARATOR, PG_PROVENANCE_REANCHOR, PG_SYNTH_PRIMARY, PG_FINDING_DEDUP_NLI, PG_MIN_CITE_SET, PG_TWO_SIDED_DEBATE.
- detector: PG_SHALLOW_REPORT_CANARY (full quad — was slate-only proposal; make it force+preflight+allowlist).
- promote: PG_SUBENTITY_QUERY_EXPANSION setdefault(:3092) → slate+force-on+preflight+allowlist (conscious LAW VI policy flip, coverage-lever precedent :1995-1998; note in diff).
- dependency flags force-on (else parent silently no-ops): PG_CORROBORATION_LAYER2_CITE, PG_CITATION_TWO_LAYER_POLICY (min-cite deps), PG_FINDING_DEDUP_QUALITATIVE, PG_CONSOLIDATION_NLI_QUALITATIVE (finding-dedup-nli deps) — slate+force-on+preflight+allowlist.
- the new PG_ACTIVATION_CANARY (from 3a-canary) → full quad so validation runs with the canary armed.
ALSO in 3a-wire: fix dead assertion literal run_gate_b.py:2429 `'anchored'` → `'candidate'` (match cross_source_synthesis.py:759 emitted text) so the silent-noop assertion can fire.
Byte-identical when the slate is not applied (unit tests / non-benchmark).

## 3a-canary — the fail-loud ACTIVATION canary (run_gate_b.py post-run block ~5288-5347)
Default-OFF opt-in `PG_ACTIVATION_CANARY` (OFF byte-identical, mirror the Wave-1d shallow-canary OFF-purity contract EXACTLY: guarded record key, missing/unreadable log → skip:no-run-log not ok). On a RELEASED non-smoke run, parse the run_log for each `[activation] <module>:` marker and assert, per activated module: POSITIVE marker PRESENT AND not-degraded booleans true AND the OLD/degrade marker ABSENT. Marker-absent OR degraded=true OR old-marker-present → overall_rc=1 (fail loud). Span-resolver: assert `reanchored_argmax:` present-or-conditionally-absent AND `reanchored_local_window:` ABSENT (inverted). STRUCTURAL, never a count threshold (§-1.3). Reuse `_CrossSourceMarkerCaptureHandler` (:2516) attach pattern.

## 3a-harden (module files, independent)
2a legacy arm-default `'treatment'` → `'unknown'` (numeric/cross-source legacy key clinical-safety); 2d two-sided-debate P3s; 2b-wiring citation-minimizer CWF-seam P2s. Each behind its existing flag, OFF byte-identical, faithfulness-neutral.

## Commit-order & file-serialization
markers (module files, mostly disjoint) → 3a-synthprimary (verified_compose.py + multi_section_generator.py) → 3a-canary (run_gate_b.py) → 3a-wire (run_gate_b.py, serialized after canary; adds PG_ACTIVATION_CANARY) → 3a-harden. run_gate_b.py diffs (canary, wire) SERIAL. multi_section_generator.py appears in markers + synthprimary + debate → serialize those. Each diff separately dual-gated before commit.
