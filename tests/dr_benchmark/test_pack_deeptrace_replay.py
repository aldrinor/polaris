"""Fail-loud REPLAY harness for scripts/dr_benchmark/pack_deeptrace.py (beat-both #1273).

Replays against the real run7 report + a synthetic >10-source fixture, asserting the
DeepTRACE pack obeys the official schema + the 10-source cap + the eval-integrity invariants
(no self-serving S{i}_content, no provenance-token leakage, citations renumbered to <=10,
dropped-source citations removed not invented). SKIPs if the banked report is absent."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "scripts" / "dr_benchmark"))
import pack_deeptrace as pd  # noqa: E402

_RUN7 = _REPO / "state" / "canary_forensic" / "run7" / "report.md"
_BIB = _REPO / "state" / "canary_forensic" / "run7" / "bibliography.json"


def _max_cite(output: str) -> int:
    return max(
        [int(t.strip()) for g in pd._CITE_RE.findall(output) for t in g.split(",") if t.strip().isdigit()] or [0]
    )


def test_real_run7_packs_to_valid_deeptrace_schema():
    if not (_RUN7.is_file() and _BIB.is_file()):
        pytest.skip("banked run7 report/bibliography absent")
    import json
    md = _RUN7.read_text(encoding="utf-8", errors="replace")
    bib = json.loads(_BIB.read_text(encoding="utf-8"))
    rec = pd.pack_report_for_deeptrace(md, bib, task_id=78, question="Q78")
    # schema: id, Question, Output, S1..S10.
    assert set(rec) == {"id", "Question", "Output"} | {f"S{i}" for i in range(1, 11)}
    # 10-source cap: at most 10 listed sources.
    assert sum(1 for i in range(1, 11) if rec[f"S{i}"]) <= 10
    # eval integrity: S{i}_content must NOT be pre-filled (the official scorer scrapes it;
    # pre-filling POLARIS's own spans is the §-1.1 self-serving-eval shortcut).
    assert not any(f"S{i}_content" in rec for i in range(1, 11))
    # no POLARIS-internal provenance tokens leak into the scored Output.
    assert "[#ev:" not in rec["Output"]
    # citations are renumbered into the 1..10 index range the scorer parses.
    assert _max_cite(rec["Output"]) <= 10
    assert len(rec["Output"]) > 0


def test_over_ten_sources_reduce_and_renumber():
    # 12 sources, each cited by a distinct sentence -> greedy cover needs all 12 but caps at 10;
    # the body must renumber to <=10 and DROP citations to the 2 non-selected sources.
    bib = [{"num": n, "url": f"https://example.com/s{n}"} for n in range(1, 13)]
    sentences = [f"## Findings"] + [f"Claim number {n} is supported [{n}]." for n in range(1, 13)]
    md = "\n".join(sentences) + "\n"
    rec = pd.pack_report_for_deeptrace(md, bib, task_id=1, question="q")
    listed = [i for i in range(1, 11) if rec[f"S{i}"]]
    assert len(listed) == 10, "must cap at exactly 10 listed sources"
    assert _max_cite(rec["Output"]) <= 10, "body citations must renumber into 1..10"
    # the 2 dropped sources' sentences are now uncited (their [N] removed), never renumbered to a bogus index.
    assert rec["Output"].count("[") <= 10


def test_trailing_citation_style_splits_into_distinct_statements():
    """POLARIS's real `text.[1] text.[2]` style must split into TWO statements so each cited
    source maps to its own statement (Codex P1 — else greedy cover drops a real statement's
    only source). Two sources cited by two distinct sentences => greedy cover keeps BOTH."""
    bib = [{"num": 1, "url": "https://example.com/a"}, {"num": 2, "url": "https://example.com/b"}]
    md = "## Findings\nClaim A is well supported.[1] Claim B is contested.[2]\n"
    rec = pd.pack_report_for_deeptrace(md, bib, task_id=1, question="q")
    # both sources are load-bearing (each covers a distinct statement) -> both listed.
    assert rec["S1"] and rec["S2"], "both sources should be kept (distinct statements)"
    # the body retains both renumbered citations.
    assert "[1]" in rec["Output"] and "[2]" in rec["Output"]


def test_markdown_list_items_split_into_distinct_statements():
    """POLARIS answers use Markdown list blocks. Two distinctly-cited bullets `A.[1]\\n- B.[2]`
    (and an intro line with no terminal punctuation followed by cited bullets) must split into
    SEPARATE statements so each cited source maps to its own statement (Codex iter2 P1 — else
    greedy set-cover collapses the bullets into one unit and drops a load-bearing source)."""
    bib = [{"num": n, "url": f"https://example.com/s{n}"} for n in (1, 2, 3)]
    # an intro with no terminal punctuation, then three cited bullets across newlines.
    md = "## Findings\nKey results follow\n- Alpha holds.[1]\n- Beta is contested.[2]\n- Gamma is novel.[3]\n"
    rec = pd.pack_report_for_deeptrace(md, bib, task_id=1, question="q")
    # each bullet is a distinct statement covered only by its own source -> greedy cover keeps all three.
    assert rec["S1"] and rec["S2"] and rec["S3"], "all three distinctly-cited bullets must be kept"
    assert "[1]" in rec["Output"] and "[2]" in rec["Output"] and "[3]" in rec["Output"]


def test_markdown_table_rows_split_into_distinct_statements():
    """POLARIS reports contain cited Markdown TABLE rows. Distinct rows (and distinct cited cells
    within a row) must split into separate statements so each row's citation stays load-bearing
    (Codex iter3 P1 — else _citation_matrix maps refs [1]-[4] to one statement and greedy cover
    keeps only one, dropping the other rows' sources)."""
    bib = [{"num": n, "url": f"https://example.com/t{n}"} for n in (1, 2, 3, 4)]
    md = (
        "## Comparison\n"
        "| Intervention | Effect | Source |\n"
        "|---|---|---|\n"
        "| Alpha | reduces risk [1] | trial A |\n"
        "| Beta | no effect [2] | trial B |\n"
        "| Gamma | increases risk [3] | trial C [4] |\n"
    )
    rec = pd.pack_report_for_deeptrace(md, bib, task_id=1, question="q")
    # every row's source is load-bearing (each covers a distinct row-statement) -> all four kept.
    assert rec["S1"] and rec["S2"] and rec["S3"] and rec["S4"], "all four table-row sources must be kept"
    for n in (1, 2, 3, 4):
        assert f"[{n}]" in rec["Output"]


def test_env_cap_over_ten_does_not_keyerror_in_main(tmp_path, monkeypatch):
    """main()'s listed-source count must iterate the real S1..S10 schema, not the raw env cap —
    PACK_DEEPTRACE_MAX_SOURCES=99 previously KeyError'd on rec['S11'] (Codex iter2 P1)."""
    import json
    monkeypatch.setenv("PACK_DEEPTRACE_MAX_SOURCES", "99")
    report = tmp_path / "r.md"
    report.write_text("## S\nClaim one [1]. Claim two [2].\n", encoding="utf-8")
    bibp = tmp_path / "b.json"
    bibp.write_text(json.dumps([{"num": 1, "url": "https://e.com/a"}, {"num": 2, "url": "https://e.com/b"}]), encoding="utf-8")
    out = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", [
        "pack_deeptrace.py", "--report", str(report), "--bibliography", str(bibp),
        "--task-id", "1", "--question", "q", "--out", str(out),
    ])
    pd.main()  # must NOT raise KeyError on S11
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data) == 1 and set(data[0]) == {"id", "Question", "Output"} | {f"S{i}" for i in range(1, 11)}


def test_always_emits_exactly_s1_through_s10():
    bib = [{"num": 1, "url": "https://example.com/a"}]
    rec = pd.pack_report_for_deeptrace("## S\nA [1].\n", bib, task_id=1, question="q")
    assert all(f"S{i}" in rec for i in range(1, 11)), "schema must always have S1..S10"
    assert rec["S1"] and all(rec[f"S{i}"] == "" for i in range(2, 11))
    # a misconfigured cap is clamped to 1..10 (no KeyError / out-of-range).
    rec2 = pd.pack_report_for_deeptrace("## S\nA [1].\n", bib, task_id=1, question="q", max_sources=99)
    assert all(f"S{i}" in rec2 for i in range(1, 11))


def test_dropped_source_citation_is_removed_not_invented():
    bib = [{"num": 1, "url": "https://example.com/a"}]  # only source 1 exists in the bib
    md = "## S\nA cites one [1] and also a non-bib source [99].\n"
    rec = pd.pack_report_for_deeptrace(md, bib, task_id=1, question="q")
    # [1] is kept+renumbered to [1]; [99] (not in bib / not covered) is dropped, never invented.
    assert "[99]" not in rec["Output"]
    assert _max_cite(rec["Output"]) <= 1
