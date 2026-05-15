"""I-arch-001c — TEMPLATE_TO_SCOPE_DOMAIN mapping coverage.

Per Codex iter-1 P3 nudge: derive the template set from
polaris_v6.templates.registry.list_template_ids() so future v6 templates
cannot silently fall through to a default policy mapping.
"""

from __future__ import annotations

from polaris_graph.nodes.scope_gate import SUPPORTED_DOMAINS
from polaris_v6.queue.actors import TEMPLATE_TO_SCOPE_DOMAIN
from polaris_v6.templates.registry import list_template_ids


def test_every_v6_template_has_a_mapping() -> None:
    """Every v6 template_id (read from config/v6_templates/*.json at runtime)
    must have an explicit entry in TEMPLATE_TO_SCOPE_DOMAIN. Catches future
    templates that would otherwise silently fall through to a default."""
    v6_template_ids = set(list_template_ids())
    mapped_ids = set(TEMPLATE_TO_SCOPE_DOMAIN.keys())
    missing = v6_template_ids - mapped_ids
    assert not missing, (
        f"v6 templates {sorted(missing)!r} have no entry in "
        f"TEMPLATE_TO_SCOPE_DOMAIN — add explicit mappings."
    )


def test_every_mapping_value_is_a_supported_scope_domain() -> None:
    """Every target domain must be in scope_gate.SUPPORTED_DOMAINS or
    pipeline-A's run_scope_gate will reject the load_scope_template call."""
    for template_id, scope_domain in TEMPLATE_TO_SCOPE_DOMAIN.items():
        assert scope_domain in SUPPORTED_DOMAINS, (
            f"template_id={template_id!r} maps to "
            f"scope_domain={scope_domain!r} which is NOT in SUPPORTED_DOMAINS "
            f"{sorted(SUPPORTED_DOMAINS)!r}"
        )


def test_all_templates_use_identity_mapping() -> None:
    """Per I-rdy-005 (#501): all 8 canonical templates have their own
    config/scope_templates/<id>.yaml and are scope_gate.SUPPORTED_DOMAINS
    members, so TEMPLATE_TO_SCOPE_DOMAIN is all-identity — every template id
    IS its own scope domain. (The earlier climate/defense/housing/trade
    placeholders that fell back to a generic policy rubric were retired.)"""
    for template_id in (
        "clinical",
        "policy",
        "tech",
        "due_diligence",
        "ai_sovereignty",
        "canada_us",
        "workforce",
        "custom",
    ):
        assert TEMPLATE_TO_SCOPE_DOMAIN[template_id] == template_id, (
            f"{template_id!r} should map to itself (its scope_template exists), "
            f"but got {TEMPLATE_TO_SCOPE_DOMAIN[template_id]!r}"
        )
