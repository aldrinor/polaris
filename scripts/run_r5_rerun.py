"""
R-5 re-run: only the 4 queries we read end-to-end in R-4. Verify the
three fixes (A: denylist, B: subject, D: content-starved) take effect.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
import time

from dotenv import load_dotenv
load_dotenv(override=False)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_honest_sweep_r3 import SWEEP_QUERIES, run_one_query  # noqa: E402

# The 4 queries we hand-audited
RERUN_SLUGS = {
    "clinical_afib_anticoagulation",
    "policy_fda_ai_devices",
    "tech_rag_architectures_2024",
    "dd_novo_nordisk_obesity_position",
}


async def main_async() -> int:
    out_root = ROOT / "outputs" / "honest_sweep_r5_rerun"
    out_root.mkdir(parents=True, exist_ok=True)

    picks = [q for q in SWEEP_QUERIES if q["slug"] in RERUN_SLUGS]
    summaries: list[dict] = []
    for q in picks:
        print(f"\n>>> R-5 RERUN {q['slug']}")
        t0 = time.time()
        s = await run_one_query(q, out_root)
        s["wall_time_seconds"] = round(time.time() - t0, 1)
        summaries.append(s)
        print(f"<<< status={s['status']} cost=${s.get('cost_usd', 0):.4f}")

    (out_root / "rerun_summary.json").write_text(
        json.dumps(summaries, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    total_cost = sum(s.get("cost_usd", 0) or 0 for s in summaries)
    print(f"\nTOTAL RERUN COST: ${total_cost:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
