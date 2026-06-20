#!/usr/bin/env python3
"""Pack a POLARIS run's report.md into the official DeepResearch-Bench-II submission
layout (report/<model>/idx-<task>.md) so the official scorer (third_party/
DeepResearch-Bench-II/run_evaluation.py, Gemini rubric judge) can score it.

The DRB-II scorer reads the markdown and truncates at MAX_PAPER_CHARS (=150000 per the
official .env_example); the run-#7 masthead-swallow (TI-22: a source masthead promoted to
a `# ` H1 + a ~95k-char swallowed line) silently consumed ~74% of the budget. This packer
removes ONLY provably-non-answer junk and FAILS LOUD on silent content loss:

  - strips foreign source-masthead `# ` H1s (the report's own structure is `##`/`###`),
  - strips oversized swallowed lines (> PACK_DRB2_MAX_LINE_CHARS),
  - strips base64 / data-URI image payloads,
  - omits gap-stub META-TEXT (placeholder prose for already-dropped claims — not answer
    content; DeepTRACE/DRB-II would score it as on-topic-but-non-substantive),
  - FAILS LOUD (SystemExit) if the ANSWER BODY (everything before `## Bibliography` /
    `## Evidence-support disclosure`) still exceeds the scorer's truncation budget — so a
    silently-truncated answer is caught, never shipped as a complete-looking report,
  - asserts idx <-> task-id alignment (scoring report-X against task-Y's rubrics is the
    §-1.4 silently-wrong-number class).

EVAL TOOLING ONLY. It never edits the scored claims or their citations — it removes only
provably-non-answer junk. Faithfulness is untouched. LAW VI: all caps are env-overridable.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

MAX_PAPER_CHARS = int(os.getenv("PACK_DRB2_MAX_PAPER_CHARS", "150000"))
MAX_LINE_CHARS = int(os.getenv("PACK_DRB2_MAX_LINE_CHARS", "5000"))

# A single-`#` H1 (`^#\s` — `## `/`### ` never match) is treated as a FOREIGN source
# masthead ONLY when it appears AFTER report body sections (`## `) have begun. POLARIS's own
# document title `# Research report` (which appears BEFORE any `## `) is KEPT (Codex over-strip
# catch: do not strip the report's own title).
_H1_RE = re.compile(r"^#\s+\S")
_BASE64_IMG_RE = re.compile(r"data:image/[^;]+;base64,", re.IGNORECASE)
# Gap-stub META-TEXT = a pipeline-internal disclosure about a slot/claim that did not verify.
# Keyed on PIPELINE-INTERNAL markers that never appear in legitimate answer prose (so a real
# sentence containing "was redacted"/"insufficient evidence" is NEVER stripped — Codex
# over-strip catch). Covers both observed stub templates: the "previously stated here"
# placeholder and the "did not survive {strict,4-role} verification ... curator-actionable gap
# ... this slot is a ..." contract-coverage disclosure.
_GAP_STUB_RE = re.compile(
    r"(?i)a claim previously stated here|"
    r"did not survive (strict|4-role|four-role|d8|provenance)[- ]?verification|"
    r"did not survive (strict|4-role|four-role) verification|"
    r"curator-actionable gap|human_gap_tasks|frame_coverage_report|"
    r"placeholder for (a|the) (claim|finding|sentence)|"
    r"this slot is a [a-z-]*\s*gap"
)
# The answer-body boundary: the appendix sections that are NOT rubric-scored answer content.
_APPENDIX_BOUNDARY_RE = re.compile(
    r"^##\s+(Bibliography|Evidence-support disclosure|References)\s*$", re.IGNORECASE
)


def strip_junk(report_md: str) -> tuple[str, dict]:
    """Return (cleaned_markdown, stats). Removes ONLY provably-non-answer junk: foreign
    source-masthead H1s (a `# ` heading appearing AFTER `## ` body sections — the report's own
    `# ` title is kept), oversized swallowed lines that are NOT markdown table rows, base64
    image payloads, and the specific gap-stub placeholder template. Deterministic; no LLM."""
    out_lines: list[str] = []
    stats = {"masthead_h1": 0, "oversized_lines": 0, "base64_lines": 0, "gap_stub_lines": 0}
    seen_h2 = False
    for line in report_md.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("## "):
            seen_h2 = True
        # foreign masthead H1 — only AFTER body sections began (keep the report's own title).
        if _H1_RE.match(line) and seen_h2:
            stats["masthead_h1"] += 1
            continue
        # oversized swallowed line — but PRESERVE wide markdown table rows (`|`-led).
        if len(line) > MAX_LINE_CHARS and not stripped.startswith("|"):
            stats["oversized_lines"] += 1
            continue
        if _BASE64_IMG_RE.search(line):
            stats["base64_lines"] += 1
            continue
        if _GAP_STUB_RE.search(line):
            stats["gap_stub_lines"] += 1
            continue
        out_lines.append(line)
    return "\n".join(out_lines).strip() + "\n", stats


def answer_body(cleaned_md: str) -> str:
    """The rubric-scored answer = everything BEFORE the first appendix boundary
    (## Bibliography / ## Evidence-support disclosure). The scorer truncates the tail, so
    the answer must fit the budget for a fair, non-truncated score."""
    lines = cleaned_md.splitlines()
    for i, line in enumerate(lines):
        if _APPENDIX_BOUNDARY_RE.match(line):
            return "\n".join(lines[:i]).strip() + "\n"
    return cleaned_md


def pack_one(
    report_md_path: Path,
    idx: int,
    *,
    task_id: object | None = None,
    out_dir: Path,
    model: str = "polaris",
    strict_truncation: bool = True,
) -> Path:
    """Pack ONE report.md into out_dir/<model>/idx-<idx>.md. Returns the written path.

    `task_id` (the DRB-II tasks_and_rubrics.jsonl idx) must equal `idx` — a mismatch means
    we would score this report against the WRONG task's rubrics (FAIL LOUD)."""
    if task_id is not None and int(task_id) != int(idx):
        raise SystemExit(
            f"[pack_drb2] FAIL-LOUD idx<->task mismatch: idx={idx} but task_id={task_id}. "
            f"Scoring against the wrong rubrics is forbidden (§-1.4 silently-wrong-number)."
        )
    report_md = report_md_path.read_text(encoding="utf-8", errors="replace")
    cleaned, stats = strip_junk(report_md)
    body = answer_body(cleaned)
    if strict_truncation and len(body) > MAX_PAPER_CHARS:
        raise SystemExit(
            f"[pack_drb2] FAIL-LOUD: answer body {len(body)} chars > scorer budget "
            f"{MAX_PAPER_CHARS} even after junk-strip {stats} — the scorer would silently "
            f"truncate scored content (the run-#7 bug). Fix the generator/render (shorten "
            f"the answer or move appendices) before submitting; set strict_truncation=False "
            f"only to MEASURE the truncation, never to hide it."
        )
    out = out_dir / model / f"idx-{idx}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(cleaned, encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Pack a POLARIS report.md for DeepResearch-Bench-II.")
    ap.add_argument("--report", required=True, help="path to POLARIS report.md")
    ap.add_argument("--idx", required=True, type=int, help="DRB-II task idx")
    ap.add_argument("--task-id", type=int, default=None, help="tasks_and_rubrics.jsonl idx (asserted == --idx)")
    ap.add_argument("--out-dir", default="report", help="output root (report/<model>/idx-N.md)")
    ap.add_argument("--model", default="polaris")
    ap.add_argument("--allow-truncation", action="store_true", help="measure-only: do NOT fail on over-budget body")
    args = ap.parse_args()
    out = pack_one(
        Path(args.report), args.idx, task_id=args.task_id,
        out_dir=Path(args.out_dir), model=args.model,
        strict_truncation=not args.allow_truncation,
    )
    print(f"[pack_drb2] wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
