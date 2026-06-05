# Codex BRIEF review — I-ready-015 (#1084): table-cell faithfulness gate (+ chart hygiene)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**REVIEW ONLY — do not modify any file. Decide the reference-source question in §3 and judge the acceptance criteria; return the YAML verdict block ONLY. Claude authors the diff after APPROVE.**

---

## 0. What this is

Brief gate for I-ready-015 (#1084), F14 P2 — the LAST of the 15 readiness issues. Branch `bot/I-ready-015-table-cell-verify` off `bot/I-ready-013`. Full finding: `.codex/I-ready-000/findings/chart_table_artifact.md`.

## 1. The gap (reproduced offline)

The benchmark `report.md` embeds LLM-generated markdown tables (Trial Summary / Timeline / Per-Trial). `_extract_trial_summary_table` (`multi_section_generator.py:2035-2134`) validates ONLY (a) the canonical header, (b) that each row's `[N]` citation marker is in `valid_citation_nums`, and (c) the dash-count. It does NOT verify the cell's NUMBER against the cited source — unlike body prose, where §9.1 strict_verify drops any sentence whose decimals are absent from the cited span. So at full cap the LLM can mis-transcribe an N / HR / endpoint value into a table cell, cite a valid `[N]`, and the row survives. In clinical context a wrong dose/HR/CI in a table cell is exactly the lethal-miss class.

**Reproduced:** strict_verify's `_decimals` gives `{'52'}` for a cell "52% reduction" and `{'42'}` for the cited span "...reduced the score by 42 percent..."; `{'52'}.issubset({'42'})` is False → the row SHOULD drop, but today only the `[N]` marker is checked so it survives. (`_decimals` + the `issubset` numeric-match are the exact primitives §9.1 strict_verify uses at `clinical_generator/strict_verify.py:107,260-265`.)

## 2. Proposed scope

**PRIMARY (the faithfulness fix):** add a cell-decimal verification step to `_extract_trial_summary_table` (and the Timeline / Per-Trial extractors that derive from the same verified prose): for each candidate row, every decimal in the row's cells must appear in the reference text (see §3); else DROP the row (same disposition as an out-of-range citation). Reuse `strict_verify._decimals`. Flag-gated `PG_SWEEP_TABLE_CELL_VERIFY` **default OFF** → byte-identical when off (consistent with the other 14 readiness issues; turned ON + preflighted in the full-cap slate after this audit passes).

**HYGIENE:** `src/tools/visual_generator.py` (raw-SVG engine) has ZERO production caller (finding-confirmed) — add a module docstring marking it UI-only/unwired to kill the false-capability trap. (Or delete it — your call; my lean is document, not delete, to avoid touching an unrelated surface.)

**DEFER (out of scope, → follow-up issue):** wiring matplotlib `data_analyzer.analyze_structured_data` into the sweep to render bar/forest figures. It needs a PAID LLM script-gen hop + a matplotlib subprocess (§8.4) and is advisory demo-polish — defer to an operator-gated follow-up. Tonight is cash-free + offline only.

## 3. DECISION (route to you): the cell-decimal REFERENCE source

- **Option B (my lean) — verified-prose subset.** `_call_trial_summary_table` already receives `verified_prose` (the strict_verified text the LLM was instructed to use as the SOLE fact source). Check each cell's decimals ⊆ `_decimals(verified_prose)`. Since the prose is already strict_verified (every decimal in it is span-backed), a cell decimal ∈ prose is transitively span-backed; a cell decimal ∉ prose is a fabrication/mis-transcription → drop. Simple, threads nothing new, robustly correct for the dominant failure (numbers not in the source at all).
- **Option A — per-`[N]` span.** Map each row's cited `[N]` → its evidence `direct_quote` span and require the cell decimals ⊆ the union of THOSE spans. More precise (also catches mis-ATTRIBUTION: a number that is in the prose but cited to the wrong `[N]`), but needs the evidence-span text threaded into the extractor (bibliography entries carry `evidence_id`+`num`; the span `direct_quote` lives on the evidence rows).

**Question:** is Option B sufficient for this P2 (with Option A's per-citation precision as a documented follow-up), or do you want Option A now? My lean: B now (high-value, low-risk, reuses verified_prose + `_decimals`); note A as a follow-up.

## 4. Acceptance criteria (GREEN)

1. **Hole closes:** a Trial Summary row whose cell decimal is absent from the reference (per §3 ruling) is DROPPED; a row whose decimals are all present is KEPT. Behavioral test on `_extract_trial_summary_table`.
2. **Flag-OFF byte-identical:** `PG_SWEEP_TABLE_CELL_VERIFY` unset → extractor behavior identical to today (existing table tests unchanged).
3. **No over-drop:** a row with NO decimals (pure text cells) is unaffected by the numeric gate (kept if it passes the existing citation/dash checks).
4. **Reuses strict_verify:** the decimal extraction is `strict_verify._decimals` (not a re-implemented regex), so the table gate and the prose gate share one numeric definition.
5. **Applies to Timeline / Per-Trial** extractors too (they derive from the same verified prose), OR scoped to Trial Summary with the others documented as follow-up — your call.
6. **Hygiene:** `visual_generator.py` documented as UI-only/unwired.
7. Faithfulness machinery otherwise untouched; offline smoke green; no chart-render code added (deferred).

## 5. Files I have ALSO checked and they're clean (adjacent-file scan)

- `multi_section_generator.py:2035-2134` `_extract_trial_summary_table` (the edit site; currently citation+dash only), `:2543-2616` `_call_trial_summary_table` (has `verified_prose` + `bibliography`), the Timeline/Per-Trial extractors nearby.
- `clinical_generator/strict_verify.py:107` `_decimals`, `:260-265` the `issubset` numeric-match — the primitive I reuse (unchanged).
- `run_honest_sweep_r3.py:3802-3822` — where the Trial Summary table / Timeline / Per-Trial blocks are appended to `sections_concat` → `report.md` (consumer; unchanged — the gate runs inside the extractor before the text is returned).
- `src/polaris_graph/tools/data_analyzer.py` (matplotlib, graph_v3/UI-only, `PG_CHART_GENERATION_ENABLED`) + `src/tools/visual_generator.py` (dead SVG) — chart subsystems; NOT wired into the sweep (deferred/hygiene).

## 6. Smoke plan (offline, cash-free)

`tests/polaris_graph/test_table_cell_verify_iready015.py`: (a) flag-ON: a row with a cell decimal absent from the reference is dropped; (b) flag-ON: a row whose decimals are all in the reference is kept; (c) flag-OFF: both rows kept (byte-identical); (d) a no-decimal text row is unaffected; (e) the decimal set is exactly `strict_verify._decimals`. Construct the raw table text + reference inline (no LLM, no spend).

## 7. Output schema (return EXACTLY this; loose prose rejected)

```yaml
verdict: APPROVE | REQUEST_CHANGES
reference_source: option_b_verified_prose | option_a_per_citation_span | other
apply_to_timeline_pertrial: yes | trial_summary_only_followup
flag_default_off_correct: yes | no
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
