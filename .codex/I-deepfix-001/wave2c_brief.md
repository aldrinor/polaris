HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

# Wave-2c brief — presentation_tables module (I-deepfix-001 #1344)

## What this is

A NEW, self-contained MODULE `src/polaris_graph/generator/presentation_tables.py`.
It is the `coverage_fix` item 4 of `REAL_PLAN_2026.md`:

> **Structured tables** — `presentation_tables.py` behind `PG_PRESENTATION_TABLES`
> (default OFF): deterministic tables of verbatim verified numbers + [N] cites.

DRB-II grounding: the Presentation dimension directly scores tables. The rubric example
"presented the change in gold prices in table form" is a like-with-like numeric comparison
(same measure, same unit, values across time-points). This module renders exactly that,
deterministically, WITHOUT any LLM/network/IO, from ALREADY-VERIFIED numeric claims.

MODULE ONLY. It is NOT wired into the render path in this build (that is a separate Batch-2
`2c-wiring` step per the build DAG). No caller is edited. No commit.

## Scope of THIS build (per the Batch-1 `2c-module` node)

- Add `src/polaris_graph/generator/presentation_tables.py`.
- Add `tests/polaris_graph/generator/test_presentation_tables_wave2c.py`.
- Do NOT touch any existing file. Do NOT commit. Do NOT wire.

## Flag (LAW VI)

`PG_PRESENTATION_TABLES`, default **OFF** (env `os.environ.get("PG_PRESENTATION_TABLES", "0")`).
OFF-values: `{"0","false","off","no",""}`.

The single public entry `render_presentation_tables(...)` is flag-gated: when OFF it returns a
no-op result (`text=""`, `changed=False`) so a future caller that only inserts `result.text`
when `result.changed` is byte-identical to today. The pure building blocks
(`group_comparable_claims`, `render_comparison_table`) are NOT flag-gated so they are directly
unit-testable, but nothing calls them on the OFF path.

## Input contract

A "verified numeric claim" is consumed as either a `VerifiedNumericClaim` dataclass, a plain
`dict`, or a duck-typed object. Fields (with fallbacks to the pipeline's `ExtractedNumericClaim`):

- `entity`  (fallback `subject`)     — row identity: entity OR time-point. REQUIRED non-empty.
- `measure` (fallback `predicate`, `endpoint_phrase`) — what is measured. REQUIRED non-empty.
- `value`   — the numeric value(s). REQUIRED non-empty. Kept as a VERBATIM string; a list/tuple
  is joined with "; " keeping each token verbatim. **Never parsed to float, never rounded,
  never reformatted.**
- `unit`    — optional (e.g. "%", "USD/oz").
- `time_window` (fallback `window`) — optional temporal qualifier; appended to the entity cell
  verbatim when present.
- `citation` (fallback `cite`, `marker`) — the citation marker, e.g. `[3]` or a `[#ev:...]`
  token. Rendered VERBATIM in its own Citation column.

A claim missing entity, measure, or value is skipped (no partial-field row invented).

## Behaviour

1. Coerce inputs -> `VerifiedNumericClaim` (skip incomplete).
2. Group by comparability key = (`measure`.strip().lower(), `unit`.strip().lower()).
   Grouping key uses normalization; the RENDERED measure/unit/value/entity are the verbatim
   original strings (first surface form for the constant measure/unit labels).
3. Keep only groups with **>= 2** claims (`_MIN_COMPARABLE = 2`). A single-claim group is
   dropped — NO single-row filler. If no group qualifies -> empty no-op result.
4. For each qualifying group render one GFM table:
   - Columns: `Entity | Measure | Value | Unit | Citation` (matches plan "columns =
     measure/value/unit/citation" plus the entity/time-point row identity column).
   - Rows = the group's claims, **stable sorted by (entity, measure)** (Python `sorted` is
     stable) -> deterministic, same-input => same table.
   - Value cell = verbatim value string. Citation cell = verbatim marker. Empty unit/citation
     render `—` (disclosed gap).
   - A `TABLE_MARKER` HTML comment + a short faithfulness disclosure note precede the table
     (idempotency + honest provenance).
5. Group ordering is sorted by (measure_lower, unit_lower) so multiple tables emit
   deterministically. Multiple qualifying groups -> multiple tables concatenated.

## Faithfulness — NEUTRAL (the binding invariant)

- Consumes ONLY already-verified claims supplied by the caller. The module performs NO
  verification and NEVER re-verifies — it does not touch strict_verify / NLI / 4-role D8 /
  provenance / span-grounding.
- Introduces NO number that is not present verbatim in a supplied verified claim. Numbers are
  copied byte-for-byte (never recomputed, never rounded). No arithmetic on values.
- Presentation-only: it reads finished verified claims and emits markdown. Same class as the
  existing `summary_table.py` (a presentation of already-verified content, CLAUDE.md §-1.3).

## Tests (`test_presentation_tables_wave2c.py`, offline, no model/network/GPU)

1. **OFF no-op** — `PG_PRESENTATION_TABLES` unset/`"0"`: `render_presentation_tables` returns
   `changed=False`, `text=""` even with >=2 comparable claims.
2. **ON well-formed table** — flag `"1"`, 3 claims sharing measure+unit: result `changed=True`,
   one table, GFM header + separator + 3 data rows, `TABLE_MARKER` present, all verbatim
   numbers present, all citation markers present.
3. **ON <2 comparable => empty** — flag `"1"`, one claim (or two claims with DIFFERENT
   measures so no group reaches 2): `changed=False`, `text=""` (no single-row filler).
4. **Verbatim numbers** — value `"3,200.50"` renders exactly `3,200.50`; the reformatted
   `3200.5` / `3,200.5` / rounded `3,201` do NOT appear. A list value keeps each token verbatim.
5. **Deterministic ordering** — same input twice => identical text; a shuffled distinct-entity
   input => identical text (sort by entity then measure fully determines order).
6. **Citation markers preserved** — `[7]` and `[#ev:...]` markers appear verbatim in output.
7. **Faithfulness-neutral / no invented numbers** — every digit sequence in the rendered table
   also appears in some input claim's value/citation (no number introduced by the module).
8. **Smoke import** — module imports clean with no side effects.

## Files ALSO checked and they're clean

- `src/polaris_graph/generator/summary_table.py` — sibling presentation module; same LAW VI
  kill-switch pattern, `_escape_cell`, TABLE_MARKER idempotency. Different job (source-per-row
  bibliography table); no overlap, no import of it.
- `src/polaris_graph/synthesis/claim_graph.py` — `ExtractedNumericClaim` field names
  (subject/predicate/value/unit/…); my fallbacks match so a future wiring step can feed real
  claims. Not imported (module-only build).
- `tests/polaris_graph/generator/test_synth_primary_wave1a.py` — Wave-1 test conventions
  (SimpleNamespace fixtures, offline, no model). Followed.
- `scripts/run_honest_sweep_r3.py` / `run_gate_b.py` — NOT touched (wiring/slate is Batch-2/3).

## Run

`python -m pytest tests/polaris_graph/generator/test_presentation_tables_wave2c.py -x -q` + smoke import.
