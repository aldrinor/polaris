# Codex Diff Review — I-bug-097 (unknown-mode warning)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- DO NOT call exec / rg / shell tools. Brief is self-contained.
```

## Pre-flight

- Brief APPROVE'd iter 1 (`.codex/I-bug-097/codex_brief_verdict.txt`).
- Diff: `.codex/I-bug-097/codex_diff.patch` (canonical-diff-sha256: `abd3a438aecd0c836c016db9c75568f3b1d86236af440e56817e8eec9070ab17`)
- src/ delta: 23 net lines (`strict_verify.py` _entailment_mode + module-level set + dedup logic)
- New test file: 119 LOC, 9 tests covering 6 distinct scenarios + parametrized known-modes

## Implementation summary

Added module-level `_UNKNOWN_MODE_WARNED: set[str] = set()` and updated `_entailment_mode()`:
- Empty / unset env → `"off"` silently (no spam at module-import or per-sentence call)
- Recognized off/warn/enforce → return as-is (no warning)
- Unrecognized non-empty value → log WARNING **once per process per typo string**, fall back to `"off"`

Per Codex iter-1 brief verdict: dedup approach = process_set; LOC OK; test surface complete.

## Tests pinned

| Test | Behavior |
|---|---|
| `test_unknown_mode_emits_warning_once_per_process` | 3 calls with same typo → exactly 1 WARNING |
| `test_unknown_mode_warning_includes_value` | WARNING message contains the typo string verbatim |
| `test_unknown_mode_different_typos_each_warn_once` | 2 distinct typos → 2 distinct warnings (each emits once) |
| `test_known_modes_emit_no_warning` (parametrized 3x off/warn/enforce) | Known modes silent |
| `test_empty_env_emits_no_warning` | Empty env = default off, silent |
| `test_unset_env_emits_no_warning` | Unset env = default off, silent |
| `test_uppercase_recognized_via_lowercase_normalization` | `ENFORCE` normalized to `enforce`, no warning |

70 tests passing across the relevant test files (9 new I-bug-097 + 27 I-bug-092 entailment + 25 baseline strict_verify + 9 cj-008).

## Auto-reset fixture

`@pytest.fixture(autouse=True) _reset_warned_set` clears `_UNKNOWN_MODE_WARNED` between tests so dedup state doesn't leak across the suite. Test isolation explicit.

## Codex iter-1 advisories addressed

1. **Concurrent first calls could emit duplicate warnings without lock**: low-severity per Codex; not addressing in this PR (would require threading.Lock import + ~5 LOC; the typical operator workflow is single-threaded process startup so the race window is small + bounded to 1 extra log line per typo).
2. **Warning reports normalized value (lower/strip), not original env string**: acknowledged per Codex "acceptable for this use case"; the operator can always inspect their actual env var if needed.

## What I want from you

1. **Verdict** APPROVE / REQUEST_CHANGES.
2. **Any P0/P1 you find** — please be exhaustive in iter 1.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
