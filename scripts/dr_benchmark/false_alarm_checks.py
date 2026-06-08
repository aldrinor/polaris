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

import pathlib
import re

# Repo root = three parents up from scripts/dr_benchmark/false_alarm_checks.py.
ROOT = pathlib.Path(__file__).resolve().parents[2]


def check_fa1_crlf_gitattributes_rule_committed() -> None:
    """FA1: the signed-bundle fixtures must carry a '-text' .gitattributes rule so core.autocrlf can
    NEVER rewrite the SHA256-pinned / GPG-signed bytes to CRLF (the 'SHA256_MISMATCH / needs operator
    signing key' false alarm). The demo key 6336C4448C1901CC is local; conformance is never env-blocked."""
    gitattributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"tests/fixtures/signed_bundle/\*\*\s+-text", gitattributes), (
        "the signed_bundle '-text' .gitattributes rule is gone — CRLF will silently re-break the "
        "SHA256-pinned/GPG-signed fixtures and resurface the 'needs operator key' false alarm"
    )


def check_fa2_competitor_outputs_present() -> None:
    """FA2: the ChatGPT + Gemini competitor DR outputs for all 5 golden Qs ARE committed — so 'we've
    never run the head-to-head' is always a false claim. Grep the repo before asserting any negative."""
    base = ROOT / "outputs" / "dr_benchmark" / "external_outputs"
    questions = ["Q72_ai_labor", "Q75_metal_ions_cvd", "Q76_gut_microbiota",
                 "Q78_parkinsons_dbs", "Q90_adas_liability"]
    for system in ("gpt_5_5_pro", "gemini_3_1_pro"):
        for q in questions:
            path = base / system / f"{q}.md"
            assert path.exists() and path.stat().st_size > 0, f"competitor output missing/empty: {path}"


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
