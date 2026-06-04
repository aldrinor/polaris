"""I-run11-007 (#1051): default OpenRouter provider-routing OFF for the dr_benchmark tests so they
assert the BASE provider block, not the live-data-dependent ranked routing from
`config/settings/openrouter_provider_routing.yaml`. Routing has dedicated coverage in
`tests/roles/test_provider_routing.py`.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_provider_routing(monkeypatch):
    monkeypatch.setenv("PG_OPENROUTER_PROVIDER_ROUTING", "0")
    from src.polaris_graph.roles import provider_routing

    provider_routing.reset_cache()
    yield
    provider_routing.reset_cache()
