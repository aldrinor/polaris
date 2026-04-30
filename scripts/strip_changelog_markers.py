"""Strip changelog markers from a diff or source file before sending
to Codex for review (autoloop V3 — Procedural Independence Protocol).

Per `.codex/REVIEW_BRIEF_FORMAT_v2.md` + sister-project research:
prior-round changelog markers (`// CORRECTED v2 per Codex round-1`,
`# Codex round-3 LOW fix`, etc.) anchor the reviewer toward
"already addressed" framings even when the underlying patch is
incomplete. Procedural Independence: remove them mechanically
rather than asking Codex to mentally suppress.

Usage:
    python scripts/strip_changelog_markers.py path/to/diff.txt
    git diff main | python scripts/strip_changelog_markers.py -

Patterns stripped (lines matching ANY of these are removed entirely
when the line is a comment line, OR the marker text is removed
when embedded in a multi-marker line):

    Codex round-N <verdict>           e.g. "Codex round-2 HIGH fix"
    CORRECTED v\\d+                    e.g. "CORRECTED v3 per Codex"
    round-N (LOW|MED|HIGH|MEDIUM)     e.g. "round-1 MED"
    R\\d+ <verdict>                    e.g. "R2 HIGH"
    iter-N findings                   e.g. "iter-12 finding"
    v\\d+ closes round-N <verdict>     e.g. "v3 closes round-2 LOW"

Lines whose entire content (after comment markers) matches the
pattern are dropped. Inline embeddings have just the marker
substring stripped, leaving the rest of the line intact.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Order matters — most specific first.
_MARKER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\bv\d+\s+(?:closes|close|closing)\s+round-?\d+\s+"
        r"(?:LOW|MED|MEDIUM|HIGH|BLOCKED)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bCodex\s+round-?\d+\s+(?:LOW|MED|MEDIUM|HIGH|BLOCKED|fix)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bCORRECTED\s+v\d+(?:\s+per\s+Codex)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:R|round-?)\d+\s+(?:LOW|MED|MEDIUM|HIGH|BLOCKED)\s+(?:fix|finding)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"\biter-?\d+\s+(?:finding|findings|fix|fixes)",
        re.IGNORECASE,
    ),
]

_COMMENT_LINE = re.compile(
    r"^(\s*(?:#|//|--|/\*|\*)\s*)(.*?)(\s*\*/?\s*)?$"
)


def _strip_line(line: str) -> str | None:
    """Returns:
      - None if the entire line should be dropped (comment-only +
        full content matches a marker)
      - the cleaned line otherwise (with any embedded markers
        stripped)
    """
    m = _COMMENT_LINE.match(line)
    if m:
        prefix, body, suffix = m.group(1), m.group(2), m.group(3) or ""
        cleaned_body = body
        for pat in _MARKER_PATTERNS:
            cleaned_body = pat.sub("", cleaned_body)
        cleaned_body = re.sub(r"\s{2,}", " ", cleaned_body).strip()
        if not cleaned_body:
            return None
        return f"{prefix}{cleaned_body}{suffix}\n"

    cleaned = line
    for pat in _MARKER_PATTERNS:
        cleaned = pat.sub("", cleaned)
    cleaned = re.sub(r"  +", " ", cleaned)
    return cleaned


def strip_text(text: str) -> str:
    out_lines: list[str] = []
    for raw in text.splitlines(keepends=True):
        cleaned = _strip_line(raw)
        if cleaned is not None:
            out_lines.append(cleaned)
    return "".join(out_lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "path",
        help="File path or '-' for stdin",
    )
    args = ap.parse_args()

    if args.path == "-":
        text = sys.stdin.read()
    else:
        text = Path(args.path).read_text(encoding="utf-8")

    sys.stdout.write(strip_text(text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
