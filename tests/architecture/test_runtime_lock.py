"""I-meta-001 (#933) — tests for the runtime architecture lock + N-way family check.

Codex APPROVE_FOR_IMPLEMENTATION iter 2: every solution in S1-S9 ships with a regression test.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.llm.openrouter_client import (
    _FAMILY_PREFIXES,
    family_from_model,
    validate_role_families,
)


# --- Family registry covers all 4 locked roles ---

def test_family_registry_has_cohere():
    """I-meta-001 V4 regression — cohere family added for Mirror role."""
    assert "cohere" in _FAMILY_PREFIXES
    assert family_from_model("cohere/command-a-plus") == "cohere"
    assert family_from_model("CohereLabs/command-a-plus-05-2026-bf16") == "cohere"


def test_family_registry_has_ibm_granite():
    """I-meta-001 V4 regression — ibm-granite family added for Sentinel role."""
    assert "ibm-granite" in _FAMILY_PREFIXES
    assert family_from_model("ibm-granite/granite-guardian-4.1-8b") == "ibm-granite"


def test_family_registry_existing_families_unchanged():
    """Don't regress the existing 10 families."""
    assert family_from_model("deepseek/deepseek-v4-pro") == "deepseek"
    assert family_from_model("qwen/qwen3.6-35b-a3b") == "qwen"
    assert family_from_model("google/gemma-4-31b-it") == "gemma"
    assert family_from_model("meta-llama/Llama-4-Maverick") == "llama"


# --- N-way family segregation ---

_LOCKED_4_ROLE_MAP = {
    "generator": "deepseek/deepseek-v4-pro",
    "mirror":    "cohere/command-a-plus",
    "sentinel":  "ibm-granite/granite-guardian-4.1-8b",
    "judge":     "qwen/qwen3.6-35b-a3b",
}


def test_validate_role_families_passes_for_locked_stack():
    """The locked 4-role architecture must pass the N-way check."""
    out = validate_role_families(_LOCKED_4_ROLE_MAP)
    assert out == {
        "generator": "deepseek",
        "mirror":    "cohere",
        "sentinel":  "ibm-granite",
        "judge":     "qwen",
    }


def test_validate_role_families_fails_on_unknown_model():
    """Unknown model family must fail closed — no silent fallback."""
    with pytest.raises(RuntimeError, match="family='unknown'"):
        validate_role_families({"generator": "made-up/model"})


def test_validate_role_families_fails_on_same_family_collision():
    """Two roles sharing a family must fail under all_distinct (default)."""
    with pytest.raises(RuntimeError, match="appears in both"):
        validate_role_families({
            "generator": "deepseek/deepseek-v4-pro",
            "mirror":    "deepseek/deepseek-v4-flash",  # same family — fail
        })


def test_validate_role_families_permit_collisions_policy():
    """permit_collisions policy returns even when roles share families."""
    out = validate_role_families({
        "generator": "deepseek/deepseek-v4-pro",
        "mirror":    "deepseek/deepseek-v4-flash",
    }, policy="permit_collisions")
    assert out["generator"] == "deepseek"
    assert out["mirror"] == "deepseek"


def test_validate_role_families_allowed_collisions_specific_pair():
    """A specific declared-allowed collision passes; others still fail."""
    out = validate_role_families({
        "generator": "deepseek/deepseek-v4-pro",
        "mirror":    "deepseek/deepseek-v4-flash",  # allowed
        "judge":     "qwen/qwen3.6-35b-a3b",
    }, allowed_collisions=[("generator", "mirror")])
    assert out["generator"] == "deepseek"
    assert out["mirror"] == "deepseek"


# --- Lock YAML loads + verifier reports OK ---

def test_runtime_lock_yaml_loads_and_declares_4_roles():
    from scripts.architecture.verify_lock import load_lock
    lock = load_lock()
    assert set(lock["required_roles"].keys()) == {"generator", "mirror", "sentinel", "judge"}


def test_runtime_lock_declared_families_present_in_registry():
    """Every family declared in the lock YAML must exist in the registry."""
    from scripts.architecture.verify_lock import load_lock
    lock = load_lock()
    for role, spec in lock["required_roles"].items():
        family = spec["family"]
        assert family in _FAMILY_PREFIXES, (
            f"lock declares family {family!r} for role {role!r} but "
            f"_FAMILY_PREFIXES is missing it"
        )


def test_verify_lock_against_code_passes_for_clean_state():
    """The runtime should match the lock when family registry + lock YAML are consistent."""
    from scripts.architecture.verify_lock import verify_lock_against_code
    results = verify_lock_against_code()
    assert set(results.keys()) == {"generator", "mirror", "sentinel", "judge"}
    for role, r in results.items():
        assert r["ok"] is True, f"role {role!r} unexpectedly failed: {r}"


# --- I-meta-002 sub-PR-1: status-independent consistency gate + slug fix ---

def test_verify_consistency_exit_0_on_clean_tree():
    """verify_consistency() returns 0 on a clean tree, regardless of lock status."""
    from scripts.architecture.verify_lock import verify_consistency
    assert verify_consistency() == 0


def test_verify_consistency_fails_on_code_default_divergence(monkeypatch):
    """A code default diverging from the lock model_slug must raise LockMismatch."""
    from scripts.architecture.verify_lock import (
        LockMismatch,
        verify_lock_against_code,
    )
    from src.polaris_graph.llm import openrouter_client

    monkeypatch.setattr(openrouter_client, "PG_JUDGE_MODEL", "qwen/wrong-slug")
    with pytest.raises(LockMismatch):
        verify_lock_against_code()


def test_judge_slug_is_corrected():
    """The lock judge model_slug is the corrected (single-hyphen) slug."""
    from scripts.architecture.verify_lock import load_lock
    lock = load_lock()
    assert lock["required_roles"]["judge"]["model_slug"] == "qwen/qwen3.6-35b-a3b"
