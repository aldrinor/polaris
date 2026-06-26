"""I-wire-008 (#1322) — JUDGE-chain provider-health deny-list filter (offline, no network).

`PG_JUDGE_UNHEALTHY_PROVIDERS` lets an operator drop a flaky host (e.g. novita that returns
no-choices bodies) from the side-judge rotation chains so calls land on a healthy host first.
LAW VI: env-driven, default-safe (empty => byte-identical). The filter PRESERVES surviving order
and NEVER strands a judge with an empty chain (logs + falls back to the original on mis-config).
"""
import pytest

from src.polaris_graph.roles import provider_routing as pr


def test_default_no_denylist_is_byte_identical(monkeypatch):
    monkeypatch.delenv("PG_JUDGE_UNHEALTHY_PROVIDERS", raising=False)
    order = ["friendli", "novita", "z-ai", "phala"]
    assert pr.filter_unhealthy(order) == order
    assert pr.unhealthy_provider_slugs() == set()


def test_denylist_drops_named_host_preserving_order(monkeypatch):
    monkeypatch.setenv("PG_JUDGE_UNHEALTHY_PROVIDERS", "novita")
    assert pr.filter_unhealthy(["friendli", "novita", "z-ai", "phala"]) == [
        "friendli", "z-ai", "phala",
    ]


def test_denylist_is_case_insensitive_and_trims(monkeypatch):
    monkeypatch.setenv("PG_JUDGE_UNHEALTHY_PROVIDERS", " Novita , Z-AI ")
    assert pr.unhealthy_provider_slugs() == {"novita", "z-ai"}
    assert pr.filter_unhealthy(["friendli", "novita", "z-ai", "phala"]) == ["friendli", "phala"]


def test_denylist_emptying_chain_warns_and_keeps_original(monkeypatch, caplog):
    monkeypatch.setenv("PG_JUDGE_UNHEALTHY_PROVIDERS", "friendli,novita,z-ai,phala")
    original = ["friendli", "novita", "z-ai", "phala"]
    with caplog.at_level("WARNING"):
        out = pr.filter_unhealthy(original)
    # Never strand a judge with no provider — fall back to the original (operator mis-config).
    assert out == original
    assert any("would empty the judge chain" in r.message for r in caplog.records)


def test_filter_handles_empty_and_none_order(monkeypatch):
    monkeypatch.setenv("PG_JUDGE_UNHEALTHY_PROVIDERS", "novita")
    assert pr.filter_unhealthy([]) == []
    assert pr.filter_unhealthy(None) == []
