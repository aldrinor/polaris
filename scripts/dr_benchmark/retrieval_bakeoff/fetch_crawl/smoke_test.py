"""I-ret-002 (#1294) layer 2 (fetch_crawl) — OFFLINE stub smoke test.

Proves, with NO network / NO GPU / NO real model or API loaders:
  1. All four layer files ``py_compile`` clean.
  2. The GATE-0 scorer-math canary PASSES on synthetic two-extreme input (good~1.0 / junk~0).
  3. The GATE-0 per-engine LIVENESS canary correctly FAILS LOUD on a simulated STUB candidate
     (an engine adapter that returns "" / a CAPTCHA shell for everything) — the drb_72 contract.
  4. The liveness canary PASSES on a simulated GOOD candidate (returns a real body).
  5. The runner scores a mocked-good engine high and a mocked-stub engine low, and records a
     no_key engine as SKIPPED (status=no_key, score=None) — never a faked number.
  6. The fixture builder's recovery rubric + tokenizer behave on synthetic bodies (no snapshots
     needed for the smoke; the real build reads banked corpora on the VM).

Exits 0 on success, non-zero on any failure (so it is a real gate, not a claim).
"""

from __future__ import annotations

import os
import py_compile
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _polaris_root import ensure_on_syspath  # noqa: E402

ensure_on_syspath()

from build_fixture import (  # noqa: E402
    FETCH_FAIL,
    RECOVERED,
    SOFT_STUB,
    WALLED,
    classify_recovery,
    classify_source_type,
    content_tokens,
)
from gate0 import (  # noqa: E402
    GateZeroError,
    assert_engine_live,
    run_scorer_canary,
)
from run_bakeoff import (  # noqa: E402
    STATUS_NO_KEY,
    STATUS_SCORED,
    EngineSpec,
    aggregate,
    rank_results,
    run_engine,
    score_url,
)

_LAYER_FILES = ("_polaris_root.py", "build_fixture.py", "run_bakeoff.py", "gate0.py", "smoke_test.py")

# A real gold MAIN-CONTENT body + its tokens (synthetic, no snapshot needed). Deliberately a
# substantive full-article-length body (> the SOFT_STUB ceiling) so its gold recovery class is
# RECOVERED — a real recovered article is long; a near-empty extract is SOFT_STUB by the rubric.
_GOLD_BODY = (
    "Subthalamic deep brain stimulation reduced motor symptoms in advanced Parkinson disease "
    "compared with medical therapy. In this randomized controlled trial, two hundred fifty "
    "patients were assigned to either neurostimulation of the subthalamic nucleus or to best "
    "medical therapy alone. The stimulation group improved substantially on the unified "
    "Parkinson disease rating scale and reduced levodopa equivalent daily dose at six months. "
    "Quality of life, measured with a validated questionnaire, improved in the stimulation arm "
    "while it remained unchanged with medical therapy. Adverse events in the stimulation group "
    "included transient confusion, dysarthria, and one intracerebral hemorrhage. The authors "
    "concluded that deep brain stimulation was superior to medical therapy for motor function "
    "and quality of life in patients with advanced disease and motor complications, though it "
    "carried a higher risk of serious adverse events related to the surgical procedure."
)
_GOLD_TOKENS = set(content_tokens(_GOLD_BODY))

_SHELL_BODY = (
    "Just a moment... This page is displayed while the website verifies you are not a bot. "
    "Cloudflare Ray ID. Performance & Security by Cloudflare. Please complete the captcha challenge."
)


def _fail(msg: str) -> None:
    raise AssertionError(msg)


def step_py_compile() -> None:
    for name in _LAYER_FILES:
        path = os.path.join(_HERE, name)
        if not os.path.isfile(path):
            _fail(f"missing layer file: {path}")
        py_compile.compile(path, doraise=True)
    print("  [PASS] py_compile: all 5 layer files compile clean")


def step_scorer_canary() -> None:
    results = run_scorer_canary()
    if not all(r.passed for r in results):
        _fail(f"scorer canary did not all pass: {[(r.name, r.passed) for r in results]}")
    print(f"  [PASS] scorer-math canary: {len(results)} cases (good~1.0 / junk~0 / empty / direction)")


def step_rubric_and_tokens() -> None:
    assert classify_recovery(_GOLD_BODY) == RECOVERED, "real body must be RECOVERED"
    assert classify_recovery(_SHELL_BODY) == WALLED, "CAPTCHA shell must be WALLED"
    assert classify_recovery("") == FETCH_FAIL, "empty must be FETCH_FAIL"
    assert classify_recovery("short abstract only.") == SOFT_STUB, "tiny non-shell body must be SOFT_STUB"
    # source-type stratification sanity (registered-domain necessary-not-sufficient handled in build).
    assert classify_source_type("https://www.nejm.org/doi/full/10.1056/x", "") == "paywalled"
    assert classify_source_type("https://www.fda.gov/drugs/label.pdf", "") == "gov"
    assert classify_source_type("https://www.youtube.com/watch?v=x", "") == "social"
    assert classify_source_type("https://example.org/article", "open_access") == "oa"
    assert content_tokens("The the AND of") == [], "stopwords-only -> empty content tokens"
    print("  [PASS] recovery rubric + source-type + tokenizer behave on synthetic bodies")


