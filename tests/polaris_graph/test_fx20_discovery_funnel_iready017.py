"""FX-20 (I-ready-017 #1128): discovery_funnel requested-vs-actual telemetry.

The funnel is derived ONLY from the recorded ToolCall rows (same source as ToolTracer.manifest), so
it equals the raw tool_trace tallies and can never fabricate. Unrecorded counts (e.g. s2 has no
num_requested) are reported as None + a *_source marker, NOT defaulted to 0. The funnel is stamped
onto the manifest by attach_tool_utilization only when the tracker is ON (byte-identical OFF).
Offline, no network.
"""
from __future__ import annotations

from pathlib import Path

import src.polaris_graph.telemetry.tool_tracer as tt


def _fresh_tracer(run_dir=None):
    tt.reset_tool_tracer()
    return tt.get_tool_tracer(run_dir)


def test_funnel_tallies_per_backend_from_recorded_rows(monkeypatch):
    tr = _fresh_tracer()
    # serper: 2 calls, requested 20+20, returned 18+15
    tr.record("serper", status="ok", result_count=18, num_requested=20)
    tr.record("serper", status="ok", result_count=15, num_requested=20)
    # s2: 1 call, returned 9, NO num_requested recorded
    tr.record("s2", status="ok", result_count=9)
    # openalex_search: 1 call, requested 12, returned 7
    tr.record("openalex_search", status="ok", result_count=7, num_requested=12)
    # fetch_content: 3 attempted, 2 ok (1 fail)
    tr.record("fetch_content", status="ok")
    tr.record("fetch_content", status="ok")
    tr.record("fetch_content", status="fail")

    f = tr.discovery_funnel()
    assert f["serper"]["calls"] == 2
    assert f["serper"]["returned"] == 33 and f["serper"]["requested"] == 40
    assert f["serper"]["requested_source"] == "tool_trace.num_requested"
    # s2 has no num_requested -> None + unrecorded marker (NOT 0)
    assert f["s2"]["returned"] == 9
    assert f["s2"]["requested"] is None
    assert f["s2"]["requested_source"] == "unrecorded"
    assert f["openalex_search"]["returned"] == 7 and f["openalex_search"]["requested"] == 12
    assert f["fetch_content"]["attempted"] == 3
    assert f["fetch_content"]["succeeded"] == 2          # fail is not a success
    assert f["fetch_content"]["succeeded"] <= f["fetch_content"]["attempted"]


def test_unrecorded_returned_is_none_not_zero(monkeypatch):
    """A backend row with NO result_count metadata -> returned is None (unrecorded), never a fake 0."""
    tr = _fresh_tracer()
    tr.record("serper", status="ok")  # no metadata at all
    f = tr.discovery_funnel()
    assert f["serper"]["calls"] == 1
    assert f["serper"]["returned"] is None
    assert f["serper"]["returned_source"] == "unrecorded"


def test_bool_metadata_not_counted_as_number(monkeypatch):
    """`clamped=True` (a bool) must not be summed as 1 into a count (bool is an int subclass)."""
    tr = _fresh_tracer()
    tr.record("serper", status="ok", result_count=5, num_requested=20, clamped=True)
    f = tr.discovery_funnel()
    assert f["serper"]["returned"] == 5 and f["serper"]["requested"] == 20  # clamped ignored


def test_funnel_equals_manifest_totals(monkeypatch):
    """fetch attempted/succeeded must reconcile with the manifest's per-tool ok/total (same rows)."""
    tr = _fresh_tracer()
    tr.record("fetch_content", status="ok")
    tr.record("fetch_content", status="fail")
    f = tr.discovery_funnel()
    m = tr.manifest()["summary_by_tool"]["fetch_content"]
    assert f["fetch_content"]["attempted"] == m["total_calls"]
    assert f["fetch_content"]["succeeded"] == m["ok_count"]


def test_attach_stamps_funnel_when_tracker_on(monkeypatch, tmp_path):
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "1")
    tr = _fresh_tracer(tmp_path)
    tr.record("serper", status="ok", result_count=10, num_requested=20)
    manifest = tt.attach_tool_utilization({}, tmp_path)
    assert "discovery_funnel" in manifest
    assert manifest["discovery_funnel"]["serper"]["returned"] == 10


def test_attach_omits_funnel_when_tracker_off(monkeypatch, tmp_path):
    """OFF -> attach is a pure no-op: no discovery_funnel key (byte-identical manifest)."""
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "0")
    _fresh_tracer(tmp_path)
    manifest = tt.attach_tool_utilization({}, tmp_path)
    assert "discovery_funnel" not in manifest
    assert "tool_utilization" not in manifest
