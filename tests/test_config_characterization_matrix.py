"""Characterization matrix for the config resolution layer (Phase 1B).

CHARACTERIZATION, NOT SPECIFICATION. Every assertion here LOCKS what the code
CURRENTLY does today (2026-07), so a future refactor (e.g. the SecretStr pass,
or moving a coercion into resolve()) that changes observable behaviour will
break a test on purpose. Nothing here asserts what the code *should* do.

Two resolution layers are exercised:

  1. ``settings.resolve(key)`` -> ``os.getenv(key, CONFIG_DEFAULTS[key])``.
     Plain string pass-through. NO coercion, NO masking. Reads LIVE env every
     call. Raises ``KeyError`` for keys absent from ``CONFIG_DEFAULTS``.

  2. ``settings.get_model_settings().<field>`` -> pydantic ``ModelSettings``,
     ``case_sensitive=True``, a FRESH instance per call (effectively live).

Coercion (int/float/bool) does NOT live in resolve(); it lives at the CALL
SITE (e.g. ``int(resolve("PG_QUERIES_PER_VECTOR"))`` in state.py:23). So the
matrix characterizes the *composed* call-site expression, documenting exactly
which value-states raise and which pass through / silently degrade.

The whole file is hermetic: env is mutated only via ``monkeypatch.setenv`` /
``monkeypatch.delenv`` (auto-reverted), no network, no filesystem writes.
"""

from __future__ import annotations

import os

import pytest

from src.polaris_graph.config_defaults import CONFIG_DEFAULTS
from src.polaris_graph.settings import get_model_settings, resolve


# ─────────────────────────────────────────────────────────────────────────────
# The golden identity every resolve() case must satisfy.
# resolve(key) MUST equal os.getenv(key, CONFIG_DEFAULTS[key]) — byte-for-byte.
# ─────────────────────────────────────────────────────────────────────────────
def _expected(key: str) -> str | None:
    """The exact value resolve() must return, computed independently."""
    return os.getenv(key, CONFIG_DEFAULTS[key])


# Representative keys per axis (from the 1B matrix spec).
A_PLAIN_STR = ["ANTIWORD_CMD", "CHROMA_PERSIST_DIR"]
B_INT_COERCED = ["PG_QUERIES_PER_VECTOR", "PG_MAX_SECTIONS"]
C_FLOAT_COERCED = ["PG_MIN_FAITHFULNESS", "PG_CROSS_REF_SIM_THRESHOLD"]
D_BOOL_KEY = ["PG_CHECKPOINT_ENABLED", "PG_AMPLIFICATION_ENABLED"]
E_MODEL_KEY = ["PG_JUDGE_MODEL", "PG_EVALUATOR_MODEL"]
F_SECRET_SHAPED = ["OPENROUTER_API_KEY", "EXA_API_KEY", "ZYTE_API_KEY"]
G_EMPTY_STR_DEFAULT = ["PG_PLANNING_GATE_MODEL", "PG_POLICY_MODEL", "OPENROUTER_PROVIDER_ORDER"]

# Every registry-backed representative (model-only field PG_EVALUATOR_MODEL is
# dual-registered, so it appears in CONFIG_DEFAULTS too and is safe here).
ALL_RESOLVE_KEYS = (
    A_PLAIN_STR + B_INT_COERCED + C_FLOAT_COERCED + D_BOOL_KEY
    + E_MODEL_KEY + F_SECRET_SHAPED + G_EMPTY_STR_DEFAULT
)

# Map each model env var -> the ModelSettings attribute it feeds.
MODEL_FIELD = {"PG_JUDGE_MODEL": "judge_model", "PG_EVALUATOR_MODEL": "evaluator_model"}


# ─────────────────────────────────────────────────────────────────────────────
# Axis A/E/F/G + the core identity — resolve() == os.getenv(key, DEFAULT).
# value-state x precedence matrix, every representative key.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", ALL_RESOLVE_KEYS)
def test_resolve_unset_returns_registry_default(monkeypatch, key):
    """value-state=unset, precedence=registry-default: resolve == CONFIG_DEFAULTS[key]."""
    monkeypatch.delenv(key, raising=False)
    assert resolve(key) == CONFIG_DEFAULTS[key]
    assert resolve(key) == _expected(key)


