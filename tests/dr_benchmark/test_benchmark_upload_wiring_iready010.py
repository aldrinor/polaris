"""I-ready-010 (#1073) — Claude-authored BEHAVIORAL coverage for Gate-B uploaded-document wiring.

The finding: the upload->citable-evidence capability is live on the pipeline-B UI/worker path
but DEAD on the Gate-B beat-both benchmark path — no benchmark question carried `uploaded_documents`
and the CLI had no flag to attach one, so the sweep injection at run_honest_sweep_r3.py:3458 never
fired. This change adds `--upload-file` (+ `--upload-classification`) to run_gate_b's `main` and a
`_resolve_benchmark_upload` helper that ingests the file in-process and shapes it as the
`{document_id, classification, filename, chunks}` entry the sweep + build_upload_evidence_rows consume.

These tests assert: (1) the resolver produces a citable ev_upload_* row; (2) sovereignty fail-loud on
non-PUBLIC_SYNTHETIC; (3) empty/missing fail-loud (LAW II); (4) the CLI attaches the upload to a COPY
of the question (the shared SWEEP_QUERIES registry stays clean); (5) flag-OFF is byte-identical; (6)
the upload imports stay lazy (the module's NO-SPEND/NO-NETWORK-at-import invariant).

Offline, no network, no spend, no heavy model: the fixture is a tiny PUBLIC_SYNTHETIC `.md` that
dispatches to DocumentIngester._parse_text (no fitz/OCR/whisper). Persistence is redirected to tmp.
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

import polaris_graph.document_ingester as document_ingester
from polaris_v6.adapters.upload_evidence import build_upload_evidence_rows
from scripts.dr_benchmark import run_gate_b
from scripts.dr_benchmark.run_gate_b import (
    _resolve_benchmark_upload,
    load_locked_questions,
    main,
)

_SLUG = "drb_72_ai_labor"

# A synthetic, unmistakably-fictional citable fact — proves the uploaded text reaches the
# evidence row's direct_quote (the string the generator + strict_verify see).
_FIXTURE_MD = (
    "# Synthetic Trial Fixture (PUBLIC_SYNTHETIC)\n\n"
    "In the synthetic ZORBLAX-7 trial, the experimental compound reduced the fictional "
    "Quibble Score by 42 percent versus placebo (p < 0.001).\n"
)


@pytest.fixture(autouse=True)
def _isolate_env():
    """Snapshot/restore os.environ so a CLI run that flips the 4-role / slate flags does not
    leak into sibling tests (mirrors test_run_gate_b_cli)."""
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


@pytest.fixture()
def _hermetic_storage(tmp_path, monkeypatch):
    """Redirect DocumentIngester persistence to tmp so the test never writes to repo data/."""
    monkeypatch.setattr(
        document_ingester, "DOCUMENT_STORAGE_DIR", tmp_path / "doc_store"
    )
    return tmp_path


def _write_fixture(tmp_path: Path, content: str = _FIXTURE_MD, name: str = "fixture.md") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ───────────────────────────────────── resolver: happy path ─────────────────────────────────────

def test_resolver_produces_citable_ev_upload_row(_hermetic_storage):
    fixture = _write_fixture(_hermetic_storage)
    allowed, blocked = _resolve_benchmark_upload(str(fixture), "PUBLIC_SYNTHETIC")

    assert blocked == 0
    assert len(allowed) == 1
    doc = allowed[0]
    assert doc["classification"] == "PUBLIC_SYNTHETIC"
    assert doc["filename"] == "fixture.md"
    assert doc["chunks"] and all(isinstance(c, str) for c in doc["chunks"])

    # The doc flows through the SAME builder the UI/worker path uses -> an ev_upload_* evidence row
    # whose direct_quote carries the uploaded text (so strict_verify + the generator can cite it).
    rows = build_upload_evidence_rows(allowed)
    assert rows, "expected at least one evidence row"
    assert rows[0]["evidence_id"].startswith("ev_upload_")
    assert rows[0]["source_url"].startswith("upload://")
    assert "ZORBLAX-7" in rows[0]["direct_quote"]
    assert rows[0]["uploaded_document"] is True


# ───────────────────────────────────── resolver: fail-loud paths ────────────────────────────────

@pytest.mark.parametrize("classification", ["CAN_REAL", "PRIVATE", "CLIENT", "UNKNOWN"])
def test_resolver_blocks_non_public_synthetic(_hermetic_storage, classification):
    """Sovereignty: anything but PUBLIC_SYNTHETIC is EXTERNAL_LEAK_FORBIDDEN — partitioned to
    `blocked`, never returned as `allowed` (it could never become external-generator evidence)."""
    fixture = _write_fixture(_hermetic_storage)
    allowed, blocked = _resolve_benchmark_upload(str(fixture), classification)
    assert allowed == []
    assert blocked == 1


def test_resolver_empty_file_fails_loud(_hermetic_storage):
    """LAW II: an empty/whitespace file yields no extractable text -> ValueError (never a silent
    zero-evidence run)."""
    fixture = _write_fixture(_hermetic_storage, content="   \n\t  \n", name="empty.md")
    with pytest.raises(ValueError, match="no extractable text"):
        _resolve_benchmark_upload(str(fixture), "PUBLIC_SYNTHETIC")


def test_resolver_missing_file_fails_loud(_hermetic_storage):
    with pytest.raises(FileNotFoundError, match="does not exist"):
        _resolve_benchmark_upload(
            str(_hermetic_storage / "nope_does_not_exist.md"), "PUBLIC_SYNTHETIC"
        )


def test_resolver_unsupported_extension_fails_loud_as_valueerror(_hermetic_storage):
    """diff-gate iter-1 P2: a DocumentIngester failure (here an unsupported extension) is
    re-raised as ValueError so the CLI converts it to a clean pre-spend rc2 — never a raw
    traceback. The file exists (so it is NOT the FileNotFoundError path)."""
    fixture = _write_fixture(_hermetic_storage, content="x", name="fixture.xyz")
    with pytest.raises(ValueError, match="fixture.xyz"):
        _resolve_benchmark_upload(str(fixture), "PUBLIC_SYNTHETIC")


# ───────────────────────────────────── CLI: attach to a COPY ────────────────────────────────────

def test_cli_attaches_upload_to_question_copy(_hermetic_storage, monkeypatch):
    """main(--only --upload-file) attaches the resolved upload to the question handed to
    run_gate_b_query — and to a COPY, leaving the shared SWEEP_QUERIES registry entry clean."""
    fixture = _write_fixture(_hermetic_storage)
    captured = {}

    async def _recording_run_gate_b_query(q, out_root, **kwargs):
        captured["q"] = q
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _recording_run_gate_b_query)

    rc = main([
        "--only", _SLUG,
        "--upload-file", str(fixture),
        "--upload-classification", "PUBLIC_SYNTHETIC",
        "--out-root", "outputs/__test_unused__",
    ])
    assert rc == 0

    # The question that reached run_gate_b_query carries the upload + a citable chunk.
    q = captured["q"]
    assert q["uploaded_documents"], "upload not attached to the run question"
    assert q["uploaded_documents_blocked_count"] == 0
    rows = build_upload_evidence_rows(q["uploaded_documents"])
    assert "ZORBLAX-7" in rows[0]["direct_quote"]

    # Registry isolation: the live SWEEP_QUERIES entry for this slug is UNMUTATED (no leak).
    registry_entry = load_locked_questions((_SLUG,))[0]
    assert "uploaded_documents" not in registry_entry
    assert "uploaded_documents_blocked_count" not in registry_entry


def test_cli_flag_off_is_byte_identical(_hermetic_storage, monkeypatch):
    """Without --upload-file, the question handed to run_gate_b_query carries NO upload keys and is
    the SAME object as the registry entry (no copy made) — flag-OFF byte-identical."""
    captured = {}

    async def _recording_run_gate_b_query(q, out_root, **kwargs):
        captured["q"] = q
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _recording_run_gate_b_query)

    rc = main(["--only", _SLUG, "--out-root", "outputs/__test_unused__"])
    assert rc == 0
    q = captured["q"]
    assert "uploaded_documents" not in q
    assert "uploaded_documents_blocked_count" not in q
    # No copy when no upload: the run question IS the registry entry.
    assert q is load_locked_questions((_SLUG,))[0]


# ───────────────────────────────────── CLI: fail-loud rc 2 ──────────────────────────────────────

def test_cli_non_public_synthetic_fails_loud_rc2(_hermetic_storage, monkeypatch, capsys):
    """A non-PUBLIC_SYNTHETIC --upload-file fails loud (rc 2) BEFORE any question runs."""
    fixture = _write_fixture(_hermetic_storage)
    called = {"n": 0}

    async def _should_not_run(q, out_root, **kwargs):
        called["n"] += 1
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _should_not_run)

    with pytest.raises(SystemExit) as exc:
        main([
            "--only", _SLUG,
            "--upload-file", str(fixture),
            "--upload-classification", "CAN_REAL",
            "--out-root", "outputs/__test_unused__",
        ])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "EXTERNAL_LEAK_FORBIDDEN" in err
    assert called["n"] == 0  # never spent a question


def test_cli_missing_upload_file_fails_loud_rc2(_hermetic_storage, monkeypatch, capsys):
    async def _should_not_run(q, out_root, **kwargs):
        raise AssertionError("must not run a question on a missing upload file")

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _should_not_run)

    with pytest.raises(SystemExit) as exc:
        main([
            "--only", _SLUG,
            "--upload-file", str(_hermetic_storage / "absent.md"),
            "--upload-classification", "PUBLIC_SYNTHETIC",
            "--out-root", "outputs/__test_unused__",
        ])
    assert exc.value.code == 2
    assert "does not exist" in capsys.readouterr().err


def test_cli_unsupported_classification_rejected_by_argparse_rc2():
    with pytest.raises(SystemExit) as exc:
        main(["--only", _SLUG, "--upload-file", "x.md", "--upload-classification", "BOGUS"])
    assert exc.value.code == 2  # argparse choices= rejects it


# ───────────────────────────────────── import-cleanliness guard ─────────────────────────────────

def test_upload_imports_are_lazy_inside_the_resolver():
    """The NO-SPEND/NO-NETWORK-at-import invariant: document_ingester / fastapi-backed upload are
    imported INSIDE _resolve_benchmark_upload, never at module top. Guards against a future hoist
    that would pull those (and a socket-opening dep chain) into `import run_gate_b`."""
    fn_src = inspect.getsource(run_gate_b._resolve_benchmark_upload)
    # Robust to single- vs multi-line import formatting: assert the module path appears
    # inside the function body (the symbols may wrap across lines).
    for lazy in (
        "from polaris_graph.document_ingester import",
        "from polaris_v6.adapters.upload_evidence import",
        "from polaris_v6.api.upload import chunk_text",
    ):
        assert lazy in fn_src, f"expected lazy import in resolver body: {lazy!r}"

    # And NOT at module top (everything before the first `def `).
    mod_src = inspect.getsource(run_gate_b)
    head = mod_src.split("\ndef ", 1)[0]
    assert "document_ingester" not in head
    assert "from polaris_v6.api.upload import" not in head
