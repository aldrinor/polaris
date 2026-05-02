M-D11 phase 1 v4 review (commit a427174).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Round 3 (commit 273cfc2) verdict was PARTIAL with 2 findings:
  1. [HIGH] DEFAULT_REPLAY_ENV_VARS still incomplete + carried
     dead OPENROUTER_PROVIDER_REQUIRE_PARAMETERS
  2. [MEDIUM] capture_env_snapshot conflated "" vs unset

Round count progression: 4 (R1) -> 3 (R2) -> 2 (R3) — converging.

## What changed in v4

`src/polaris_graph/audit_ir/model_pin.py`:
  - PIN_SCHEMA_VERSION bumped "v3" -> "v4" (rejects v3 dicts;
    semantics of env_snapshot changed)
  - DEFAULT_REPLAY_ENV_VARS: 22 -> 36 vars
    * Removed dead: OPENROUTER_PROVIDER_REQUIRE_PARAMETERS
    * Added (NLI selection + faithfulness):
      PG_NLI_MODEL, PG_FAITHLENS_MODEL,
      PG_NLI_FAITHFULNESS_FLOOR
    * Added (cross-source):
      PG_CROSS_SOURCE_ENABLED, PG_CROSS_SOURCE_MIN_SIM,
      PG_CROSS_SOURCE_MIN_NLI, PG_CROSS_SOURCE_MAX_SOURCES,
      PG_CROSS_SOURCE_SELF_CHECK_MIN
    * Added (pipeline budgets):
      PG_V3_MAX_GAP_SEARCHES, PG_V3_SYNTH_BUDGET_PCT,
      PG_V3_ANALYSIS_ENABLED, PG_STORM_ENABLED
    * Added (call profile max-tokens):
      PG_V3_SCOPE_MAX_TOKENS, PG_V3_OUTLINE_MAX_TOKENS,
      PG_VERIFY_MAX_TOKENS
  - env_snapshot type: `dict[str, str]` -> `dict[str, str | None]`
    * None = unset at capture time (phase 2 must DELETE)
    * "" = explicitly set to "" (phase 2 must SET)
    * Module docstring documents phase-2 contract
  - capture_env_snapshot uses `os.environ.get(name)` (no "")
    default — preserves None
  - _validate_env_snapshot preserves None instead of converting

`tests/polaris_graph/test_md11_model_pin.py`:
  - 63 tests (was 58), all passing
  - Added: test_default_replay_env_vars_drops_dead_var,
    test_default_replay_env_vars_includes_round3_additions,
    test_capture_env_snapshot_explicit_empty_preserved,
    test_pin_from_dict_rejects_v3_schema,
    test_pins_not_equivalent_when_env_var_unset_vs_empty
  - Updated capture_env_snapshot_missing test to assert None
    (was empty string under v3)

## Your job

GREEN / PARTIAL / DISAGREE on v4.

1. **Round 3 fix integration**:
   - [ ] env capture set covers live behavior knobs
   - [ ] dead var dropped
   - [ ] None vs "" distinction correct + replay-safe
   - [ ] no regressions

2. **Replay completeness check**: with 36 env vars now in
   DEFAULT_REPLAY_ENV_VARS, are there still genuine
   replay-critical vars missing? The full inventory has
   817 names, but only a subset materially alters output.
   Anything important still missing?

3. **None semantics**: phase 2 will need to do
   `if v is None: os.environ.pop(name, None) else: os.environ[name] = v`.
   Is that the right contract, or should phase 2 also handle a
   third state ("")?

4. **Schema bump**: v3 -> v4. The semantics of env_snapshot
   changed (None now meaningful), so v3 dicts can't be loaded
   safely. Hard reject correct?

5. **Phase 2 readiness**: with v4 schema locked, can replay
   confidently rehydrate? Or are there still structural gaps?

6. **Asymptote check**: round counts 4 -> 3 -> 2. If this round
   is GREEN or has only low-severity findings, lock. If still
   substantive PARTIAL, that's round 4 — getting close to the
   asymptoting/converging boundary per autoloop V2.

## Output

`outputs/codex_findings/md11_phase1_v4_review/findings.md`:

```markdown
# Codex round 4 — M-D11 phase 1 v4 (commit a427174)

## Verdict
GREEN / PARTIAL / DISAGREE

## Round 3 fix integration
- [x/no] env capture set covers live knobs
- [x/no] dead var dropped
- [x/no] None vs "" distinction correct
- [x/no] no regressions

## New findings (if any)
- [...]

## Final word
GREEN to lock M-D11 phase 1 / PARTIAL with edits.
```

Be terse. Under 60 lines.