@pytest.mark.parametrize("key", ALL_RESOLVE_KEYS)
def test_resolve_valid_override_process_env_wins(monkeypatch, key):
    """value-state=valid, precedence=process-env override: env value wins over default."""
    monkeypatch.setenv(key, "override-value-XYZ")
    assert resolve(key) == "override-value-XYZ"
    assert resolve(key) == _expected(key)


@pytest.mark.parametrize("key", ALL_RESOLVE_KEYS)
def test_resolve_empty_string_override(monkeypatch, key):
    """value-state=empty: an explicitly-set '' overrides the default and returns ''.

    (For int/float/bool keys this is the raw resolve() layer; the coercion tests
    below characterize what int()/float()/=='1' then do with that '').
    """
    monkeypatch.setenv(key, "")
    assert resolve(key) == ""
    assert resolve(key) == _expected(key)


@pytest.mark.parametrize("key", ALL_RESOLVE_KEYS)
def test_resolve_malformed_passes_through_raw_at_resolve_layer(monkeypatch, key):
    """value-state=malformed: resolve() NEVER coerces -> returns the raw garbage string.

    Malformedness only matters at the coercion call site (see int/float tests);
    resolve() itself is a pure str pass-through and never raises on the value.
    """
    monkeypatch.setenv(key, "not-a-number-@@@")
    assert resolve(key) == "not-a-number-@@@"
    assert resolve(key) == _expected(key)


def test_plain_str_no_coercion_type_is_str(monkeypatch):
    """Axis A: plain-str keys are returned as raw str, never coerced/parsed."""
    for key in A_PLAIN_STR:
        monkeypatch.setenv(key, "  spaced/value  ")
        val = resolve(key)
        assert isinstance(val, str)
        assert val == "  spaced/value  "  # not stripped, not normalized


def test_empty_string_default_keys_return_empty_when_unset(monkeypatch):
    """Axis G: these keys default to '' (falsy 'auto/disabled' sentinel) when unset."""
    for key in G_EMPTY_STR_DEFAULT:
        monkeypatch.delenv(key, raising=False)
        assert resolve(key) == ""


# ─────────────────────────────────────────────────────────────────────────────
# Axis F — secret-shaped keys. Documents the CURRENT pre-SecretStr state:
# KEY/TOKEN/SECRET-shaped values are PLAIN str (or None), never masked.
# ─────────────────────────────────────────────────────────────────────────────

def test_secret_shaped_keys_are_plain_str_not_secretstr(monkeypatch):
    """No SecretStr in this codebase yet: secrets resolve to a plain, un-masked str.

    LOCKS the pre-SecretStr baseline so a future SecretStr migration must
    consciously update this test.
    """
    for key in ["OPENROUTER_API_KEY", "EXA_API_KEY", "ZYTE_API_KEY"]:
        monkeypatch.setenv(key, "sk-super-secret-123")
        val = resolve(key)
        assert type(val) is str  # exactly str, NOT SecretStr / a wrapper
        assert val == "sk-super-secret-123"  # value is exposed verbatim, no masking
        assert "****" not in repr(val)


def test_secret_default_shapes(monkeypatch):
    """Unset secret defaults: '' for OPENROUTER/EXA, None for ZYTE (verbatim registry)."""
    for key in ["OPENROUTER_API_KEY", "EXA_API_KEY", "ZYTE_API_KEY"]:
        monkeypatch.delenv(key, raising=False)
    assert resolve("OPENROUTER_API_KEY") == ""
    assert resolve("EXA_API_KEY") == ""
    assert resolve("ZYTE_API_KEY") is None  # None default -> None, not ''


# ─────────────────────────────────────────────────────────────────────────────
# Axis B — int-coerced call sites: int(resolve(key)).
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", B_INT_COERCED)
def test_int_coercion_unset_default_parses(monkeypatch, key):
    """Unset: int(resolve(key)) equals int() of the registry default."""
    monkeypatch.delenv(key, raising=False)
    assert int(resolve(key)) == int(CONFIG_DEFAULTS[key])


@pytest.mark.parametrize("key", B_INT_COERCED)
def test_int_coercion_valid_override(monkeypatch, key):
    """Valid override: int(resolve(key)) reflects the env integer."""
    monkeypatch.setenv(key, "7")
    assert int(resolve(key)) == 7


@pytest.mark.parametrize("key", B_INT_COERCED)
def test_int_coercion_malformed_raises_valueerror_at_call_site(monkeypatch, key):
    """Malformed: resolve() succeeds; int() at the CALL SITE raises ValueError.

    (resolve() does NOT raise — it returns the raw string. The failure is the
    call-site int(...), exactly as at state.py:23 / :44 module-import time.)
    """
    monkeypatch.setenv(key, "not-an-int")
    raw = resolve(key)  # does NOT raise
    assert raw == "not-an-int"
    with pytest.raises(ValueError):
        int(raw)