def step_liveness_fails_on_stub() -> None:
    """The drb_72 contract: a STUB engine (returns "" / shell for everything) FAILS LOUD."""
    spec = EngineSpec(name="zyte", pip_id="zyte-api>=0.7.0", import_name="zyte_api",
                      needs_key_env="ZYTE_API_KEY")

    def _stub_empty(_url: str) -> str:
        return ""  # a dead engine that returns nothing for every URL

    def _stub_shell(_url: str) -> str:
        return _SHELL_BODY  # a wired-but-walled engine that returns a CAPTCHA shell

    for label, stub in (("empty", _stub_empty), ("shell", _stub_shell)):
        raised = False
        try:
            assert_engine_live(spec, fetch_override=stub, liveness_url="https://example.com/")
        except GateZeroError:
            raised = True
        if not raised:
            _fail(f"liveness canary FAILED to fail-loud on a {label} stub engine (drb_72 hole open)")
    print("  [PASS] liveness canary FAILS LOUD on empty-stub AND shell-stub engines (drb_72 contract)")


def step_liveness_passes_on_good() -> None:
    spec = EngineSpec(name="crawl4ai", pip_id="crawl4ai>=0.6.0", import_name="crawl4ai",
                      is_baseline=True, needs_browser=True)

    def _good(_url: str) -> str:
        return _GOLD_BODY

    res = assert_engine_live(spec, fetch_override=_good, liveness_url="https://example.com/")
    if not res.passed:
        _fail("liveness canary should PASS on a good engine returning real content")
    print("  [PASS] liveness canary PASSES on a simulated good engine")


def step_runner_scores_and_skips() -> None:
    """run_engine scores a mocked-good engine high, a mocked-stub engine low, and a no_key SKIP."""
    fixture = [
        {"url": "https://a.example/1", "recovery_class": RECOVERED,
         "reference_tokens": sorted(_GOLD_TOKENS), "source_type": "paywalled", "tier": "T1"},
        {"url": "https://b.example/2", "recovery_class": RECOVERED,
         "reference_tokens": sorted(_GOLD_TOKENS), "source_type": "oa", "tier": "T1"},
        {"url": "https://c.example/3", "recovery_class": WALLED,
         "reference_tokens": sorted(content_tokens(_SHELL_BODY)), "source_type": "gov", "tier": "T4"},
    ]

    good_spec = EngineSpec(name="crawl4ai", pip_id="crawl4ai>=0.6.0", import_name="crawl4ai",
                           is_baseline=True, needs_browser=True)
    stub_spec = EngineSpec(name="playwright", pip_id="playwright>=1.45.0", import_name="playwright",
                           needs_browser=True)
    nokey_spec = EngineSpec(name="firecrawl", pip_id="firecrawl-py>=2.0.0", import_name="firecrawl",
                            needs_key_env="FIRECRAWL_API_KEY")

    def _good_fetch(url: str) -> str:
        # Return gold for the RECOVERED rows, a shell for the WALLED row (a perfect engine).
        return _SHELL_BODY if url.endswith("/3") else _GOLD_BODY

    def _stub_fetch(_url: str) -> str:
        return ""  # dead engine for every URL

    good = run_engine(good_spec, fixture, fetch_override=_good_fetch)
    stub = run_engine(stub_spec, fixture, fetch_override=_stub_fetch)

    assert good["status"] == STATUS_SCORED, "good engine should be scored"
    assert stub["status"] == STATUS_SCORED, "stub engine (override) should be scored, just badly"
    assert good["score"] is not None and stub["score"] is not None
    assert good["score"] > stub["score"], (
        f"good engine score {good['score']} must beat stub engine score {stub['score']}"
    )
    # The good engine recovers both RECOVERED rows (recovery_rate >= 2/3); the dead stub recovers none.
    assert good["metric"]["recovery_rate"] >= 2 / 3, "good engine must recover the 2 RECOVERED rows"
    assert stub["metric"]["recovery_rate"] == 0.0, "dead stub engine must recover nothing"

    # A no_key engine (no FIRECRAWL_API_KEY in the smoke env) must be SKIPPED, not faked.
    saved = os.environ.pop("FIRECRAWL_API_KEY", None)
    try:
        nokey = run_engine(nokey_spec, fixture)  # no override -> real availability check
    finally:
        if saved is not None:
            os.environ["FIRECRAWL_API_KEY"] = saved
    assert nokey["status"] == STATUS_NO_KEY, f"keyless firecrawl must be no_key, got {nokey['status']}"
    assert nokey["score"] is None, "a skipped engine must have score=None, never a faked number"

    ranked = rank_results([good, stub, nokey])
    assert ranked[0]["engine"] == "crawl4ai", "the good engine must rank first"
    assert ranked[-1]["engine"] == "firecrawl", "the skipped (None-score) engine must rank last"

    # aggregate sanity on an empty set.
    empty_metric = aggregate([])
    assert empty_metric["score"] == 0.0 and empty_metric["n"] == 0
    print("  [PASS] runner: good>stub score, no_key SKIPPED (score=None), ranking sane")


