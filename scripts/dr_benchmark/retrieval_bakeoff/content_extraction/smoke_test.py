"""smoke_test.py -- OFFLINE stub smoke for the content_extraction bake-off.

Proves, with NO GPU / NO network / MOCKED model loaders:
  A. every file in this layer compiles (py_compile).
  B. the SCORER-MATH canary passes (gold-in -> ~1.0, junk-in -> ~0, graded mid).
  C. the per-candidate LIVENESS canary CORRECTLY FAILS on a simulated STUB
     candidate that returns "" on the known-good page (exits non-zero) -- the
     anti-drb_72 discrimination (a dead candidate must fail loud, not score low).
  D. a genuinely-low-but-LIVE candidate (real body, partial) does NOT trip the
     liveness canary (proves it discriminates dead from merely-poor).
  E. the FAITHFULNESS substring check PASSES an extractive output and FAILS a
     paraphrased/reordered output (the generative-rewrite discrimination). If it
     can't fail the paraphrase the check is decorative.
  F. needs_gpu candidates are honestly SKIPPED (not faked) with no GPU.

All real extractors (Trafilatura seam, resiliparse, justext, readability, vLLM,
mineru) are MOCKED here -- the smoke never imports the heavy deps. Exit 0 on
success, non-zero on any failure.
"""

from __future__ import annotations

import os
import py_compile
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # import sibling modules by bare name

import _candidates  # noqa: E402
import gate0  # noqa: E402
from _candidates import Candidate  # noqa: E402
from _scoring import (  # noqa: E402
    OfficialScorerStatus,
    check_faithfulness,
    rouge_n,
    score_official_or_fallback,
)


def _fail(msg: str) -> None:
    print(f"[SMOKE-FAIL] {msg}", file=sys.stderr)
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"[SMOKE-OK] {msg}")


# ---------------------------------------------------------------------------
# A. py_compile every file
# ---------------------------------------------------------------------------

def check_py_compile() -> None:
    files = [
        "__init__.py",
        "_scoring.py",
        "_candidates.py",
        "build_fixture.py",
        "gate0.py",
        "run_bakeoff.py",
        "smoke_test.py",
    ]
    for fname in files:
        path = os.path.join(HERE, fname)
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as exc:
            _fail(f"py_compile failed for {fname}: {exc}")
    _ok(f"py_compile clean on {len(files)} files")


# ---------------------------------------------------------------------------
# B. scorer-math canary
# ---------------------------------------------------------------------------

def check_scorer_math() -> None:
    results = gate0.check_scorer_math()
    for r in results:
        if not r.passed:
            _fail(f"scorer-math canary '{r.name}' failed: {r.detail}")
    _ok("scorer-math canary passes (gold->~1.0, junk->~0, graded mid)")


# ---------------------------------------------------------------------------
# Mocked candidate registry (NO heavy deps): stub / live / low / generative.
# ---------------------------------------------------------------------------

def _good_body_extractor(html: str) -> str:
    """A working extractive tool: returns the article body verbatim."""
    # Pull the two sentences that ARE in the known-good HTML (extractive).
    return (
        "Tirzepatide reduces major adverse cardiovascular events. In the SURMOUNT-MMO "
        "randomized controlled trial, tirzepatide reduced the incidence of major adverse "
        "cardiovascular events compared with placebo over a median follow-up of three years "
        "in adults with obesity. The treatment group received a once-weekly subcutaneous "
        "dose escalated to fifteen milligrams, and the absolute risk reduction was "
        "statistically significant with a hazard ratio below one."
    )


def _stub_extractor(html: str) -> str:
    """A DEAD/stub candidate: returns empty string on the known-good page."""
    return ""


def _low_but_live_extractor(html: str) -> str:
    """A genuinely-poor-but-LIVE extractor: real partial body (verbatim), >min chars."""
    return (
        "tirzepatide reduced the incidence of major adverse cardiovascular events "
        "compared with placebo over a median follow-up of three years in adults with obesity."
    )


def _generative_extractor(html: str) -> str:
    """A generative yardstick: PARAPHRASES (not verbatim) -> faithfulness must flag."""
    return (
        "A weekly injection of the dual agonist drug lowered heart attack and stroke risk "
        "versus dummy treatment across a three-year window among heavier patients, "
        "with the benefit reaching statistical importance at the top dose level."
    )


