"""Tests for scripts/check_signed_bundles.py — the I-ux-001a CI honesty guard.

Covers all three signature states (gpg_verified / present_unverified-as-missing
/ missing) end-to-end against the SHIPPED trust-root pubkey, in the same
isolated-keyring mode the production guard uses.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_signed_bundles.py"

GPG_AVAILABLE = shutil.which("gpg") is not None
pytestmark = pytest.mark.skipif(
    not GPG_AVAILABLE, reason="gpg binary not available in test env",
)


def _run_guard() -> tuple[int, str]:
    r = subprocess.run(
        ["python", str(SCRIPT)], capture_output=True, text=True,
        cwd=str(REPO_ROOT),
    )
    return r.returncode, r.stdout + r.stderr


def test_guard_passes_with_signed_bundles_in_place():
    """Happy path — both must-be-signed bundles ship with valid signatures."""
    rc, out = _run_guard()
    assert rc == 0, f"guard failed unexpectedly: {out}"
    assert "All " in out and "signature-verified" in out


def test_guard_fails_when_asc_missing(tmp_path):
    """If the .asc disappears, the guard must FAIL non-zero (the demo bundle
    can never silently lose its seal)."""
    target = REPO_ROOT / "web/public/canonical_bundles/v1_canonical_success/manifest.yaml.asc"
    if not target.is_file():
        pytest.skip("repo state: target bundle currently has no .asc")
    backup = tmp_path / "manifest.yaml.asc"
    shutil.copy2(target, backup)
    try:
        target.unlink()
        rc, out = _run_guard()
        assert rc != 0, "guard should have failed without a signature"
        assert "manifest.yaml.asc missing" in out or "missing or empty" in out
    finally:
        shutil.copy2(backup, target)
    # Sanity: positive path restored.
    rc, _ = _run_guard()
    assert rc == 0


def test_guard_fails_on_wrong_signature(tmp_path):
    """If the .asc doesn't actually GPG-verify against the trust root (e.g. a
    placeholder or a sig from a different key), the guard must FAIL."""
    target = REPO_ROOT / "web/public/canonical_bundles/v1_canonical_success/manifest.yaml.asc"
    if not target.is_file():
        pytest.skip("repo state: target bundle currently has no .asc")
    backup = tmp_path / "manifest.yaml.asc"
    shutil.copy2(target, backup)
    try:
        target.write_text(
            "-----BEGIN PGP SIGNATURE-----\n"
            "# placeholder, not a real signature\n"
            "-----END PGP SIGNATURE-----\n",
            encoding="utf-8",
        )
        rc, out = _run_guard()
        assert rc != 0, "guard should have failed on an invalid signature"
        assert "FAIL" in out
    finally:
        shutil.copy2(backup, target)
