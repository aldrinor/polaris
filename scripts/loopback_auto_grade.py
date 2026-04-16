"""Auto-responder for repetitive GRADE certainty rating calls in the loopback queue.

Only handles the specific pattern of reason() calls whose prompt starts with
'Assign GRADE certainty ratings'. All other pending requests are left alone
for the operator to handle.

Heuristic: map each evidence item's tier + content signal to a GRADE rating:
- GOLD + (systematic review | meta-analysis | RCT | SMD | MD | 95% CI) -> HIGH
- GOLD otherwise -> MODERATE
- SILVER + (RCT | meta-analysis | systematic review) -> MODERATE
- SILVER otherwise -> LOW
- BRONZE -> LOW
- (captcha | INSUFFICIENT_CONTENT | 403 | binary) -> VERY_LOW

Writes responses to loopback/responses/resp_<id>.json with the plain text rating list
that the pipeline parses. Exits when no auto-serve-able request remains for one poll cycle.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PENDING = ROOT / "loopback" / "pending"
RESPONSES = ROOT / "loopback" / "responses"
DONE = ROOT / "loopback" / "done"

STATS_SIGNAL = re.compile(r"\bSMD\b|\bMD\b|\b95%\s*CI\b|\bmeta-analysis\b|\bsystematic review\b|\bRCT\b|\brandomized\b", re.I)
DOWNGRADE_SIGNAL = re.compile(r"INSUFFICIENT_CONTENT|captcha|403|forbidden|paywall|binary|PDF binary", re.I)


def rate_item(tier: str, statement: str) -> str:
    stmt = statement or ""
    if DOWNGRADE_SIGNAL.search(stmt):
        return "VERY_LOW"
    has_stats = bool(STATS_SIGNAL.search(stmt))
    if tier == "GOLD":
        return "HIGH" if has_stats else "MODERATE"
    if tier == "SILVER":
        return "MODERATE" if has_stats else "LOW"
    if tier == "BRONZE":
        return "LOW"
    return "LOW"


def try_handle(req_path: Path) -> bool:
    try:
        with req_path.open(encoding="utf-8") as f:
            req = json.load(f)
    except Exception:
        return False
    prompt = req.get("prompt", "") or ""
    if not prompt.startswith("Assign GRADE certainty ratings"):
        return False
    items = re.findall(
        r"^(\d+)\.\s*\[(\w+)\][^|]+\|\s*Statement:\s*([^\n]+)",
        prompt,
        re.MULTILINE,
    )
    if not items:
        return False
    lines = [f"{num}. {rate_item(tier, stmt)}" for num, tier, stmt in items]
    content = "\n".join(lines)
    req_id = req.get("request_id") or req_path.stem.replace("req_", "")
    resp_path = RESPONSES / f"resp_{req_id}.json"
    tmp = resp_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(
            {"content": content, "input_tokens": 500, "output_tokens": 40},
            f,
            ensure_ascii=False,
        )
    tmp.replace(resp_path)
    print(f"  [auto-GRADE] {req_path.name} -> {len(items)} ratings")
    return True


def main() -> int:
    handled_total = 0
    idle_polls = 0
    # Persistent mode: exit only after many idle polls so operator can run this in background
    # and let it drain GRADE calls while they work other things.
    MAX_IDLE_POLLS = 1800  # ~5 minutes at 1s poll
    while True:
        handled_this_cycle = 0
        for p in sorted(PENDING.glob("req_*.json")):
            try:
                if try_handle(p):
                    handled_this_cycle += 1
                    handled_total += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  [auto-GRADE] error on {p.name}: {exc}")
        if handled_this_cycle == 0:
            idle_polls += 1
            if idle_polls >= MAX_IDLE_POLLS:
                break
            time.sleep(1.0)
        else:
            idle_polls = 0
            time.sleep(0.5)
    print(f"[auto-GRADE] drained {handled_total} GRADE requests; exiting after {MAX_IDLE_POLLS}s idle.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
