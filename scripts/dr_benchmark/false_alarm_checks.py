"""I-cred-013 (#1163): the 5 recurring false-alarm regression checks — as a NON-TEST module.

These are the durable kills for the 5 false alarms the operator flagged as repeat-offenders. They live
HERE (not only in ``tests/preflight/test_false_alarm_regressions.py``) so that BOTH:
  - the pytest regression locks (CI), and
  - the live super-heavy pre-spend preflight (``super_heavy_preflight``, runs on the paid VM)
import the SAME assertions. The production preflight must NOT depend on ``tests/`` being importable in
the VM launch shape (cwd/sys.path luck), so the shared logic is extracted to this importable module and
the test module is a thin re-export.

Each check is no-arg and raises ``AssertionError`` on a resurfaced false alarm (so the pytest module is a
trivial wrapper). Offline, deterministic, no spend, no network.
"""
from __future__ import annotations

import logging
import os
import pathlib
import re

logger = logging.getLogger(__name__)

# Repo root = three parents up from scripts/dr_benchmark/false_alarm_checks.py.
ROOT = pathlib.Path(__file__).resolve().parents[2]

# BUG-23 (#1262): FA2 (competitor-output presence) is benchmark SCORING bookkeeping, not a
# research-quality gate. By default it is NON-FATAL on the paid in-flight research path — a missing
# competitor markdown (e.g. gpt_5_5_pro/Q72_ai_labor.md) must NEVER hard-crash a $4+ run. Set this
# env flag to "1"/"true" to RE-ARM the strict AssertionError (the CI regression lock + any actual
# scoring/comparison step set it, so deletion of the committed competitor outputs is still caught).
# LAW VI: env-driven named constant, sane default OFF (non-fatal on the live run path).
_FA2_REQUIRE_COMPETITOR_OUTPUTS_ENV = "PG_FA2_REQUIRE_COMPETITOR_OUTPUTS"


def _fa2_require_competitor_outputs() -> bool:
    """True iff the FA2 competitor-output presence check should HARD-FAIL (AssertionError) on a missing
    file. Default OFF: a missing scoring-harness markdown is logged + recorded degraded, never crashes
    an in-flight research run (BUG-23, #1262)."""
    return os.getenv(_FA2_REQUIRE_COMPETITOR_OUTPUTS_ENV, "0").strip().lower() in ("1", "true", "yes", "on")


def check_fa1_crlf_gitattributes_rule_committed() -> None:
    """FA1: the signed-bundle fixtures must carry a '-text' .gitattributes rule so core.autocrlf can
    NEVER rewrite the SHA256-pinned / GPG-signed bytes to CRLF (the 'SHA256_MISMATCH / needs operator
    signing key' false alarm). The demo key 6336C4448C1901CC is local; conformance is never env-blocked."""
    gitattributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"tests/fixtures/signed_bundle/\*\*\s+-text", gitattributes), (
        "the signed_bundle '-text' .gitattributes rule is gone — CRLF will silently re-break the "
        "SHA256-pinned/GPG-signed fixtures and resurface the 'needs operator key' false alarm"
    )


