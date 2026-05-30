#!/usr/bin/env python3
"""Deterministic verifier for ``docs/canonical_pin.txt`` (I-meta-002 #973).

The canonical pin records ``<sha256>  <path>`` for each file that the §3.1 boot
ritual must confirm has not drifted. Historically the pin was reconciled with
``sha256sum`` over the working-tree bytes on a Windows ``autocrlf=true`` checkout
for some entries and over git-normalized (LF) content for others, so a single
``sha256sum`` could never match all entries on both Windows and Linux/CI.

This verifier uses ONE stable basis that matches git's text normalization:

  * normalize ``\\r\\n`` -> ``\\n`` ONLY (git collapses CRLF pairs; it does NOT
    reinterpret a lone carriage return), then
  * HARD-FAIL if any bare ``\\r`` (0x0D) remains. A stray CR in a pinned text
    file is suspicious and must STOP the boot ritual rather than hash clean --
    this is the trust-anchor tripwire (Codex brief-gate iter-1 P1). Without it,
    ``\\r\\n -> \\n`` followed by ``\\r -> \\n`` would let a bare-CR mutation hash
    identically to a newline and silently pass.

Because git stores the 14 pinned files as pure LF (verified), the LF-normalized
sha256 computed here equals the git blob content sha on every platform. The
verifier is OS-independent: pure file read + ``hashlib``, no ``git`` subprocess.

Usage::

    python scripts/verify_canonical_pin.py              # verify; exit 1 on any mismatch / bare-CR / missing
    python scripts/verify_canonical_pin.py --regenerate  # rewrite the pin from current normalized content, then verify

``--regenerate`` is the one-time reconciliation path; it also refuses (raises) if
any pinned file contains a bare CR, so a regenerate can never bake in a masked CR.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PIN_PATH = REPO_ROOT / "docs" / "canonical_pin.txt"

# Two-space separator, matching the existing ``sha256sum``-style pin format.
_PIN_SEP = "  "


class BareCarriageReturnError(ValueError):
    """A pinned file contains a bare CR (0x0D) after CRLF->LF normalization."""


def normalized_sha256(path: Path) -> str:
    """Return the SHA256 hex of ``path``'s git-normalized (LF) content.

    Collapses ``\\r\\n`` to ``\\n`` only -- identical to git text normalization --
    then raises :class:`BareCarriageReturnError` if any bare ``\\r`` remains, so a
    lone CR can never be normalized away and mask a real mutation.
    """
    data = path.read_bytes()
    normalized = data.replace(b"\r\n", b"\n")
    if b"\r" in normalized:
        raise BareCarriageReturnError(f"bare CR (0x0D) present in {path}")
    return hashlib.sha256(normalized).hexdigest()


def parse_pin(pin_text: str) -> list[tuple[str, str]]:
    """Parse ``<sha>  <path>`` lines; skip blanks and ``#`` comments."""
    entries: list[tuple[str, str]] = []
    for raw in pin_text.splitlines():  # splitlines() handles CRLF or LF line endings
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2:
            raise ValueError(f"malformed canonical_pin line: {raw!r}")
        sha, rel = parts
        entries.append((sha, rel))
    return entries


def verify(pin_path: Path = PIN_PATH) -> list[str]:
    """Return a list of human-readable problems; an empty list means all clean."""
    problems: list[str] = []
    entries = parse_pin(pin_path.read_text(encoding="utf-8"))
    for pinned_sha, rel in entries:
        target = REPO_ROOT / rel
        if not target.is_file():
            problems.append(f"MISSING: {rel}")
            continue
        try:
            actual = normalized_sha256(target)
        except BareCarriageReturnError as exc:
            problems.append(f"BARE-CR: {rel} ({exc})")
            continue
        if actual != pinned_sha:
            problems.append(f"DRIFT: {rel}\n   pin={pinned_sha}\n   got={actual}")
    return problems


def regenerate(pin_path: Path = PIN_PATH) -> int:
    """Rewrite ``pin_path`` from current normalized content. Return entry count.

    Preserves the existing pinned path set and order; only the SHA values change.
    Raises if a pinned file is missing or contains a bare CR (so regenerate can
    never bake in a masked carriage return).
    """
    entries = parse_pin(pin_path.read_text(encoding="utf-8"))
    new_lines: list[str] = []
    for _old_sha, rel in entries:
        target = REPO_ROOT / rel
        if not target.is_file():
            raise FileNotFoundError(f"cannot regenerate: pinned file missing: {rel}")
        actual = normalized_sha256(target)  # raises BareCarriageReturnError on bare CR
        new_lines.append(f"{actual}{_PIN_SEP}{rel}")
    pin_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return len(new_lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify or regenerate docs/canonical_pin.txt on a git-normalized (LF) basis."
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="rewrite the pin from current normalized content (one-time reconciliation), then verify",
    )
    parser.add_argument("--pin", type=Path, default=PIN_PATH, help="path to canonical_pin.txt")
    args = parser.parse_args(argv)

    if args.regenerate:
        count = regenerate(args.pin)
        print(f"regenerated {args.pin} ({count} entries, git-normalized LF basis)")

    problems = verify(args.pin)
    if problems:
        print("CANONICAL PIN VERIFY FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print("canonical pin OK: all entries match (git-normalized LF basis, bare-CR rejected)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
