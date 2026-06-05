# Claude architect audit — I-ready-015 (#1084): table-cell faithfulness gate

Reviewer: Claude (architect). Scope: the END RESULT of the #1084 diff (build commit + the P2 symmetry fixup on `bot/I-ready-015-table-cell-verify`, off `bot/I-ready-013`). Method: §-1.1 line-by-line.

## 1. The gap closed (reproduced)

- Body prose passes §9.1 strict_verify — a sentence whose decimal is absent from its cited span is DROPPED. The LLM-emitted Trial Summary table did NOT get this: `_extract_trial_summary_table` validated only the `[N]` citation marker + dash count, NOT the cell's NUMBER against the source. So a mis-transcribed N / HR / endpoint value could survive with a valid `[N]`. In clinical context a wrong cell number is the lethal-miss class. REPRODUCED: strict_verify's `_decimals` gives `{'52'}` for a "52% reduction" cell and `{'42'}` for the source; today the row survives because only `[N]` is checked.
- The gate now drops any row whose data-cell decimals are not a subset of `_decimals(verified_prose)` (the strict_verified prose = the table's sole fact source).

## 2. Faithfulness invariant

- **Reuses the §9.1 numeric definition.** The gate uses `strict_verify._decimals` (lazy-imported), so the table cell check and the prose sentence check share ONE numeric-token definition — no divergent re-implementation. VERIFIED (source-pin test).
- **Additive, safe direction.** The gate only DROPS rows whose numbers aren't in the verified prose; it can never fabricate a row or keep a worse one. A no-decimal text row is unaffected. There is no path where a legitimately-verified row (all cell decimals in the prose) is dropped. VERIFIED (keep/drop/no-decimal tests).
- **Citation markers are not data — symmetric.** `[N]` markers are stripped (`_CITATION_MARKER_RE.sub`) from BOTH the row (so a cited `[3]` isn't failed for "3") AND the source prose (Codex diff-gate P2 — so a fabricated cell value equal to a citation number like '5'/[5] can't falsely pass). VERIFIED (citation-marker-not-data + fabricated-equal-to-citation tests).

## 3. Safety / honesty

- **Flag-OFF byte-identical.** `PG_SWEEP_TABLE_CELL_VERIFY` default OFF → `_cell_verify=False` → no `_decimals` import, no gate; a 2-arg call (`verified_prose=""`) keeps the gate inert even when the flag is ON (backward-compat for existing callers/tests). The 59 m36/m41 table regression tests pass unchanged. VERIFIED.
- **Hygiene, no false capability.** `src/tools/visual_generator.py` (dead raw-SVG engine, zero production caller) documented as UNWIRED/UI-only so no one reports "POLARIS renders charts" on its basis. Chart RENDERING (matplotlib `data_analyzer`) is honestly deferred to an operator-gated follow-up (#1095) — NOT claimed as done.

## 4. Scope honesty

Per Codex brief ruling: Option B (prose-subset) on the Trial Summary table ONLY this issue. Documented follow-ups (#1095): Option A per-`[N]`-span attribution check (catches a number cited to the wrong source); the Timeline / Per-Trial extractors (separate code paths); the `_decimals` comma-format over-drop (safe direction, shared primitive); chart rendering. HONEST RESIDUAL: the gate is flag-OFF until the full-capability slate turns it ON after this audit; until then the benchmark table cells are unverified (baseline-equivalent to today).

## 5. Verdict

Faithfulness-aligned (closes a real strict_verify bypass in table cells), additive + safe-direction (only drops fabricated/mis-transcribed numbers, never fabricates), flag-OFF byte-identical, symmetric citation-marker handling, reuses the §9.1 `_decimals` primitive. 8 behavioral + 59 table regression green; `verify_lock --consistency` OK.

**Architect verdict: APPROVE.** Residuals (Option A, Timeline/Per-Trial, comma-format, chart rendering) tracked in #1095, non-blocking.
