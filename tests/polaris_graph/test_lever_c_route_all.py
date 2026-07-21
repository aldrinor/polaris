"""Lever C (coverage): PG_ROUTE_ALL_BASKETS registration + kill-switch.

The routing logic itself is pre-existing (route_orphan_baskets_to_section_plans); this change only
moves the flag into central config (resolve) and confirms the default-OFF byte-identity contract.
"""
import pytest

import src.polaris_graph.generator.verified_compose as vc
from src.polaris_graph.settings import resolve


def test_registered_in_central_config(monkeypatch):
    monkeypatch.delenv("PG_ROUTE_ALL_BASKETS", raising=False)
    # resolve() must not KeyError (registered) and default to '0'.
    assert resolve("PG_ROUTE_ALL_BASKETS") == "0"


def test_default_off(monkeypatch):
    monkeypatch.delenv("PG_ROUTE_ALL_BASKETS", raising=False)
    assert vc.route_all_baskets_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "on", "yes", "TRUE", "On"])
def test_truthy_arms(monkeypatch, val):
    monkeypatch.setenv("PG_ROUTE_ALL_BASKETS", val)
    assert vc.route_all_baskets_enabled() is True


@pytest.mark.parametrize("val", ["", "0", "false", "off", "no"])
def test_off_tokens_stay_off(monkeypatch, val):
    monkeypatch.setenv("PG_ROUTE_ALL_BASKETS", val)
    assert vc.route_all_baskets_enabled() is False


def test_off_returns_plans_unchanged(monkeypatch):
    """OFF (default) => route_orphan_baskets_to_section_plans returns the SAME plan list (byte-
    identical placement) regardless of orphan baskets."""
    monkeypatch.delenv("PG_ROUTE_ALL_BASKETS", raising=False)

    class _Cred:
        baskets = [object()]  # an orphan basket present

    plans = ["p1", "p2"]
    out = vc.route_orphan_baskets_to_section_plans(
        plans, _Cred(), section_plan_cls=object
    )
    assert out is plans  # unchanged identity on the OFF path