@pytest.mark.parametrize("key", B_INT_COERCED)
def test_int_coercion_empty_string_raises_valueerror(monkeypatch, key):
    """Empty '': resolve() returns ''; int('') raises ValueError at the call site."""
    monkeypatch.setenv(key, "")
    assert resolve(key) == ""
    with pytest.raises(ValueError):
        int(resolve(key))


# ─────────────────────────────────────────────────────────────────────────────
# Axis C — float-coerced call sites: float(resolve(key)).
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", C_FLOAT_COERCED)
def test_float_coercion_unset_default_parses(monkeypatch, key):
    """Unset: float(resolve(key)) equals float() of the registry default."""
    monkeypatch.delenv(key, raising=False)
    assert float(resolve(key)) == float(CONFIG_DEFAULTS[key])


@pytest.mark.parametrize("key", C_FLOAT_COERCED)
def test_float_coercion_valid_override(monkeypatch, key):
    """Valid override: float(resolve(key)) reflects the env float."""
    monkeypatch.setenv(key, "0.42")
    assert float(resolve(key)) == 0.42


@pytest.mark.parametrize("key", C_FLOAT_COERCED)
def test_float_coercion_malformed_raises_valueerror_at_call_site(monkeypatch, key):
    """Malformed: resolve() succeeds; float() at the call site raises ValueError."""
    monkeypatch.setenv(key, "zero-point-five")
    raw = resolve(key)
    assert raw == "zero-point-five"
    with pytest.raises(ValueError):
        float(raw)


@pytest.mark.parametrize("key", C_FLOAT_COERCED)
def test_float_coercion_empty_string_raises_valueerror(monkeypatch, key):
    """Empty '': float('') raises ValueError at the call site."""
    monkeypatch.setenv(key, "")
    assert resolve(key) == ""
    with pytest.raises(ValueError):
        float(resolve(key))


# ─────────────────────────────────────────────────────────────────────────────
# Axis D — boolean call sites: resolve(key) == "1".
# NEVER raises. ONLY the literal '1' is True; every other value is False.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", D_BOOL_KEY)
def test_bool_coercion_literal_one_is_true(monkeypatch, key):
    """value '1' -> True (the only truthy value under the =='1' contract)."""
    monkeypatch.setenv(key, "1")
    assert (resolve(key) == "1") is True


@pytest.mark.parametrize(
    "value", ["0", "", "true", "TRUE", "yes", "on", " 1", "1 ", "01", "not-a-bool"]
)
@pytest.mark.parametrize("key", D_BOOL_KEY)
def test_bool_coercion_non_one_is_false_never_raises(monkeypatch, key, value):
    """Any non-'1' value (incl. empty, malformed, 'true', whitespace-padded) -> False.

    Characterizes that the ==\"1\" contract silently degrades rather than raising.
    """
    monkeypatch.setenv(key, value)
    assert (resolve(key) == "1") is False


@pytest.mark.parametrize("key", D_BOOL_KEY)
def test_bool_coercion_unset_uses_default(monkeypatch, key):
    """Unset: default '0'->False (CHECKPOINT), '1'->True (AMPLIFICATION)."""
    monkeypatch.delenv(key, raising=False)
    expected = CONFIG_DEFAULTS[key] == "1"
    assert (resolve(key) == "1") is expected
    # sanity-check the two representatives have the documented opposite defaults
    if key == "PG_CHECKPOINT_ENABLED":
        assert expected is False
    if key == "PG_AMPLIFICATION_ENABLED":
        assert expected is True


# ─────────────────────────────────────────────────────────────────────────────
# Axis E — model keys via get_model_settings() (pydantic layer, case-sensitive).
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", E_MODEL_KEY)
def test_model_setting_unset_returns_field_default(monkeypatch, key):
    """Unset: get_model_settings().<field> equals the pydantic field default."""
    monkeypatch.delenv(key, raising=False)
    field = MODEL_FIELD[key]
    val = getattr(get_model_settings(), field)
    if key == "PG_JUDGE_MODEL":
        assert val == "qwen/qwen3.6-35b-a3b"
    if key == "PG_EVALUATOR_MODEL":
        assert val is None  # 'str | None' with None default


