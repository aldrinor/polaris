"""I-cred-008b (#1162) — the coverage-gap fail-loud SURVIVES every swallow-point + named-status routing.

The disclosure populate runs at four resolve sites; sites 1/3 (and the M-44/M-47 REGEN re-runs of them)
plus the fact-dedup re-resolve and the quantified path all sit inside broad ``except``/``return_exceptions``
handlers that safe-degrade on their OWN faults. A credibility-disclosure coverage gap must NEVER be
swallowed by any of them — it is a faithfulness abort that must reach the run handler as
``abort_credibility_coverage_gap``. These tests pin that contract by SOURCE inspection (the swallow-points
are inside one heavy async function; source assertions are the honest offline proof the guards exist on the
exact handlers) plus a behavioral check of the run-handler discrimination predicate.
"""
from __future__ import annotations

import inspect
import re

import src.polaris_graph.generator.multi_section_generator as m


def _normalize(src: str) -> str:
    return re.sub(r"\s+", " ", src)


def test_fact_dedup_except_reraises_credibility_pass_error():
    src = _normalize(inspect.getsource(m.generate_multi_section_report))
    # The fact-dedup safe-degrade handler must re-raise CredibilityPassError before logging "without dedup".
    assert "if isinstance(exc, CredibilityPassError): raise" in src, (
        "fact-dedup except must re-raise CredibilityPassError (fail-loud), not swallow it"
    )


def test_m44_regen_reraises_credibility_pass_error():
    src = _normalize(inspect.getsource(m.generate_multi_section_report))
    # M-44 regen uses gather(return_exceptions=True); a captured CredibilityPassError must be re-raised.
    assert "if isinstance(regen_result, CredibilityPassError): raise regen_result" in src, (
        "M-44 regen must re-raise a captured CredibilityPassError (return_exceptions=True swallows otherwise)"
    )


def test_m47_regen_reraises_credibility_pass_error():
    src = _normalize(inspect.getsource(m.generate_multi_section_report))
    # M-47 regen's except Exception wraps _bounded_run; must re-raise CredibilityPassError.
    # (two distinct re-raise sites carry isinstance(exc, CredibilityPassError): one fact-dedup, one M-47.)
    assert src.count("if isinstance(exc, CredibilityPassError): raise") >= 2, (
        "M-47 regen except must also re-raise CredibilityPassError (fact-dedup + M-47 = 2 sites)"
    )


def test_all_four_sites_present_in_source():
    """Each of the four cited-prose resolve sites carries the apply_disclosure_to_svs call (site map)."""
    gen_src = inspect.getsource(m.generate_multi_section_report)
    run_section_src = inspect.getsource(m._run_section)
    # site 1 (legacy _run_section) and site 2 (fact-dedup) live across the two functions
    assert "apply_disclosure_to_svs" in run_section_src, "site 1 (legacy _run_section) missing populate"
    assert gen_src.count("apply_disclosure_to_svs") >= 1, "site 2 (fact-dedup) missing populate"

    import src.polaris_graph.generator.contract_section_runner as csr
    assert "apply_disclosure_to_svs" in inspect.getsource(csr.run_contract_section), (
        "site 3 (contract runner) missing populate"
    )
    import src.polaris_graph.generator.quantified_analysis as qa
    assert "apply_disclosure_to_svs" in inspect.getsource(qa.run_quantified_section), (
        "site 4 (quantified) missing populate"
    )


def test_run_section_has_additive_credibility_analysis_param():
    sig = inspect.signature(m._run_section)
    assert sig.parameters["credibility_analysis"].default is None  # byte-identical when unpassed

    import src.polaris_graph.generator.contract_section_runner as csr
    assert inspect.signature(csr.run_contract_section).parameters[
        "credibility_analysis"].default is None
    import src.polaris_graph.generator.quantified_analysis as qa
    assert inspect.signature(qa.run_quantified_section).parameters[
        "credibility_analysis"].default is None


# ── named-status routing in the run handler (behavioral discrimination) ──────
def test_named_status_routing_uses_the_real_handler_classifier():
    """Codex #008b P2-1/P1-1: exercise the ACTUAL run-handler classifier (_credibility_abort_status),
    NOT a mirrored predicate. A coverage-gap CredibilityPassError -> the named status; a NON-coverage
    CredibilityPassError (judge_error) AND any other exception -> None => error_unexpected. This pins the
    P1-1 fix: a non-coverage pass failure routes to error_unexpected, it does NOT escape run_one_query
    (the old sibling-`except` re-raise let it escape)."""
    from src.polaris_graph.synthesis.credibility_pass import CredibilityPassError
    from scripts.run_honest_sweep_r3 import _credibility_abort_status, to_unified_status

    coverage_gap = CredibilityPassError(
        "abort_credibility_coverage_gap: a cited evidence_id ('e9') emitted by the resolver has no "
        "credibility/origin coverage"
    )
    judge_err = CredibilityPassError(
        "abort_credibility_pass_error: the production credibility judge failed for 2 source(s)"
    )
    assert _credibility_abort_status(coverage_gap) == "abort_credibility_coverage_gap"
    assert _credibility_abort_status(judge_err) is None          # => error_unexpected, NOT an escape
    assert _credibility_abort_status(ValueError("unrelated")) is None
    # the named status is a registered terminal status (round-trips through the unified map)
    assert to_unified_status("abort_credibility_coverage_gap") == "abort_credibility_coverage_gap"


def test_runner_registers_named_status_and_handler():
    import scripts.run_honest_sweep_r3 as r
    assert "abort_credibility_coverage_gap" in r.UNIFIED_STATUS_VALUES
    assert r.to_unified_status("abort_credibility_coverage_gap") == "abort_credibility_coverage_gap"
    # Codex #008b P1-1: the run handler routes via _credibility_abort_status INSIDE the generic
    # `except Exception` (so a NON-coverage CredibilityPassError becomes error_unexpected, never an
    # escape — the old sibling-`except _CredPassErrForAbort` + `raise` let it escape run_one_query).
    src = _normalize(inspect.getsource(r.run_one_query))
    assert "_credibility_abort_status(exc)" in src
