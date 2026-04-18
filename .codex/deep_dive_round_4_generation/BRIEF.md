# Deep-dive R4 — Generation outline collapse (BUG-M-203)

**Target**: M-203. `_parse_outline()` in
`src/polaris_graph/generator/multi_section_generator.py` doesn't
enforce the prompt's 3-5 section count or non-overlapping evidence
assignment. On empty/invalid planner output, silently falls back to
a single generic "Efficacy" section with no abort signal.

## Mandate

Produce the fix SPEC.

1. Read `multi_section_generator.py:_parse_outline` and
   `_call_outline` + the fallback path.
2. Enumerate every way planner output can fail today
   (empty, malformed JSON, zero valid sections after filtering,
   <3 sections, overlapping ev_ids, etc.).
3. Choose: (a) retry with tighter prompt, then abort if still bad;
   or (b) abort immediately; or (c) fallback BUT emit a new
   manifest status `partial_outline_fallback` so the UI/downstream
   can see it.
4. Specify the fix + 4-6 tests.

## Output

Write to `outputs/codex_findings/deep_dive_round_4/findings.md`
with the same frontmatter pattern as R1-R3.

## Anti-circle-jerk

If you find the fallback actually HELPS in practice (e.g., 50% of
real runs trip it and the resulting single-section report is still
useful), say so with evidence. Don't default to "abort everything".

## Context

- `outputs/codex_findings/full_audit_pass_1/findings.md` §4
- `outputs/honest_sweep_r6_validation/clinical/clinical_afib_anticoagulation/manifest.json`
  shows `outline_sections: ["Efficacy"]` — the fallback firing in
  production
- Code: `src/polaris_graph/generator/multi_section_generator.py`
- Prior rounds: R1 manifest (`c764ddb`), R2 B-102 scoped,
  R3 scope gate (`95a9709`). Unified taxonomy already has
  `partial_*` class; adding a new one is cheap.

## Expected duration

5-10 minutes.
