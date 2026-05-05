"""GPG setup helper for slice 004 audit-bundle signing.

Generates an unprotected GPG keypair (no passphrase) suitable for the
local Sep 6 demo, then prints the key id so the operator can paste it
into `.env` as `POLARIS_GPG_KEY_ID`.

This is a DEMO helper — the keypair is unprotected (passphrase=''), which
is fine for a local non-production demo on the operator's laptop. For a
real production deployment the key MUST be HSM-backed and have a strong
passphrase per CLAUDE.md §9 invariants.

Usage:
    python scripts/setup_gpg_for_demo.py --name "POLARIS Demo" \
        --email demo@polaris-canada.local

After it prints `POLARIS_GPG_KEY_ID=<long_key_id>`, append that line to
`.env` and reboot the FastAPI backend so create_app() picks it up.

Verifies preflight:
- gpg binary on PATH
- python-gnupg installed
- no existing key with the same uid (refuses to clobber)

LAW II — no fake working: this script does NOT silently succeed if gpg
is missing or if the key generation fails. It surfaces the error and
exits non-zero.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from typing import Optional


def _check_gpg_binary() -> Optional[str]:
    """Return path to gpg binary or None."""
    return shutil.which("gpg")


def _existing_key_id(name: str, email: str) -> Optional[str]:
    """Return key fingerprint if a key with this uid already exists."""
    try:
        out = subprocess.check_output(
            ["gpg", "--list-secret-keys", "--with-colons", f"<{email}>"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except subprocess.CalledProcessError:
        return None
    for line in out.splitlines():
        if line.startswith("fpr:"):
            return line.split(":")[9]
    return None


def _generate_key(name: str, email: str) -> str:
    """Generate an unprotected RSA-4096 keypair via gpg --batch."""
    batch = (
        "%no-protection\n"
        "Key-Type: RSA\n"
        "Key-Length: 4096\n"
        "Subkey-Type: RSA\n"
        "Subkey-Length: 4096\n"
        f"Name-Real: {name}\n"
        f"Name-Email: {email}\n"
        "Expire-Date: 1y\n"
        "%commit\n"
    )
    proc = subprocess.run(
        ["gpg", "--batch", "--gen-key"],
        input=batch,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"gpg --gen-key failed (rc={proc.returncode}): {proc.stderr.strip()}"
        )
    fpr = _existing_key_id(name, email)
    if not fpr:
        raise RuntimeError(
            "gpg --gen-key returned 0 but no key with this uid found afterward"
        )
    return fpr


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a local GPG demo keypair for slice 004 signing"
    )
    p.add_argument(
        "--name", default="POLARIS Demo",
        help="Real name on the key (default: 'POLARIS Demo')",
    )
    p.add_argument(
        "--email", default="demo@polaris-canada.local",
        help="Email on the key (default: demo@polaris-canada.local)",
    )
    p.add_argument(
        "--reuse-existing", action="store_true",
        help="If a key with this uid exists, print its id rather than failing",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    gpg_path = _check_gpg_binary()
    if not gpg_path:
        print(
            "ERROR: gpg binary not on PATH. Install GnuPG first.\n"
            "  macOS:   brew install gnupg\n"
            "  Linux:   apt-get install gnupg\n"
            "  Windows: gpg4win.org or 'winget install GnuPG.GnuPG'",
            file=sys.stderr,
        )
        return 2

    try:
        import gnupg  # noqa: F401
    except ImportError:
        print(
            "WARNING: python-gnupg not installed. The slice 004 audit-bundle "
            "signer needs it; install via 'pip install python-gnupg' before "
            "running the demo backend.",
            file=sys.stderr,
        )

    existing = _existing_key_id(args.name, args.email)
    if existing:
        if args.reuse_existing:
            print(f"Reusing existing key: {existing}")
            print(f"POLARIS_GPG_KEY_ID={existing}")
            return 0
        print(
            f"ERROR: a key for <{args.email}> already exists (fpr={existing}). "
            f"Re-run with --reuse-existing to print its id, or pick a different "
            f"--email.",
            file=sys.stderr,
        )
        return 3

    print(f"Generating GPG keypair for {args.name} <{args.email}>...")
    try:
        fpr = _generate_key(args.name, args.email)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 4

    print(f"Generated key: {fpr}")
    print("")
    print("Append this line to your .env (and reboot the FastAPI backend):")
    print(f"POLARIS_GPG_KEY_ID={fpr}")
    print("")
    print(
        "Verify with: PYTHONPATH=src python -c "
        "\"from dotenv import load_dotenv; load_dotenv(); "
        "from fastapi.testclient import TestClient; "
        "from polaris_v6.api.app import create_app; "
        "print(TestClient(create_app()).get('/api/audit-bundle/health').json())\""
    )
    print(
        "Expected: signing_backend != 'sentinel' (a real GPGSigner injected "
        "by create_app)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
