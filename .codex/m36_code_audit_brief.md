You are auditing M-36 (Trial Summary markdown table synthesis) as
a code review BEFORE the next full-scale sweep runs. Narrow scope.

## Scope discipline

Audit ONLY the M-36 diff. New post-synthesis stage in
`multi_section_generator.py`; +8 lines in the sweep script; new
test file. Nothing else is modified.

Do NOT invent adversarial probes. If you find a real defect, cite
the exact file + line and map to real-world LLM output behavior.

## Context

### V23 problem (Codex DR pass-11 gap #4)

> Add at least one trial summary table and one benefit-risk or
> NNT/NNH table, plus subsections for evidence architecture,
> safety, prescribing, limitations, and ongoing evidence.

V23 report was prose-only. Both ChatGPT DR and Gemini DR have
trial-comparison tables that compress trial × endpoints × results
into skim-able form. V23 loses Structural depth LOSE_BOTH largely
on this dimension.

M-36 addresses the trial-summary half of gap #4 only. The
benefit-risk / NNT table is M-36b (separate, post-approval).

### The fix

New async function `_call_trial_summary_table` in
`src/polaris_graph/generator/multi_section_generator.py`. One LLM
call over VERIFIED PROSE + global bibliography, emits a markdown
table. Deterministic parser / validator
`_extract_trial_summary_table` drops rows with out-of-range
citation numbers and collapses to empty string when nothing valid
remains (no stub table ever emitted).

Critical design property: the input prose is already
strict_verified. No per-cell provenance is required because:
1. The LLM is told to use ONLY facts present in the prose.
2. Citation numbers are validated against the bibliography.
3. A row with any out-of-range [N] is dropped wholesale.
4. A row without any [N] is dropped wholesale.

### Smoke test I already ran (live DeepSeek V3.2-exp on V23 prose)

- Prose: 1920 words from V23's verified sections
- Bibliography: 31 entries (V23's actual)
- LLM input: 3960 tokens, output: 196 tokens
- Result: 4-row table (SURPASS-2, SURPASS-3, SURPASS-AP-Combo,
  SURMOUNT-4), all with in-range [N] citations, proper "—"
  abstention on unknown values.

## Files to read

```
src/polaris_graph/generator/multi_section_generator.py
  - new constants _TRIAL_SUMMARY_TABLE_HEADER_RE,
    _MARKDOWN_TABLE_SEPARATOR_RE, _CITATION_MARKER_RE
  - new TRIAL_SUMMARY_TABLE_SYSTEM_PROMPT
  - new _extract_trial_summary_table(raw, valid_citation_nums)
  - new _call_trial_summary_table(...)
  - MultiSectionResult: +3 new fields
  - generate_multi_section_report: +2 new kwargs,
    new stage between limitations and return
tests/polaris_graph/test_m36_trial_summary_table.py (NEW, ~440 LOC, 28 tests)
scripts/run_honest_sweep_r3.py (lines ~1013-1020, table insert in assembly)
```

Do NOT read:
- archive/, outputs/ (except smoke-test output outputs/_m36_smoke.txt if desired)
- competitor PDFs, loopback/
- pre-existing failing-imports test files (test_m25_*.py / test_m28_*.py / test_m29_*.py — known orthogonal issue, not caused by M-36)

## What to verify

1. **No fabrication surface**. Does the parser genuinely refuse
   to emit rows with invalid [N] citations? Does any code path
   bypass the validator (e.g. emit the LLM response directly)?

2. **Parser robustness**. Is the header regex tight enough that
   it won't falsely match a non-trial-summary table (e.g. a
   hypothetical outline table the LLM might try to embed)?
   Does the separator check reject cell-aligned separators like
   `| :--- |` with colons? Do fence-stripping rules handle
   edge cases (backticks in row data, partial fences)?

3. **Orchestrator preconditions**. `_call_trial_summary_table`
   short-circuits on empty prose, empty bibliography, or
   bibliography without any `num` field. Are there other
   preconditions that should be added (e.g. prose with no [N]
   markers at all — not worth calling LLM)?

4. **Schema compatibility**. `MultiSectionResult` gained three
   fields with defaults. Are any downstream consumers (the
   sweep script's manifest assembly, evaluator_gate, external
   evaluator, etc.) broken by the schema change? Each field has
   a default so positional instantiation should still work.

5. **Token/cost bounds**. `max_tokens=800` default. Prose can
   be 10K+ chars; prompt serialization is quadratic in prose
   length. Is there a ceiling on how much prose is sent? The
   smoke test used 1920 words = ~12KB → 3960 tokens. Larger
   reports could push 8K+ input tokens. Is that an issue?

6. **Sweep assembly**. `scripts/run_honest_sweep_r3.py:1013-1020`
   inserts `### Trial Summary\n\n{table}` between section
   bodies and Limitations. Does this interact with the
   evaluator's PT01..PT13 checks (section ordering, Methods
   placement, etc.)? The existing Limitations insertion uses
   the same pattern, so the precedent says "no conflict", but
   confirm.

7. **Citation range validation**. Valid-num set is built from
   `{int(e.get("num")) for e in bibliography if isinstance(e.get("num"), int)}`.
   What if `num` is a string (YAML / JSON edge case)?
   Currently treated as missing → dropped from valid set.
   Intentional, or should it coerce? (I think current strict
   behavior is right — bibliography "num" should always be int;
   if it's not, that's an upstream bug.)

8. **Preamble / trailing-prose handling**. The parser skips
   leading empty lines after the header match (bug fix during
   development — `\s*` regex consumed preceding `\n`). Any
   other position where the regex leading-anchor could shift
   the slice start by a byte?

## What counts as a blocker vs medium

- **BLOCKER**: any path that emits a table row with a cited
  number not in the bibliography; any path that emits the raw
  LLM response bypassing the validator; any path that crashes
  the sweep when the new stage runs; any schema incompat that
  breaks existing manifest serialization.
- **MEDIUM**: tighten regex, add precondition, smoke-test
  edge cases, documentation.
- **LOW**: style / comments.

## Deliverable

Write `outputs/codex_findings/m36_code_audit/findings.md` with:
- Final verdict (READY | BLOCKED | CONDITIONAL)
- Blockers (zero if READY)
- Mediums (non-gating)
- One-sentence note on whether the "no per-cell provenance"
  property holds (input-prose-is-already-verified principle).
