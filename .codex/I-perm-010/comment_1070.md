**Cap raised 150 → 1500 (operator decision 2026-06-10), AND an honest correction to this issue's framing.**

`PG_LIVE_MAX_EV_TO_GEN` is now **1500** (the full extracted set) in the Gate-B slate, preflight floor
locked at 1500 so it cannot silently regress; the three slate test fixtures were updated to the new
value (not relaxed). Rationale: this is the GLOBAL POOL the sections draw from, not a per-prompt size.
Each section independently selects only `PG_MAX_EV_PER_SECTION` rows, and the generator is a
1M-context model — so a global pool cap had no provider justification and only starved niche sections.

**Correction this issue needs:** the saved drb_76 run shows the cap was NOT the dominant source loss
in practice. `manifest.json`: ~800 discovered, ~500 fetched, but only **46 evidence rows** reached the
generator, with `evidence_selection.dropped_count=0` — the 150 cap never even engaged (46 < 150). The
real ~90% collapse is UPSTREAM at fetch→extract→merge. So this cap fix is necessary but NOT sufficient;
the dominant loss is owned by the extraction stage (#1201) and is now tracked under the funnel-first
plan **#1204**. Leaving OPEN until the funnel trace + live §-1.1 audit confirm sources actually flow.
