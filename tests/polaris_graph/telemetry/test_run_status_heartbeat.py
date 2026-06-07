"""Unit tests for the AC1 run-status heartbeat (I-obs-001 #1141)."""
from __future__ import annotations

import json
import threading
import time

import pytest

from polaris_graph.telemetry import run_status_heartbeat as hb


def _write(run_dir, **kw):
    base = dict(
        run_dir=run_dir,
        run_id="SWEEP_test_0001",
        slug="drb_72",
        query_index=3,
        query_total=5,
        stage="four_role_progress",
        started_monotonic=time.monotonic() - 12.3,
        running_cost_usd=4.21,
        budget_cap_usd=25.0,
    )
    base.update(kw)
    hb.write_heartbeat(**base)


def test_enabled_default_on(monkeypatch):
    monkeypatch.delenv(hb.HEARTBEAT_ENABLED_ENV, raising=False)
    assert hb.heartbeat_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "OFF", "False"])
def test_disabled_values(monkeypatch, val):
    monkeypatch.setenv(hb.HEARTBEAT_ENABLED_ENV, val)
    assert hb.heartbeat_enabled() is False


def test_writes_both_targets_with_schema(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    mirror = tmp_path / "state" / "run_status.json"
    monkeypatch.setenv(hb.RUN_STATUS_PATH_ENV, str(mirror))
    monkeypatch.delenv(hb.HEARTBEAT_ENABLED_ENV, raising=False)
    _write(run_dir, sources_kept=38, sections_done=6, sections_total=9,
           claims_verified=41, claims_total=120)

    per_run = run_dir / hb.RUN_STATUS_FILENAME
    assert per_run.exists() and mirror.exists()
    for p in (per_run, mirror):
        doc = json.loads(p.read_text(encoding="utf-8"))
        assert doc["run_id"] == "SWEEP_test_0001"
        assert doc["slug"] == "drb_72"
        assert doc["query_index"] == 3 and doc["query_total"] == 5
        assert doc["stage"] == "four_role_progress"
        assert doc["running_cost_usd"] == 4.21 and doc["budget_cap_usd"] == 25.0
        assert doc["sources_kept"] == 38
        assert doc["claims_verified"] == 41 and doc["claims_total"] == 120
        assert doc["elapsed_s"] >= 12.0
        assert doc["last_update_utc"].endswith("Z")


def test_apply_persisted_sources_kept_injects_when_absent():
    """The run loop sets the kept-source count once at retrieval_done; later stages that pass
    no explicit value inherit it (so run_status.json never reverts to sources_kept=None)."""
    kw: dict = {}
    out = hb.apply_persisted_sources_kept(kw, 180)
    assert out is kw  # mutates in place
    assert kw["sources_kept"] == 180


def test_apply_persisted_sources_kept_does_not_override_explicit():
    """A stage that reports its own sources_kept (e.g. a re-measured corpus) is NOT clobbered."""
    kw = {"sources_kept": 42}
    hb.apply_persisted_sources_kept(kw, 180)
    assert kw["sources_kept"] == 42


def test_apply_persisted_sources_kept_noop_while_unknown():
    """Before retrieval_done the count is unknown (None) — no key is added (stays absent → None)."""
    kw: dict = {}
    hb.apply_persisted_sources_kept(kw, None)
    assert "sources_kept" not in kw


def test_off_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv(hb.HEARTBEAT_ENABLED_ENV, "0")
    mirror = tmp_path / "state" / "run_status.json"
    monkeypatch.setenv(hb.RUN_STATUS_PATH_ENV, str(mirror))
    run_dir = tmp_path / "run"
    _write(run_dir)
    assert not (run_dir / hb.RUN_STATUS_FILENAME).exists()
    assert not mirror.exists()


def test_io_error_is_swallowed(tmp_path, monkeypatch):
    """A failing os.replace must NOT raise into the caller (run-outcome safety)."""
    monkeypatch.delenv(hb.HEARTBEAT_ENABLED_ENV, raising=False)
    monkeypatch.setenv(hb.RUN_STATUS_PATH_ENV, str(tmp_path / "state" / "run_status.json"))
    monkeypatch.setattr(hb.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    _write(tmp_path / "run")  # must not raise; temp files cleaned up
    leftover = list((tmp_path / "run").glob("*.tmp")) if (tmp_path / "run").exists() else []
    assert leftover == []


def test_concurrent_writers_produce_valid_json(tmp_path, monkeypatch):
    """Parent + seam-worker both write; unique temps + atomic replace => no corruption."""
    monkeypatch.delenv(hb.HEARTBEAT_ENABLED_ENV, raising=False)
    mirror = tmp_path / "state" / "run_status.json"
    monkeypatch.setenv(hb.RUN_STATUS_PATH_ENV, str(mirror))
    run_dir = tmp_path / "run"

    def worker(stage):
        for _ in range(20):
            _write(run_dir, stage=stage)

    threads = [threading.Thread(target=worker, args=(f"s{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # final file is a complete, parseable object; no leftover temps
    json.loads((run_dir / hb.RUN_STATUS_FILENAME).read_text(encoding="utf-8"))
    json.loads(mirror.read_text(encoding="utf-8"))
    assert list(run_dir.glob("*.tmp")) == []
