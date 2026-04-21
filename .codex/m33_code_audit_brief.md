You are auditing M-33 (raise `section_max_tokens` 1200→2400 in the
sweep caller) as a code review BEFORE V23 sweep runs. Narrow scope.

## Scope discipline (user mandate, reconfirmed)

Audit ONLY the M-33 diff. This is a ONE-PARAMETER change in
`scripts/run_honest_sweep_r3.py` plus a test guard. No executable
code paths are modified. No new helpers. No new state.

Do NOT invent probe patterns. If you find a real defect, cite the
specific line(s) you believe are defective with the actual changed
text.

## Context

V22 sweep ran after M-32 was shipped (primary-study claim-frame
prompt rule). V22 beat V21 on narrative depth by only +15% (1964
words vs 1706) and still lost LOSE_BOTH against ChatGPT DR (4830w)
and Gemini DR (6054w) on narrative depth. Diagnostic grep of the
V22 per-section output tokens found:

    section_1: 965 tokens
    section_2: 1047 tokens
    section_3: 1200 tokens  ← EXACTLY the cap
    section_4: 980 tokens
    section_5: 1016 tokens
    section_6: 1006 tokens

Section 3 hit exactly `section_max_tokens=1200` — capped
mid-generation. The in-module default for
`generate_multi_section_report` is 2400 (M-24 fix). The sweep caller
was clobbering the default with an override of 1200.

This is the same regression class as M-31 (script override clobbers
upstream default).

## Changes

1. `scripts/run_honest_sweep_r3.py` (~line 967):
   - Changed `section_max_tokens=1200,` to `section_max_tokens=2400,`
   - Added comment block referencing the M-33 rationale, mirroring
     the M-31 comment style on the adjacent `outline_max_tokens`
     line.

2. `tests/polaris_graph/test_m33_section_max_tokens.py`:
   - `TestSweepSectionMaxTokens::test_sweep_script_uses_adequate_section_max_tokens`
     — static guard: regex match any `section_max_tokens=N` in the
     sweep script; assert `int(N) >= 2400`.
   - `TestModuleDefaultUnchanged::test_module_default_is_at_least_2400`
     — uses `inspect.signature` on
     `generate_multi_section_report`; assert the default value for
     `section_max_tokens` is `>= 2400`. Protects against someone
     silently lowering the module default and defeating the guard.

No changes to `multi_section_generator.py`. The module default has
been 2400 since M-24.

## Your task

1. Confirm the diff is in fact only `section_max_tokens=1200` →
   `section_max_tokens=2400` plus a comment block in the sweep
   script. No other executable-code changes in that file.
2. Confirm the module default is already 2400 in
   `multi_section_generator.py` (so the M-33 change makes the
   sweep match, not lower, the upstream ceiling).
3. Confirm the two new tests actually enforce what the fix needs:
   - Test 1 guards against a future edit reintroducing a low
     override in the sweep.
   - Test 2 guards against someone lowering the module default,
     which would silently defeat the sweep-side guard.
4. Confirm no other caller of `generate_multi_section_report`
   in the tree still passes a too-low override. (grep the repo.)
5. Non-regression: the M-31 `outline_max_tokens=2500` line must
   still be present on the adjacent line of the same call.

## Out of scope

- Whether M-33 will empirically close the V22 narrative-depth gap —
  that's the V23 sweep's job, not this audit's.
- Whether Fix A (per-trial sub-sections or trial-matrix selector)
  is also needed — tracked separately as task #5.
- Prompt-engineering style (placement of the comment block).

## Verdict format

Write `outputs/codex_findings/m33_code_audit/findings.md`:

```
# M-33 code audit

VERDICT: READY | NOT_READY

## Blockers
- <list or none>

## Mediums
- <list or none>

## Lows / nits
- <list or none>

## Notes
<any other observations>
```

If READY, V23 sweep launches. If NOT_READY, the blocker MUST cite
the specific line being flagged — no hypothetical regression probes.

## Actual deliverable check

Run `python -m pytest -q tests/polaris_graph/test_m33_section_max_tokens.py`
and confirm both tests pass. Report the pass/fail count in Notes.
