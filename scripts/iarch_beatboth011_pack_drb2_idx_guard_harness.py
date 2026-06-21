#!/usr/bin/env python3
"""I-beatboth-011 idx 15 (#1289) — fail-loud harness for the pack_drb2 id<->idx + topic-overlap guards.

§-1.4 behavioral acceptance (non-zero exit on regression). The defect: a DRB-II run's internal id
("task72") does NOT equal its catalog `idx` field (task72 -> idx 56), and the old `task_id == idx`
guard PASSES when both are wrong-but-equal — so packing AI-labor prose with `--idx 72` silently
scored it against idx-72's task (Parkinson's), a near-zero (§-1.4 silently-wrong-number).

Asserts (against the REAL third_party/DeepResearch-Bench-II/tasks_and_rubrics.jsonl):
  (1) CORRECT idx (56, the AI-labor task) packs cleanly — no SystemExit.
  (2) WRONG idx (72, Parkinson's) raises SystemExit (the topic-overlap guard fires on zero overlap).
  (3) id<->idx offset: --task-name "task72" with --idx 72 raises SystemExit (task72 resolves to idx 56).
  (4) id<->idx offset: --task-name "task72" with --idx 56 packs cleanly (correct pairing).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from scripts.dr_benchmark import pack_drb2  # noqa: E402

_TASKS = pack_drb2._DEFAULT_TASKS_JSONL

# A realistic AI-labor report (matches DRB-II idx 56 "Impact of Generative AI on the Labor Market").
_AI_LABOR_REPORT = """# Generative AI and the Labor Market: Displacement, Wages, and Reinstatement

## Executive Summary
Generative artificial intelligence has measurably affected employment, wages, and occupational
exposure across the labor market. Field experiments show customer-support productivity gains, while
the task framework predicts both displacement and reinstatement effects on workers.

## Bibliography
[1] Example.
"""


def _fail(msg: str) -> None:
    print(f"FAIL I-beatboth-011 idx15 pack_drb2 guard: {msg}")
    sys.exit(1)


def _pack(idx: int, *, task_name: str | None, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "report.md"
    report.write_text(_AI_LABOR_REPORT, encoding="utf-8")
    return pack_drb2.pack_one(
        report, idx, task_name=task_name, tasks_jsonl=_TASKS,
        out_dir=out_dir / "out", model="polaris", strict_truncation=True,
    )


def main() -> None:
    if not _TASKS.exists():
        _fail(f"DRB-II catalog not found at {_TASKS} — cannot exercise the guard (needed for this harness)")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        # (1) correct idx 56 (AI-labor) -> clean pack.
        try:
            out = _pack(56, task_name=None, out_dir=td / "c1")
        except SystemExit as e:
            _fail(f"(1) correct --idx 56 wrongly raised SystemExit: {e}")
        if not out.exists():
            _fail("(1) correct --idx 56 did not write the packed file")
        print("(1) ok: correct idx 56 (AI-labor) packs cleanly.")

        # (2) wrong idx 72 (Parkinson's) -> topic-overlap guard fires.
        raised = False
        try:
            _pack(72, task_name=None, out_dir=td / "c2")
        except SystemExit as e:
            raised = "topic mismatch" in str(e).lower() or "zero content" in str(e).lower()
        if not raised:
            _fail("(2) wrong --idx 72 (Parkinson's) did NOT raise the topic-mismatch SystemExit")
        print("(2) ok: wrong idx 72 (Parkinson's) -> topic-overlap guard fired.")

        # (3) id<->idx offset: --task-name task72 with --idx 72 -> SystemExit (task72 is idx 56).
        raised = False
        try:
            _pack(72, task_name="task72", out_dir=td / "c3")
        except SystemExit as e:
            raised = "offset" in str(e).lower() or "resolves to" in str(e).lower() or "topic mismatch" in str(e).lower()
        if not raised:
            _fail("(3) --task-name task72 + --idx 72 did NOT raise the id<->idx offset SystemExit")
        print("(3) ok: --task-name task72 + --idx 72 -> id<->idx offset guard fired.")

        # (4) correct pairing: --task-name task72 with --idx 56 -> clean pack.
        try:
            out = _pack(56, task_name="task72", out_dir=td / "c4")
        except SystemExit as e:
            _fail(f"(4) correct --task-name task72 + --idx 56 wrongly raised SystemExit: {e}")
        if not out.exists():
            _fail("(4) correct task-name+idx pairing did not write the packed file")
        print("(4) ok: --task-name task72 + --idx 56 packs cleanly.")

    print(
        "PASS I-beatboth-011 idx15: the pack_drb2 topic-overlap guard fires on a wrong-idx mispairing "
        "(AI-labor report vs idx-72 Parkinson's) and the id<->idx offset guard catches --task-name "
        "task72 + --idx 72 (task72 is idx 56), while both correct pairings pack cleanly. "
        "§-1.4 silently-wrong-number closed."
    )


if __name__ == "__main__":
    main()
