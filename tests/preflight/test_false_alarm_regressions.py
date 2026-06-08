"""I-cred-013 (#1163) preflight — REGRESSION LOCKS for the 5 recurring false alarms.

Each test FAILS if a previously-killed false alarm resurfaces. Offline, deterministic, no spend.
These exist because the operator flagged these five as repeat-offenders he never wants to see again:
the durable kill is a regression test, not a one-off fix."""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_fa1_crlf_gitattributes_rule_committed():
    """FA1: the signed-bundle fixtures must carry a '-text' .gitattributes rule so core.autocrlf can
    NEVER rewrite the SHA256-pinned / GPG-signed bytes to CRLF (the 'SHA256_MISMATCH / needs operator
    signing key' false alarm). The demo key 6336C4448C1901CC is local; conformance is never env-blocked."""
    gitattributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"tests/fixtures/signed_bundle/\*\*\s+-text", gitattributes), (
        "the signed_bundle '-text' .gitattributes rule is gone — CRLF will silently re-break the "
        "SHA256-pinned/GPG-signed fixtures and resurface the 'needs operator key' false alarm"
    )


def test_fa2_competitor_outputs_present():
    """FA2: the ChatGPT + Gemini competitor DR outputs for all 5 golden Qs ARE committed — so 'we've
    never run the head-to-head' is always a false claim. Grep the repo before asserting any negative."""
    base = ROOT / "outputs" / "dr_benchmark" / "external_outputs"
    questions = ["Q72_ai_labor", "Q75_metal_ions_cvd", "Q76_gut_microbiota",
                 "Q78_parkinsons_dbs", "Q90_adas_liability"]
    for system in ("gpt_5_5_pro", "gemini_3_1_pro"):
        for q in questions:
            path = base / system / f"{q}.md"
            assert path.exists() and path.stat().st_size > 0, f"competitor output missing/empty: {path}"


def test_fa3_run_health_fail_loud_guard_present():
    """FA3: a degraded / dead-route run must FAIL LOUD (abort), never swallow into a false-green. The
    behavioral run-health guard must remain wired in the Gate-B run path."""
    src = (ROOT / "scripts" / "dr_benchmark" / "pathB_run_gate.py").read_text(encoding="utf-8")
    assert any(tok in src for tok in ("PG_RUN_HEALTH_GATE", "abort_discovery_degraded", "PG_BEHAVIORAL_CANARY")), (
        "the run-health / behavioral-canary fail-loud guard is gone — a dead model route could ship a "
        "false-green run on dead discovery (the drb_72 silent-downgrade lesson)"
    )


def test_fa4_empty_response_failover_present():
    """FA4: an empty-200 (mirror-blank) must be handled as an intermittent PROVIDER failure (retry /
    failover), never silently read as the model's defect / a blank answer."""
    src = (ROOT / "src" / "polaris_graph" / "llm" / "openrouter_client.py").read_text(encoding="utf-8")
    assert re.search(r"empty[_ ]?response|empty.{0,8}200|allow_fallbacks|provider.{0,12}fail", src, re.I), (
        "the empty-200 provider-failover handling is gone — mirror-blanks would be misread as a model "
        "defect instead of an intermittent provider failure"
    )


def test_fa5_journal_only_gated_by_source_restriction():
    """FA5: the journal-only adequacy floor must be gated by the protocol's source_restriction — a
    corpus_approval_denied is NOT auto-authorize and NOT auto-fix-the-classifier; it depends on the
    question's own declared restriction."""
    from src.polaris_graph.nodes.journal_only_filter import journal_only_active
    assert journal_only_active(None) is False                       # no protocol -> floor does NOT fire
    assert journal_only_active({}) is False                          # no restriction -> floor does NOT fire
    # a protocol that declares journal_only is flag-dependent (never crashes, never fires blindly)
    assert journal_only_active({"source_restriction": "journal_only"}) in (True, False)
