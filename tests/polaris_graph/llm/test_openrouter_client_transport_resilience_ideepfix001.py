"""I-deepfix-001 B3 (#1370) — offline tests for the WT-5 openrouter_client + routing-config fixes.

Pure Python, no network. Covers:
  * ``_client_limits_from_env`` — UNSET (both) => None (byte-identical legacy client, NO limits= kwarg);
    SET => an httpx.Limits carrying exactly the env-overridden field(s), httpx defaults elsewhere,
  * ``_fresh_conn_on_disconnect_enabled`` — DEFAULT OFF + truthy parse,
  * the generator provider fanout gate-fix (Codex+Fable P1-1): the yaml generator pins are RESTORED as
    the DEFAULT (``role_provider_routing("generator")`` returns the ranked order/ignore = byte-identical
    to the pre-B3 pinned routing), while mirror stays pinned + judge stays unpinned (only generator
    touched); the B3 fanout is gated behind ``PG_GENERATOR_PROVIDER_FANOUT`` (default OFF).
"""

from __future__ import annotations

import httpx
import pytest

from src.polaris_graph.llm import openrouter_client as oc


# ── B3(a) httpx.Limits from env (byte-identity gate) ─────────────────────────────────────────────
def test_limits_none_when_both_unset(monkeypatch):
    monkeypatch.delenv(oc._ENV_OPENROUTER_KEEPALIVE_EXPIRY_S, raising=False)
    monkeypatch.delenv(oc._ENV_OPENROUTER_MAX_KEEPALIVE, raising=False)
    # None => the caller passes NO limits= kwarg => byte-identical legacy AsyncClient construction.
    assert oc._client_limits_from_env() is None


def test_limits_none_when_blank_or_unparsable(monkeypatch):
    monkeypatch.setenv(oc._ENV_OPENROUTER_KEEPALIVE_EXPIRY_S, "  ")
    monkeypatch.setenv(oc._ENV_OPENROUTER_MAX_KEEPALIVE, "not-an-int")
    assert oc._client_limits_from_env() is None


def test_limits_set_both(monkeypatch):
    monkeypatch.setenv(oc._ENV_OPENROUTER_KEEPALIVE_EXPIRY_S, "1.5")
    monkeypatch.setenv(oc._ENV_OPENROUTER_MAX_KEEPALIVE, "8")
    limits = oc._client_limits_from_env()
    assert isinstance(limits, httpx.Limits)
    assert limits.max_keepalive_connections == 8
    assert limits.keepalive_expiry == 1.5


def test_limits_set_only_keepalive_expiry_keeps_httpx_default_max(monkeypatch):
    monkeypatch.setenv(oc._ENV_OPENROUTER_KEEPALIVE_EXPIRY_S, "2")
    monkeypatch.delenv(oc._ENV_OPENROUTER_MAX_KEEPALIVE, raising=False)
    limits = oc._client_limits_from_env()
    assert isinstance(limits, httpx.Limits)
    assert limits.keepalive_expiry == 2.0
    # httpx default (20) is preserved when the max-keepalive knob is unset.
    assert limits.max_keepalive_connections == httpx.Limits().max_keepalive_connections


# ── B3(a) fresh-connection-before-retry flag ─────────────────────────────────────────────────────
def test_fresh_conn_default_off(monkeypatch):
    monkeypatch.delenv(oc._ENV_OPENROUTER_FRESH_CONN_ON_DISCONNECT, raising=False)
    assert oc._fresh_conn_on_disconnect_enabled() is False


@pytest.mark.parametrize("val", ["0", "", "false", "off", "no"])
def test_fresh_conn_falsy(monkeypatch, val):
    monkeypatch.setenv(oc._ENV_OPENROUTER_FRESH_CONN_ON_DISCONNECT, val)
    assert oc._fresh_conn_on_disconnect_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "on", "yes", "ON"])
def test_fresh_conn_truthy(monkeypatch, val):
    monkeypatch.setenv(oc._ENV_OPENROUTER_FRESH_CONN_ON_DISCONNECT, val)
    assert oc._fresh_conn_on_disconnect_enabled() is True


# ── P1-1 generator provider FANOUT gate (Codex+Fable gate-fix) ───────────────────────────────────
def test_generator_routing_pinned_by_default(monkeypatch):
    # Gate-fix P1-1: the generator `order`/`ignore` pins are RESTORED in the yaml, so
    # role_provider_routing("generator") returns the ranked healthy chain (byte-identical to the pre-B3
    # pinned routing). The unpinned FANOUT is now behind PG_GENERATOR_PROVIDER_FANOUT, applied in
    # openrouter_client — NOT by removing the yaml pins.
    from src.polaris_graph.roles import provider_routing as pr

    monkeypatch.delenv("PG_OPENROUTER_PROVIDER_ROUTING", raising=False)  # routing enabled by default
    monkeypatch.delenv("PG_PROVIDER_ROUTING_CONFIG", raising=False)      # use the committed config
    pr.reset_cache()
    try:
        gen = pr.role_provider_routing("generator")
        assert gen is not None
        assert gen["order"] == ["friendli", "novita", "z-ai", "phala"]
        assert gen["ignore"] == [
            "deepinfra", "fireworks", "cloudflare", "atlas-cloud", "baidu",
            "gmicloud", "wandb", "siliconflow", "streamlake",
        ]
        # The judge is intentionally unpinned (unchanged) — sanity that "None" is the unpinned shape.
        assert pr.role_provider_routing("judge") is None
        # The mirror stays pinned with a real order chain (only the generator gating was touched).
        mirror = pr.role_provider_routing("mirror")
        assert mirror is not None and mirror["order"]
    finally:
        pr.reset_cache()


def test_generator_provider_fanout_default_off(monkeypatch):
    monkeypatch.delenv(oc._ENV_GENERATOR_PROVIDER_FANOUT, raising=False)
    assert oc._generator_provider_fanout_enabled() is False


@pytest.mark.parametrize("val", ["0", "", "false", "off", "no", "nonsense"])
def test_generator_provider_fanout_falsy(monkeypatch, val):
    monkeypatch.setenv(oc._ENV_GENERATOR_PROVIDER_FANOUT, val)
    assert oc._generator_provider_fanout_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "on", "yes", "YES"])
def test_generator_provider_fanout_truthy(monkeypatch, val):
    monkeypatch.setenv(oc._ENV_GENERATOR_PROVIDER_FANOUT, val)
    assert oc._generator_provider_fanout_enabled() is True
