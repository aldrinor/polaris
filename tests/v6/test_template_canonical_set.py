"""I-rdy-005 (#501) — template-set drift guard.

`config/scope_templates/` is the single source of truth for the canonical 8
templates. This test asserts EXACT set-equality of the canonical 8 across every
id-carrying surface in the codebase, so a future edit that adds / removes /
renames a template on one surface but not the others fails CI.

This is the enforceable "zero template mismatch" guarantee for I-rdy-005.
"""

from __future__ import annotations

import re
import sys
import typing
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = str(REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# The canonical 8 — the one set every surface must agree on.
CANONICAL_8 = {
    "clinical",
    "policy",
    "tech",
    "due_diligence",
    "ai_sovereignty",
    "canada_us",
    "workforce",
    "custom",
}


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def _ids_in_block(text: str, start_marker: str, end_marker: str = "];") -> set[str]:
    """Extract `id: "<id>"` literals from the block delimited by the markers."""
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return set(re.findall(r'id:\s*"([a-z_]+)"', text[start:end]))


# ── filesystem source of truth ───────────────────────────────────────────────


def test_scope_templates_dir_is_canonical_8():
    stems = {p.stem for p in (REPO_ROOT / "config" / "scope_templates").glob("*.yaml")}
    assert stems == CANONICAL_8


def test_v6_templates_dir_is_canonical_8():
    stems = {p.stem for p in (REPO_ROOT / "config" / "v6_templates").glob("*.json")}
    assert stems == CANONICAL_8


# ── backend ──────────────────────────────────────────────────────────────────


def test_registry_list_template_ids_is_canonical_8():
    from polaris_v6.templates.registry import list_template_ids

    assert set(list_template_ids()) == CANONICAL_8


def test_scope_gate_supported_domains_is_canonical_8():
    from polaris_graph.nodes.scope_gate import SUPPORTED_DOMAINS

    assert set(SUPPORTED_DOMAINS) == CANONICAL_8


def test_run_request_template_id_literal_is_canonical_8():
    from polaris_v6.schemas.run_request import TemplateId

    assert set(typing.get_args(TemplateId)) == CANONICAL_8


def test_actors_template_to_scope_domain_is_canonical_8_identity():
    from polaris_v6.queue.actors import TEMPLATE_TO_SCOPE_DOMAIN

    assert set(TEMPLATE_TO_SCOPE_DOMAIN) == CANONICAL_8
    # All-identity: every canonical template id IS its own scope domain.
    for template_id, scope_domain in TEMPLATE_TO_SCOPE_DOMAIN.items():
        assert template_id == scope_domain


def test_v30_synthesizer_dicts_are_canonical_8():
    from polaris_graph.v30_contract_synthesizer import (
        _REQUIRED_FIELDS_FOR_TEMPLATE,
        _TYPE_FOR_TEMPLATE,
    )

    assert set(_TYPE_FOR_TEMPLATE) == CANONICAL_8
    assert set(_REQUIRED_FIELDS_FOR_TEMPLATE) == CANONICAL_8


# ── frontend (parsed textually — no node runtime needed) ─────────────────────


def test_frontend_api_ts_template_id_union_is_canonical_8():
    text = _read("web/lib/api.ts")
    m = re.search(r"export type TemplateId\s*=([^;]+);", text)
    assert m, "TemplateId union not found in web/lib/api.ts"
    assert set(re.findall(r'"([a-z_]+)"', m.group(1))) == CANONICAL_8


def test_frontend_landing_page_templates_is_canonical_8():
    assert _ids_in_block(_read("web/app/page.tsx"), "const templates") == CANONICAL_8


def test_frontend_dashboard_fallback_is_canonical_8():
    assert (
        _ids_in_block(_read("web/app/dashboard/page.tsx"), "FALLBACK_TEMPLATES")
        == CANONICAL_8
    )


# ── benchmark ────────────────────────────────────────────────────────────────


def test_benchmark_carney_templates_is_canonical_8():
    text = _read("scripts/v6/benchmark/api_benchmark_runner.py")
    m = re.search(r"CARNEY_TEMPLATES\s*=\s*frozenset\(\{([^}]+)\}\)", text)
    assert m, "CARNEY_TEMPLATES frozenset not found in api_benchmark_runner.py"
    assert set(re.findall(r'"([a-z_]+)"', m.group(1))) == CANONICAL_8
