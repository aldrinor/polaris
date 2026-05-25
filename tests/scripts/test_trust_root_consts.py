"""I-ux-001a — defense-in-depth test for the baked TRUST_ROOT_BASE64 + PINNED_FP
constants in web/lib/gpg_verify_bundle.ts.

Codex diff iter-3 P1: my first attempt baked a hand-transcribed armored pubkey
into the TS const; 4-byte transcription errors produced a different fingerprint
than the pinned one, so production would have always degraded to
present_unverified. This test prevents that class of mismatch from ever
recurring silently:

  1. Decode TRUST_ROOT_BASE64 — bytes must match the shipped
     docs/carney_handover/polaris_demo_pubkey.asc EXACTLY.
  2. PINNED_FP must match state/polaris_gpg_keyid.txt exactly.
  3. Dearmor the decoded bytes through gpg --show-keys and assert the parsed
     primary-key fingerprint equals PINNED_FP.
"""
from __future__ import annotations

import base64
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TS_FILE = REPO_ROOT / "web" / "lib" / "gpg_verify_bundle.ts"
TRUST_ROOT_FILE = REPO_ROOT / "docs" / "carney_handover" / "polaris_demo_pubkey.asc"
PIN_FILE = REPO_ROOT / "state" / "polaris_gpg_keyid.txt"

GPG_AVAILABLE = shutil.which("gpg") is not None


def _extract_baked_consts() -> tuple[str, str]:
    text = TS_FILE.read_text(encoding="utf-8")
    fp_m = re.search(r'const PINNED_FP\s*=\s*"([0-9A-F]{40})"', text)
    b64_m = re.search(r'const TRUST_ROOT_BASE64\s*=\s*\n?\s*"([A-Za-z0-9+/=]+)"', text)
    assert fp_m, "PINNED_FP constant not found in gpg_verify_bundle.ts"
    assert b64_m, "TRUST_ROOT_BASE64 constant not found in gpg_verify_bundle.ts"
    return fp_m.group(1), b64_m.group(1)


def test_baked_trust_root_matches_shipped_file():
    """Decoded TRUST_ROOT_BASE64 must equal the shipped pubkey file bytes."""
    _, b64 = _extract_baked_consts()
    decoded = base64.b64decode(b64)
    shipped = TRUST_ROOT_FILE.read_bytes()
    assert decoded == shipped, (
        f"TRUST_ROOT_BASE64 ({len(decoded)} bytes) does not match the shipped "
        f"{TRUST_ROOT_FILE} ({len(shipped)} bytes). Regenerate the const via: "
        f"`base64 -w0 < docs/carney_handover/polaris_demo_pubkey.asc`."
    )


def test_baked_pinned_fp_matches_pin_file():
    """PINNED_FP must equal the fingerprint in state/polaris_gpg_keyid.txt."""
    fp, _ = _extract_baked_consts()
    pinned = PIN_FILE.read_text(encoding="utf-8").strip().upper().replace(" ", "")
    assert fp == pinned, (
        f"PINNED_FP in gpg_verify_bundle.ts ({fp}) does not match "
        f"state/polaris_gpg_keyid.txt ({pinned})."
    )


@pytest.mark.skipif(not GPG_AVAILABLE, reason="gpg binary not available")
def test_baked_trust_root_dearmored_has_pinned_fingerprint():
    """End-to-end: dearmored TRUST_ROOT_BASE64 must yield a key whose primary
    fingerprint equals PINNED_FP. Catches the transcription-error class even
    if test 1 somehow accepts bytes that aren't a valid OpenPGP packet."""
    fp, b64 = _extract_baked_consts()
    decoded = base64.b64decode(b64)
    p = subprocess.run(
        ["gpg", "--no-options", "--batch", "--show-keys", "--with-fingerprint",
         "--with-colons"],
        input=decoded, capture_output=True,
    )
    assert p.returncode == 0, (
        f"gpg --show-keys failed on decoded TRUST_ROOT_BASE64: "
        f"{p.stderr.decode('utf-8','replace').strip()}"
    )
    fps = []
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("fpr:"):
            parts = line.split(":")
            if len(parts) >= 10 and parts[9]:
                fps.append(parts[9])
    assert fps, "no fingerprint parsed from gpg --show-keys output"
    assert fps[0] == fp, (
        f"dearmored trust root primary fingerprint ({fps[0]}) != PINNED_FP ({fp})"
    )
