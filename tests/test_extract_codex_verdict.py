"""Tests for the I-sec-001 (#535) codex-transcript leak-prevention tooling:
scripts/extract_codex_verdict.py and scripts/ci/codex_artifact_gate.py.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def _load(modname: str, relpath: str):
    spec = importlib.util.spec_from_file_location(modname, _REPO / relpath)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


ecv = _load("extract_codex_verdict", "scripts/extract_codex_verdict.py")
gate = _load("codex_artifact_gate", "scripts/ci/codex_artifact_gate.py")


# A realistic raw transcript: preamble + the verdict block + trailing prose.
_GOOD_RAW = """\
codex
some preamble reasoning the model emitted while exploring the repo ...
exec
git diff --stat

verdict: APPROVE
novel_p0: []
continuing_p0: []
p1: []
p2:
  - "P2: a minor naming nit"
convergence_call: accept_remaining
remaining_blockers_for_execution: []
tokens used
12345
trailing transcript prose that must NOT survive extraction
more trailing junk
"""


# ── extract ───────────────────────────────────────────────────────

def test_extract_writes_slim_block_only(tmp_path):
    raw = tmp_path / "raw.txt"
    raw.write_text(_GOOD_RAW, encoding="utf-8")
    out = tmp_path / "slim.txt"
    assert ecv.cmd_extract(raw, out) == 0
    text = out.read_text(encoding="utf-8")
    assert text.startswith("verdict: APPROVE")
    assert "trailing transcript prose" not in text
    assert "tokens used" not in text
    assert "some preamble reasoning" not in text
    assert "P2: a minor naming nit" in text
    assert ecv.cmd_validate(out) == 0  # the slim output round-trips


def test_extract_takes_the_LAST_verdict_block(tmp_path):
    # codex often prints the block twice; the final one wins.
    doubled = _GOOD_RAW + "\n" + (
        "verdict: REQUEST_CHANGES\nnovel_p0: []\ncontinuing_p0: []\n"
        "p1: []\np2: []\nconvergence_call: continue\n"
        "remaining_blockers_for_execution: []\n")
    raw = tmp_path / "raw.txt"
    raw.write_text(doubled, encoding="utf-8")
    out = tmp_path / "slim.txt"
    assert ecv.cmd_extract(raw, out) == 0
    assert out.read_text(encoding="utf-8").startswith("verdict: REQUEST_CHANGES")


def test_extract_blocks_secret_in_verdict(tmp_path):
    fake = "sk-" + "A1b2C3d4" * 6  # synthetic OpenAI-shaped key, not real
    raw = tmp_path / "raw.txt"
    raw.write_text(
        "verdict: REQUEST_CHANGES\nnovel_p0: []\ncontinuing_p0: []\n"
        f'p1:\n  - "leaked: {fake}"\np2: []\n'
        "convergence_call: continue\nremaining_blockers_for_execution: []\n",
        encoding="utf-8")
    out = tmp_path / "slim.txt"
    assert ecv.cmd_extract(raw, out) == 4  # secret-detected exit code
    assert not out.exists()               # nothing written on a leak


# ── parse / serialize ─────────────────────────────────────────────

def test_parse_returns_none_when_no_block():
    assert ecv.parse_verdict_block("just transcript text, no verdict") is None


def test_parse_returns_none_on_missing_keys():
    assert ecv.parse_verdict_block(
        "verdict: APPROVE\nnovel_p0: []\n") is None  # 5 keys missing


def test_parse_inline_nonempty_list_not_dropped():
    """Codex diff-review iter-1 P1: a non-empty inline flow list must be
    parsed, not silently dropped."""
    block = (
        'verdict: REQUEST_CHANGES\nnovel_p0: []\ncontinuing_p0: []\n'
        'p1: ["P1: first finding", "P1: second finding"]\np2: []\n'
        'convergence_call: continue\nremaining_blockers_for_execution: []\n')
    parsed = ecv.parse_verdict_block(block)
    assert parsed is not None
    assert parsed["p1"] == ["P1: first finding", "P1: second finding"]
    slim = ecv.serialize_verdict(parsed)
    assert "P1: first finding" in slim and "P1: second finding" in slim


def test_parse_inline_list_with_comma_inside_quotes():
    block = (
        'verdict: APPROVE\nnovel_p0: []\ncontinuing_p0: []\n'
        'p1: []\np2: ["P2: a, b, c is one item"]\n'
        'convergence_call: accept_remaining\n'
        'remaining_blockers_for_execution: []\n')
    parsed = ecv.parse_verdict_block(block)
    assert parsed is not None
    assert parsed["p2"] == ["P2: a, b, c is one item"]


def test_serialize_roundtrip_is_idempotent():
    parsed = ecv.parse_verdict_block(_GOOD_RAW)
    assert parsed is not None
    once = ecv.serialize_verdict(parsed)
    assert ecv.serialize_verdict(ecv.parse_verdict_block(once)) == once


# ── validate ──────────────────────────────────────────────────────

def test_validate_rejects_oversized(tmp_path):
    big = tmp_path / "big.txt"
    big.write_text("verdict: APPROVE\n" + "x" * (ecv.SLIM_BYTE_CAP + 10),
                   encoding="utf-8")
    assert ecv.cmd_validate(big) == 1


def test_validate_rejects_trailing_transcript(tmp_path):
    f = tmp_path / "trail.txt"
    f.write_text(_GOOD_RAW, encoding="utf-8")  # raw — has trailing prose
    assert ecv.cmd_validate(f) == 1


# ── codex_artifact_gate path rules ────────────────────────────────

def test_gate_denylist_blocks_raw_transcripts():
    for name in ("codex_brief_review_iter1.txt", "codex_diff_review_iter2.txt",
                 "codex_brief_verdict_iter3.txt", "codex_diff_audit_iter_2.txt",
                 "codex_brief_review.txt"):
        assert gate.DENY_RE.search(name), f"denylist must catch {name}"


def test_gate_allowlist_permits_slim_artifacts():
    for name in ("brief.md", "diff_brief.md", "codex_brief_verdict.txt",
                 "codex_diff_audit.txt", "codex_diff.patch"):
        assert name in gate.ALLOWED_BASENAMES, name
        assert not gate.DENY_RE.search(name), f"{name} wrongly denied"


def test_gate_force_approve_is_exempt():
    assert gate.FORCE_APPROVE_RE.match("codex_brief_verdict_iter5_force_approve.txt")
