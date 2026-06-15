"""BUG-2 (#1262) — reasoning-budget governance for the distillate keystone.

Token-starvation class vs CLAUDE.md §9.1.8 ("reasoning always max"), fixed WITH
CARE so it does NOT reintroduce the drb_76 ReasoningFirstTruncationError (reasoning
eating the whole completion ceiling -> ZERO content) on the deliberately small calls.

What this fix does, and what these tests pin:

* The MAIN section-prose writer in the distillate path is the REDUCE call
  (`multi_section_generator` site `reasoning_max_tokens=_reduce_reasoning_tokens()`,
  call_type="section_reduce"). Its keystone-birth default (5000, #1209) sat BELOW
  deepseek-v4-pro's typical 5-18k reasoning band and below the equivalent legacy
  section writer's ~13k headroom, so a provider that honors reasoning.max_tokens
  could truncate the plan -> empty draft -> the section DROPS. The fix raises that
  budget to a sane env-driven FLOOR (`PG_DISTILL_REDUCE_REASONING_MIN_TOKENS`) and
  clamps any too-small override UP to it.
* The deliberate SMALL-call reductions are LEFT INTACT:
    - MAP per-source extraction (`_map_reasoning_tokens`, default 4096), and
    - the ≤3-sentence / JSON contract-slot calls
      (`PG_CONTRACT_SLOT_REASONING_MAX_TOKENS`, default 2048).
  Those tight budgets are what PREVENT the drb_76 empty-content collapse; maxing
  them would REGRESS drb_76. The mandatory regression assertions below pin them.

FAITHFULNESS: this fix touches reasoning BUDGET sizing only. No hard gate
(strict_verify / NLI / 4-role / span-grounding) is imported, called, or altered
here; raising the REDUCE reasoning floor can only let MORE sections finish
composing (never fewer, never a relaxed verdict).

The edited `evidence_distiller.py` lives in this isolated worktree; the test loads
it by file path so it exercises exactly the patched code, while letting its sibling
`src.polaris_graph...` imports resolve against the installed package.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

# ── Load the PATCHED evidence_distiller.py from this worktree by file path ──────
# Pre-seed sys.modules under the canonical dotted name so the module's
# `from src.polaris_graph.generator.* import ...` statements resolve against the
# installed package while THIS file's body is the worktree-edited source.
_DISTILLER_PATH = (
    Path(__file__).resolve().parents[3]
    / "src" / "polaris_graph" / "generator" / "evidence_distiller.py"
)
_MODNAME = "src.polaris_graph.generator.evidence_distiller"


def _load_patched_distiller():
    spec = importlib.util.spec_from_file_location(_MODNAME, _DISTILLER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODNAME] = module
    spec.loader.exec_module(module)
    return module


ed = _load_patched_distiller()

# Sanity: we really loaded the worktree-edited file, not some stale copy.
assert _DISTILLER_PATH.exists(), f"patched distiller missing: {_DISTILLER_PATH}"


# A defensible lower bound for "full section-prose reasoning is not starved".
# deepseek-v4-pro emits ~5-18k reasoning tokens for full prose composition; the
# keystone-birth 5000 default was below that band. Anything >= this counts as a
# sane, un-starved main-section reasoning budget.
SANE_MAIN_SECTION_REASONING_FLOOR = 8192


# ── MAIN section-prose (REDUCE) reasoning is NOT capped below a sane floor ─────
def test_reduce_reasoning_default_is_not_starved(monkeypatch):
    """Default REDUCE reasoning budget must clear the sane main-section floor."""
    monkeypatch.delenv("PG_DISTILL_REDUCE_REASONING_TOKENS", raising=False)
    monkeypatch.delenv("PG_DISTILL_REDUCE_REASONING_MIN_TOKENS", raising=False)
    val = ed._reduce_reasoning_tokens()
    assert val >= SANE_MAIN_SECTION_REASONING_FLOOR, (
        f"REDUCE (main section-prose) reasoning budget {val} is starved "
        f"below the sane floor {SANE_MAIN_SECTION_REASONING_FLOOR}"
    )
    # And specifically: it is no longer the keystone-birth 5000 starvation value.
    assert val > 5000, "REDUCE reasoning still at the starved 5000 default"


def test_reduce_reasoning_floor_clamps_a_too_small_override(monkeypatch):
    """A too-small env override is clamped UP to the floor (drb_78 starvation
    class can never be reintroduced via config)."""
    monkeypatch.delenv("PG_DISTILL_REDUCE_REASONING_MIN_TOKENS", raising=False)
    floor = ed.PG_DISTILL_REDUCE_REASONING_MIN_TOKENS
    # The exact drb_78 starvation value the bug spec cites.
    monkeypatch.setenv("PG_DISTILL_REDUCE_REASONING_TOKENS", "1000")
    val = ed._reduce_reasoning_tokens()
    assert val == floor, (
        f"a 1000-token REDUCE override must clamp UP to the floor {floor}, got {val}"
    )
    assert val >= SANE_MAIN_SECTION_REASONING_FLOOR


def test_reduce_reasoning_honors_a_higher_override(monkeypatch):
    """An operator may still raise the budget ABOVE the floor (LAW VI; §9.1.8
    'reasoning always max' — the floor is a minimum, not a cap)."""
    monkeypatch.delenv("PG_DISTILL_REDUCE_REASONING_MIN_TOKENS", raising=False)
    floor = ed.PG_DISTILL_REDUCE_REASONING_MIN_TOKENS
    higher = floor + 20000
    monkeypatch.setenv("PG_DISTILL_REDUCE_REASONING_TOKENS", str(higher))
    assert ed._reduce_reasoning_tokens() == higher


def test_reduce_reasoning_min_floor_is_sane_and_env_named():
    """The floor itself is an env-driven named constant (LAW VI) at a sane value."""
    assert isinstance(ed.PG_DISTILL_REDUCE_REASONING_MIN_TOKENS, int)
    assert ed.PG_DISTILL_REDUCE_REASONING_MIN_TOKENS >= SANE_MAIN_SECTION_REASONING_FLOOR


# ── Deliberate SMALL-call reductions are PRESERVED (no drb_76 regression) ──────
def test_map_reasoning_small_call_reduction_preserved(monkeypatch):
    """MAP per-source extraction stays a tight 4096 — NOT maxed (drb_76 guard)."""
    monkeypatch.delenv("PG_DISTILL_MAP_REASONING_TOKENS", raising=False)
    assert ed._map_reasoning_tokens() == 4096
    # The small MAP call must stay strictly below the main-section reasoning floor;
    # otherwise it is no longer the protective small-call reduction.
    assert ed._map_reasoning_tokens() < ed.PG_DISTILL_REDUCE_REASONING_MIN_TOKENS


def test_contract_slot_small_call_reduction_preserved(monkeypatch):
    """The ≤3-sentence / JSON contract-slot reasoning budget stays a tight 2048.

    This is the drb_76 protection (a tiny terse call must NOT reason until the
    completion ceiling and emit zero content). BUG-2 left it deliberately tight;
    this regression assertion fails loudly if anyone "maxes" it.
    """
    monkeypatch.delenv("PG_CONTRACT_SLOT_REASONING_MAX_TOKENS", raising=False)
    import src.polaris_graph.generator.multi_section_generator as msg
    import importlib as _il
    _il.reload(msg)
    assert msg.PG_CONTRACT_SLOT_REASONING_MAX_TOKENS == 2048
    # And it stays below the main-section floor — i.e. still a small-call reduction.
    assert msg.PG_CONTRACT_SLOT_REASONING_MAX_TOKENS < ed.PG_DISTILL_REDUCE_REASONING_MIN_TOKENS


# ── Ordering invariant: main-section >> the two small-call budgets ────────────
def test_main_section_reasoning_dominates_small_calls(monkeypatch):
    """§9.1.8 served per-call: full-prose REDUCE gets the large budget, the terse
    MAP and contract-slot calls stay tight."""
    monkeypatch.delenv("PG_DISTILL_REDUCE_REASONING_TOKENS", raising=False)
    monkeypatch.delenv("PG_DISTILL_REDUCE_REASONING_MIN_TOKENS", raising=False)
    monkeypatch.delenv("PG_DISTILL_MAP_REASONING_TOKENS", raising=False)
    monkeypatch.delenv("PG_CONTRACT_SLOT_REASONING_MAX_TOKENS", raising=False)
    import src.polaris_graph.generator.multi_section_generator as msg
    import importlib as _il
    _il.reload(msg)
    reduce_budget = ed._reduce_reasoning_tokens()
    assert reduce_budget > ed._map_reasoning_tokens()
    assert reduce_budget > msg.PG_CONTRACT_SLOT_REASONING_MAX_TOKENS
