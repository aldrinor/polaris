"""Fail-loud REPLAY harness for scripts/dr_benchmark/pack_drb2.py (beat-both #1273).

Acceptance per §-1.4: the effect must appear on a REAL banked report, not a synthetic
toy. We replay against state/canary_forensic/run7/report.md (the run that exhibited the
TI-22 masthead-swallow) and assert the packer removes the junk, the answer body fits the
official scorer's truncation budget, and the alignment/truncation guards FAIL LOUD. If the
banked report is absent the test SKIPS (never silently passes)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "scripts" / "dr_benchmark"))
import pack_drb2 as p  # noqa: E402

_RUN7 = _REPO / "state" / "canary_forensic" / "run7" / "report.md"


def _run7_md() -> str:
    if not _RUN7.is_file():
        pytest.skip(f"banked run7 report absent: {_RUN7}")
    return _RUN7.read_text(encoding="utf-8", errors="replace")


def test_strip_removes_masthead_swallow_and_gapstub_on_real_run7():
    md = _run7_md()
    cleaned, stats = p.strip_junk(md)
    # TI-22: a foreign `# ` masthead H1 + oversized swallowed line(s) were present and removed.
    assert stats["masthead_h1"] >= 1, "expected the source-masthead H1 to be stripped"
    assert stats["oversized_lines"] >= 1, "expected the ~95k-char swallowed line to be stripped"
    # the strip materially shrinks the report (the masthead junk was the bulk).
    assert len(cleaned) < len(md) * 0.5, "masthead junk should be the majority of run7 bytes"
    # the masthead heading is gone (a foreign `# ` H1 after body sections began).
    assert "# The American Society for Experimental NeuroTherapeutics" not in cleaned
    # the gap-stub meta-text is gone — keyed on the pipeline marker, not the loose phrase.
    assert "curator-actionable gap" not in cleaned
    assert stats["gap_stub_lines"] >= 1, "expected run7's curator-actionable-gap stub to be stripped"
    # no surviving NON-table line exceeds the line cap.
    assert max((len(l) for l in cleaned.splitlines() if not l.lstrip().startswith("|")), default=0) <= p.MAX_LINE_CHARS


def test_does_not_over_strip_title_table_or_legit_sentences():
    """Codex over-strip catches: the report's OWN `# ` title (before any `## `), wide markdown
    table rows, and legitimate sentences merely containing 'was redacted' / 'insufficient
    evidence' must all be PRESERVED."""
    # own document title (appears before any `## `) is kept; a later foreign `# ` masthead is dropped.
    md = "# Research report\n\n## Findings\nReal content [1].\n\n# Some Journal Masthead 2020\n"
    cleaned, stats = p.strip_junk(md)
    assert "# Research report" in cleaned
    assert "# Some Journal Masthead 2020" not in cleaned
    assert stats["masthead_h1"] == 1
    # a wide markdown table row (`|`-led, > line cap) is preserved.
    wide_row = "| col1 | " + ("x" * (p.MAX_LINE_CHARS + 100)) + " |"
    assert wide_row in p.strip_junk("## T\n" + wide_row + "\n")[0]
    # a legitimate sentence containing the loose phrases is preserved.
    legit = "## S\nThe document was redacted by the agency and there was insufficient evidence for the claim [3].\n"
    assert "redacted by the agency" in p.strip_junk(legit)[0]


def test_answer_body_fits_the_scorer_budget_on_real_run7():
    cleaned, _ = p.strip_junk(_run7_md())
    body = p.answer_body(cleaned)
    # The rubric-scored answer (before ## Bibliography) must fit the scorer's truncation
    # budget so no scored content is silently truncated (the run-#7 failure mode).
    assert 0 < len(body) <= p.MAX_PAPER_CHARS
    # and the appendix really is excluded.
    assert "## Bibliography" not in body


def test_pack_one_writes_submission_layout(tmp_path):
    out = p.pack_one(_RUN7, 78, task_id=78, out_dir=tmp_path, model="polaris", strict_truncation=False)
    assert out == tmp_path / "polaris" / "idx-78.md"
    assert out.is_file() and out.stat().st_size > 0


def test_idx_task_mismatch_fails_loud(tmp_path):
    with pytest.raises(SystemExit):
        p.pack_one(_RUN7, 78, task_id=99, out_dir=tmp_path)


def test_over_budget_answer_body_fails_loud(tmp_path):
    # Synthesize an answer body that exceeds the budget -> strict pack must FAIL LOUD
    # (never silently ship a report whose scored content the scorer would truncate).
    # NOTE: must be MANY lines each under MAX_LINE_CHARS, else the oversized-line strip
    # (correctly) removes a single giant line and the body is no longer over-budget.
    big = tmp_path / "big.md"
    line = "word " * 100  # ~500 chars/line, well under MAX_LINE_CHARS
    n_lines = (p.MAX_PAPER_CHARS // len(line)) + 50  # total > MAX_PAPER_CHARS
    big.write_text("## Key Findings\n" + "\n".join([line] * n_lines) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        p.pack_one(big, 1, task_id=1, out_dir=tmp_path, strict_truncation=True)
    # measure-only mode (allow_truncation) must NOT raise — it lets us quantify the overflow.
    out = p.pack_one(big, 1, task_id=1, out_dir=tmp_path, strict_truncation=False)
    assert out.is_file()
