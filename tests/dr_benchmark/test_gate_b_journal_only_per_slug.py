"""Per-slug journal_only activation in Gate-B (I-ready-017 FIX-JO #1100/#1134). NO run, NO spend.

Proves the FIX-JO wiring: the Gate-B per-question path activates the journal_only corpus-quality
contract ONLY for the journal-only benchmark slug (drb_72_ai_labor — the AI-labor LITERATURE
REVIEW whose contract is journal_only), and leaves it INERT for every other slug — crucially
WITHOUT a blanket global activation, so the generic workforce T3 statistical-agency path survives
for a non-lit-review workforce query.

The seam under test is ``run_gate_b.apply_journal_only_for_slug`` (the helper that
``run_gate_b_query`` calls per question, before ``run_one_query``). The downstream consumer is
``run_honest_sweep_r3.run_one_query`` -> ``_jo_active`` = ``journal_only_active(scope_template)``,
which requires BOTH the runtime flag (set/cleared here) AND the protocol's
``source_restriction: journal_only`` (declared in workforce.yaml). So this test asserts the SAME
predicate the production sweep evaluates: ``journal_only_active(load_scope_template('workforce'))``.

Hermetic: the journal_only flag is snapshot/restored so the test leaves ``os.environ`` byte-
identical. NO corpus re-run, NO network, NO spend.
"""

from __future__ import annotations

import os

import pytest

from scripts.dr_benchmark.run_gate_b import (
    JOURNAL_ONLY_BENCHMARK_SLUGS,
    apply_journal_only_for_slug,
)
from src.polaris_graph.nodes.journal_only_filter import (
    JOURNAL_ONLY_FLAG,
    journal_only_active,
)
from src.polaris_graph.nodes.scope_gate import load_scope_template

_JOURNAL_ONLY_SLUG = "drb_72_ai_labor"
# A non-journal workforce-DOMAIN slug: same domain template as drb_72 (so it loads the journal_only
# protocol field), but NOT a journal_only benchmark slug — proves activation is keyed on the SLUG,
# not on the domain template (both share workforce.yaml's source_restriction: journal_only).
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


def test_drb_72_is_a_journal_only_benchmark_slug():
    """The named constant carries drb_72 (the contract drives activation, not a stray literal)."""
    assert _JOURNAL_ONLY_SLUG in JOURNAL_ONLY_BENCHMARK_SLUGS
    # The non-journal workforce slug is NOT in the set (it must take the OFF branch).
    assert _NON_JOURNAL_WORKFORCE_SLUG not in JOURNAL_ONLY_BENCHMARK_SLUGS


def test_journal_only_slug_activates_against_workforce_protocol():
    """drb_72 -> flag set ON AND journal_only_active(workforce template) is True (the SAME predicate
    run_one_query evaluates as _jo_active). Activation requires BOTH the flag and the protocol."""
    set_on = apply_journal_only_for_slug(_JOURNAL_ONLY_SLUG)
    assert set_on is True
    assert os.environ.get(JOURNAL_ONLY_FLAG) == "1"

    workforce_protocol = load_scope_template("workforce")
    assert journal_only_active(workforce_protocol) is True


def test_non_journal_workforce_slug_does_not_activate_no_blanket():
    """A NON-journal workforce slug -> flag NOT set AND journal_only_active(workforce template) is
    False. This is the critical anti-regression: NO blanket activation on the shared workforce
    template, so the generic T3 statistical-agency path is preserved for non-lit-review queries."""
    set_on = apply_journal_only_for_slug(_NON_JOURNAL_WORKFORCE_SLUG)
    assert set_on is False
    # Flag must be ABSENT (deterministically cleared), not merely != "1".
    assert JOURNAL_ONLY_FLAG not in os.environ

    workforce_protocol = load_scope_template("workforce")
    # Same workforce template that DOES declare source_restriction: journal_only, yet inactive —
    # because the per-slug flag is OFF. Proves keying on slug, not on the domain template.
    assert journal_only_active(workforce_protocol) is False


def test_flag_is_deterministically_cleared_across_slugs_no_loop_leak():
    """The --all loop runs slugs in one process; a stale journal_only flag from drb_72 must NOT
    carry into a subsequent non-journal slug. apply_journal_only_for_slug clears it deterministically."""
    # drb_72 turns it ON.
    assert apply_journal_only_for_slug(_JOURNAL_ONLY_SLUG) is True
    assert os.environ.get(JOURNAL_ONLY_FLAG) == "1"
    # The next (non-journal) slug must turn it OFF — not inherit the stale ON.
    assert apply_journal_only_for_slug(_NON_JOURNAL_WORKFORCE_SLUG) is False
    assert JOURNAL_ONLY_FLAG not in os.environ
    # And it does NOT activate against the workforce protocol after the clear.
    assert journal_only_active(load_scope_template("workforce")) is False
