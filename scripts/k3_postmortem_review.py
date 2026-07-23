#!/usr/bin/env python3
"""Feed the post-mortem brief + fix artifacts to kimi-k3 and capture its independent verdict."""
from __future__ import annotations
import asyncio, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: E402

SCRATCH = Path("/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad")
OUT = SCRATCH / "verdict_k3_postmortem.txt"

def read(p: str, cap: int = 24000) -> str:
    fp = ROOT / p
    if not fp.exists():
        return f"[missing: {p}]"
    t = fp.read_text(errors="ignore")
    return t if len(t) <= cap else t[:cap] + f"\n...[truncated {len(t)-cap} chars]"

def find_latest(glob: str) -> str:
    fs = sorted(ROOT.glob(glob), key=lambda x: x.stat().st_mtime, reverse=True)
    return str(fs[0].relative_to(ROOT)) if fs else ""

async def main() -> int:
    brief = read("outputs/gate_inputs/postmortem_review_brief.md")
    # standalone fix modules (the reviewable units)
    mods = {
        "narrative_consolidation.py": read("src/polaris_graph/generator/narrative_consolidation.py"),
        "cleaned_output_guard.py": read("src/polaris_graph/generator/cleaned_output_guard.py"),
        "exclusive_citation_eligibility.py": read("src/polaris_graph/retrieval/exclusive_citation_eligibility.py"),
        "coverage_obligations.py": read("src/polaris_graph/generator/coverage_obligations.py"),
    }
    forensic = (SCRATCH / "sol_forensic_verdict.txt").read_text(errors="ignore") if (SCRATCH / "sol_forensic_verdict.txt").exists() else "[forensic missing]"
    rpt = find_latest("outputs/race_7phase*/**/draw_1/report.md")
    report_sample = read(rpt, cap=12000) if rpt else "[no report]"

    prompt = (
        brief
        + "\n\n===== FIX MODULE SOURCE =====\n"
        + "\n\n".join(f"----- {n} -----\n{c}" for n, c in mods.items())
        + "\n\n===== FORENSIC FINDINGS (Sol, earlier) =====\n" + forensic[:14000]
        + f"\n\n===== DEGRADED REPORT SAMPLE ({rpt}) =====\n" + report_sample
        + "\n\n===== NOW PRODUCE YOUR INDEPENDENT K3 VERDICT (REVIEWER: K3) in the brief's output format. Be blunt, specific, line-level. Do not rubber-stamp. ====="
    )
    system = (
        "You are K3, a rigorous independent code+ML reviewer. You are one of three reviewers doing a "
        "post-mortem on RACE 'fixes' that DEGRADED the score. Give your own blunt, evidence-based verdict; "
        "focus on root cause, how to unwire post-generation/subtractive fixes, and a concrete PRE-generation "
        "(search scope-contract + compose-prompt) redesign that GROWS comprehensiveness. Do not defer."
    )
    client = OpenRouterClient(model="moonshotai/kimi-k3")
    try:
        resp = await client.generate(
            prompt=prompt, system=system, max_tokens=32768,
            temperature=0.3, reasoning_max_tokens=16384,
        )
        out = (resp.content or "").strip()
    finally:
        if hasattr(client, "close"):
            try:
                await client.close()
            except Exception:
                pass
    if not out:
        out = "[K3 returned empty content]"
    OUT.write_text(out + "\n")
    print(f"WROTE {OUT} ({len(out)} chars)")
    return 0

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
