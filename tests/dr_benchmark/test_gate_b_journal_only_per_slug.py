"""journal_only is DISABLED for the benchmark (I-ready-019 #1146, operator credibility-model
directive 2026-06-07): ``JOURNAL_ONLY_BENCHMARK_SLUGS`` is EMPTY, so NO benchmark question is
journal-only — drb_72 (and every other slug) uses the broad credibility corpus. The
``apply_journal_only_for_slug`` mechanism is KEPT dormant so a future operator-approved journal-only
question can be re-enabled by appending a slug.

Supersedes I-ready-017 FIX-JO (#1100/#1134), which had activated journal_only for drb_72; the paid
re-run showed the journal-only distinct-journal COUNT floor (5<12 — a §-1.1-banned metadata proxy)
starved an otherwise-adequate corpus ("adequacy=proceed uncovered=0") and forced
abort_corpus_inadequate. NO run, NO spend.

Hermetic: the journal_only flag is snapshot/restored so each test leaves ``os.environ`` byte-identical.
"""

from __future__ import annotations

import os

import pytest

import scripts.dr_benchmark.run_gate_b as run_gate_b
from scripts.dr_benchmark.run_gate_b import (
    JOURNAL_ONLY_BENCHMARK_SLUGS,
    apply_journal_only_for_slug,
)
from src.polaris_graph.nodes.journal_only_filter import (
    JOURNAL_ONLY_FLAG,
    journal_only_active,
)
from src.polaris_graph.nodes.scope_gate import load_scope_template

_DRB_72 = "drb_72_ai_labor"
_NON_JOURNAL_WORKFORCE_SLUG = "workforce_generic_labour_query"


@pytest.fixture(autouse=True)
def _restore_journal_only_flag():
    """Snapshot/restore PG_SOURCE_RESTRICTION_JOURNAL_ONLY so each test leaves env byte-identical."""
    had = JOURNAL_ONLY_FLAG in os.environ
    prev = os.environ.get(JOURNAL_ONLY_FLAG)
    try:
        yield
    finally:
        if had:
            os.environ[JOURNAL_ONLY_FLAG] = prev  # type: ignore[assignment]
        else:
            os.environ.pop(JOURNAL_ONLY_FLAG, None)


def test_no_benchmark_slug_is_journal_only():
    """I-ready-019: the activation set is EMPTY — no benchmark question is journal-only."""
    assert JOURNAL_ONLY_BENCHMARK_SLUGS == frozenset()
    assert _DRB_72 not in JOURNAL_ONLY_BENCHMARK_SLUGS


def test_drb_72_uses_broad_credibility_corpus_not_journal_only():
    """drb_72 -> flag NOT set AND journal_only_active(workforce template) is False (the SAME predicate
    run_one_query evaluates as _jo_active). The broad credibility corpus + general adequacy govern."""
    set_on = apply_journal_only_for_slug(_DRB_72)
    assert set_on is False
    # Flag must be ABSENT (deterministically cleared), not merely != "1".
    assert JOURNAL_ONLY_FLAG not in os.environ
    assert journal_only_active(load_scope_template("workforce")) is False


def test_generic_workforce_slug_also_not_journal_only():
    """A non-lit-review workforce slug is likewise not journal-only (it never was) — confirms the
    broad-corpus behaviour is uniform now, not a special-case for drb_72."""
    set_on = apply_journal_only_for_slug(_NON_JOURNAL_WORKFORCE_SLUG)
    assert set_on is False
    assert JOURNAL_ONLY_FLAG not in os.environ
    assert journal_only_active(load_scope_template("workforce")) is False


def test_flag_deterministically_cleared_no_loop_leak():
    """Even if a stale flag is present (a conservative .env default, or a prior process), apply clears
    it for every slug (none is journal-only), so the --all loop never leaks a stale ON into a run."""
    os.environ[JOURNAL_ONLY_FLAG] = "1"  # simulate a stale ON
    assert apply_journal_only_for_slug(_DRB_72) is False
    assert JOURNAL_ONLY_FLAG not in os.environ
    assert journal_only_active(load_scope_template("workforce")) is False


def test_mechanism_retired_never_masks_even_when_activated(monkeypatch):
    """RETIRED (GATE_GENERALIZE_FIX45_PLAN §5/§7 U11): the journal-only mask is retired.
    Even if a future slug re-arms the legacy per-slug flag seam, journal_only_active is
    neutralized to always-False so NO masking can fire — the C2-safe adequacy + acquisition-
    receipt-gated build_source_kind_eligibility path (quality_eligibility.py) replaces it."""
    monkeypatch.setattr(run_gate_b, "JOURNAL_ONLY_BENCHMARK_SLUGS", frozenset({_DRB_72}))
    set_on = run_gate_b.apply_journal_only_for_slug(_DRB_72)
    assert set_on is True
    assert os.environ.get(JOURNAL_ONLY_FLAG) == "1"
    # The legacy flag seam still toggles, but the mask is RETIRED: active is always False.
    assert journal_only_active(load_scope_template("workforce")) is False
