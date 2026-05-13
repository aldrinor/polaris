"""I-carney-005 — POLARIS v6 preflight diagnostics.

Runs inside the container; checks:
- Required env vars present
- Redis broker reachable
- GPG keyring contains the configured POLARIS_GPG_KEY_ID
- run_store sqlite path writable

Exits 0 on success, non-zero per failure type (LAW II: fail loud, not silent).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


REQUIRED_VARS_API = [
    "POLARIS_V6_REDIS_URL",
    "POLARIS_V6_RUN_DB",
]
RECOMMENDED_VARS = [
    "OPENROUTER_API_KEY",
    "SERPER_API_KEY",
    "POLARIS_GPG_KEY_ID",
]


def check_env() -> list[str]:
    failures: list[str] = []
    for var in REQUIRED_VARS_API:
        if not os.environ.get(var):
            failures.append(f"missing required env var: {var}")
    for var in RECOMMENDED_VARS:
        if not os.environ.get(var):
            print(f"[preflight] WARN: recommended env var unset: {var}")
    return failures


def check_redis() -> list[str]:
    failures: list[str] = []
    url = os.environ.get("POLARIS_V6_REDIS_URL", "redis://redis:6379/0")
    try:
        import redis  # noqa: PLC0415
        client = redis.from_url(url)
        client.ping()
        print(f"[preflight] redis reachable: {url}")
    except Exception as exc:
        failures.append(f"redis unreachable at {url}: {exc}")
    return failures


def check_gpg(strict: bool = True) -> list[str]:
    """Per Codex diff iter-1 P2: in a GPG-deploy preflight, POLARIS_GPG_KEY_ID
    being unset is a HARD failure (signed bundles are the deploy's reason
    for existing). Set strict=False only for non-bundling subcommands.
    """
    failures: list[str] = []
    key_id = os.environ.get("POLARIS_GPG_KEY_ID", "").strip()
    if not key_id:
        msg = "POLARIS_GPG_KEY_ID unset; signed bundles unavailable"
        if strict:
            failures.append(msg)
        else:
            print(f"[preflight] WARN: {msg}")
        return failures
    homedir = os.environ.get("GNUPGHOME", "/app/gpg")
    if not Path(homedir).exists():
        failures.append(f"GNUPGHOME {homedir} does not exist")
        return failures
    try:
        import gnupg  # noqa: PLC0415
        gpg = gnupg.GPG(gnupghome=homedir)
        keys = gpg.list_keys(secret=True, keys=[key_id])
        if not keys:
            failures.append(f"GPG key {key_id} not in keyring at {homedir}")
        else:
            print(f"[preflight] GPG key {key_id} present in {homedir}")
    except Exception as exc:
        failures.append(f"GPG check failed: {exc}")
    return failures


def check_run_db() -> list[str]:
    failures: list[str] = []
    db_path = os.environ.get("POLARIS_V6_RUN_DB", "/app/state/v6_runs.sqlite")
    parent = Path(db_path).parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        # Touch a write probe to verify perms (idempotent).
        probe = parent / ".preflight_probe"
        probe.write_text("ok")
        probe.unlink()
        print(f"[preflight] run_db parent writable: {parent}")
    except Exception as exc:
        failures.append(f"run_db parent {parent} not writable: {exc}")
    return failures


def main() -> int:
    all_failures: list[str] = []
    all_failures.extend(check_env())
    all_failures.extend(check_redis())
    all_failures.extend(check_gpg())
    all_failures.extend(check_run_db())

    if all_failures:
        print("\n[preflight] FAILED:")
        for f in all_failures:
            print(f"  - {f}")
        return 1
    print("\n[preflight] all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
