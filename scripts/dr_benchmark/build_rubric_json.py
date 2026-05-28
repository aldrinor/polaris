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
from pathlib import Path

# Codex PR-3 diff P2 #4: hard-coded EXPECTED rubric shape (FROZEN gold_rubrics_pathB.md v3).
# The parser FAILS CLOSED if the markdown drifts from this — drift is a freeze violation,
# not a "should silently update" case. Update these together with a new freeze_pin.txt SHA.
_EXPECTED_QUESTIONS = ("Q75", "Q76", "Q78", "Q72", "Q90")
_EXPECTED_ELEMENT_COUNTS = {"Q75": 7, "Q76": 8, "Q78": 8, "Q72": 8, "Q90": 8}

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

    # Codex PR-3 diff P2 #4: fail closed if the parsed shape doesn't match the FROZEN
    # rubric (different question set, missing question, or wrong element count).
    parsed_qids = tuple(q["question_id"] for q in questions)
    if parsed_qids != _EXPECTED_QUESTIONS:
        raise ValueError(
            f"parsed question set {parsed_qids} != expected {_EXPECTED_QUESTIONS}; "
            "the FROZEN rubric markdown drifted — fix the source or update the expected set "
            "(and re-pin freeze_pin.txt)"
        )
    for q in questions:
        expected = _EXPECTED_ELEMENT_COUNTS[q["question_id"]]
        if len(q["elements"]) != expected:
            raise ValueError(
                f"{q['question_id']}: parsed {len(q['elements'])} elements != "
                f"expected {expected}; parser dropped an element OR rubric drifted"
            )
    # Codex PR-3 diff P2 #3: omit build_timestamp_utc from the snapshot so the JSON is
    # deterministic (same markdown -> same SHA). Audit trail is the pinned rubric_sha256.
    return {
        "rubric_sha256": rubric_sha,
        "rubric_path": str(rubric_md).replace("\\", "/"),
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
    md_pinned = _read_pinned_sha(args.freeze_pin, "gold_rubrics_pathB.md")
    # Codex PR-3 diff P2 #3: require the markdown SHA to be pinned (unless explicit
    # --allow-unpinned for initial build). Missing pin = pre-registration unanchored.
    if md_pinned is None and not args.allow_unpinned:
        print(
            f"[build_rubric_json] freeze_pin.txt has NO pin for gold_rubrics_pathB.md "
            f"-- pre-registration unanchored. Use --allow-unpinned ONLY for the initial build.",
            file=sys.stderr,
        )
        return 2
    if md_pinned is not None and md_pinned != rubric_sha and not args.allow_unpinned:
        print(
            f"[build_rubric_json] rubric SHA {rubric_sha} != pinned {md_pinned}; "
            f"freeze_pin.txt out of sync — refusing to overwrite the JSON.",
            file=sys.stderr,
        )
        return 2

    doc = build_rubric_json(args.rubric)
    payload = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    out_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    # Codex PR-3 diff P2 #3: check the existing JSON pin (if any) matches the just-built SHA.
    json_pinned = _read_pinned_sha(args.freeze_pin, "rubric_v3_frozen.json")
    if json_pinned is not None and json_pinned != out_sha and not args.allow_unpinned:
        print(
            f"[build_rubric_json] rebuilt JSON SHA {out_sha} != pinned {json_pinned}; "
            f"freeze_pin.txt out of sync OR build is no longer deterministic.",
            file=sys.stderr,
        )
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Write bytes (not write_text) so Windows doesn't translate LF→CRLF and break the
    # deterministic SHA. The on-disk SHA must equal the in-memory payload SHA byte-for-byte.
    args.out.write_bytes(payload.encode("utf-8"))
    print(f"[build_rubric_json] wrote {args.out} (rubric_sha256={rubric_sha[:16]}…, "
          f"json_sha256={out_sha[:16]}…, "
          f"{len(doc['questions'])} questions, "
          f"{sum(len(q['elements']) for q in doc['questions'])} elements)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
