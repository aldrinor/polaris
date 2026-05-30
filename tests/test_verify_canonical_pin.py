"""Tests for scripts/verify_canonical_pin.py (I-meta-002 #973). NO network / NO spend.

Asserts the canonical-pin verifier uses a stable git-normalized (LF) basis:
- a CRLF file and the same file with LF hash identically (cross-platform stability);
- a real content change is still detected as a mismatch (the gate still catches mutation);
- the committed docs/canonical_pin.txt verifies clean;
- a bare CR injected into a pinned file HARD-FAILS instead of hashing clean
  (Codex brief-gate iter-1 P1 tripwire) — a lone \\r must stop the ritual, not be
  normalized away;
- --regenerate refuses when a file has a bare CR, and preserves the pinned path set/order.
"""

from __future__ import annotations

import hashlib

import pytest

import scripts.verify_canonical_pin as vcp


def _write(path, data: bytes) -> None:
    path.write_bytes(data)


def test_crlf_and_lf_hash_identically(tmp_path):
    crlf = tmp_path / "crlf.md"
    lf = tmp_path / "lf.md"
    _write(crlf, b"line one\r\nline two\r\n")
    _write(lf, b"line one\nline two\n")
    assert vcp.normalized_sha256(crlf) == vcp.normalized_sha256(lf)
    # and it equals the plain sha256 of the LF content (the git blob basis)
    assert vcp.normalized_sha256(crlf) == hashlib.sha256(b"line one\nline two\n").hexdigest()


def test_real_content_change_is_detected(tmp_path):
    original = tmp_path / "doc.md"
    _write(original, b"dose is 2.1 percent\n")
    pinned = vcp.normalized_sha256(original)
    # a genuine content change must change the hash (gate still catches mutation)
    _write(original, b"dose is 9.9 percent\n")
    assert vcp.normalized_sha256(original) != pinned


def test_bare_cr_hard_fails(tmp_path):
    """A lone \\r (not part of \\r\\n) must raise, never hash clean."""
    sneaky = tmp_path / "bare_cr.md"
    _write(sneaky, b"first half\rsecond half\n")  # bare CR, no following LF
    with pytest.raises(vcp.BareCarriageReturnError):
        vcp.normalized_sha256(sneaky)


def test_bare_cr_surfaces_as_verify_problem(tmp_path):
    target = tmp_path / "x.md"
    _write(target, b"ok line\n")
    good_sha = vcp.normalized_sha256(target)
    pin = tmp_path / "pin.txt"
    pin.write_text(f"{good_sha}  x.md\n", encoding="utf-8")
    # repoint REPO_ROOT at tmp so the relative path resolves
    orig_root = vcp.REPO_ROOT
    vcp.REPO_ROOT = tmp_path
    try:
        assert vcp.verify(pin) == []  # clean first
        _write(target, b"ok line\rinjected\n")  # bare CR mutation
        problems = vcp.verify(pin)
        assert len(problems) == 1
        assert problems[0].startswith("BARE-CR:")
    finally:
        vcp.REPO_ROOT = orig_root


def test_regenerate_preserves_path_set_and_order(tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    _write(a, b"alpha\r\n")
    _write(b, b"beta\n")
    pin = tmp_path / "pin.txt"
    pin.write_text("0000  a.md\n1111  b.md\n", encoding="utf-8")  # stale shas
    orig_root = vcp.REPO_ROOT
    vcp.REPO_ROOT = tmp_path
    try:
        count = vcp.regenerate(pin)
        assert count == 2
        entries = vcp.parse_pin(pin.read_text(encoding="utf-8"))
        assert [rel for _sha, rel in entries] == ["a.md", "b.md"]  # order + set preserved
        assert vcp.verify(pin) == []  # regenerated pin verifies clean
        # CRLF file 'a' was normalized to LF before hashing
        assert entries[0][0] == hashlib.sha256(b"alpha\n").hexdigest()
    finally:
        vcp.REPO_ROOT = orig_root


def test_regenerate_refuses_on_bare_cr(tmp_path):
    a = tmp_path / "a.md"
    _write(a, b"has\rbare cr\n")
    pin = tmp_path / "pin.txt"
    pin.write_text("0000  a.md\n", encoding="utf-8")
    orig_root = vcp.REPO_ROOT
    vcp.REPO_ROOT = tmp_path
    try:
        with pytest.raises(vcp.BareCarriageReturnError):
            vcp.regenerate(pin)
    finally:
        vcp.REPO_ROOT = orig_root


def test_committed_canonical_pin_verifies_clean():
    """The real docs/canonical_pin.txt must verify clean under the LF basis."""
    problems = vcp.verify(vcp.PIN_PATH)
    assert problems == [], f"canonical pin has unresolved drift: {problems}"
