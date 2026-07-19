"""Canary-secret tests for the centralized redaction helper (defense-in-depth).

These use a KNOWN sentinel value (``CANARY``) planted as a fake API key / token, then
assert the helper NEVER lets that sentinel through a diagnostic path (mapping dump, string
log line, config ``safe_repr``). They also lock the byte-identical guarantee: redaction is
identity on data that carries no secret-looking key, so wiring it at a log boundary cannot
perturb ordinary text.

Context: the S4 threat model found POLARIS does not log secret values today, so this is
defense-in-depth. The `test_synthetic_config_dump_is_redacted` case models the exact
boundary the helper protects — a future "dump the effective settings" path — and proves the
sentinel is masked there.
"""

from __future__ import annotations

import re

from src.polaris_graph.util.secret_redaction import (
    REDACTED,
    is_secret_key,
    redact,
    register_known_secret,
    safe_repr,
)

CANARY = "CANARY-sk-live-0xDEADBEEF-do-not-log"


def _no_canary(rendered: str) -> None:
    assert CANARY not in rendered, f"secret leaked: {rendered!r}"
    assert REDACTED in rendered


# ── key-based masking on mappings ────────────────────────────────────────────
def test_secret_keys_in_mapping_are_masked():
    src = {
        "OPENROUTER_API_KEY": CANARY,
        "POLARIS_AUTH_SECRET": CANARY,
        "SERPER_API_KEY": CANARY,
        "some_password": CANARY,
        "AUTH_TOKEN": CANARY,
        "MY_CREDENTIAL": CANARY,
    }
    out = redact(src)
    for k in src:
        assert out[k] == REDACTED, k
    _no_canary(repr(out))


def test_non_secret_keys_are_untouched_byte_identical():
    src = {"PG_JUDGE_MODEL": "qwen/qwen3", "max_tokens": "8000", "slug": "abc"}
    assert redact(src) == src  # identity: no secret-looking key


def test_nested_mapping_and_list_recursion():
    src = {"outer": {"NESTED_API_KEY": CANARY, "plain": "keep"}, "items": ["a", "b"]}
    out = redact(src)
    assert out["outer"]["NESTED_API_KEY"] == REDACTED
    assert out["outer"]["plain"] == "keep"
    assert out["items"] == ["a", "b"]
    _no_canary(repr(out))


# ── string / inline shapes ───────────────────────────────────────────────────
def test_inline_keyvalue_shapes_masked():
    for line in (
        f"OPENROUTER_API_KEY={CANARY}",
        f'"api_key": "{CANARY}"',
        f"Authorization: Bearer {CANARY}",
        f"password = {CANARY}",
    ):
        out = redact(line)
        _no_canary(out)


def test_registered_known_secret_scrubbed_from_free_text():
    register_known_secret(CANARY)
    # A key whose name gives NO hint it is secret — only the registry catches it.
    leaked = f"upstream error: connection failed with credential {CANARY} rejected"
    out = redact(leaked)
    _no_canary(out)


def test_plain_text_is_byte_identical():
    text = "Retrieved 42 documents for slug clinical-xyz in 1.3s"
    assert redact(text) == text


def test_max_tokens_not_falsely_redacted():
    # 'TOKENS' (plural) is not the secret token 'TOKEN'; a hot config key must survive.
    for line in ("PG_GRADE_MAX_TOKENS=8000", "max_tokens=8000", '"max_tokens": 8000'):
        assert redact(line) == line, line
    assert redact({"PG_GRADE_MAX_TOKENS": "8000"}) == {"PG_GRADE_MAX_TOKENS": "8000"}


# ── safe_repr on config-like objects ─────────────────────────────────────────
class _FakeSettings:
    def __init__(self):
        self.judge_model = "qwen/qwen3"
        self.openrouter_api_key = CANARY
        self.serper_api_key = CANARY
        self.max_tokens = 8000


def test_safe_repr_masks_secret_attrs():
    out = safe_repr(_FakeSettings())
    _no_canary(out)
    assert "judge_model" in out and "qwen/qwen3" in out  # non-secrets preserved


def test_synthetic_config_dump_is_redacted():
    """Models the boundary this helper protects: dumping effective settings to a log.

    Proves that if such a path is ever added, routing the mapping through ``redact`` before
    it becomes output masks the sentinel while leaving operational config visible.
    """
    effective_config = {
        "PG_JUDGE_MODEL": "qwen/qwen3.6-35b-a3b",
        "OPENROUTER_API_KEY": CANARY,
        "SERPER_API_KEY": CANARY,
        "POLARIS_AUTH_SECRET": CANARY,
        "PG_MAX_ITERATIONS": "12",
    }
    dumped = "\n".join(f"{k}={v}" for k, v in redact(effective_config).items())
    _no_canary(dumped)
    assert "PG_JUDGE_MODEL=qwen/qwen3.6-35b-a3b" in dumped
    assert "PG_MAX_ITERATIONS=12" in dumped


def test_is_secret_key_matches_expected_tokens():
    for k in ("X_API_KEY", "auth_token", "MY_SECRET", "db_password", "svc_credential",
              "AUTHORIZATION", "POLARIS_AUTH_SECRET"):
        assert is_secret_key(k), k
    # 'tokens' plural and unrelated words must NOT match (avoids masking hot config keys).
    for k in ("judge_model", "max_tokens", "PG_GRADE_MAX_TOKENS", "slug", "author_name"):
        assert not is_secret_key(k), k


def test_no_partial_leak_when_values_overlap():
    short, long = "abcdef123", "abcdef123456789"
    register_known_secret(short)
    register_known_secret(long)
    out = redact(f"vals {long} and {short}")
    assert short not in out and long not in out
    assert not re.search(r"[0-9]{6,}", out)  # no numeric tail survived
