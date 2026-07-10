"""Offline unit tests for the fetch harness content bridge (``--dump-bodies``).

Exercises the PURE ``bodies_from_results`` projection and the ``write_bodies``
JSON writer against a FAKE results structure (no network, no src imports). Proves
the bodies.json row shape the compose harness consumes and the full-body /
head / empty fallback chain. Mirrors the intent of the harness's own oracle tests.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HARNESS_PATH = _REPO_ROOT / "scripts" / "fetch_cited_content_harness.py"

_spec = importlib.util.spec_from_file_location("fetch_cited_content_harness", _HARNESS_PATH)
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)  # module-level imports are stdlib+yaml only (offline)


def _fake_results() -> list[dict]:
    """A results structure like ``run_case``/``_timeout_result`` produce, covering
    the three quote sources: full body, head-only, and timeout (neither)."""
    return [
        {  # dump-mode row: carries the FULL body
            "name": "good_oa_pdf_nber", "ev": "ev_123",
            "url": "https://example.org/a.pdf", "verdict": "PASS",
            "access_method": "pdf_slice", "quote_head": "HEAD only 300",
            "quote_full": "X" * 20000,
        },
        {  # no quote_full -> falls back to the 300-char head
            "name": "head_fallback", "ev": "ev_456",
            "url": "https://example.org/b", "verdict": "DEGRADED_OK",
            "access_method": "zyte", "quote_head": "just a head",
        },
        {  # timeout row: no quote at all -> empty string, never a crash
            "name": "timed_out", "ev": "", "url": "https://example.org/c",
            "verdict": "UNREACHABLE", "access_method": "none",
            "quote_head": "", "quote_full": "",
        },
    ]


def test_bodies_row_shape_and_keys():
    rows = harness.bodies_from_results(_fake_results())
    assert len(rows) == 3
    for row in rows:
        assert set(row.keys()) == {"name", "ev", "url", "verdict", "access_method", "quote"}


def test_full_body_preferred_over_head():
    rows = harness.bodies_from_results(_fake_results())
    assert rows[0]["quote"] == "X" * 20000            # full body, not the 300-char head
    assert rows[0]["name"] == "good_oa_pdf_nber"
    assert rows[0]["verdict"] == "PASS"
    assert rows[0]["access_method"] == "pdf_slice"


def test_head_fallback_when_no_full_body():
    rows = harness.bodies_from_results(_fake_results())
    assert rows[1]["quote"] == "just a head"


def test_timeout_row_yields_empty_quote():
    rows = harness.bodies_from_results(_fake_results())
    assert rows[2]["quote"] == ""
    assert rows[2]["verdict"] == "UNREACHABLE"


def test_bodies_from_results_is_non_mutating():
    results = _fake_results()
    before = json.dumps(results, sort_keys=True)
    harness.bodies_from_results(results)
    assert json.dumps(results, sort_keys=True) == before   # pure: no in-place edits


def test_write_bodies_roundtrip(tmp_path):
    results = _fake_results()
    path = harness.write_bodies(results, tmp_path)
    assert path == tmp_path / "bodies.json"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == harness.bodies_from_results(results)
    assert on_disk[0]["quote"] == "X" * 20000