@pytest.mark.parametrize("key", E_MODEL_KEY)
def test_model_setting_valid_override(monkeypatch, key):
    """Valid override: the correctly-cased env var flows into the field."""
    monkeypatch.setenv(key, "vendor/model-9")
    assert getattr(get_model_settings(), MODEL_FIELD[key]) == "vendor/model-9"


def test_model_setting_case_sensitive_lowercase_alias_ignored(monkeypatch):
    """case_sensitive=True: a lowercased env name does NOT override; default stands."""
    monkeypatch.delenv("PG_JUDGE_MODEL", raising=False)
    monkeypatch.setenv("pg_judge_model", "SHOULD-BE-IGNORED")
    assert get_model_settings().judge_model == "qwen/qwen3.6-35b-a3b"
    # and the correctly-cased var still wins when present
    monkeypatch.setenv("PG_JUDGE_MODEL", "CORRECT")
    assert get_model_settings().judge_model == "CORRECT"


def test_model_evaluator_dual_registered_agrees_across_layers(monkeypatch):
    """PG_EVALUATOR_MODEL is in BOTH CONFIG_DEFAULTS(None) and ModelSettings(None).

    Both layers must agree today: unset -> None on each.
    """
    monkeypatch.delenv("PG_EVALUATOR_MODEL", raising=False)
    assert resolve("PG_EVALUATOR_MODEL") is None
    assert get_model_settings().evaluator_model is None
    monkeypatch.setenv("PG_EVALUATOR_MODEL", "eval/model-1")
    assert resolve("PG_EVALUATOR_MODEL") == "eval/model-1"
    assert get_model_settings().evaluator_model == "eval/model-1"


# ─────────────────────────────────────────────────────────────────────────────
# Read-timing / freshness — resolve() and get_model_settings() read LIVE env.
# ─────────────────────────────────────────────────────────────────────────────

def test_resolve_reads_live_env_every_call(monkeypatch):
    """Freshness contract: a value set AFTER import is seen on the NEXT resolve()."""
    key = "ANTIWORD_CMD"
    monkeypatch.delenv(key, raising=False)
    assert resolve(key) == CONFIG_DEFAULTS[key]  # default first
    monkeypatch.setenv(key, "live-1")
    assert resolve(key) == "live-1"  # picked up without re-import
    monkeypatch.setenv(key, "live-2")
    assert resolve(key) == "live-2"  # and again — no caching


def test_get_model_settings_returns_fresh_instance_each_call(monkeypatch):
    """A fresh ModelSettings per call => effectively live despite per-instance snapshot."""
    monkeypatch.setenv("PG_JUDGE_MODEL", "first")
    s1 = get_model_settings()
    assert s1.judge_model == "first"
    monkeypatch.setenv("PG_JUDGE_MODEL", "second")
    s2 = get_model_settings()
    assert s2.judge_model == "second"  # new instance sees the new env
    assert s1 is not s2  # not a cached singleton
    assert s1.judge_model == "first"  # the old snapshot did NOT mutate


# ─────────────────────────────────────────────────────────────────────────────
# Axis H — unregistered key: resolve() raises KeyError (intentional gate).
# ─────────────────────────────────────────────────────────────────────────────

def test_resolve_unregistered_key_raises_keyerror(monkeypatch):
    """A key absent from CONFIG_DEFAULTS raises KeyError, even if the ENV var is set."""
    key = "PG_TOTALLY_UNREGISTERED_KEY_XYZ"
    assert key not in CONFIG_DEFAULTS
    with pytest.raises(KeyError):
        resolve(key)
    # setting the env var does NOT rescue it — the gate is the registry, not env
    monkeypatch.setenv(key, "whatever")
    with pytest.raises(KeyError):
        resolve(key)


# ─────────────────────────────────────────────────────────────────────────────
# Precedence — process-env vs registry default (the only two live tiers in the
# config module; there is NO dedicated CLI tier inside resolve()/ModelSettings).
# ─────────────────────────────────────────────────────────────────────────────

def test_precedence_process_env_beats_registry_default(monkeypatch):
    """Process env strictly wins over the registry default for every representative."""
    for key in ALL_RESOLVE_KEYS:
        monkeypatch.setenv(key, "PROC-WINS")
        assert resolve(key) == "PROC-WINS"
        assert resolve(key) != CONFIG_DEFAULTS[key] or CONFIG_DEFAULTS[key] == "PROC-WINS"