def _make(name, key, extract, *, needs_gpu, extractive, role) -> Candidate:
    return Candidate(
        name=name,
        key=key,
        impl_id=f"mock:{key}",
        license="mock",
        role=role,
        needs_gpu=needs_gpu,
        extractive=extractive,
        extract=extract,
    )


# ---------------------------------------------------------------------------
# C+D. liveness canary discriminates DEAD (stub) from LOW-BUT-LIVE
# ---------------------------------------------------------------------------

def check_liveness_discrimination() -> None:
    live = _make("live", "live", _good_body_extractor, needs_gpu=False, extractive=True, role="baseline")
    stub = _make("stub", "stub", _stub_extractor, needs_gpu=False, extractive=True, role="candidate")
    low = _make("low", "low", _low_but_live_extractor, needs_gpu=False, extractive=True, role="candidate")
    gpu = _make("gpu", "gpu", _good_body_extractor, needs_gpu=True, extractive=True, role="candidate")

    live_res = gate0.check_candidate_liveness(live, allow_gpu=False)
    if not live_res.passed:
        _fail(f"liveness wrongly failed a LIVE candidate: {live_res.detail}")

    stub_res = gate0.check_candidate_liveness(stub, allow_gpu=False)
    if stub_res.passed:
        _fail("liveness FAILED TO CATCH a stub candidate (returned '') -- anti-drb_72 broken")
    _ok(f"liveness correctly FAILS stub candidate: {stub_res.detail}")

    low_res = gate0.check_candidate_liveness(low, allow_gpu=False)
    if not low_res.passed:
        _fail(f"liveness wrongly tripped on a low-but-LIVE candidate: {low_res.detail}")
    _ok("liveness correctly PASSES a genuinely-low-but-live candidate (dead != poor)")

    # F. needs_gpu honestly skipped (not faked) when no GPU.
    gpu_res = gate0.check_candidate_liveness(gpu, allow_gpu=False)
    if not gpu_res.passed or "SKIPPED" not in gpu_res.detail:
        _fail(f"needs_gpu candidate not honestly skipped: {gpu_res.detail}")
    _ok("needs_gpu candidate honestly SKIPPED (not faked) with no GPU")

    # Now prove the full gate0 EXITS NON-ZERO when a stub is in the registry.
    registry = [live, stub]
    report = gate0.run_gate0(allow_gpu=False, candidates=registry)
    if report["all_passed"]:
        _fail("gate0.run_gate0 reported all_passed with a stub candidate present")
    # Confirm the would-be exit code is non-zero (mirror gate0.main's logic).
    exit_code = 0 if report["all_passed"] else 1
    if exit_code == 0:
        _fail("gate0 with a stub candidate did not produce a non-zero exit")
    _ok("gate0 with a stub candidate -> all_passed=False -> non-zero exit (FAIL LOUD)")


# ---------------------------------------------------------------------------
# E. faithfulness discriminates extractive (pass) from paraphrase (fail)
# ---------------------------------------------------------------------------

def check_faithfulness_discrimination() -> None:
    html = gate0.KNOWN_GOOD_HTML

    extractive_out = _good_body_extractor(html)
    rep_ok = check_faithfulness(extractive_out, html)
    if not rep_ok.is_faithful:
        _fail(
            f"faithfulness WRONGLY failed an extractive output "
            f"(verbatim_fraction={rep_ok.verbatim_fraction:.3f}): {rep_ok.first_violation!r}"
        )
    _ok(f"faithfulness PASSES extractive output (verbatim_fraction={rep_ok.verbatim_fraction:.3f})")

    paraphrase_out = _generative_extractor(html)
    rep_bad = check_faithfulness(paraphrase_out, html)
    if rep_bad.is_faithful:
        _fail(
            "faithfulness FAILED TO FLAG a paraphrase -- the check is decorative "
            f"(verbatim_fraction={rep_bad.verbatim_fraction:.3f})"
        )
    _ok(f"faithfulness FLAGS paraphrase (verbatim_fraction={rep_bad.verbatim_fraction:.3f}) -> never-crown")


# ---------------------------------------------------------------------------
# Structural never-crown: a generative role cannot win even with higher F1.
# ---------------------------------------------------------------------------

