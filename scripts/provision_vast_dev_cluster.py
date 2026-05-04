"""Provision substrate for Phase 0 Task 0.3 — Vast.ai US dev cluster.

This is a SUBSTRATE script, not a runtime. It does NOT call the Vast.ai
API. Per `feedback_substrate_is_not_product.md`, agent-actionable substrate
ships now; runtime provisioning waits for user authorization (cost +
account credentials).

What this script does:
  - Loads a config (`config/provisioning/vast_dev_cluster.yaml`)
  - Validates required fields (gpu_type, region, max_hourly_usd, min_vram_gb)
  - Prints the dry-run plan (what would be requested)
  - In `--apply` mode, fail-loudly if VAST_API_KEY is missing

When the user is ready to provision:
  1. Set VAST_API_KEY in .env
  2. Adjust config/provisioning/vast_dev_cluster.yaml
  3. Run `python scripts/provision_vast_dev_cluster.py --dry-run` to confirm
  4. Run `python scripts/provision_vast_dev_cluster.py --apply` (NOT YET
     IMPLEMENTED — substrate-only; needs vastai_sdk integration once
     hardware path A/B/C decision (Task 0.6) is locked)

Per CLAUDE.md LAW II — no fake working: this script REFUSES to silently
provision; --apply is gated behind a NotImplementedError until the user
authorizes the integration.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml


_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CONFIG = _REPO_ROOT / "config" / "provisioning" / "vast_dev_cluster.yaml"


@dataclass(frozen=True)
class VastDevClusterConfig:
    gpu_type: str
    region: str
    max_hourly_usd: float
    min_vram_gb: int
    image: str
    disk_gb: int
    notes: str

    @classmethod
    def from_yaml(cls, raw: dict) -> "VastDevClusterConfig":
        required = {
            "gpu_type", "region", "max_hourly_usd",
            "min_vram_gb", "image", "disk_gb",
        }
        missing = required - raw.keys()
        if missing:
            raise ValueError(f"missing required keys: {sorted(missing)}")
        if not isinstance(raw["max_hourly_usd"], (int, float)):
            raise ValueError("max_hourly_usd must be numeric")
        if raw["max_hourly_usd"] <= 0:
            raise ValueError("max_hourly_usd must be > 0")
        if not isinstance(raw["min_vram_gb"], int) or raw["min_vram_gb"] <= 0:
            raise ValueError("min_vram_gb must be positive int")
        if not isinstance(raw["disk_gb"], int) or raw["disk_gb"] <= 0:
            raise ValueError("disk_gb must be positive int")
        return cls(
            gpu_type=str(raw["gpu_type"]),
            region=str(raw["region"]),
            max_hourly_usd=float(raw["max_hourly_usd"]),
            min_vram_gb=int(raw["min_vram_gb"]),
            image=str(raw["image"]),
            disk_gb=int(raw["disk_gb"]),
            notes=str(raw.get("notes", "")),
        )


def load_config(path: Path) -> VastDevClusterConfig:
    if not path.is_file():
        raise FileNotFoundError(f"config not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"config must be a YAML mapping, got {type(raw).__name__}")
    return VastDevClusterConfig.from_yaml(raw)


def render_plan(config: VastDevClusterConfig) -> str:
    return (
        f"Vast.ai dev cluster provisioning plan:\n"
        f"  gpu_type:        {config.gpu_type}\n"
        f"  region:          {config.region}\n"
        f"  min_vram_gb:     {config.min_vram_gb}\n"
        f"  max_hourly_usd:  ${config.max_hourly_usd:.2f}\n"
        f"  image:           {config.image}\n"
        f"  disk_gb:         {config.disk_gb}\n"
        f"  notes:           {config.notes or '(none)'}"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Provision substrate for Vast.ai US dev cluster"
    )
    p.add_argument(
        "--config",
        type=Path,
        default=_DEFAULT_CONFIG,
        help=f"Provisioning config (default: {_DEFAULT_CONFIG.relative_to(_REPO_ROOT)})",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--dry-run", action="store_true",
        help="Validate config + print plan (default)",
    )
    g.add_argument(
        "--apply", action="store_true",
        help="Actually provision (NOT IMPLEMENTED — gated on Task 0.6 + VAST_API_KEY)",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    plan = render_plan(config)
    print(plan)
    if args.apply:
        if not os.environ.get("VAST_API_KEY", "").strip():
            print(
                "ERROR: --apply requires VAST_API_KEY in env (LAW II — no fake working)",
                file=sys.stderr,
            )
            return 3
        raise NotImplementedError(
            "Vast.ai apply path is substrate-only. Phase 0 Task 0.6 "
            "(hardware Path A/B/C decision) must lock first. Track at "
            "polaris-controls/PLAN.md and the project task list."
        )
    print("\n(dry-run; no API calls made)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
