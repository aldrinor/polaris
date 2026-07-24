"""Regression tests for the CANONICAL-family judge-lane guard (Gate-B 4-role independence).

Covers the alias-bypass hole Sol caught (raw provider-prefix distinctness let a canonical-alias
re-pick — e.g. Judge ``moonshot/...`` vs Generator ``moonshotai/...``, both lineage ``kimi`` —
slip past the 4-distinct-family invariant) and the legitimate distinct-family judge override that
unblocks a Kimi-K3 generator run. The guard now derives the CANONICAL lineage (via
``openrouter_client.family_from_model``) for all four active slugs, and honors an explicit
``PG_<ROLE>_MODEL`` override while the downstream all-distinct gate still enforces independence.
"""
import os

import pytest

from scripts.dr_benchmark.run_gate_b import assert_four_role_families_distinct


_ROLE_ENVS = (
    "PG_GENERATOR_MODEL", "PG_BENCHMARK_JUDGE_MODEL", "PG_MIRROR_MODEL", "PG_SENTINEL_MODEL",
)


def _set(monkeypatch, gen, *, judge=None, mirror=None, sentinel=None):
    for k in _ROLE_ENVS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PG_GENERATOR_MODEL", gen)
    if judge is not None:
        monkeypatch.setenv("PG_BENCHMARK_JUDGE_MODEL", judge)
    if mirror is not None:
        monkeypatch.setenv("PG_MIRROR_MODEL", mirror)
    if sentinel is not None:
        monkeypatch.setenv("PG_SENTINEL_MODEL", sentinel)


def test_distinct_kimi_generator_plus_deepseek_judge_passes(monkeypatch):
    """The intended unblock config: kimi-k3 generator + deepseek judge -> 4 distinct canonical families."""
    _set(monkeypatch, "moonshotai/kimi-k3", judge="deepseek/deepseek-v4-pro")
    fams = assert_four_role_families_distinct()  # returns provider-prefix labels
    assert fams["generator"] == "moonshotai"
    assert fams["judge"] == "deepseek"
    assert len(set(fams.values())) == 4  # all distinct (prefix AND canonical)


def test_judge_generator_exact_prefix_collision_raises(monkeypatch):
    """Judge == Generator family (kimi) must raise (self-verify)."""
    _set(monkeypatch, "moonshotai/kimi-k3", judge="moonshotai/kimi-k2.6")
    with pytest.raises(RuntimeError):
        assert_four_role_families_distinct()


def test_judge_mirror_exact_prefix_collision_raises(monkeypatch):
    """Judge (z-ai/glm -> glm) collides with the default Mirror (glm) -> raise."""
    _set(monkeypatch, "moonshotai/kimi-k3", judge="z-ai/glm-5.1")
    with pytest.raises(RuntimeError):
        assert_four_role_families_distinct()


def test_kimi_alias_bypass_is_caught(monkeypatch):
    """The bug Sol found: Generator moonshotai/* + Judge moonshot/* carry DISTINCT prefixes but are BOTH
    canonical ``kimi`` — the prefix guard passes, so ONLY the CANONICAL guard catches this self-verify
    collision. ``match="CANONICAL"`` asserts the canonical guard (not the prefix guard) fired."""
    _set(monkeypatch, "moonshotai/kimi-k3", judge="moonshot/kimi-k2.6")
    with pytest.raises(RuntimeError, match="CANONICAL"):
        assert_four_role_families_distinct()


def test_glm_alias_bypass_is_caught(monkeypatch):
    """Generator z-ai/* (+ default z-ai mirror, the allowed pair) + Judge zhipuai/* are all canonical
    ``glm`` with DISTINCT prefixes for the judge — the prefix guard passes (judge prefix zhipuai is
    distinct), so ONLY the CANONICAL guard catches the judge==generator ``glm`` lineage. No mirror
    override (that would prefix-collide with the sentinel and mask the canonical path)."""
    _set(monkeypatch, "z-ai/glm-5.2", judge="zhipuai/glm-4")
    with pytest.raises(RuntimeError, match="CANONICAL"):
        assert_four_role_families_distinct()


def test_allowed_generator_mirror_collision_passes_but_third_raises(monkeypatch):
    """The lock's one allowed collision (generator+mirror same family) passes; a THIRD same-family role raises."""
    # gen glm + default mirror glm = the allowed pair -> passes
    _set(monkeypatch, "z-ai/glm-5.2")
    assert_four_role_families_distinct()
    # add a third glm role (sentinel) -> raises
    _set(monkeypatch, "z-ai/glm-5.2", sentinel="zhipuai/glm-4")
    with pytest.raises(RuntimeError):
        assert_four_role_families_distinct()


def test_off_state_default_no_override_passes(monkeypatch):
    """No judge override: the default judge resolves to its canonical lane (kimi) and passes with a
    glm generator (generator+mirror allowed collision, judge kimi + sentinel minimax distinct)."""
    for k in _ROLE_ENVS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PG_GENERATOR_MODEL", "z-ai/glm-5.2")
    fams = assert_four_role_families_distinct()  # provider-prefix labels
    assert fams["judge"] == "moonshotai"
    assert fams["sentinel"] == "minimax"
