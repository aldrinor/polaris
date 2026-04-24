You are auditing M-33 pass-2 (widened fix for section_max_tokens +
outline_max_tokens ceilings across ALL callers of
`generate_multi_section_report`).

## Scope discipline

Audit ONLY the diff from the last two commits. The pass-1 fix raised
the ceiling in `scripts/run_honest_sweep_r3.py` only. Pass-2 widens
the fix to cover a second caller
(`scripts/run_honest_on_prerebuild_corpus.py`) that the pass-1 audit
flagged but whose audit session was cut off before writing a verdict.

This is PROMPT-FREE CHANGE. No executable code logic is altered. Only
caller-side `outline_max_tokens=` and `section_max_tokens=` parameter
values change (800→2500 and 1200→2400 respectively), plus the M-31
and M-33 test guards are widened from a single-script match to a
directory-walk across all callers.

Do NOT invent probe patterns. Cite actual lines if flagging defects.

## Commits in scope

`git log --oneline -n 2`:

- 23b00c9  PL: M-33 pass-2 — fix second caller + widen test guards
- 59a1496  PL: M-33 section_max_tokens 1200→2400 (script override clobbered default)

## Changes (pass-2 only)

1. `scripts/run_honest_on_prerebuild_corpus.py` (line ~273):
   - `outline_max_tokens=800,` → `outline_max_tokens=2500,`
   - `section_max_tokens=1200,` → `section_max_tokens=2400,`
   - New comment block referencing M-31/M-33 rationale.

2. `tests/polaris_graph/test_m33_section_max_tokens.py`:
   - Replaced `TestSweepSectionMaxTokens::test_sweep_script_uses_adequate_section_max_tokens`
     (single-file regex match) with
     `TestAllCallersSectionMaxTokens::test_all_script_callers_use_adequate_section_max_tokens`
     which walks `scripts/*.py`, filters to files that import
     `generate_multi_section_report`, and enforces `section_max_tokens >= 2400`
     on every such file.

3. `tests/polaris_graph/test_m31_outline_resilience.py`:
   - Same widening: single-file regex match replaced by directory walk
     enforcing `outline_max_tokens >= 2500` on every caller of
     `generate_multi_section_report`.

4. `TestModuleDefaultUnchanged` (M-33) is unchanged — it still uses
   `inspect.signature` to verify the in-module default remains 2400.

## Your task

1. Confirm the pass-2 diff is exactly what this brief describes and
   nothing more. No executable code paths changed; no new state; no
   new helpers.
2. Re-run the authoritative grep:
   `python -m pytest -q tests/polaris_graph/test_m31_outline_resilience.py tests/polaris_graph/test_m32_claim_frame_prompt.py tests/polaris_graph/test_m33_section_max_tokens.py`
   and report pass/fail count.
3. Run this exact PowerShell/Bash equivalent grep to verify no
   remaining low callers exist anywhere in `scripts/`:
   `grep -rn "section_max_tokens\s*=\s*[0-9]\+" scripts/*.py | grep -v ".bak"`
   Any match below 2400 is a blocker. Any match ≥ 2400 is fine.
   Repeat for `outline_max_tokens\s*=\s*[0-9]\+` with threshold 2500.
4. Confirm the widened test guards correctly catch low values (sanity
   check: the tests pass now; construct a mental scenario where a
   dev adds a new script with section_max_tokens=1200 — should fail).
5. Confirm the module default in
   `src/polaris_graph/generator/multi_section_generator.py:885` is
   still `section_max_tokens: int = 2400` (unchanged from pass-1).

## Out of scope

- Whether M-33 will empirically close the V22 narrative-depth gap.
- Per-trial framing quality — that's the V23 sweep's output-side
  concern.
- Pipeline C or orchestration/ — frozen.

## Verdict format

Write `outputs/codex_findings/m33_code_audit/findings_pass2.md`:

```
# M-33 code audit (pass 2)

VERDICT: READY | NOT_READY

## Blockers
- <list or none>

## Mediums
- <list or none>

## Lows / nits
- <list or none>

## Notes
<any other observations, plus pytest pass count>
```

If READY, V23 sweep launches.
