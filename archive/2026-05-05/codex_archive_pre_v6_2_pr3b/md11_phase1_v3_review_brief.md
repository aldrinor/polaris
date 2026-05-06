M-D11 phase 1 v3 review (commit 273cfc2).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Round 2 (commit 472b865) verdict was PARTIAL with 3 findings:
  1. [HIGH] env capture set used wrong var name
     (OPENROUTER_FALLBACKS) and missed NLI knobs + v3 prompt
     toggles
  2. [MEDIUM] missing call-profile knobs (max_tokens vars)
  3. [LOW] capture_pin didn't validate
     retrieval_source_versions symmetrically with
     pin_from_dict

This v3 commit addresses all 3.

## What changed in v3

`src/polaris_graph/audit_ir/model_pin.py`:
  - PIN_SCHEMA_VERSION bumped "v2" -> "v3" (rejects v2 dicts
    on load)
  - DEFAULT_ROUTING_ENV_VARS renamed to DEFAULT_REPLAY_ENV_VARS
    (broader scope), old name kept as alias for backward compat
  - Env set fixed + extended (22 vars total, was 12):
    * OPENROUTER_FALLBACKS -> OPENROUTER_ALLOW_FALLBACKS
    * Added: PG_NLI_DISPUTE_THRESHOLD, PG_NLI_CONTEXT_WINDOW,
      PG_NLI_DOMAIN_ADAPTIVE, PG_NLI_DOMAIN_FLOOR,
      PG_FAITHFULNESS_NLI_THRESHOLD
    * Added: PG_V3_SURFACE_ANALYSIS, PG_V3_COMPARISON_TABLES,
      PG_PHASE_5_ENABLED
    * Added (call profile): PG_SECTION_WRITER_MAX_TOKENS,
      PG_SECTION_CONTINUATION_MAX_TOKENS, PG_GLM5_MIN_MAX_TOKENS
  - New `_validate_retrieval_source_versions(data)` helper
    called from both capture_pin and pin_from_dict (symmetric
    str->str validation with non-empty key check)

`tests/polaris_graph/test_md11_model_pin.py`:
  - 58 tests (was 49), all passing locally
  - Added: test_default_replay_env_vars_uses_correct_fallbacks_var,
    test_default_replay_env_vars_includes_nli_knobs,
    test_default_replay_env_vars_includes_v3_toggles,
    test_default_replay_env_vars_includes_call_profile,
    test_default_routing_env_vars_alias_to_replay_env_vars,
    test_capture_pin_rejects_non_str_retrieval_value,
    test_capture_pin_rejects_non_str_retrieval_key,
    test_capture_pin_rejects_empty_retrieval_key,
    test_pin_from_dict_rejects_v2_schema

## Your job

GREEN / PARTIAL / DISAGREE on v3.

1. **Round 2 fix integration**:
   - [ ] env capture set fixed + extended correctly
   - [ ] call-profile knobs covered
   - [ ] retrieval_source_versions validated symmetrically
   - [ ] no regressions to v2 work

2. **Coverage completeness**: with 22 env vars in the default
   set, are there other replay-critical vars I missed?
   `docs/pipeline_audit_context/08_env_var_inventory.md`
   lists 817 total — most are ephemeral but a subset alters
   behavior materially. Anything obvious still missing?

3. **Schema bump rationale**: I bumped to v3 (not minor v2.1)
   because the env var set is incompatible — pins captured
   with old DEFAULT_ROUTING_ENV_VARS contain
   OPENROUTER_FALLBACKS (a non-existent var) which would
   mislead replay. Hard reject of v2 dicts is correct, right?

4. **Phase 2 readiness**: with v3 schema, can phase 2 (replay)
   confidently rehydrate a pipeline run, or are there other
   structural gaps before we lock?

## Output

`outputs/codex_findings/md11_phase1_v3_review/findings.md`:

```markdown
# Codex round 3 — M-D11 phase 1 v3 (commit 273cfc2)

## Verdict
GREEN / PARTIAL / DISAGREE

## Round 2 fix integration
- [x/no] env capture set corrected
- [x/no] call-profile knobs covered
- [x/no] retrieval_source_versions validated symmetrically
- [x/no] no regressions

## New findings (if any)
- [...]

## Final word
GREEN to lock M-D11 phase 1 / PARTIAL with edits.
```

Be terse. Under 60 lines.
