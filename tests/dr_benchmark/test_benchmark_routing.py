"""Runtime-routing tests for the 5 LOCKED golden DRB-EN benchmark questions
(I-meta-002 PR-11 / #937).

NO NETWORK, NO SPEND. These tests prove the wiring landed in PR-11: the 5
benchmark questions are registered in `scripts.run_honest_sweep_r3.SWEEP_QUERIES`
with a domain whose scope template carries their frozen native
`per_query_report_contract` entry, so the 4-role Gate-B builder can reach the
required-element denominator at runtime.

For each benchmark slug they assert:
  (a) a SWEEP_QUERIES entry exists with that slug AND the expected domain; and
  (b) load_scope_template(domain) then
      native_gate_b_inputs.load_required_entities(template, slug) resolves to a
      NON-EMPTY required_entities list (the contract is reachable at runtime).

They ALSO assert that a deliberately-wrong slug fails CLOSED
(`load_required_entities` raises) — proving a routing typo can never silently
skip the safety gate. All resolution is pure config (YAML read + dict index);
nothing here performs a live fetch or spends.
"""

from __future__ import annotations

import importlib

import pytest

from src.polaris_graph.nodes.scope_gate import load_scope_template
from src.polaris_graph.roles.native_gate_b_inputs import load_required_entities

# The 5 LOCKED golden DRB-EN benchmark slugs -> the domain whose scope template
# holds each one's frozen per_query_report_contract entry (PR-10 commit bc926b3a).
# Source of the slug<->domain truth: .codex/I-safety-002b/golden_questions_locked.md
# (#75/#76/#78 clinical, #72 workforce, #90 policy).
_EXPECTED_ROUTING: dict[str, str] = {
    "drb_75_metal_ions_cvd": "clinical",
    "drb_76_gut_microbiota_crc": "clinical",
    "drb_78_parkinsons_dbs": "clinical",
    "drb_72_ai_labor": "workforce",
    "drb_90_adas_liability": "policy",
}


def _sweep_queries() -> list[dict]:
    """Import the sweep module fresh and return its SWEEP_QUERIES registry.

    The import itself must be no-network (module-level import is the established
    pattern across tests/polaris_graph/*); registering a benchmark question must
    never trigger a live fetch.
    """
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    return sweep.SWEEP_QUERIES


def _entry_for_slug(slug: str) -> dict:
    matches = [q for q in _sweep_queries() if q.get("slug") == slug]
    assert matches, f"no SWEEP_QUERIES entry registered for slug {slug!r}"
    assert len(matches) == 1, (
        f"slug {slug!r} is registered {len(matches)} times in SWEEP_QUERIES; "
        f"each benchmark slug must be registered exactly once"
    )
    return matches[0]


@pytest.mark.parametrize(
    ("slug", "expected_domain"), sorted(_EXPECTED_ROUTING.items())
)
def test_benchmark_slug_registered_with_expected_domain(
    slug: str, expected_domain: str
) -> None:
    """(a) Each benchmark slug is registered in SWEEP_QUERIES with the right domain."""
    entry = _entry_for_slug(slug)
    assert entry["domain"] == expected_domain, (
        f"slug {slug!r} registered with domain {entry['domain']!r}, "
        f"expected {expected_domain!r}"
    )


@pytest.mark.parametrize(
    ("slug", "expected_domain"), sorted(_EXPECTED_ROUTING.items())
)
def test_benchmark_contract_reachable_at_runtime(
    slug: str, expected_domain: str
) -> None:
    """(b) The native contract resolves to a NON-EMPTY required_entities list.

    Mirrors the runtime resolution path: load the registered domain's scope
    template, then key the per_query_report_contract by the question slug. A
    non-empty list proves the 4-role Gate-B builder can build a real coverage
    denominator (never a vacuous empty-denominator pass).
    """
    template = load_scope_template(expected_domain)
    entities = load_required_entities(template, slug)
    assert isinstance(entities, list) and entities, (
        f"contract for slug {slug!r} in domain {expected_domain!r} resolved to "
        f"an empty/absent required_entities list"
    )


def test_registration_domain_matches_contract_template_for_every_benchmark() -> None:
    """End-to-end: the domain each slug is REGISTERED with is the domain whose
    template actually carries its contract.

    This is the routing invariant that PR-11 fixes — a slug registered under a
    domain whose template lacks its contract would fail-close at runtime and
    silently skip the 4-role safety gate.
    """
    for slug, expected_domain in _EXPECTED_ROUTING.items():
        entry = _entry_for_slug(slug)
        registered_domain = entry["domain"]
        template = load_scope_template(registered_domain)
        # Must not raise: the contract is reachable via the REGISTERED domain.
        entities = load_required_entities(template, slug)
        assert entities, (
            f"slug {slug!r} registered under domain {registered_domain!r} but "
            f"that template carries no usable contract"
        )
        assert registered_domain == expected_domain


def test_wrong_slug_fails_closed() -> None:
    """A deliberately-wrong slug raises — proving the M3a builder guard fails
    CLOSED (a routing typo can never silently skip the safety gate)."""
    template = load_scope_template("clinical")
    with pytest.raises(ValueError):
        load_required_entities(template, "drb_999_definitely_not_a_real_slug")
