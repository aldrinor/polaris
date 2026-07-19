"""Demonstrate the oracle as a working REGRESSION GATE on a produced artifact.

With the LLM I/O frozen by the cassette, the ONLY thing that can change the output artifact is the
code. So:
  * an unchanged 'refactor' replays a **byte-identical** artifact  -> PASS,
  * a real behaviour change produces a **different** artifact       -> the byte-diff CATCHES it.

This is the "byte-compare final observable outputs across a frozen trace" property codex flagged as
the requirement for using the oracle to verify refactors.

    /home/polaris/pipeline-env/bin/python tests/oracle/demo_artifact_diff.py   (from repo root, PYTHONPATH=.)
"""

from __future__ import annotations

import asyncio

from dotenv import load_dotenv

load_dotenv("/workspace/POLARIS/.env", override=True)

from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: E402
from tests.oracle.llm_cassette import llm_cassette  # noqa: E402

TAPE = "tests/oracle/cassettes/demo_artifact.jsonl"


async def assemble(joiner) -> str:
    """A tiny 'pipeline unit': two LLM calls assembled into a formatted artifact."""
    client = OpenRouterClient(model="z-ai/glm-5.2")
    a = (await client.generate("Reply with exactly one word: apple", max_tokens=8, temperature=0.0)).content
    b = (await client.generate("Reply with exactly one word: banana", max_tokens=8, temperature=0.0)).content
    return joiner(a, b)


def join_v1(a: str, b: str) -> str:
    return f"# Report\n- {a}\n- {b}\n"


def join_v2(a: str, b: str) -> str:
    # a 'refactor' that actually changes observable behaviour (bullets -> numbers)
    return f"# Report\n1. {a}\n2. {b}\n"


def main() -> None:
    with llm_cassette(TAPE, "record"):                       # 1 paid run
        golden = asyncio.run(assemble(join_v1))
    print("GOLDEN artifact recorded:\n" + golden)

    with llm_cassette(TAPE, "replay"):                       # unchanged code, frozen I/O
        same = asyncio.run(assemble(join_v1))
    assert same == golden, "unchanged refactor must replay byte-identical"
    print("PASS: unchanged code replays byte-identical (no false regression).")

    with llm_cassette(TAPE, "replay"):                       # a real behaviour change
        changed = asyncio.run(assemble(join_v2))
    assert changed != golden, "a behaviour change must produce a different artifact"
    print("CAUGHT: the behaviour change produced a different artifact — regression detected:")
    print("  golden :", repr(golden))
    print("  changed:", repr(changed))
    print("=== ORACLE IS A WORKING REGRESSION GATE: byte-identical on no-op, diff on real change ===")


if __name__ == "__main__":
    main()
