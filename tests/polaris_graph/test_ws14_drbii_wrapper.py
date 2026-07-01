"""I-deepfix-001 WS-14 part 2 — DRB-II submission wrapper: offline shape + argv contract.

DRB-II is the OFFICIAL harness (Gemini judge). These tests prove the thin adapter (a) builds the
right submission shape from a rendered report, (b) emits a well-formed argv to invoke the official
run_evaluation.py, and (c) never requires the harness / Gemini / network at import or test time.
No re-implementation of DRB-II scoring is asserted via the honesty fields.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from scripts.dr_benchmark.drbii_wrapper import (  # noqa: E402
    DEFAULT_EVAL_SCRIPT,
    build_drbii_submission,
    drbii_score_command,
    write_drbii_submission,
)

SAMPLE_REPORT = """# Research report: semaglutide cardiovascular outcomes

## Findings
Semaglutide 2.4 mg reduced major adverse cardiovascular events by 20% [#ev:src0:10-42].

## Bibliography
1. SELECT trial, NEJM 2023.
"""

SAMPLE_REFS = [
    {"id": "src0", "title": "SELECT trial", "url": "https://doi.org/10.1056/x", "authors": ["Lincoff", "Brown"]},
    "https://example.org/guideline",
    "A bare title reference",
]


def test_build_submission_has_drbii_keys():
    sub = build_drbii_submission(SAMPLE_REPORT, task_id=56, references=SAMPLE_REFS)
    for k in ("article", "task_id", "idx", "references", "model", "submission_filename",
              "submission_relpath", "scorer", "reimplemented"):
        assert k in sub, f"missing key {k}"
    assert sub["article"] == SAMPLE_REPORT, "article text must pass through verbatim"
    assert sub["task_id"] == 56 and sub["idx"] == 56
    assert sub["submission_filename"] == "idx-56.md", "harness keys files by idx-<N> (^idx-(\\d+))"
    assert sub["submission_relpath"] == "polaris/idx-56.md"
    assert sub["n_references"] == 3


def test_task_id_is_not_transformed():
    # The run-id<->idx offset is REAL; the wrapper must NOT auto-map. Given idx 56, it stays 56.
    sub = build_drbii_submission(SAMPLE_REPORT, task_id="56", references=None)
    assert sub["idx"] == 56, "string '56' coerces to int 56, no offset applied"


def test_references_normalized_from_dict_and_string():
    sub = build_drbii_submission(SAMPLE_REPORT, task_id=1, references=SAMPLE_REFS)
    refs = sub["references"]
    assert refs[0] == {"id": "src0", "title": "SELECT trial",
                       "url": "https://doi.org/10.1056/x", "authors": ["Lincoff", "Brown"]}
    # a bare URL string -> url slot; a bare non-URL string -> title slot
    assert refs[1]["url"] == "https://example.org/guideline" and refs[1]["title"] == ""
    assert refs[2]["title"] == "A bare title reference" and refs[2]["url"] == ""
    # auto-assigned ids for the bare strings
    assert refs[1]["id"] == "ref_2" and refs[2]["id"] == "ref_3"


def test_none_references_is_empty_list():
    sub = build_drbii_submission(SAMPLE_REPORT, task_id=0, references=None)
    assert sub["references"] == [] and sub["n_references"] == 0


def test_build_rejects_bad_task_id():
    with pytest.raises(ValueError):
        build_drbii_submission(SAMPLE_REPORT, task_id="not-an-int")
    with pytest.raises(ValueError):
        build_drbii_submission(SAMPLE_REPORT, task_id=-1)
    with pytest.raises(ValueError):
        build_drbii_submission(None, task_id=5)  # fail loud on missing article


def test_honesty_official_scorer_not_reimplemented():
    sub = build_drbii_submission(SAMPLE_REPORT, task_id=56)
    assert sub["reimplemented"] is False, "DRB-II is the official harness; we do NOT re-implement it"
    assert "run_evaluation.py" in sub["scorer"] and "official" in sub["scorer"].lower()


def test_score_command_wellformed_argv():
    argv = drbii_score_command("report", "result.jsonl")
    assert isinstance(argv, list) and all(isinstance(a, str) for a in argv)
    assert DEFAULT_EVAL_SCRIPT in argv, "default eval script (documented placeholder) present"
    assert "--pdf_dir" in argv and argv[argv.index("--pdf_dir") + 1] == "report"
    assert "--out_jsonl" in argv and argv[argv.index("--out_jsonl") + 1] == "result.jsonl"
    assert "--tasks_jsonl" in argv
    assert argv[0], "argv[0] is the python executable (non-empty)"


def test_score_command_env_overrides(monkeypatch):
    monkeypatch.setenv("PG_DRBII_EVAL_SCRIPT", "/vm/DRB-II/run_evaluation.py")
    monkeypatch.setenv("PG_DRBII_TASKS_JSONL", "/vm/DRB-II/tasks.jsonl")
    monkeypatch.setenv("PG_DRBII_PYTHON", "/usr/bin/python3")
    argv = drbii_score_command("/sub/report", "/out/result.jsonl")
    assert argv[0] == "/usr/bin/python3"
    assert argv[1] == "/vm/DRB-II/run_evaluation.py"
    assert argv[argv.index("--tasks_jsonl") + 1] == "/vm/DRB-II/tasks.jsonl"


def test_score_command_kwargs_override_env(monkeypatch):
    monkeypatch.setenv("PG_DRBII_EVAL_SCRIPT", "/env/run_evaluation.py")
    argv = drbii_score_command(
        "report", "out.jsonl",
        eval_script="/explicit/run_evaluation.py", extra_args=["--chunk_size", "50"],
    )
    assert argv[1] == "/explicit/run_evaluation.py", "explicit kwarg beats env"
    assert argv[-2:] == ["--chunk_size", "50"]


def test_score_command_offline_no_harness_required(monkeypatch, tmp_path):
    # Point at a non-existent script + non-existent pdf_dir; the command must still build (pure argv,
    # no filesystem check, no harness import) — proving it is offline-safe at build time.
    monkeypatch.delenv("PG_DRBII_EVAL_SCRIPT", raising=False)
    ghost_script = str(tmp_path / "does_not_exist" / "run_evaluation.py")
    argv = drbii_score_command(tmp_path / "nope", tmp_path / "out.jsonl", eval_script=ghost_script)
    assert not os.path.exists(ghost_script), "the eval script need not exist to build the argv"
    assert argv[1] == ghost_script and "--pdf_dir" in argv


def test_write_submission_materializes_layout(tmp_path):
    sub = build_drbii_submission(SAMPLE_REPORT, task_id=56, references=SAMPLE_REFS)
    written = write_drbii_submission(sub, tmp_path)
    assert written.exists()
    assert written.name == "idx-56.md" and written.parent.name == "polaris"
    assert written.read_text(encoding="utf-8") == SAMPLE_REPORT
    # the written root is exactly what drbii_score_command consumes as --pdf_dir
    argv = drbii_score_command(tmp_path, tmp_path / "result.jsonl")
    assert str(tmp_path) in argv


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
