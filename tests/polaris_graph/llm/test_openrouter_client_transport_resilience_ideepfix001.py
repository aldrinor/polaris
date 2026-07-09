"""I-deepfix-001 B3 (#1370) — offline tests for the WT-5 openrouter_client + routing-config fixes.

Pure Python, no network. Covers:
  * ``_client_limits_from_env`` — UNSET (both) => None (byte-identical legacy client, NO limits= kwarg);
    SET => an httpx.Limits carrying exactly the env-overridden field(s), httpx defaults elsewhere,
  * ``_fresh_conn_on_disconnect_enabled`` — DEFAULT OFF + truthy parse,
  * the generator-UNPIN config edit: ``role_provider_routing("generator")`` now returns None (order
    removed => allow_fallbacks:true burst-spread), while mirror stays pinned (only generator touched).
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


# ── B3(c) generator UNPIN in openrouter_provider_routing.yaml ────────────────────────────────────
def test_generator_routing_unpinned(monkeypatch):
    # The generator block's `order`/`ignore` are REMOVED, so role_provider_routing("generator")
    # returns None => openrouter_client keeps allow_fallbacks:true and OpenRouter spreads the burst.
    from src.polaris_graph.roles import provider_routing as pr

    monkeypatch.delenv("PG_OPENROUTER_PROVIDER_ROUTING", raising=False)  # routing enabled by default
    monkeypatch.delenv("PG_PROVIDER_ROUTING_CONFIG", raising=False)      # use the committed config
    pr.reset_cache()
    try:
        assert pr.role_provider_routing("generator") is None
        # The judge is also intentionally unpinned (unchanged) — sanity that "None" is the unpinned shape.
        assert pr.role_provider_routing("judge") is None
        # Only the generator was touched: the mirror stays pinned with a real order chain.
        mirror = pr.role_provider_routing("mirror")
        assert mirror is not None and mirror["order"]
    finally:
        pr.reset_cache()
