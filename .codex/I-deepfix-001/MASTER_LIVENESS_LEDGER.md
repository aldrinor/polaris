# MASTER LIVENESS LEDGER — the anti-dark gate for the paid VM run (I-deepfix-001 #1344)

**Operator fear this document kills (2026-07-07):** "you complete 8 waves, run on the VM, FORGET to monitor
that all 8 fired, let it run dark, then say 'we fucked up again' and rebuild — wasting another night."

**HARD RULE:** the paid VM run is NOT "success" and I do NOT declare any benchmark result until EVERY row
below shows FIRED with a real realized-effect count in the ACTUAL run log. No exceptions. No "assume it fired."

## Three structural protections (do not depend on me remembering)

1. **Fail-loud activation canary — ARMED.** `PG_ACTIVATION_CANARY="1"` + `PG_LOG_LEVEL="INFO"` are on the
   official slate. `assert_activation_markers_fired()` (run_gate_b.py) raises `RuntimeError` (overall_rc=1)
   if any ON flag's `[activation]` marker is ABSENT, its honesty booleans unhealthy, or a degrade/fail-open
   marker present. So a DARK flag CRASHES the run — it cannot silently ship a bad report.
2. **Preflight PROVEN table BEFORE spend.** A small real run fills the `preflight FIRED?` column below. I do
   NOT launch the big paid run until every row is FIRED. (Offline unit tests are NOT preflight.)
3. **Live monitor during the run.** Arm a Monitor on the run log for the expected `[activation]` markers +
   the canary result, so a missing/failed marker wakes me instantly — not dependent on 5-min polling memory.

## The ledger — every wave flag (fill FIRED counts from the REAL run log, never assume)

