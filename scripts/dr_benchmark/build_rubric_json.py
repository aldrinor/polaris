"""Build the companion JSON snapshot of the frozen gold rubric (I-safety-002b #925 PR-3).

Per Codex PR-3 design answer A (companion-json + dual SHA-pin): the canonical rubric is the
human-readable `.codex/I-safety-002b/gold_rubrics_pathB.md`. This tool parses it ONCE into
`outputs/dr_benchmark/rubric_v3_frozen.json` (machine-readable), then BOTH files are SHA256-
pinned in `.codex/I-safety-002b/freeze_pin.txt`. Any edit to the markdown invalidates the JSON
pin; the builder refuses to overwrite without matching the markdown's pinned sha.

Schema:
{
  "rubric_sha256": "<sha256 of the source markdown>",
  "rubric_path": ".codex/I-safety-002b/gold_rubrics_pathB.md",
  "build_timestamp_utc": "...",
  "questions": [
    {
      "question_id": "Q75" | "Q76" | "Q78" | "Q72" | "Q90",
      "domain": "Health (clinical)" | ...,
      "elements": [{"element_id": "Q75-E1", "requirement_text": "..."}, ...]
    },
    ...
  ]
}
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_QUESTION_HEADER = re.compile(
    r"^##\s+#(?P<num>\d+)\s+—\s+(?P<title>.+?)\s*$",
    re.MULTILINE,
)
_ELEMENT_LINE = re.compile(
    r"^(?P<n>\d+)\.\s+(?P<text>.+?)$",
    re.MULTILINE,
)


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _read_pinned_sha(freeze_pin_path: Path, rubric_relpath: str) -> str | None:
    if not freeze_pin_path.exists():
        return None
    for line in freeze_pin_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1].endswith(rubric_relpath):
            return parts[0]
    return None


def build_rubric_json(rubric_md: Path) -> dict:
    """Parse the frozen rubric markdown into the companion-JSON dict."""
    text = rubric_md.read_text(encoding="utf-8")
    rubric_sha = _sha256(rubric_md)
    questions: list[dict] = []

    # Slice by "## #N — Title" headers; ignore non-question headers (CHANGELOG, etc.).
    headers = list(_QUESTION_HEADER.finditer(text))
    for i, m in enumerate(headers):
        qnum = f"Q{m.group('num')}"
        title = m.group("title").strip()
        body_start = m.end()
        body_end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[body_start:body_end]
        # Extract numbered top-level elements: "1. ...", "2. ..." at start of line.
        elements: list[dict] = []
        for em in _ELEMENT_LINE.finditer(body):
            n = int(em.group("n"))
            elem_text = em.group("text").strip()
            # Stop if the numbering resets / we leave the element list.
            if n != len(elements) + 1:
                break
            elements.append({
                "element_id": f"{qnum}-E{n}",
                "requirement_text": elem_text,
            })
        questions.append({
            "question_id": qnum,
            "title": title,
            "elements": elements,
        })

    return {
        "rubric_sha256": rubric_sha,
        "rubric_path": str(rubric_md).replace("\\", "/"),
        "build_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "questions": questions,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build the frozen-rubric JSON snapshot.")
    p.add_argument("--rubric", type=Path, default=Path(".codex/I-safety-002b/gold_rubrics_pathB.md"))
    p.add_argument("--out", type=Path, default=Path("outputs/dr_benchmark/rubric_v3_frozen.json"))
    p.add_argument("--freeze-pin", type=Path, default=Path(".codex/I-safety-002b/freeze_pin.txt"))
    p.add_argument("--allow-unpinned", action="store_true",
                   help="bypass the freeze-pin check (use ONLY for initial build before pinning)")
    args = p.parse_args(argv)

    if not args.rubric.exists():
        print(f"[build_rubric_json] rubric not found: {args.rubric}", file=sys.stderr)
        return 1

    rubric_sha = _sha256(args.rubric)
    pinned = _read_pinned_sha(args.freeze_pin, "gold_rubrics_pathB.md")
    if pinned is not None and pinned != rubric_sha and not args.allow_unpinned:
        print(
            f"[build_rubric_json] rubric SHA {rubric_sha} != pinned {pinned}; "
            f"freeze_pin.txt out of sync — refusing to overwrite the JSON.",
            file=sys.stderr,
        )
        return 2

    doc = build_rubric_json(args.rubric)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(doc, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[build_rubric_json] wrote {args.out} (rubric_sha256={rubric_sha[:16]}…, "
          f"{len(doc['questions'])} questions, "
          f"{sum(len(q['elements']) for q in doc['questions'])} elements)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