def step_score_url_direction() -> None:
    s_good = score_url(_GOLD_BODY, RECOVERED, _GOLD_TOKENS, reference_trustworthy=True)
    s_junk = score_url(_SHELL_BODY, RECOVERED, _GOLD_TOKENS, reference_trustworthy=True)
    assert s_good["reference_recall"] > 0.9 and s_good["recovered"]
    assert s_junk["reference_recall"] < 0.1 and not s_junk["recovered"]
    print("  [PASS] score_url: good recall>0.9 recovered; junk recall<0.1 not-recovered")


def step_wall_break_is_a_win() -> None:
    """§-1.3 anti-inversion: beating an incumbent wall (gold WALLED -> engine RECOVERED) is a WIN."""
    # Engine returns the full real article on a row the incumbent WALLED (gold tokens = shell tokens,
    # reference NOT trustworthy). This must be recovered=True AND wall_broken=True, never penalized.
    s = score_url(_GOLD_BODY, WALLED, set(content_tokens(_SHELL_BODY)), reference_trustworthy=False)
    assert s["effective_recovery_class"] == RECOVERED, "a real article body must be RECOVERED"
    assert s["recovered"] is True, "recovering a walled URL must count as recovered"
    assert s["wall_broken"] is True, "turning a gold-WALLED row into RECOVERED is a wall break"
    assert s["reference_meaningful"] is False, "a shell gold body is not a trustworthy reference"

    # And in aggregate, beating walls only HELPS: an engine that breaks every wall must out-score
    # one that reproduces the incumbent walls.
    incumbent_walled = [
        {"url": f"https://w.example/{i}", "recovery_class": WALLED,
         "reference_tokens": sorted(content_tokens(_SHELL_BODY)), "source_type": "paywalled",
         "tier": "T1"}
        for i in range(3)
    ]
    breaker_spec = EngineSpec(name="zyte", pip_id="zyte-api>=0.7.0", import_name="zyte_api",
                              needs_key_env="ZYTE_API_KEY")
    reproducer_spec = EngineSpec(name="crawl4ai", pip_id="crawl4ai>=0.6.0", import_name="crawl4ai",
                                 is_baseline=True, needs_browser=True)
    breaker = run_engine(breaker_spec, incumbent_walled, fetch_override=lambda _u: _GOLD_BODY)
    reproducer = run_engine(reproducer_spec, incumbent_walled, fetch_override=lambda _u: _SHELL_BODY)
    assert breaker["score"] > reproducer["score"], (
        f"a wall-breaker {breaker['score']} must out-score an incumbent-wall reproducer "
        f"{reproducer['score']} — beating walls can never lower a score (§-1.3)"
    )
    assert breaker["metric"]["wall_break_rate"] == 1.0, "breaker must break all 3 walls"
    assert reproducer["metric"]["wall_break_rate"] == 0.0, "reproducer breaks no walls"
    print("  [PASS] wall-break is a WIN: breaker out-scores reproducer; wall_break_rate correct")


def main() -> int:
    print("=== fetch_crawl OFFLINE smoke test (no network / no GPU / mocked engines) ===")
    steps = (
        ("py_compile", step_py_compile),
        ("scorer_canary", step_scorer_canary),
        ("rubric_and_tokens", step_rubric_and_tokens),
        ("liveness_fails_on_stub", step_liveness_fails_on_stub),
        ("liveness_passes_on_good", step_liveness_passes_on_good),
        ("score_url_direction", step_score_url_direction),
        ("wall_break_is_a_win", step_wall_break_is_a_win),
        ("runner_scores_and_skips", step_runner_scores_and_skips),
    )
    for name, fn in steps:
        try:
            fn()
        except Exception:  # noqa: BLE001 — any failure is a smoke failure (non-zero exit).
            print(f"  [FAIL] {name}", file=sys.stderr)
            traceback.print_exc()
            print("SMOKE: FAIL", file=sys.stderr)
            return 1
    print("SMOKE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
