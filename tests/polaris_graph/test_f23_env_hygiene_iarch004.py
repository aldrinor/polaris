"""F23 (I-arch-004 A3) — .env-ification hygiene grab-bag.

The LAST A3 fix. Pure hygiene: every value that F23 lifts into an env var
keeps its CURRENT literal as the DEFAULT, so behavior is BYTE-IDENTICAL when
the env var is unset. These tests prove exactly that (default-equals-old) and
that an override is honored.

Two test shapes are used, matched to how each value is read:

1. **Module-constant reads** (research_planner DEFAULT_MAX_SUBQUERIES /
   MIN_SUBQUERIES) are read at import time, so they are proven BEHAVIORALLY:
   reload with env unset -> old literal; reload with env set -> override.

2. **Call-site reads** (fact_dedup / audit-critique max_tokens; the sweep
   caller's outline_max_tokens / section_temperature) are read inside the
   function body via ``os.getenv(NAME, "DEFAULT")`` at call time. A live call
   would cost money + need an LLM, so they are proven by a SOURCE-level
   byte-identical assertion: the exact ``os.getenv(NAME, "<old literal>")``
   string must appear in the function source. This proves (a) the env name is
   wired to the real call site and (b) the default equals the old literal
   byte-for-byte. This is the same static-guard convention used by the M-31 /
   M-33 regression tests for the same call site.

NONE of this touches a faithfulness gate (strict_verify / NLI / 4-role D8 /
provenance / span-grounding) — F23 is hygiene only.
"""
from __future__ import annotations

import inspect
import pathlib
import re

import pytest


# ──────────────────────────────────────────────────────────────────────────
# 1. research_planner module constants — behavioral default-equals-old.
#    Proven in a SUBPROCESS so the live module is never reloaded (reloading
#    research_planner would swap its class identities and pollute sibling
#    planning tests that import the same symbols). The subprocess imports the
#    real module under the chosen env and prints the resolved constants.
# ──────────────────────────────────────────────────────────────────────────

_PLANNER_MAX_ENV = "PG_PLANNER_MAX_SUBQUERIES"
_PLANNER_MIN_ENV = "PG_PLANNER_MIN_SUBQUERIES"
_PLANNER_MAX_OLD = 40
_PLANNER_MIN_OLD = 12


def _resolve_planner_consts(env_overrides: dict[str, str | None]) -> tuple[int, int]:
    """Import research_planner in a clean subprocess under the given env and
    return (DEFAULT_MAX_SUBQUERIES, MIN_SUBQUERIES). ``None`` value => unset."""
    import os
    import subprocess
    import sys as _sys

    child_env = dict(os.environ)
    # Strip both knobs first so the parent's env can't leak a stale value.
    for key in (_PLANNER_MAX_ENV, _PLANNER_MIN_ENV):
        child_env.pop(key, None)
    for key, val in env_overrides.items():
        if val is None:
            child_env.pop(key, None)
        else:
            child_env[key] = val
    # The repo root is two parents up from tests/polaris_graph/.
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    child_env["PYTHONPATH"] = (
        str(repo_root / "src") + os.pathsep + child_env.get("PYTHONPATH", "")
    )
    code = (
        "import src.polaris_graph.planning.research_planner as rp;"
        "print(rp.DEFAULT_MAX_SUBQUERIES, rp.MIN_SUBQUERIES)"
    )
    out = subprocess.check_output(
        [_sys.executable, "-c", code],
        env=child_env,
        cwd=str(repo_root),
        text=True,
    )
    a, b = out.split()
    return int(a), int(b)


def test_planner_subqueries_default_equals_old():
    """Unset env => the historical literals 40 / 12 (byte-identical)."""
    max_v, min_v = _resolve_planner_consts(
        {_PLANNER_MAX_ENV: None, _PLANNER_MIN_ENV: None}
    )
    assert max_v == _PLANNER_MAX_OLD
    assert min_v == _PLANNER_MIN_OLD


def test_planner_subqueries_read_override():
    """Env override is honored by both planner bounds."""
    max_v, min_v = _resolve_planner_consts(
        {_PLANNER_MAX_ENV: "55", _PLANNER_MIN_ENV: "7"}
    )
    assert max_v == 55
    assert min_v == 7


# ──────────────────────────────────────────────────────────────────────────
# 2. Call-site env reads — source-level byte-identical proof.
#    Each tuple: (callable_or_source_provider, env_name, old_literal_default).
# ──────────────────────────────────────────────────────────────────────────