| Wave | Flag | Expected [activation] marker | canary spec | preflight FIRED? | RUN FIRED? |
|---|---|---|---|---|---|
| 1 | PG_WORKFORCE_T3_TARGETING | **NO [activation] marker emitted by credibility_llm_tiering.py** | ❌ **NO canary spec** (force-ON, spec=0) — AUTOMATED-CANARY BLIND; relies on manual ledger read only | ⬜ | ⬜ |
| 1 | PG_DEBATE_CON_BASKET_CONSOLIDATION | **NO [activation] marker emitted by debate_consolidation.py** | ❌ **NO canary spec** — AUTOMATED-CANARY BLIND | ⬜ | ⬜ |
| 1 | PG_A1_BASKET_FALLBACK | **NO [activation] marker emitted by contract_section_runner.py** | ❌ **NO canary spec** — AUTOMATED-CANARY BLIND | ⬜ | ⬜ |
| 1 | PG_RENDER_CHROME_SCREEN | **NO [activation] marker emitted by key_findings.py** (only FF3's) | ❌ **NO canary spec** — AUTOMATED-CANARY BLIND | ⬜ | ⬜ |
| 1 | PG_DEPTH_DECHROME_MEMBERS | **NO [activation] marker emitted by depth_synthesis.py** | ❌ **NO canary spec** — AUTOMATED-CANARY BLIND | ⬜ | ⬜ |
| 2 | PG_POST_FETCH_ENRICH_PARALLEL | live_retriever fire-log (~5990), NOT a canary [activation] marker | ❌ **NO canary spec** — AUTOMATED-CANARY BLIND | ⬜ | ⬜ |
| 2 | PG_WALL_CLASSIFY_RESCUE | `[activation] wall_classify_rescue: armed enrich_parallel=` (marker EXISTS) | ❌ **NO canary spec registered** (marker present but not in _ACTIVATION_MARKER_SPECS) | ⬜ | ⬜ |

> **CRITICAL ANTI-DARK GAP found 2026-07-07 (Wave-9 target):** the 7 Wave-1/2 flags above are all quad-pinned FORCE-ON
> (slate_refs=4) but have ZERO registered `_ActivationMarkerSpec` (spec=0). So `assert_activation_markers_fired` does NOT
> cover them — a DARK Wave-1/2 flag on the paid VM run would NOT crash the run (overall_rc stays 0); only a MANUAL ledger
> read of the run log catches it. Rule #2's automated structural guarantee is INCOMPLETE for waves 1-2. Wave-9 =
> instrument each with a realized-effect `[activation]` marker (add to the 5 marker-less modules; wall_classify already has
> one) + register a fail-loud spec, mirroring the Wave-6b/6c/7 pattern. Waves 3-4 (below) DO have specs — those are covered.
| 3 | PG_QGEN_PARALLEL_QUERIES | `[activation] qgen_parallel_fanout: ... issued=` (numeric>=2) | wave3 | ⬜ | ⬜ |
| 3 | PG_OPENALEX_DATE_FILTER | `[activation] openalex_date_filter:` | wave3 | ⬜ | ⬜ |
| 3 | PG_LANDMARK_EXPANDER | `[activation] landmark_study_expansion: expanded_queries=` (ran-ok; NOT unavailable_failopen) | wave3 | ⬜ | ⬜ |
| 4 | PG_OPENALEX_MATCH_VALIDATE | `[activation] openalex_match_validate: checked= rejected=` | yes | ⬜ | ⬜ |
| 4 | PG_RESOLVE_PUBDATE_FROM_HTML | `[activation] pubdate_html_resolve: resolved= unresolved=` | yes | ⬜ | ⬜ |
| 5 | ~~FF2-TRUNC-v2~~ RETIRED (e55637b3) | — (unsound lexical leg removed; no marker, not on slate) | n/a | ➖ | ➖ |
| 5 | FF3-TRUNC-SEM (PG_FF3_TRUNC_SEM) | `[activation] ff3_trunc_sem: reached=(True\|False) screened= detected= repaired= dropped=` (degrade: `unavailable_failopen`) | yes | ⬜ | ⬜ |
| 6 | PG_RENDER_SUMMARY_TABLE (Wave-6a vocab + Wave-6b canary) | `[activation] summary_table: reached=(True\|False) rows= cols=` (degrade: `unavailable_failopen`) | **DONE (1f3d2ced)** — fail-loud _ActivationMarkerSpec added with flag_default_on=True (matches default-ON producer); dark render crashes (overall_rc=1), honest rows=0 passes, NO count>0 gate | ⬜ | ⬜ |
| 6c | PG_STANCE_DIVERSIFY_SEEDS (a09fe434) | `[activation] stance_diversify_seeds: issued=` (realized post-budget count; degrade: `unavailable_failopen`) | DONE — quad-pinned (slate 1716 / preflight 2045 / force-on 2339 / allowlist 3749) + fail-loud spec 3305-3323; additive fail-open, default-OFF byte-identical, marker realized-count | ⬜ | ⬜ |
| 7 | PG_CROSS_SECTION_REPETITION_GUARD (f9173615) | `[activation] cross_section_repetition_guard: consolidated=` (realized count; degrade: `unavailable_failopen`) | DONE — activated built-but-dark module (committed + wired caller multi_section_generator.py:10251 after engine, before remap); quad-pinned + fail-loud spec (WAVE3 tuple); render-only consolidate-not-drop, fail-conservative, default-OFF byte-identical | ⬜ | ⬜ |
| 6 | (table + 14-study coverage flag[s]) | TBD@build | TBD | ⬜ | ⬜ |
| 7 | PG_CONTENT_SHELL_REFETCH | `[activation] content_shell_refetch:` | TBD@build | ⬜ | ⬜ |
| 7 | PG_CROSS_SOURCE_THREAD_CONSOLIDATION | `[activation] cross_source_body:` | check | ⬜ | ⬜ |
| 7 | PG_CROSS_SECTION_REPETITION_GUARD | cross-section repetition-guard marker | TBD@build | ⬜ | ⬜ |

(Update the exact marker strings + canary-spec column as each wave commits; add Wave-6 rows at build.
Every row's RUN FIRED? must be a real count read from the run log before declaring the run good.)

## Run-day procedure (bound to this ledger)
1. Deploy committed HEAD to the VM. Confirm the slate sets PG_ACTIVATION_CANARY=1 + PG_LOG_LEVEL=INFO.
2. Small preflight run → grep the log for each row's marker → fill `preflight FIRED?`. ANY dark row → fix
   BEFORE the paid run (do not spend). Rebuild that flag's wiring, re-preflight.
3. Only when ALL preflight rows FIRED → launch the paid drb_72 run. Arm a Monitor on the run log markers.
4. During the run: forensic 5-min line-by-line read; the canary fail-louds on any dark flag.
5. After the run: fill `RUN FIRED?` from the log for every row. If the canary raised OR any row is dark →
   the run is NOT a success; do NOT score-as-final; fix + resume-from-closest-checkpoint. Only an all-FIRED,
   canary-green run gets scored + benchmarked vs GPT/Gemini.
