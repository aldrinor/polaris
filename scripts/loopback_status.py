"""Quick status of the loopback pipeline + list of pending requests."""

import json
import os
import sys
import subprocess
from pathlib import Path

LOOPBACK = Path("C:/POLARIS/loopback")
LOG = Path("C:/POLARIS/logs/pg_loopback_minimal_stdout.log")
ERR = Path("C:/POLARIS/logs/pg_loopback_minimal_stderr.log")


def main():
    pending = sorted(LOOPBACK.joinpath("pending").glob("req_*.json"))
    done_req = list(LOOPBACK.joinpath("done").glob("req_*.json"))
    done_resp = list(LOOPBACK.joinpath("done").glob("resp_*.json"))

    print("=" * 70)
    print(f"  PIPELINE STATUS ({Path.cwd()})")
    print("=" * 70)

    # Process alive?
    try:
        result = subprocess.run(
            ["powershell", "-Command", "Get-Process python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],
            capture_output=True, text=True, timeout=10,
        )
        pids = [p for p in result.stdout.strip().split() if p]
        print(f"  python process: {'ALIVE pid=' + str(pids) if pids else 'DEAD'}")
    except Exception as e:
        print(f"  python process: ? (check failed: {e})")

    print(f"  pending requests: {len(pending)}")
    print(f"  resolved requests: {len(done_resp)}")

    if pending:
        print("\n  PENDING:")
        for p in pending:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                print(
                    f"    {p.name}  call_type={d.get('call_type', '?')}  "
                    f"prompt={len(d.get('prompt', ''))}c  "
                    f"schema={d.get('schema_name') or '(none)'}"
                )
            except Exception as e:
                print(f"    {p.name}  (read err: {e})")

    print(f"\n  --- last 8 log lines ({LOG.name}) ---")
    if LOG.exists():
        lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-8:]:
            print(f"    {line[:200]}")
    if ERR.exists():
        err_size = ERR.stat().st_size
        if err_size > 0:
            print(f"\n  --- stderr ({err_size}B) ---")
            err_lines = ERR.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in err_lines[-5:]:
                print(f"    {line[:200]}")


if __name__ == "__main__":
    main()