def _fact_dedup_callsite_source() -> str:
    """The fact-dedup rewrite call lives in a nested closure inside
    generate_multi_section_report; grab the whole function source."""
    from src.polaris_graph.generator import multi_section_generator as msg

    return inspect.getsource(msg.generate_multi_section_report)


def _audit_critique_source() -> str:
    from src.polaris_graph.tools import react_agent as ra

    return inspect.getsource(ra)


@pytest.mark.parametrize(
    "source_fn,env_name,old_default",
    [
        (_fact_dedup_callsite_source, "PG_FACT_DEDUP_MAX_TOKENS", "2048"),
        (_audit_critique_source, "PG_AUDIT_CRITIQUE_MAX_TOKENS", "2048"),
    ],
)
def test_callsite_env_default_equals_old_literal(source_fn, env_name, old_default):
    """The exact ``os.getenv(NAME, "<old literal>")`` (or os.environ.get)
    string must be present at the call site. This proves the env var is wired
    AND its default is byte-identical to the value the code used before F23."""
    src = source_fn()
    # Accept either os.getenv(...) or os.environ.get(...) forms.
    pat = re.compile(
        r"os\.(?:getenv|environ\.get)\(\s*[\"']"
        + re.escape(env_name)
        + r"[\"']\s*,\s*[\"']"
        + re.escape(old_default)
        + r"[\"']\s*\)"
    )
    assert pat.search(src), (
        f"{env_name} with byte-identical default {old_default!r} not found at "
        f"the call site. F23 requires the env-read default to equal the old "
        f"literal so an unset env is byte-identical."
    )


# ──────────────────────────────────────────────────────────────────────────
# 3. Sweep-caller env reads (outline_max_tokens / section_temperature) +
#    M-31 guard preservation in the new env form.
# ──────────────────────────────────────────────────────────────────────────

_SWEEP_SCRIPT = pathlib.Path("scripts/run_honest_sweep_r3.py")


def _sweep_source() -> str:
    assert _SWEEP_SCRIPT.is_file(), f"{_SWEEP_SCRIPT} not found"
    return _SWEEP_SCRIPT.read_text(encoding="utf-8")


def test_sweep_outline_max_tokens_env_default_equals_old():
    """outline_max_tokens at the active sweep caller is now env-driven with
    the historical literal 2500 as default (byte-identical when unset)."""
    src = _sweep_source()
    pat = re.compile(
        r"os\.environ\.get\(\s*[\"']PG_MS_OUTLINE_MAX_TOKENS[\"']\s*,\s*"
        r"[\"']2500[\"']\s*,?\s*\)"
    )
    assert pat.search(src), (
        "PG_MS_OUTLINE_MAX_TOKENS with default 2500 not found at the sweep "
        "caller; F23 must keep the M-31 literal as the byte-identical default."
    )


def test_sweep_outline_max_tokens_default_preserves_m31_floor():
    """M-31 protection preserved across the env-ification: the new env-read
    default for outline_max_tokens must be >= 2500 (the V19/V20 JSON-truncation
    floor). M-31's bare-digit regex no longer matches the env form, so this
    test carries the floor guarantee forward in the new shape."""
    src = _sweep_source()
    m = re.search(
        r"PG_MS_OUTLINE_MAX_TOKENS[\"']\s*,\s*[\"'](\d+)[\"']",
        src,
    )
    assert m is not None, "outline_max_tokens env default literal not found"
    assert int(m.group(1)) >= 2500, (
        f"outline_max_tokens env default {m.group(1)} is below the M-31 "
        f"floor of 2500 — would re-introduce the JSON-truncation failure."
    )


def test_sweep_section_temperature_env_default_equals_old():
    """section_temperature at the active sweep caller is now env-driven with
    the historical literal 0.3 as default (byte-identical when unset)."""
    src = _sweep_source()
    pat = re.compile(
        r"os\.environ\.get\(\s*[\"']PG_SECTION_TEMPERATURE[\"']\s*,\s*"
        r"[\"']0\.3[\"']\s*,?\s*\)"
    )
    assert pat.search(src), (
        "PG_SECTION_TEMPERATURE with default 0.3 not found at the sweep "
        "caller; F23 must keep the literal 0.3 as the byte-identical default."
    )
