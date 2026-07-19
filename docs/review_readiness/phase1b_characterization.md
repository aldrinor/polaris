# Phase 1B — full-behaviour config characterization matrix

**129 characterization tests** (tests/test_config_characterization_matrix.py) locking today's
config-resolution behaviour across the axes that apply to this codebase:

- **value-state**: unset → registry default · empty '' · valid override · malformed (str passes
  through raw; int/float coercion raises ValueError at the call site; bool `==\"1\"` never raises)
- **precedence**: process-env > .env > registry default (`load_dotenv(override=False)`); no dedicated
  CLI tier in the config layer
- **key-case**: case-sensitive at both layers (ModelSettings `case_sensitive=True`; resolve()/registry
  reject a lowercase form of a registered key)
- **read-timing**: resolve() reads live env every call; get_model_settings() returns a fresh instance
  (effectively live)
- **runtime type**: str (resolve) · coerced-at-call-site (int/float/bool) · pydantic ModelSettings
  (str / str|None) · **no SecretStr in the codebase today** (documented so a future SecretStr pass
  must consciously update these tests)

Representative keys per type (plain-str, int-coerced, float-coerced, bool, model, secret-shaped,
empty-default, unregistered→KeyError). Every assertion is characterization (locks current behaviour),
not specification. Oracle replay byte-identical (golden 9c0a3d43); the test file is inert to runtime.
Addresses codex's three flagged axes (.env precedence, ModelSettings empty-value, resolve key-case).
