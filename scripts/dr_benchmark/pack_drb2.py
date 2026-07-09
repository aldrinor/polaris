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
import json
import os
import re
import sys
from pathlib import Path

MAX_PAPER_CHARS = int(os.getenv("PACK_DRB2_MAX_PAPER_CHARS", "150000"))
MAX_LINE_CHARS = int(os.getenv("PACK_DRB2_MAX_LINE_CHARS", "5000"))

# I-beatboth-011 idx 15 (#1289): the DRB-II task catalog. A run's internal id (e.g. "task72") does
# NOT equal its DRB-II `idx` field (task72 -> idx 56), so packing AI-labor prose with the wrong
# `--idx 72` would score it against idx-72's task (Parkinson's) — a silent near-zero (§-1.4
# silently-wrong-number). The topic-overlap guard below resolves the task at `--idx` and refuses a
# report whose H1/opening shares ZERO content words with that task's (English) description.
_DEFAULT_TASKS_JSONL = (
    Path(__file__).resolve().parents[2] / "third_party" / "DeepResearch-Bench-II" / "tasks_and_rubrics.jsonl"
)
# Content word for topic-overlap: a >=3-char alpha token (drops the structural stopwords). Lowercased.
_TOPIC_WORD_RE = re.compile(r"[a-z][a-z'-]{2,}")
_TOPIC_STOPWORDS = frozenset({
    "the", "and", "for", "with", "this", "that", "from", "into", "over", "under", "about", "review",
    "report", "research", "study", "analysis", "impact", "role", "case", "based", "using", "between",
    "their", "these", "those", "which", "while", "have", "has", "are", "was", "were", "its", "via",
})

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
    r"this slot is a [a-z-]*\s*gap|"
    # N4 (I-deepfix-001 wave-2): plain-English gap disclosure (carries [N]).
    r"insufficient verified evidence"
)
# The answer-body boundary: the appendix sections that are NOT rubric-scored answer content.
# I-deepfix-001 (#1344): ALSO match the T5 audit-machinery appendix header the render emits
# (run_honest_sweep_r3._AUDIT_MACHINERY_APPENDIX_BOUNDARY: "## Appendix: audit, disclosure, and
# weighting (not scored as report claims)"). It carries a trailing parenthetical, so its branch
# allows any trailing content after "weighting" (the anchored `\s*$` on the other three stays).
# Without this branch the reliability/audit-counts block (moved to a TYPED trailing appendix so the
# scored body opens on a real claim) would fall INSIDE the scored answer, diluting recall / risking
# scorer truncation of real body content. Boundary/segmentation only — never drops any report bytes.
_APPENDIX_BOUNDARY_RE = re.compile(
    r"^##\s+(?:Bibliography|Evidence-support disclosure|References)\s*$"
    r"|^##\s+Appendix:\s*audit,\s*disclosure,\s*and\s*weighting\b.*$",
    re.IGNORECASE,
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


def _topic_words(text: str) -> set[str]:
    """Lowercased content-word set for topic-overlap (drops structural stopwords)."""
    return {w for w in _TOPIC_WORD_RE.findall((text or "").lower()) if w not in _TOPIC_STOPWORDS}


def _load_drb2_tasks(tasks_jsonl: Path | None) -> list[dict]:
    """Load the DRB-II task catalog (or [] when the file is absent/unreadable — the topic guard then
    no-ops with a warning rather than blocking a legitimate run whose data file is not present)."""
    if not tasks_jsonl or not Path(tasks_jsonl).exists():
        return []
    out: list[dict] = []
    for line in Path(tasks_jsonl).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue
    return out


def _resolve_idx_for_task_name(task_name: str, records: list[dict]) -> str | None:
    """The DRB-II `idx` field of the record whose `id` == task_name (e.g. "task72" -> "56")."""
    for r in records:
        if str(r.get("id")) == str(task_name):
            return str(r.get("idx"))
    return None


def _report_topic_text(report_md: str) -> str:
    """The report's TOPIC surface: its first `# ` H1 plus the opening ~2000 chars of prose. Robust
    against a generic H1 — a correctly-paired report's opening always names its own subject."""
    h1 = ""
    for line in (report_md or "").splitlines():
        if _H1_RE.match(line):
            h1 = line.lstrip("#").strip()
            break
    return f"{h1}\n{(report_md or '')[:2000]}"


def _assert_drb2_topic_match(idx: int, report_md: str, records: list[dict]) -> None:
    """FAIL LOUD (SystemExit) if the report's topic shares ZERO content words with the DRB-II task at
    `idx` (resolved by the record's `idx` FIELD, the id<->idx offset). Uses the task's English
    `description` (robust to zh prompts). No-ops when the catalog is unavailable or either side yields
    no extractable topic words (never a false positive). Fires exactly on a wrong-idx mispairing
    (AI-labor report vs idx-72 Parkinson's = zero shared words); never on a correct run."""
    if not records:
        print("[pack_drb2] WARN: DRB-II task catalog unavailable; idx<->topic guard skipped.")
        return
    rec = next((r for r in records if str(r.get("idx")) == str(idx)), None)
    if rec is None:
        print(f"[pack_drb2] WARN: no DRB-II task with idx={idx} in the catalog; topic guard skipped.")
        return
    desc_words = _topic_words(str(rec.get("description") or ""))
    report_words = _topic_words(_report_topic_text(report_md))
    if not desc_words or not report_words:
        return  # cannot judge — do not false-positive
    if not (desc_words & report_words):
        raise SystemExit(
            f"[pack_drb2] FAIL-LOUD topic mismatch at --idx {idx}: the report shares ZERO content "
            f"words with DRB-II idx {idx} (id={rec.get('id')!r}, {str(rec.get('description'))[:90]!r}). "
            f"You are almost certainly packing against the WRONG idx — the id<->idx offset is real "
            f"(id 'task72' is idx 56, NOT 72). Pass the correct --idx (or --task-name). "
            f"(§-1.4 silently-wrong-number)"
        )


def pack_one(
    report_md_path: Path,
    idx: int,
    *,
    task_id: object | None = None,
    task_name: str | None = None,
    tasks_jsonl: Path | None = None,
    out_dir: Path,
    model: str = "polaris",
    strict_truncation: bool = True,
) -> Path:
    """Pack ONE report.md into out_dir/<model>/idx-<idx>.md. Returns the written path.

    `task_id` (the DRB-II tasks_and_rubrics.jsonl idx) must equal `idx` — a mismatch means
    we would score this report against the WRONG task's rubrics (FAIL LOUD).

    I-beatboth-011 idx 15 (#1289): two stronger guards close the silently-wrong-idx landmine the
    `task_id == idx` check misses (it passes when BOTH are wrong-but-equal):
      (A) `task_name` (e.g. "task72") is resolved to its DRB-II `idx` field via the catalog and
          asserted == `idx`, so the real id<->idx offset (task72 -> idx 56) is enforced in code.
      (B) a topic-overlap guard refuses a report whose opening shares zero content words with the
          task at `idx` (the AI-labor-vs-Parkinson's mispairing)."""
    if task_id is not None and int(task_id) != int(idx):
        raise SystemExit(
            f"[pack_drb2] FAIL-LOUD idx<->task mismatch: idx={idx} but task_id={task_id}. "
            f"Scoring against the wrong rubrics is forbidden (§-1.4 silently-wrong-number)."
        )
    records = _load_drb2_tasks(tasks_jsonl)
    # (A) id<->idx resolution: a `--task-name` must map (by the catalog's `idx` field) to `--idx`.
    if task_name is not None:
        resolved = _resolve_idx_for_task_name(task_name, records)
        if resolved is None and records:
            raise SystemExit(
                f"[pack_drb2] FAIL-LOUD: --task-name {task_name!r} not found in the DRB-II catalog."
            )
        if resolved is not None and str(resolved) != str(idx):
            raise SystemExit(
                f"[pack_drb2] FAIL-LOUD id<->idx offset: --task-name {task_name!r} resolves to DRB-II "
                f"idx {resolved}, but --idx {idx} was given. The run id ('task72') is NOT the idx "
                f"(56) — pass --idx {resolved}. (§-1.4 silently-wrong-number)"
            )
    report_md = report_md_path.read_text(encoding="utf-8", errors="replace")
    # (B) topic-overlap belt-and-suspenders (fires on a wrong-idx mispairing, never on a correct run).
    _assert_drb2_topic_match(idx, report_md, records)
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
    ap.add_argument("--idx", required=True, type=int, help="DRB-II task idx (the catalog `idx` field, NOT the run id number)")
    ap.add_argument("--task-id", type=int, default=None, help="tasks_and_rubrics.jsonl idx (asserted == --idx)")
    ap.add_argument("--task-name", default=None, help="DRB-II task id e.g. 'task72' (resolved to its idx via the catalog and asserted == --idx)")
    ap.add_argument("--tasks-jsonl", default=str(_DEFAULT_TASKS_JSONL), help="DRB-II tasks_and_rubrics.jsonl (for the id<->idx + topic-overlap guards)")
    ap.add_argument("--out-dir", default="report", help="output root (report/<model>/idx-N.md)")
    ap.add_argument("--model", default="polaris")
    ap.add_argument("--allow-truncation", action="store_true", help="measure-only: do NOT fail on over-budget body")
    args = ap.parse_args()
    out = pack_one(
        Path(args.report), args.idx, task_id=args.task_id,
        task_name=args.task_name, tasks_jsonl=Path(args.tasks_jsonl) if args.tasks_jsonl else None,
        out_dir=Path(args.out_dir), model=args.model,
        strict_truncation=not args.allow_truncation,
    )
    print(f"[pack_drb2] wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
