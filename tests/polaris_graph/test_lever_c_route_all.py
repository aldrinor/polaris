"""Lever C (coverage): PG_ROUTE_ALL_BASKETS registration + kill-switch.

The routing logic itself is pre-existing (route_orphan_baskets_to_section_plans); the champion
default is now single-sourced in central config and explicit 0 remains the rollback path.
"""
import pytest

import src.polaris_graph.generator.verified_compose as vc
from src.polaris_graph.settings import resolve


def test_registered_in_central_config(monkeypatch):
    monkeypatch.delenv("PG_ROUTE_ALL_BASKETS", raising=False)
    # Champion behavior is single-sourced centrally; run recipes carry no override.
    assert resolve("PG_ROUTE_ALL_BASKETS") == "1"


def test_central_default_on(monkeypatch):
    monkeypatch.delenv("PG_ROUTE_ALL_BASKETS", raising=False)
    assert vc.route_all_baskets_enabled() is True


@pytest.mark.parametrize("val", ["1", "true", "on", "yes", "TRUE", "On"])
def test_truthy_arms(monkeypatch, val):
    monkeypatch.setenv("PG_ROUTE_ALL_BASKETS", val)
    assert vc.route_all_baskets_enabled() is True


@pytest.mark.parametrize("val", ["", "0", "false", "off", "no"])
def test_off_tokens_stay_off(monkeypatch, val):
    monkeypatch.setenv("PG_ROUTE_ALL_BASKETS", val)
    assert vc.route_all_baskets_enabled() is False


def test_off_returns_plans_unchanged(monkeypatch):
    """Explicit OFF => route_orphan_baskets_to_section_plans returns the SAME plan list (byte-
    identical placement) regardless of orphan baskets."""
    monkeypatch.setenv("PG_ROUTE_ALL_BASKETS", "0")

    class _Cred:
        baskets = [object()]  # an orphan basket present

    plans = ["p1", "p2"]
    out = vc.route_orphan_baskets_to_section_plans(
        plans, _Cred(), section_plan_cls=object
    )
    assert out is plans  # unchanged identity on the OFF path


# ── Lever C — multi-citation (PG_VERIFIED_COMPOSE_MULTICITED) registration ──────────────


def test_multicited_registered_and_default_off(monkeypatch):
    monkeypatch.delenv("PG_VERIFIED_COMPOSE_MULTICITED", raising=False)
    assert resolve("PG_VERIFIED_COMPOSE_MULTICITED") == "0"
    assert vc._multicited_compose_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "on", "yes"])
def test_multicited_truthy_arms(monkeypatch, val):
    monkeypatch.setenv("PG_VERIFIED_COMPOSE_MULTICITED", val)
    assert vc._multicited_compose_enabled() is True


@pytest.mark.parametrize("val", ["", "0", "false", "off", "no"])
def test_multicited_off_tokens_stay_off(monkeypatch, val):
    monkeypatch.setenv("PG_VERIFIED_COMPOSE_MULTICITED", val)
    assert vc._multicited_compose_enabled() is False


# ── Lever C+ — marginal-coverage router (PG_ROUTE_MIN_OVERLAP / PG_ROUTE_MARGIN) ──────────


_PW = [("S1", {"ai", "labor", "automation"}), ("S2", {"wage", "income"}), ("S3", {"skill"})]


def test_router_thresholds_registered_default(monkeypatch):
    monkeypatch.delenv("PG_ROUTE_MIN_OVERLAP", raising=False)
    monkeypatch.delenv("PG_ROUTE_MARGIN", raising=False)
    assert resolve("PG_ROUTE_MIN_OVERLAP") == "1" and resolve("PG_ROUTE_MARGIN") == "0"
    assert vc._route_min_overlap() == 1 and vc._route_margin() == 0


def test_router_default_is_legacy_byte_identical():
    # min_overlap=1, margin=0 == 'route to max-overlap section when best>=1'; ties keep the FIRST.
    assert vc._best_route_target({"ai", "wage"}, _PW, 1, 0) == "S1"       # 1-1 tie -> first
    assert vc._best_route_target({"ai", "labor"}, _PW, 1, 0) == "S1"      # S1=2
    assert vc._best_route_target({"zzz"}, _PW, 1, 0) is None              # no overlap -> residual


def test_router_min_overlap_prunes_one_word_matches():
    assert vc._best_route_target({"ai"}, _PW, 2, 0) is None               # 1 < 2 -> residual
    assert vc._best_route_target({"ai", "labor"}, _PW, 2, 0) == "S1"      # 2 >= 2 -> route


def test_router_margin_prunes_near_ties():
    assert vc._best_route_target({"ai", "wage"}, _PW, 1, 1) is None       # 1 vs 1, margin 0 < 1
    assert vc._best_route_target({"ai", "labor", "wage"}, _PW, 1, 1) == "S1"  # 2 vs 1, margin 1


def test_router_thresholds_fail_safe(monkeypatch):
    monkeypatch.setenv("PG_ROUTE_MIN_OVERLAP", "garbage")
    monkeypatch.setenv("PG_ROUTE_MARGIN", "garbage")
    assert vc._route_min_overlap() == 1 and vc._route_margin() == 0      # bad value -> legacy default
