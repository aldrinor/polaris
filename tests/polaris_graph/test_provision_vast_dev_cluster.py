"""Tests for scripts/provision_vast_dev_cluster.py — Phase 0 substrate."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import provision_vast_dev_cluster as pvdc  # noqa: E402


_VALID_CONFIG_YAML = """
gpu_type: "H100"
region: "US-West"
min_vram_gb: 80
max_hourly_usd: 4.50
image: "vastai/pytorch:2.4-cu124"
disk_gb: 200
notes: "test cluster"
"""


def test_config_loads_valid_yaml(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text(_VALID_CONFIG_YAML, encoding="utf-8")
    cfg = pvdc.load_config(p)
    assert cfg.gpu_type == "H100"
    assert cfg.region == "US-West"
    assert cfg.min_vram_gb == 80
    assert cfg.max_hourly_usd == 4.5
    assert cfg.image.startswith("vastai/pytorch")
    assert cfg.disk_gb == 200


def test_config_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        pvdc.load_config(tmp_path / "nope.yaml")


def test_config_rejects_missing_keys(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text("gpu_type: H100\nregion: US-West\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required keys"):
        pvdc.load_config(p)


def test_config_rejects_negative_max_hourly(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text(
        _VALID_CONFIG_YAML.replace("max_hourly_usd: 4.50", "max_hourly_usd: -1.0"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="max_hourly_usd must be > 0"):
        pvdc.load_config(p)


def test_config_rejects_zero_min_vram(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text(
        _VALID_CONFIG_YAML.replace("min_vram_gb: 80", "min_vram_gb: 0"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="min_vram_gb must be positive"):
        pvdc.load_config(p)


def test_render_plan_includes_all_fields():
    cfg = pvdc.VastDevClusterConfig(
        gpu_type="H100",
        region="US-West",
        max_hourly_usd=4.5,
        min_vram_gb=80,
        image="vastai/pytorch:2.4-cu124",
        disk_gb=200,
        notes="test",
    )
    plan = pvdc.render_plan(cfg)
    assert "H100" in plan
    assert "US-West" in plan
    assert "$4.50" in plan
    assert "80" in plan
    assert "200" in plan


def test_main_dry_run_prints_plan(tmp_path: Path, capsys):
    p = tmp_path / "c.yaml"
    p.write_text(_VALID_CONFIG_YAML, encoding="utf-8")
    rc = pvdc.main(["--config", str(p), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Vast.ai dev cluster provisioning plan" in out
    assert "no API calls made" in out


def test_main_default_is_dry_run(tmp_path: Path, capsys):
    p = tmp_path / "c.yaml"
    p.write_text(_VALID_CONFIG_YAML, encoding="utf-8")
    rc = pvdc.main(["--config", str(p)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no API calls made" in out


def test_main_apply_without_api_key_returns_3(
    tmp_path: Path, monkeypatch, capsys,
):
    p = tmp_path / "c.yaml"
    p.write_text(_VALID_CONFIG_YAML, encoding="utf-8")
    monkeypatch.delenv("VAST_API_KEY", raising=False)
    rc = pvdc.main(["--config", str(p), "--apply"])
    assert rc == 3
    err = capsys.readouterr().err
    assert "VAST_API_KEY" in err


def test_main_apply_with_api_key_raises_not_implemented(
    tmp_path: Path, monkeypatch,
):
    """LAW II: don't silently provision — apply path is gated."""
    p = tmp_path / "c.yaml"
    p.write_text(_VALID_CONFIG_YAML, encoding="utf-8")
    monkeypatch.setenv("VAST_API_KEY", "sk_fake_for_test")
    with pytest.raises(NotImplementedError, match="substrate-only"):
        pvdc.main(["--config", str(p), "--apply"])


def test_main_missing_config_returns_2(tmp_path: Path):
    rc = pvdc.main(["--config", str(tmp_path / "nope.yaml")])
    assert rc == 2


def test_default_config_file_is_valid():
    """The shipped default config must load and validate cleanly."""
    repo_root = Path(__file__).resolve().parents[2]
    default = repo_root / "config" / "provisioning" / "vast_dev_cluster.yaml"
    assert default.is_file(), f"default config missing: {default}"
    cfg = pvdc.load_config(default)
    assert cfg.max_hourly_usd > 0
    assert cfg.min_vram_gb > 0
