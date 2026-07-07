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
| 1 | PG_WORKFORCE_T3_TARGETING | workforce/statistical-agency T3 marker | check | ⬜ | ⬜ |
| 1 | PG_DEBATE_CON_BASKET_CONSOLIDATION | debate con-basket consolidation marker | check | ⬜ | ⬜ |
| 1 | PG_A1_BASKET_FALLBACK | A1 basket-fallback marker | check | ⬜ | ⬜ |
| 1 | PG_RENDER_CHROME_SCREEN | render chrome-screen marker | check | ⬜ | ⬜ |
| 1 | PG_DEPTH_DECHROME_MEMBERS | depth de-chrome members marker | check | ⬜ | ⬜ |
| 2 | PG_POST_FETCH_ENRICH_PARALLEL | `[activation] PG_POST_FETCH_ENRICH_PARALLEL ON — pre-batched` | check | ⬜ | ⬜ |
| 2 | PG_WALL_CLASSIFY_RESCUE | wall-classify rescue marker | check | ⬜ | ⬜ |
| 3 | PG_QGEN_PARALLEL_QUERIES | `[activation] qgen_parallel_fanout: ... issued=` (numeric>=2) | wave3 | ⬜ | ⬜ |
| 3 | PG_OPENALEX_DATE_FILTER | `[activation] openalex_date_filter:` | wave3 | ⬜ | ⬜ |
| 3 | PG_LANDMARK_EXPANDER | `[activation] landmark_study_expansion: expanded_queries=` (ran-ok; NOT unavailable_failopen) | wave3 | ⬜ | ⬜ |
| 4 | PG_OPENALEX_MATCH_VALIDATE | `[activation] openalex_match_validate: checked= rejected=` | yes | ⬜ | ⬜ |
| 4 | PG_RESOLVE_PUBDATE_FROM_HTML | `[activation] pubdate_html_resolve: resolved= unresolved=` | yes | ⬜ | ⬜ |
| 5 | ~~FF2-TRUNC-v2~~ RETIRED (e55637b3) | — (unsound lexical leg removed; no marker, not on slate) | n/a | ➖ | ➖ |
| 5 | FF3-TRUNC-SEM (PG_FF3_TRUNC_SEM) | `[activation] ff3_trunc_sem: reached=(True\|False) screened= detected= repaired= dropped=` (degrade: `unavailable_failopen`) | yes | ⬜ | ⬜ |
| 6 | PG_RENDER_SUMMARY_TABLE (already-wired; Wave-6a vocab) | `[summary-table] rows= cols= geo_filled= domain_filled= risk_filled=` (logged INFO, run_honest_sweep_r3.py:16698) | **NEEDS fail-loud spec (Wave-6b)** — currently NOT in assert_activation_markers_fired; add spec so dark table crashes, honest rows=0 passes | ⬜ | ⬜ |
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
