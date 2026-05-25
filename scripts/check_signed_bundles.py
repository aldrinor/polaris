#!/usr/bin/env python3
"""POLARIS CI guard: enforce that every "must-be-signed" bundle in the repo
has a `manifest.yaml.asc` that GPG-verifies against the SHIPPED trust-root
pubkey (`docs/carney_handover/polaris_demo_pubkey.asc`) AND whose signing
key fingerprint matches the pinned canonical key (`state/polaris_gpg_keyid.txt`).

I-ux-001a (GH#874) — LAW-II "no fake working" gate. Codex iter-3 P0 on the
I-ux-001 plan: the demo bundle was unsigned but the UI could render "Signed
bundle" from any `.asc` presence. This script blocks the regression: a CI
failure here means a bundle the UI labels "signed" wouldn't actually verify
in a reviewer's hands.

Verification runs in an ISOLATED temporary GNUPGHOME (Codex brief iter-2 P2)
so the host's default keyring cannot accidentally satisfy the check.

Exit codes:
  0 — every checked bundle verifies + fingerprint matches
  1 — one or more failures (each printed with reason)
  2 — environment setup failure (gpg missing, trust root missing, etc.)
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TRUST_ROOT_PUBKEY = REPO_ROOT / "docs/carney_handover/polaris_demo_pubkey.asc"
PINNED_FP_FILE = REPO_ROOT / "state/polaris_gpg_keyid.txt"

# Bundles the UI may label "signed" — every one MUST GPG-verify.
MUST_BE_SIGNED = [
    REPO_ROOT / "web/public/canonical_bundles/v1_canonical_success",
    REPO_ROOT / "tests/fixtures/signed_bundle/v1_canonical",
]


def _read_pinned_fp() -> str | None:
    if not PINNED_FP_FILE.is_file():
        return None
    fp = PINNED_FP_FILE.read_text(encoding="utf-8").strip().upper().replace(" ", "")
    return fp if re.fullmatch(r"[0-9A-F]{40}", fp) else None


def _verify_one(bundle_dir: Path, pinned_fp: str) -> tuple[bool, str]:
    """Return (ok, message). Verifies with `gpgv` against a freshly-dearmored
    binary keyring built ONLY from the shipped trust root.

    Why gpgv (Codex iter-1 P1 on the diff + cross-platform):
    - gpgv is the dedicated verify-only tool: it does NOT spawn gpg-agent
      (so it works in restricted/CI environments AND Windows MSYS where a
      fresh GNUPGHOME can't start an agent).
    - It takes an explicit --keyring file; it never reads ~/.gnupg or any
      host config (no keyboxd, no gpg.conf), so the prior `use-keyboxd`
      leak Codex flagged cannot happen.
    - The keyring is built fresh from the shipped trust-root pubkey each
      run, so the only key gpgv can trust is the one we pinned.
    """
    manifest = bundle_dir / "manifest.yaml"
    asc = bundle_dir / "manifest.yaml.asc"
    if not manifest.is_file():
        return False, f"manifest.yaml missing"
    if not asc.is_file() or asc.stat().st_size == 0:
        return False, f"manifest.yaml.asc missing or empty"

    tmpdir = Path(tempfile.mkdtemp(prefix="polaris-ci-gpgv-"))
    keyring = tmpdir / "trust.gpg"
    try:
        # Dearmor the shipped pubkey into a binary keyring gpgv can read.
        with open(TRUST_ROOT_PUBKEY, "rb") as src, open(keyring, "wb") as dst:
            de = subprocess.run(
                ["gpg", "--no-options", "--batch", "--dearmor"],
                stdin=src, stdout=dst, stderr=subprocess.PIPE, text=False,
            )
            if de.returncode != 0:
                return False, f"gpg --dearmor trust root failed: {de.stderr.decode('utf-8','replace').strip()}"

        # MSYS gpgv mangles absolute Windows paths in --keyring (it prepends
        # ~/.gnupg/ to anything containing a colon). Workaround: run from the
        # tmpdir and pass a relative keyring filename. Absolute paths for the
        # signature + manifest go through fine (different code path).
        v = subprocess.run(
            ["gpgv", "--keyring", "./trust.gpg", "--status-fd", "1",
             str(asc.resolve()), str(manifest.resolve())],
            cwd=str(tmpdir), capture_output=True, text=True,
        )
        if v.returncode != 0:
            return False, f"gpgv --verify FAILED: {v.stderr.strip().splitlines()[-1] if v.stderr.strip() else 'no detail'}"
        m = re.search(r"VALIDSIG\s+([0-9A-F]{40})\b", v.stdout + v.stderr, re.I)
        if not m:
            return False, "could not parse signing-key fingerprint from gpgv status"
        actual_fp = m.group(1).upper()
        if actual_fp != pinned_fp:
            return False, f"fingerprint mismatch: signed by {actual_fp[:16]}..., expected pinned {pinned_fp[:16]}..."
        return True, f"OK -- verified by pinned key {actual_fp[:16]}..."
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main() -> int:
    if not shutil.which("gpg"):
        print("FAIL: gpg binary not on PATH", file=sys.stderr)
        return 2
    if not shutil.which("gpgv"):
        print("FAIL: gpgv binary not on PATH", file=sys.stderr)
        return 2
    if not TRUST_ROOT_PUBKEY.is_file():
        print(f"FAIL: trust root pubkey missing at {TRUST_ROOT_PUBKEY}", file=sys.stderr)
        return 2
    pinned_fp = _read_pinned_fp()
    if not pinned_fp:
        print(f"FAIL: pinned fingerprint missing/invalid at {PINNED_FP_FILE}", file=sys.stderr)
        return 2

    failures: list[tuple[Path, str]] = []
    for bundle in MUST_BE_SIGNED:
        if not bundle.is_dir():
            failures.append((bundle, "bundle directory missing"))
            print(f"FAIL  {bundle}: bundle directory missing")
            continue
        ok, msg = _verify_one(bundle, pinned_fp)
        marker = "OK   " if ok else "FAIL "
        print(f"{marker} {bundle.relative_to(REPO_ROOT)}: {msg}")
        if not ok:
            failures.append((bundle, msg))

    if failures:
        print(f"\n{len(failures)} bundle(s) failed signature verification.", file=sys.stderr)
        return 1
    print(f"\nAll {len(MUST_BE_SIGNED)} bundle(s) signature-verified against pinned key {pinned_fp[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
