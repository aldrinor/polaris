"""Demonstrate the oracle wired to the REAL LLM boundary.

RECORD (one small paid run) -> REPLAY twice (no network) -> assert record==replay and the two
replays are byte-identical. Run with the GPU/cu128 env from the repo root:

    /home/polaris/pipeline-env/bin/python tests/oracle/demo_llm_record_replay.py
"""

from __future__ import annotations

import asyncio

from dotenv import load_dotenv

load_dotenv("/workspace/POLARIS/.env", override=True)

from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: E402
from tests.oracle.llm_cassette import llm_cassette  # noqa: E402

TAPE = "tests/oracle/cassettes/demo_llm.jsonl"
PROMPTS = [
    "Reply with exactly one word: apple",
    "Reply with exactly one word: banana",
]


async def scenario() -> list[str]:
    client = OpenRouterClient(model="z-ai/glm-5.2")
    out: list[str] = []
    for p in PROMPTS:
        r = await client.generate(p, max_tokens=8, temperature=0.0)
        out.append(r.content)
    return out


def main() -> None:
    with llm_cassette(TAPE, "record"):
        recorded = asyncio.run(scenario())
    print("RECORDED (paid):", recorded)

    with llm_cassette(TAPE, "replay"):
        replay1 = asyncio.run(scenario())
    with llm_cassette(TAPE, "replay"):
        replay2 = asyncio.run(scenario())
    print("REPLAY 1 (free):", replay1)
    print("REPLAY 2 (free):", replay2)

    assert replay1 == recorded, f"replay must reproduce recorded: {replay1!r} != {recorded!r}"
    assert replay1 == replay2, "the two replays must be byte-identical (deterministic)"
    print("=== ORACLE WIRED TO REAL LLM: record==replay, replays byte-identical, 0 network on replay ===")


if __name__ == "__main__":
    main()
