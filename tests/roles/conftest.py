"""I-run11-007 (#1051): default the OpenRouter provider-routing OFF for the role unit tests so they
assert the BASE provider block (require_parameters only). The committed
`config/settings/openrouter_provider_routing.yaml` would otherwise inject order/ignore/allow_fallbacks
into every built body and is live-data-dependent. The dedicated `test_provider_routing.py` re-enables
routing against a FIXTURE config to exercise the feature deterministically.
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