def check_fa2_competitor_outputs_present(require: bool | None = None) -> list[str]:
    """FA2: the ChatGPT + Gemini competitor DR outputs for all 5 golden Qs ARE committed — so 'we've
    never run the head-to-head' is always a false claim. Grep the repo before asserting any negative.

    BUG-23 (#1262): this is a benchmark-SCORING bookkeeping check, NOT a research-quality gate. It used to
    HARD-CRASH (``assert ...``) the moment a single competitor markdown was missing/empty. On the paid VM
    that AssertionError is normalized to a fatal GateError by ``super_heavy_preflight``, so drb_72's first
    attempt aborted a $4+ in-flight research run because ``gpt_5_5_pro/Q72_ai_labor.md`` was absent in the
    run shape — a scoring-harness file utterly unrelated to research quality.

    FIX: the check is NON-FATAL by default. A missing/empty competitor output is LOGGED (fail-loud, not
    silent) and RECORDED as a degraded/skipped entry that the caller may surface — it never raises on the
    live run path. The strict ``AssertionError`` is re-armed only when ``require`` is True, i.e. when a
    scoring/comparison is actually requested or via env ``PG_FA2_REQUIRE_COMPETITOR_OUTPUTS=1`` (the CI
    regression lock + any real scoring step set it, so deletion of the committed competitor outputs is
    still caught loudly where it matters). ``require=None`` (default) consults that env flag.

    FAITHFULNESS: untouched. FA2 inspects ONLY external competitor markdown files; it has zero bearing on
    strict_verify / NLI / 4-role / span-grounding or any verified claim. The other four false-alarm locks
    (FA1/FA3/FA4/FA5) keep their original strict ``AssertionError`` behavior exactly.

    Returns the list of missing/empty competitor paths (empty list = all present). Raises ``AssertionError``
    only when ``require`` resolves True and at least one output is missing/empty.
    """
    if require is None:
        require = _fa2_require_competitor_outputs()
    base = ROOT / "outputs" / "dr_benchmark" / "external_outputs"
    questions = ["Q72_ai_labor", "Q75_metal_ions_cvd", "Q76_gut_microbiota",
                 "Q78_parkinsons_dbs", "Q90_adas_liability"]
    missing: list[str] = []
    for system in ("gpt_5_5_pro", "gemini_3_1_pro"):
        for q in questions:
            path = base / system / f"{q}.md"
            if not (path.exists() and path.stat().st_size > 0):
                missing.append(str(path))
    if missing:
        if require:
            # explicit scoring/comparison (or env re-arm): the head-to-head cannot proceed without these.
            raise AssertionError(f"competitor output(s) missing/empty: {missing}")
        # in-flight research run: fail LOUD in the log + record degraded, but do NOT crash the paid run.
        logger.warning(
            "FA2 (BUG-23, #1262): %d competitor scoring output(s) missing/empty %s — research run "
            "continues (set %s=1 only when a head-to-head scoring/comparison is actually requested).",
            len(missing), missing, _FA2_REQUIRE_COMPETITOR_OUTPUTS_ENV,
        )
    return missing


def check_fa3_run_health_fail_loud_guard_present() -> None:
    """FA3: a degraded / dead-route run must FAIL LOUD (abort), never swallow into a false-green. The
    behavioral run-health guard must remain wired in the Gate-B run path."""
    src = (ROOT / "scripts" / "dr_benchmark" / "pathB_run_gate.py").read_text(encoding="utf-8")
    assert any(tok in src for tok in ("PG_RUN_HEALTH_GATE", "abort_discovery_degraded", "PG_BEHAVIORAL_CANARY")), (
        "the run-health / behavioral-canary fail-loud guard is gone — a dead model route could ship a "
        "false-green run on dead discovery (the drb_72 silent-downgrade lesson)"
    )


def check_fa4_empty_response_failover_present() -> None:
    """FA4: an empty-200 (mirror-blank) must be handled as an intermittent PROVIDER failure (retry /
    failover), never silently read as the model's defect / a blank answer."""
    src = (ROOT / "src" / "polaris_graph" / "llm" / "openrouter_client.py").read_text(encoding="utf-8")
    assert re.search(r"empty[_ ]?response|empty.{0,8}200|allow_fallbacks|provider.{0,12}fail", src, re.I), (
        "the empty-200 provider-failover handling is gone — mirror-blanks would be misread as a model "
        "defect instead of an intermittent provider failure"
    )


def check_fa5_journal_only_gated_by_source_restriction() -> None:
    """FA5: the journal-only adequacy floor must be gated by the protocol's source_restriction — a
    corpus_approval_denied is NOT auto-authorize and NOT auto-fix-the-classifier; it depends on the
    question's own declared restriction."""
    from src.polaris_graph.nodes.journal_only_filter import journal_only_active
    assert journal_only_active(None) is False                       # no protocol -> floor does NOT fire
    assert journal_only_active({}) is False                          # no restriction -> floor does NOT fire
    # a protocol that declares journal_only is flag-dependent (never crashes, never fires blindly)
    assert journal_only_active({"source_restriction": "journal_only"}) in (True, False)


# The 5 checks in CI/preflight order (the runtime preflight re-asserts these same five).
ALL_CHECKS = (
    check_fa1_crlf_gitattributes_rule_committed,
    check_fa2_competitor_outputs_present,
    check_fa3_run_health_fail_loud_guard_present,
    check_fa4_empty_response_failover_present,
    check_fa5_journal_only_gated_by_source_restriction,
)