def check_never_crown() -> None:
    from _candidates import is_eligible_to_win

    gen = _make("gen", "gen", _generative_extractor, needs_gpu=False, extractive=False, role="yardstick_non_sovereign")
    det = _make("det", "det", _good_body_extractor, needs_gpu=False, extractive=True, role="baseline")
    if is_eligible_to_win(gen):
        _fail("generative yardstick is eligible to win -- never-crown is NOT structural")
    if not is_eligible_to_win(det):
        _fail("deterministic extractor wrongly marked ineligible")
    _ok("structural never-crown holds (generative yardstick ineligible regardless of F1)")


# ---------------------------------------------------------------------------
# Sanity: rouge_n behaves (extra guard the scorer is not trivially constant).
# ---------------------------------------------------------------------------

def check_rouge_sanity() -> None:
    same = rouge_n("alpha beta gamma delta", "alpha beta gamma delta", n=2)
    if same.f1 < 0.99:
        _fail(f"rouge_n self-overlap not ~1.0: {same.f1}")
    disjoint = rouge_n("alpha beta gamma", "delta epsilon zeta", n=2)
    if disjoint.f1 > 0.05:
        _fail(f"rouge_n disjoint not ~0: {disjoint.f1}")
    _ok("rouge_n sanity (self->~1.0, disjoint->~0)")


# ---------------------------------------------------------------------------
# G. faithfulness survives HTML entities + unicode (advisor blocker 2):
#    a verbatim extractor whose DECODED output meets entity-encoded source must
#    still pass -- else the >=floor win-gate would hard-drop the lead on artifact.
# ---------------------------------------------------------------------------

def check_entity_unicode_faithfulness() -> None:
    # Source HTML carries entities (&amp; &nbsp; &#39;) and an en-dash entity.
    entity_html = (
        "<html><body><article><h1>Dose &amp; safety</h1>"
        "<p>The 5&nbsp;mg dose reduced events by 30&ndash;40 percent in Smith&#39;s "
        "randomized controlled trial of adults with type 2 diabetes and obesity.</p>"
        "</article></body></html>"
    )
    # A faithful extractor emits DECODED text (real "&", real space, en-dash, ').
    decoded_extractive = (
        "Dose & safety. The 5 mg dose reduced events by 30–40 percent in "
        "Smith's randomized controlled trial of adults with type 2 diabetes and obesity."
    )
    rep = check_faithfulness(decoded_extractive, entity_html)
    if not rep.is_faithful:
        _fail(
            "faithfulness WRONGLY failed a verbatim extractor over entity/unicode source "
            f"(verbatim_fraction={rep.verbatim_fraction:.3f}); decode/normalize is broken: "
            f"{rep.first_violation!r}"
        )
    _ok(
        "faithfulness survives HTML entities + unicode "
        f"(verbatim_fraction={rep.verbatim_fraction:.3f}) -> lead not hard-dropped on artifact"
    )


# ---------------------------------------------------------------------------
# H. official-or-fallback PRIMARY scorer is honestly FLAGGED when absent
#    (advisor blocker 1): no official scorer -> scorer_used must say fallback,
#    never silently presented as the official published number.
# ---------------------------------------------------------------------------

def check_scorer_provenance() -> None:
    absent = OfficialScorerStatus(
        available=False,
        eval_script_path="",
        benchmark_jsonl_path="",
        reason="smoke: no repo",
    )
    scored = score_official_or_fallback("alpha beta gamma", "alpha beta gamma", absent)
    if scored.scorer_used != "fallback_rederived":
        _fail(f"absent official scorer did not flag fallback: {scored.scorer_used}")
    # And when 'available' with an injected runner, scorer_used must say official.
    present = OfficialScorerStatus(
        available=True,
        eval_script_path="x/eval_baselines.py",
        benchmark_jsonl_path="x/benchmark/WebMainBench_100.jsonl",
        reason="smoke: injected",
    )
    scored2 = score_official_or_fallback(
        "a b c", "a b c", present, official_runner=lambda c, g: 0.6402
    )
    if scored2.scorer_used != "official" or abs(scored2.f1 - 0.6402) > 1e-9:
        _fail(f"injected official runner not used as PRIMARY: {scored2}")
    _ok("scorer provenance honest (absent->fallback_rederived FLAGGED; present->official PRIMARY)")


def main() -> int:
    print("=== content_extraction bake-off OFFLINE smoke ===")
    check_py_compile()
    check_rouge_sanity()
    check_scorer_math()
    check_liveness_discrimination()
    check_faithfulness_discrimination()
    check_entity_unicode_faithfulness()
    check_scorer_provenance()
    check_never_crown()
    print("=== SMOKE PASSED ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