# ─────────────────────────────────────────────────────────────────────────────
# Axis I — .env PRECEDENCE TIER (codex-flagged).
#
# GROUND TRUTH of THIS module: settings.py does NOT call load_dotenv itself. Its
# resolve()/ModelSettings read ONLY os.getenv/os.environ. The codebase's OTHER
# modules (state.py, graph.py, checkpoint_manager.py, ...) call
# ``load_dotenv()`` — i.e. ``load_dotenv(override=False)`` — at import time,
# which COPIES .env keys into os.environ *only for keys not already present*.
# So the observable precedence the config layer sees is entirely produced by
# that copy step:
#
#   registry default  <  .env value  <  process-env value
#
# and, critically, override=False means a key ALREADY in os.environ (process
# env) is NOT overwritten by .env. These tests reproduce the real mechanism
# (a temp .env file fed through dotenv.load_dotenv(override=False)) and then
# assert what resolve()/get_model_settings() actually return. Cleanup pops any
# key the dotenv load injected into os.environ so the suite stays hermetic
# (monkeypatch.setenv/delenv can't auto-revert os.environ mutations that
# load_dotenv performs directly).
# ─────────────────────────────────────────────────────────────────────────────

import tempfile  # noqa: E402

from dotenv import load_dotenv  # noqa: E402


def _write_env_file(tmp_path, **pairs):
    """Write a temp .env file with the given KEY=VALUE pairs, return its path."""
    p = tmp_path / "hermetic.env"
    p.write_text("".join(f"{k}={v}\n" for k, v in pairs.items()))
    return str(p)


def test_dotenv_only_key_beats_registry_default(tmp_path, monkeypatch):
    """(a) A key present ONLY in .env (not in process env) beats the registry default.

    Mechanism: load_dotenv(override=False) injects the key into os.environ because
    it is absent there; resolve() then reads it via os.getenv and returns the
    .env value in preference to CONFIG_DEFAULTS[key].
    """
    key = "ANTIWORD_CMD"
    assert key in CONFIG_DEFAULTS
    default = CONFIG_DEFAULTS[key]
    monkeypatch.delenv(key, raising=False)  # ensure NOT in process env
    assert resolve(key) == default  # baseline: registry default stands

    env_path = _write_env_file(tmp_path, ANTIWORD_CMD="from-dotenv-only")
    try:
        loaded = load_dotenv(env_path, override=False)
        assert loaded is True
        assert os.environ.get(key) == "from-dotenv-only"  # dotenv copied it in
        assert resolve(key) == "from-dotenv-only"  # .env value beats default
        assert resolve(key) != default
    finally:
        os.environ.pop(key, None)  # undo the direct os.environ mutation


def test_dotenv_only_key_beats_default_model_layer(tmp_path, monkeypatch):
    """(a') Same layering through the pydantic ModelSettings path.

    A model key present only in .env (loaded into os.environ) overrides the
    pydantic field default on the next fresh get_model_settings() read.
    """
    monkeypatch.delenv("PG_JUDGE_MODEL", raising=False)
    assert get_model_settings().judge_model == "qwen/qwen3.6-35b-a3b"  # field default

    env_path = _write_env_file(tmp_path, PG_JUDGE_MODEL="dotenv/judge-model")
    try:
        assert load_dotenv(env_path, override=False) is True
        assert get_model_settings().judge_model == "dotenv/judge-model"
    finally:
        os.environ.pop("PG_JUDGE_MODEL", None)


def test_process_env_beats_dotenv_because_override_false(tmp_path, monkeypatch):
    """(b) A key in BOTH process-env and .env resolves to the PROCESS-ENV value.

    override=False is the codebase-wide setting (bare ``load_dotenv()``): a key
    ALREADY in os.environ is left untouched, so .env never shadows real env.
    """
    key = "ANTIWORD_CMD"
    monkeypatch.setenv(key, "from-process-env")  # process env set FIRST
    env_path = _write_env_file(tmp_path, ANTIWORD_CMD="from-dotenv")
    try:
        assert load_dotenv(env_path, override=False) is True
        # os.environ still holds the process value — dotenv did not overwrite it.
        assert os.environ[key] == "from-process-env"
        assert resolve(key) == "from-process-env"  # process env wins over .env
        assert resolve(key) != "from-dotenv"
    finally:
        # monkeypatch.setenv reverts the process value; nothing extra to pop
        # (dotenv left os.environ[key] as the monkeypatched value it found).
        pass


