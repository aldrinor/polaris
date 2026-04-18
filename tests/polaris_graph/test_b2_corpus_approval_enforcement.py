"""
Codex round 1 B-2 regression test: corpus approval must be enforced.

The sweep orchestrator previously wrote corpus_approval.json with
approved=False, then proceeded anyway. This test pins the fix:
denied approval short-circuits the pipeline with a pipeline-verdict
artifact, zero LLM cost.

We test the decision-gate logic directly since a full orchestrator
run requires network + API keys.
"""
from __future__ import annotations

from src.polaris_graph.nodes.corpus_approval_gate import (
    CorpusSource,
    check_auto_approve_allowed,
    compute_tier_distribution,
)


def _rubber_stamp_note() -> str:
    return "ok"  # trivial, should trigger auto-approve denial


def test_b2_rubber_stamp_note_rejected_for_material_deviation() -> None:
    """If the corpus has material deviation, a trivial note must be
    rejected by check_auto_approve_allowed."""
    # 9 T5 + 1 T1 = way over T5 cap for clinical template
    classified = [
        CorpusSource(url=f"https://industry/{i}", title="", domain="industry",
                     tier="T5", tier_confidence=0.9, tier_rule="",
                     tier_reasons=[])
        for i in range(9)
    ] + [
        CorpusSource(url="https://pmc/1", title="", domain="pmc",
                     tier="T1", tier_confidence=0.9, tier_rule="",
                     tier_reasons=[]),
    ]
    protocol = {
        "expected_tier_distribution": [
            {"tier": "T1", "min_fraction": 0.3, "max_fraction": 0.6},
            {"tier": "T5", "min_fraction": 0.0, "max_fraction": 0.15},
        ],
    }
    report = compute_tier_distribution(classified, protocol)
    assert report.has_material_deviation is True
    ok, err = check_auto_approve_allowed(report, _rubber_stamp_note())
    assert ok is False
    assert "note" in err.lower() or "deviation" in err.lower()


def test_b2_substantive_note_accepted_for_material_deviation() -> None:
    """A real, substantive note (>=30 chars, not in trivial set) is OK."""
    classified = [
        CorpusSource(url=f"https://industry/{i}", title="", domain="industry",
                     tier="T5", tier_confidence=0.9, tier_rule="",
                     tier_reasons=[])
        for i in range(9)
    ] + [
        CorpusSource(url="https://pmc/1", title="", domain="pmc",
                     tier="T1", tier_confidence=0.9, tier_rule="",
                     tier_reasons=[]),
    ]
    protocol = {
        "expected_tier_distribution": [
            {"tier": "T1", "min_fraction": 0.3, "max_fraction": 0.6},
            {"tier": "T5", "min_fraction": 0.0, "max_fraction": 0.15},
        ],
    }
    report = compute_tier_distribution(classified, protocol)
    substantive = (
        "This market-research corpus is heavily weighted toward "
        "industry analyst reports because the research question "
        "specifically asks about competitor positioning; peer-reviewed "
        "T1 sources are rare in this domain."
    )
    ok, _err = check_auto_approve_allowed(report, substantive)
    assert ok is True


def test_b2_sweep_orchestrator_has_enforcement_branch() -> None:
    """Verify the code has an `if not approved` short-circuit that
    writes an abort report instead of proceeding to synthesis."""
    import inspect

    import scripts.run_honest_sweep_r3 as sweep
    src = inspect.getsource(sweep.run_one_query)
    # The enforcement branch must exist and route to a short-circuit
    assert "if not approved:" in src, (
        "orchestrator must have `if not approved:` branch that aborts"
    )
    assert "abort_corpus_approval_denied" in src, (
        "orchestrator must emit status=abort_corpus_approval_denied"
    )
    # And the branch must return BEFORE the generation call
    approval_idx = src.find("if not approved:")
    generation_idx = src.find("generate_multi_section_report(")
    assert approval_idx < generation_idx, (
        "enforcement branch must precede multi-section generator call"
    )
    # The abort branch must contain a return statement
    branch_section = src[approval_idx:generation_idx]
    assert "return summary" in branch_section, (
        "approval-denied branch must `return summary` before generation"
    )


def test_b2_expected_str_helper() -> None:
    """The abort-artifact helper formats expected tier distribution
    from a protocol dict."""
    from scripts.run_honest_sweep_r3 import expected_str_for_abort
    protocol = {
        "expected_tier_distribution": [
            {"tier": "T1", "min_fraction": 0.3, "max_fraction": 0.6},
            {"tier": "T3", "min_fraction": 0.05, "max_fraction": 0.25},
        ],
    }
    s = expected_str_for_abort(protocol)
    assert "T1 30-60%" in s
    assert "T3 5-25%" in s


def test_b2_expected_str_helper_empty_protocol() -> None:
    from scripts.run_honest_sweep_r3 import expected_str_for_abort
    assert expected_str_for_abort({}) == "per scope template"
