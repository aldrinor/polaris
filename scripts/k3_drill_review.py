#!/usr/bin/env python3
"""Feed the drill brief + pipeline artifacts to kimi-k3 for its independent max-reasoning verdict."""
from __future__ import annotations
import asyncio, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: E402
SCRATCH = Path("/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad")
OUT = SCRATCH / "verdict_k3_drill.txt"

def read(p, cap=22000):
    fp = ROOT / p
    if not fp.exists(): return f"[missing: {p}]"
    t = fp.read_text(errors="ignore")
    return t if len(t) <= cap else t[:cap] + f"\n...[truncated {len(t)-cap}]"

def latest(glob, cap=14000):
    fs = sorted(ROOT.glob(glob), key=lambda x: x.stat().st_mtime, reverse=True)
    return read(str(fs[0].relative_to(ROOT)), cap) if fs else "[none]"

def slice_file(p, start, end):
    fp = ROOT / p
    if not fp.exists(): return f"[missing {p}]"
    ls = fp.read_text(errors="ignore").splitlines()
    return "\n".join(ls[start-1:end])

async def main():
    parts = [
        read("outputs/gate_inputs/drill_review_brief.md"),
        "\n\n===== WINNING REPORT (new pre-gen config, draw 1, 0.5062) =====\n" + latest("outputs/race_newconfig/**/draw_1/report.md", 15000),
        "\n\n===== scope_contract.py =====\n" + read("src/polaris_graph/retrieval/scope_contract.py"),
        "\n\n===== section prompt templates (multi_section_generator.py ~3600-3985) =====\n" + slice_file("src/polaris_graph/generator/multi_section_generator.py", 3600, 3985),
        "\n\n===== coverage_obligations.py =====\n" + read("src/polaris_graph/generator/coverage_obligations.py", 9000),
        "\n\n===== NOW PRODUCE YOUR INDEPENDENT K3 VERDICT (REVIEWER: K3) in the brief's output format. Ranked, evidence-first, pre-generation only, smart/general, no hardcode/overfit/adjective. Do not rubber-stamp. =====",
    ]
    prompt = "".join(parts)
    system = ("You are K3, a rigorous independent code+ML reviewer at MAX reasoning, one of three drilling for the "
              "next PRE-GENERATION smart levers (Readability laggard; push Comp+Insight past champion) for a RACE "
              "research pipeline. Blunt, evidence-based, ranked. Every idea must be pre-generation, smart (semantic/"
              "prompt-derived), general (no hardcode/overfit), non-adjective. Do not defer.")
    client = OpenRouterClient(model="moonshotai/kimi-k3")
    try:
        resp = await client.generate(prompt=prompt, system=system, max_tokens=32768, temperature=0.3, reasoning_max_tokens=16384)
        out = (resp.content or "").strip() or "[K3 empty]"
    finally:
        if hasattr(client, "close"):
            try: await client.close()
            except Exception: pass
    OUT.write_text(out + "\n")
    print(f"WROTE {OUT} ({len(out)} chars)")

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