def test_dotenv_override_false_is_the_codebase_setting():
    """Guard: load_dotenv's default override is False, matching every bare
    ``load_dotenv()`` call in src/polaris_graph (state.py, graph.py, ...).

    If a dependency bump flipped this default, the (b) precedence above would
    silently invert; this locks the assumption the layering tests rely on.
    """
    import inspect

    assert inspect.signature(load_dotenv).parameters["override"].default is False


# ─────────────────────────────────────────────────────────────────────────────
# Axis J — ModelSettings EMPTY-VALUE / malformed-value (codex-flagged).
#
# For a model key, characterize EXACTLY what get_model_settings().<field>
# returns when the env var is '' and when it is a malformed-looking string.
# ACTUAL behaviour (pydantic-settings, plain ``str`` / ``str | None`` fields,
# no validators): the empty string stays '' (it is NOT coerced to None and NOT
# ignored), and an arbitrary/malformed string is preserved VERBATIM — the field
# type is an unconstrained str, so there is no notion of "malformed".
# ─────────────────────────────────────────────────────────────────────────────

def test_model_setting_empty_string_stays_empty_string(monkeypatch):
    """env='' -> field is '' exactly (NOT None, NOT the default, NOT dropped)."""
    monkeypatch.setenv("PG_JUDGE_MODEL", "")
    val = get_model_settings().judge_model
    assert val == ""
    assert val is not None  # empty string is NOT normalized to None
    assert val != "qwen/qwen3.6-35b-a3b"  # the field default did NOT stand


def test_model_setting_optional_empty_string_stays_empty_not_none(monkeypatch):
    """For a ``str | None`` field (PG_EVALUATOR_MODEL), env='' still yields ''.

    Even though None is a valid value for this field, an explicit empty-string
    env var is passed through as '' — pydantic does NOT map ''->None here.
    """
    monkeypatch.setenv("PG_EVALUATOR_MODEL", "")
    val = get_model_settings().evaluator_model
    assert val == ""
    assert val is not None  # distinct from the unset case, which IS None


def test_model_setting_malformed_string_preserved_verbatim(monkeypatch):
    """Malformed-looking value: the field is an unconstrained str, so the raw
    string is stored byte-for-byte — no parsing, no rejection, no coercion.

    (N/A-for-validation: 'malformed' is undefined for a free-form str field;
    this LOCKS that there is no hidden validator that would reject it.)
    """
    garbage = "not/a real::model @@@  \t"
    monkeypatch.setenv("PG_JUDGE_MODEL", garbage)
    assert get_model_settings().judge_model == garbage  # verbatim, incl. trailing ws


# ─────────────────────────────────────────────────────────────────────────────
# Axis K — resolve()-LAYER KEY-CASE sensitivity (codex-flagged).
#
# resolve() looks a key up in CONFIG_DEFAULTS (exact string membership) then
# reads os.getenv(key) (exact, case-sensitive). So a LOWERCASE form of a
# registered key is a DIFFERENT, unregistered key: setting it in env does NOT
# override the correctly-cased resolve(), and resolve(lowercase) raises KeyError.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", ["PG_MAX_SECTIONS", "ANTIWORD_CMD"])
def test_resolve_is_case_sensitive_lowercase_env_does_not_override(monkeypatch, key):
    """A lowercase-named env var does NOT feed the correctly-cased resolve(key)."""
    lower = key.lower()
    assert lower != key  # sanity: the two names actually differ
    assert lower not in CONFIG_DEFAULTS  # lowercase form is unregistered
    monkeypatch.delenv(key, raising=False)  # correct-case var unset
    monkeypatch.setenv(lower, "LOWERCASE-SHOULD-NOT-WIN")
    # resolve of the CORRECT case ignores the lowercase env and returns default:
    assert resolve(key) == CONFIG_DEFAULTS[key]
    assert resolve(key) != "LOWERCASE-SHOULD-NOT-WIN"


@pytest.mark.parametrize("key", ["PG_MAX_SECTIONS", "ANTIWORD_CMD"])
def test_resolve_lowercase_key_raises_keyerror_even_when_env_set(monkeypatch, key):
    """resolve(lowercase) raises KeyError — the lowercase key is not registered,
    and an env var by that name does NOT rescue it (the gate is the registry)."""
    lower = key.lower()
    monkeypatch.setenv(lower, "present-in-env")
    with pytest.raises(KeyError):
        resolve(lower)
