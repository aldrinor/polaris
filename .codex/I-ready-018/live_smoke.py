"""I-ready-018 (#1100 keystone) LIVE smoke — empirical before/after proof.

PART A (control, proves the diagnosis): a raw OpenRouter POST replicating the OLD call body
(strict json_schema response_format + a forced reasoning block + provider.require_parameters:true)
against deepseek/deepseek-v4-pro -> expect HTTP 404 "No endpoints found" (the exact failure the
drb_72 run hit on every STORM/agentic discovery call).

PART B (proves the fix): the FIXED generate_structured(reasoning_enabled=False) against
deepseek/deepseek-v4-pro using the REAL discovery schemas (AgenticRoundAnalysis = the searcher's
round-analysis, StormPersonaBatch = STORM persona-gen) -> expect a PARSED object, not a 404.

Cost: a few cents. Run from repo root with the local .env (OPENROUTER_API_KEY).
"""
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.getcwd(), ".env"))

import httpx

from src.polaris_graph.llm.openrouter_client import OpenRouterClient, OPENROUTER_BASE_URL
from src.polaris_graph.schemas import AgenticRoundAnalysis
from src.polaris_graph.agents.storm_interviews import StormPersonaBatch

MODEL = "deepseek/deepseek-v4-pro"
KEY = os.environ["OPENROUTER_API_KEY"]
BASE = OPENROUTER_BASE_URL.rstrip("/")

results = {}


def part_a_control() -> None:
    """Raw POST with the conflicting OLD body + the GENERATOR'S EXACT provider pin
    (role_provider_routing('generator') order + allow_fallbacks:false + require_parameters:true)
    -> expect 404 No endpoints found. Relaxing the pin (earlier control) routed to DeepInfra and
    got 200, which is itself the proof that the 404 is the pinned-provider + require_parameters
    filter — exactly what the keystone fix sidesteps by not sending strict schema at all."""
    from src.polaris_graph.roles.provider_routing import role_provider_routing
    gen_routing = role_provider_routing("generator")
    provider_block = {"require_parameters": True, "allow_fallbacks": False}
    if gen_routing.get("order"):
        provider_block["order"] = gen_routing["order"]
    if gen_routing.get("ignore"):
        provider_block["ignore"] = gen_routing["ignore"]
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Return JSON {\"ok\": true}."}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "Probe", "strict": True,
                            "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}},
                                       "required": ["ok"], "additionalProperties": False}},
        },
        "reasoning": {"enabled": True},
        "provider": provider_block,
        "max_tokens": 64,
    }
    try:
        r = httpx.post(BASE + "/chat/completions",
                       headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
                       json=body, timeout=60)
        code = r.status_code
        snippet = r.text[:200]
        is_404_noendpoint = code == 404 and ("no endpoint" in r.text.lower() or "no allowed providers" in r.text.lower())
        results["A_control"] = {"status": code, "is_404_noendpoint": is_404_noendpoint, "snippet": snippet}
        print(f"[PART A control] strict-schema + reasoning + require_parameters on {MODEL}: "
              f"HTTP {code}  404_no_endpoint={is_404_noendpoint}\n   {snippet}")
    except Exception as e:  # noqa: BLE001
        results["A_control"] = {"error": f"{type(e).__name__}: {e}"}
        print(f"[PART A control] raw call raised: {e}")


async def _structured(schema, prompt) -> dict:
    client = OpenRouterClient(model=MODEL)
    try:
        obj = await client.generate_structured(prompt=prompt, schema=schema, reasoning_enabled=False, max_tokens=2048)
        ok = isinstance(obj, schema)
        return {"parsed": ok, "type": type(obj).__name__}
    except Exception as e:  # noqa: BLE001
        return {"parsed": False, "error": f"{type(e).__name__}: {str(e)[:160]}"}
    finally:
        await client.close()


async def part_b_fix() -> None:
    agentic = await _structured(
        AgenticRoundAnalysis,
        "You are analyzing search results for a literature review on AI's impact on the labor market. "
        "Decide whether to continue searching and propose follow-up queries. Respond as the schema.",
    )
    results["B_agentic"] = agentic
    print(f"[PART B fix] generate_structured AgenticRoundAnalysis on {MODEL}: {agentic}")

    persona = await _structured(
        StormPersonaBatch,
        "Generate a set of diverse expert personas (economist, labor sociologist, technologist) who would "
        "interview sources for a review of AI's restructuring impact on the labor market. Respond as the schema.",
    )
    results["B_storm"] = persona
    print(f"[PART B fix] generate_structured StormPersonaBatch on {MODEL}: {persona}")


def main() -> int:
    part_a_control()
    asyncio.run(part_b_fix())
    a = results.get("A_control", {})
    b_ok = results.get("B_agentic", {}).get("parsed") and results.get("B_storm", {}).get("parsed")
    diagnosis_proven = a.get("is_404_noendpoint") is True
    print("\n=== SUMMARY ===")
    print(f"diagnosis (old body 404s): {'PROVEN' if diagnosis_proven else 'NOT reproduced (control: ' + str(a) + ')'}")
    print(f"fix (real discovery schemas parse): {'PASS' if b_ok else 'FAIL'}")
    # The fix-proof (Part B) is the gating assertion; Part A is corroborating evidence.
    if b_ok:
        print("KEYSTONE_SMOKE_OK")
        return 0
    print("KEYSTONE_SMOKE_FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
