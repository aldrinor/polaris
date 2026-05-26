"""
verify_screenshot_manifest.py — helper called from codex-visual-required.yml.

Reads the manifest produced by visual_review_gate.py at
`outputs/visual_review_gate/<id>/iter_N/manifest.json` and verifies:
- the manifest has >= 1 entry (P1-iter2 fix)
- every `<label>.png` exists at the same directory
- every file's sha256 matches the manifest entry's `sha256` field

Exits 0 on success, 1 on any drift. Logs each failure on its own line.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: verify_screenshot_manifest.py <manifest.json> <screenshots_dir>", file=sys.stderr)
        return 2

    manifest_path = pathlib.Path(sys.argv[1])
    screenshots_dir = pathlib.Path(sys.argv[2])

    if not manifest_path.is_file():
        print(f"ERROR: manifest not at {manifest_path}", file=sys.stderr)
        return 1

    try:
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: manifest is not valid JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(entries, list) or len(entries) < 1:
        print(f"ERROR: manifest at {manifest_path} is empty or not a list", file=sys.stderr)
        return 1

    errors: list[str] = []
    for entry in entries:
        label = entry.get("label")
        declared = entry.get("sha256")
        if not label or not declared:
            errors.append(f"manifest entry malformed (missing label/sha256): {entry}")
            continue
        p = screenshots_dir / f"{label}.png"
        if not p.exists():
            errors.append(f"screenshot file missing: {p}")
            continue
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        actual = h.hexdigest()
        if actual != declared:
            errors.append(
                f"screenshot SHA drift: {p} declared={declared} actual={actual}"
            )

    if errors:
        print("ERROR: manifest verification failed:")
        for e in errors:
            print(f"  {e}")
        return 1

    print(f"OK: all {len(entries)} screenshots present with matching SHA256")
    return 0


if __name__ == "__main__":
    sys.exit(main())
