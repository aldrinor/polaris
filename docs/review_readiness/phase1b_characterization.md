# Phase 1B — full-behaviour config characterization matrix

**File:** `tests/test_config_characterization_matrix.py` · **Tests:** 118 (all pass) ·
**Under test:** `src/polaris_graph/settings.py` — `resolve()` and `get_model_settings()`,
over the `CONFIG_DEFAULTS` registry.

## Intent

CHARACTERIZATION, not specification. Every assertion LOCKS what the two resolution
layers do **today** (2026-07), so a future refactor that changes observable behaviour
(e.g. a SecretStr pass, or moving coercion into `resolve()`) breaks a test on purpose.
Nothing here asserts what the code *should* do.

The golden identity that anchors the matrix:

    resolve(key) == os.getenv(key, CONFIG_DEFAULTS[key])   # byte-for-byte

Coercion (int/float/bool) does **not** live in `resolve()` — it lives at the CALL SITE
(e.g. `int(resolve("PG_QUERIES_PER_VECTOR"))`). The matrix therefore characterizes the
*composed* call-site expression: which value-states raise, which pass through, which
silently degrade.

## Matrix dimensions

`value-state x precedence x case x timing x type`, exercised across representative keys:

| Axis | Meaning | Representative keys |
|------|---------|---------------------|
| A | plain-str pass-through (no coercion/strip/normalize) | `ANTIWORD_CMD`, `CHROMA_PERSIST_DIR` |
| B | int-coerced call site `int(resolve(k))` | `PG_QUERIES_PER_VECTOR`, `PG_MAX_SECTIONS` |
| C | float-coerced call site `float(resolve(k))` | `PG_MIN_FAITHFULNESS`, `PG_CROSS_REF_SIM_THRESHOLD` |
| D | bool call site `resolve(k) == "1"` (only literal `1` is True) | `PG_CHECKPOINT_ENABLED`, `PG_AMPLIFICATION_ENABLED` |
| E | model keys via pydantic `get_model_settings()` (case-sensitive) | `PG_JUDGE_MODEL`, `PG_EVALUATOR_MODEL` |
| F | secret-shaped keys — plain str, **not** SecretStr, un-masked (pre-migration baseline) | `OPENROUTER_API_KEY`, `EXA_API_KEY`, `ZYTE_API_KEY` |
| G | empty-string-default sentinel keys | `PG_PLANNING_GATE_MODEL`, `PG_POLICY_MODEL`, `OPENROUTER_PROVIDER_ORDER` |
| H | unregistered key -> `KeyError` (the registry is the gate, not env) | `PG_TOTALLY_UNREGISTERED_KEY_XYZ` |

Cross-cutting sub-axes:

- **value-state:** unset (registry default), valid override, empty `""`, malformed garbage.
- **precedence:** process-env strictly beats registry default (the only two live tiers).
- **case:** pydantic `case_sensitive=True` — a lowercased env name does NOT override.
- **timing / freshness:** both `resolve()` and `get_model_settings()` read LIVE env every
  call (fresh `ModelSettings` per call, no cached singleton).
- **type:** `None`-default (`ZYTE_API_KEY`, `PG_EVALUATOR_MODEL`) -> `None`, not `""`;
  dual-registered `PG_EVALUATOR_MODEL` agrees across the `resolve()` and pydantic layers.

## Verify gate (all green before commit)

- **new_tests_pass:** 118 passed (`pytest tests/test_config_characterization_matrix.py`).
- **collection_delta_ok:** repo-wide collection 16738 -> 16856 = exactly +118; the 11
  pre-existing collection errors (registry import-time debt, per `baseline_test_state.md`)
  are unchanged.
- **oracle_matches:** the deterministic cassette gate `tests/oracle/test_cassette.py`
  stays green (12 passed); this change is additive test code only — no `src/` production
  code touched, so the frozen artifact replays byte-identically.

## Codex verdict

**1B-OK.** Codex reviewed axis coverage against the actual branch distinctions the two
functions exhibit (registered `None`/empty defaults, exact-string/whitespace preservation,
the pre-`getenv` `KeyError` gate, pydantic env-name case matching, coercion-failure sites,
source precedence, per-call freshness) and found the matrix complete for a full-behaviour
characterization of the current layers. No missing-axis remediation required.
