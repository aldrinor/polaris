M-D11 phase 1 v2 review (commit 472b865).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Phase D M-D2 phase b GREEN-locked at v5 (5-round autoloop).
M-D11 phase 1 v1 round-1 was PARTIAL with 4 findings:
  1. singular `llm_model` insufficient (real stack has
     generator/evaluator/judge/inductor)
  2. env-driven routing/prompt toggles not captured
  3. pin_from_dict didn't re-apply capture_pin invariants
  4. no pin_schema_version field

This v2 commit redesigns to address all 4.

## What changed in v2

`src/polaris_graph/audit_ir/model_pin.py`:
  - `PIN_SCHEMA_VERSION = "v2"` constant
  - `DEFAULT_ROUTING_ENV_VARS` tuple: OPENROUTER_BASE_URL,
    OPENROUTER_PROVIDER_ORDER, OPENROUTER_FALLBACKS,
    OPENROUTER_REQUIRE_PARAMETERS, OPENROUTER_DEFAULT_MODEL,
    PG_V3_ANALYTICAL_PROMPT, PG_V3_DEPTH_GATE,
    POLARIS_CITEFIRST_ENABLED, PG_PROVENANCE_MIN_CONTENT_OVERLAP,
    PG_NLI_ENABLED, PG_NLI_THRESHOLD
  - ModelPin v2 dataclass:
    * pin_schema_version: str = "v2"
    * llm_models: dict[str, str] (role → model_id)
    * llm_providers: dict[str, str] (role → provider)
    * prompt_version_hashes: dict[str, str] (role → SHA-256)
    * env_snapshot: dict[str, str]
    * (rest unchanged: retrieval_source_versions, inductor_*,
      validation_set_hash, notes)
  - `capture_env_snapshot(names)` helper
  - `_validate_role_dict(name, data, *, require_non_empty=True)`
    used by both capture_pin and pin_from_dict
  - `_validate_env_snapshot(data)` for env shape validation
  - `capture_pin(...)` signature: takes llm_models dict
    (required), llm_providers dict (optional, auto-fills
    "openrouter" for missing roles), role_prompts dict
    (optional, hashes per role), env_snapshot OR
    capture_env_var_names (mutually exclusive)
  - `pin_from_dict(data)` re-applies every capture_pin
    invariant: schema_version match, run_id non-empty after
    strip, llm_models non-empty + role/value non-empty,
    providers must cover all model roles, prompts subset of
    model roles, env_snapshot shape, retrieval str→str
  - `pins_equivalent_for_replay(a, b)` compares
    pin_schema_version + new dict fields + env_snapshot

`tests/polaris_graph/test_md11_model_pin.py`:
  - 49 tests (was 22), all passing locally

## Your job

GREEN / PARTIAL / DISAGREE on v2.

1. **Round 1 fix integration**:
   - [ ] multi-model dict shape rehydrates real pipeline
   - [ ] env_snapshot covers behavior-affecting toggles
   - [ ] pin_from_dict re-validates symmetrically
   - [ ] pin_schema_version forward-compat works

2. **New schema gaps**: did the redesign introduce anything
   missing? E.g. tokenizer/sampling params, retrieval-tier
   config, M-16 audit-bundle pointer, evidence-pool snapshot.

3. **Validation symmetry**: capture_pin auto-fills providers
   for missing roles, but pin_from_dict requires every model
   role to have a provider on disk. Is that the right
   asymmetry, or should pin_from_dict also auto-fill?

4. **env_snapshot capture set**: DEFAULT_ROUTING_ENV_VARS is
   pulled from openrouter_client + synthesis_prompts +
   pipeline gates. Anything missing that affects runtime
   behavior?

5. **Replay equivalence semantics**: pin_schema_version is
   compared (different versions ≠ replay-equivalent). Is
   that the right call vs. cross-version compat?

6. **Phase 2 readiness**: with v2 schema locked, can the
   replay module load + reconfigure pipelines without further
   breaking changes?

## Output

`outputs/codex_findings/md11_phase1_v2_review/findings.md`:

```markdown
# Codex round 2 — M-D11 phase 1 v2 (commit 472b865)

## Verdict
GREEN / PARTIAL / DISAGREE

## Round 1 fix integration
- [x/no] multi-model dict shape adequate
- [x/no] env_snapshot covers behavior-affecting toggles
- [x/no] pin_from_dict re-validates symmetrically
- [x/no] pin_schema_version forward-compat works

## New findings (if any)
- [...]

## Final word
GREEN to lock M-D11 phase 1 / PARTIAL with edits.
```

Be terse. Under 60 lines.
