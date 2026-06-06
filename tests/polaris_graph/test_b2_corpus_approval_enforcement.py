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
    AuthorizedSweep,
    CorpusSource,
    check_auto_approve_allowed,
    compute_tier_distribution,
)


def _material_deviation_report():
    """9 T5 + 1 T1 = way over the clinical T5 cap → material deviation."""
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
    return report


def test_b2_rubber_stamp_note_rejected_for_material_deviation() -> None:
    """FX-05: on material deviation, NO free-text credential (and no missing
    authorization) auto-approves — default-deny gates spend."""
    report = _material_deviation_report()
    ok, err = check_auto_approve_allowed(report, None)
    assert ok is False
    assert "authoriz" in err.lower() or "deviation" in err.lower()


def test_b2_free_text_note_alone_never_auto_approves() -> None:
    """FX-05 (was test_b2_substantive_note_accepted, which encoded the loophole):
    a free-text note — however substantive — NEVER auto-approves a material-
    deviation corpus. Only a structured AuthorizedSweep does."""
    report = _material_deviation_report()
    substantive = (
        "This market-research corpus is heavily weighted toward "
        "industry analyst reports because the research question "
        "specifically asks about competitor positioning; peer-reviewed "
        "T1 sources are rare in this domain."
    )
    ok_note, err_note = check_auto_approve_allowed(report, substantive)
    assert ok_note is False, "a free-text note must NOT auto-approve (FX-05)"
    assert err_note  # a non-empty denial reason

    # The ONE sanctioned path: a complete structured authorization.
    auth = AuthorizedSweep(
        authorized_by="env:PG_AUTHORIZED_SWEEP_APPROVAL",
        authorized_at="2026-06-06T00:00:00Z",
        flag_source="env",
    )
    ok_auth, err_auth = check_auto_approve_allowed(report, auth)
    assert ok_auth is True
    assert err_auth == ""


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


def test_fx05_live_honest_cycle_aborts_before_generation() -> None:
    """FX-05: run_live_honest_cycle must short-circuit on denial BEFORE the live
    DeepSeek generation call (§9.1 #5 — no generator tokens on a denied corpus)."""
    import inspect

    import scripts.run_live_honest_cycle as live
    src = inspect.getsource(live.main_async)
    assert "if not approved:" in src
    assert "abort_corpus_approval_denied" in src
    approval_idx = src.find("if not approved:")
    gen_idx = src.find("generate_live_draft(")
    assert approval_idx != -1 and gen_idx != -1
    assert approval_idx < gen_idx, "abort branch must precede live generation"
    assert "return" in src[approval_idx:gen_idx], "denied branch must return early"


def test_fx05_prerebuild_aborts_before_generation() -> None:
    """FX-05: run_honest_on_prerebuild_corpus must short-circuit on denial BEFORE
    generate_multi_section_report."""
    import inspect

    import scripts.run_honest_on_prerebuild_corpus as pre
    src = inspect.getsource(pre.main_async)
    assert "if not approved:" in src
    assert "abort_corpus_approval_denied" in src
    approval_idx = src.find("if not approved:")
    gen_idx = src.find("generate_multi_section_report(")
    assert approval_idx != -1 and gen_idx != -1
    assert approval_idx < gen_idx, "abort branch must precede multi-section generation"
    assert "return" in src[approval_idx:gen_idx], "denied branch must return early"


def test_fx05_honest_pipeline_aborts_before_strict_verify() -> None:
    """FX-05: run_honest_pipeline must short-circuit on denial BEFORE strict_verify
    / report / evaluator work, returning status=abort_corpus_approval_denied."""
    import inspect

    import src.polaris_graph.honest_pipeline as hp
    src = inspect.getsource(hp.run_honest_pipeline)
    assert "if not approved:" in src
    assert "abort_corpus_approval_denied" in src
    approval_idx = src.find("if not approved:")
    verify_idx = src.find("strict_verify(")
    assert approval_idx != -1 and verify_idx != -1
    assert approval_idx < verify_idx, "abort branch must precede strict_verify"
    assert "return PipelineResult(" in src[approval_idx:verify_idx], (
        "denied branch must return an abort PipelineResult before strict_verify"
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
