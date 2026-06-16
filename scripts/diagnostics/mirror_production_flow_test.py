#!/usr/bin/env python3
"""FAITHFUL Mirror test (I-run11-005): run the EXACT production 2-pass Mirror (run_mirror: RAG
documents + Cohere-style citations + pass1/pass2 binding) against candidate models, so we learn
whether a model works in the REAL flow (blank? citations? binding?) WITHOUT a 40-min full run.
The earlier simple-prompt spot-check misled us (GLM 'worked' on a bare prompt, blanked in the real
2-pass RAG flow). This replicates the actual seam Mirror call.

Env is set to match run-17 (PG_MIRROR_REASONING=false, PG_SENTINEL_MAX_TOKENS=4000). Run from repo root.
"""
from __future__ import annotations
import os, sys, json, traceback

# match run-17's Mirror config BEFORE importing the transport (it reads env at module/call time)
os.environ.setdefault("PG_MIRROR_REASONING", "false")
os.environ.setdefault("PG_SENTINEL_MAX_TOKENS", "4000")
os.environ.setdefault("PG_FOUR_ROLE_TRANSPORT", "openrouter")
# load OPENROUTER_API_KEY from .env if not already set
if not os.getenv("OPENROUTER_API_KEY"):
    try:
        for line in open(".env", encoding="utf-8"):
            if line.startswith("OPENROUTER_API_KEY="):
                os.environ["OPENROUTER_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    except Exception:
        pass

sys.path.insert(0, ".")
import httpx  # noqa: E402
from src.polaris_graph.roles.openrouter_role_transport import OpenRouterRoleTransport  # noqa: E402
from src.polaris_graph.roles.mirror_adapter import run_mirror  # noqa: E402
from src.polaris_graph.roles.role_transport import EvidenceDocument  # noqa: E402

# real claim + documents (drb_72 evidence)
CLAIM = ("In recent decades the labor market has 'polarized': wage gains went disproportionately to "
         "the top and bottom of the skill distribution, not the middle.")
e = json.load(open("outputs/audits/I-run11-004/m25_bakeoff/evidence_pool.json", encoding="utf-8"))
DOCS = [EvidenceDocument(doc_id=x["evidence_id"], text=(x.get("direct_quote") or x.get("statement") or "")[:2000])
        for x in e[:4] if (x.get("direct_quote") or x.get("statement"))]

CANDIDATES = [
    "z-ai/glm-5.1",                              # locked Mirror (blanks in prod)
    "meta-llama/llama-4-maverick",               # run-17 choice
    "meta-llama/llama-4-scout",
    "mistralai/mistral-small-3.2-24b-instruct",
    "cohere/command-a-03-2025",                  # Cohere = native citations (if on OpenRouter)
]


def main():
    print(f"docs={len(DOCS)} (ids={[d.doc_id for d in DOCS]})\n")
    for slug in CANDIDATES:
        # the transport resolves the Mirror model from PG_MIRROR_MODEL, NOT the request slug —
        # set it per candidate + re-instantiate so we ACTUALLY test each model (faithful to run-17).
        os.environ["PG_MIRROR_MODEL"] = slug
        client = httpx.Client(timeout=180.0)
        transport = OpenRouterRoleTransport(client)
        try:
            pass2, records = run_mirror(transport, CLAIM, DOCS, model_slug=slug)
            served = records[0].served_model if records else "?"
            atext = getattr(pass2, "answer_text", "") or ""
            print(f"[OK]   {slug}: served={served} pass1_chars={len(atext)} "
                  f"classification={getattr(pass2,'classification',None)!r}")
        except Exception as ex:
            print(f"[FAIL] {slug}: served-as={os.environ['PG_MIRROR_MODEL']} "
                  f"{type(ex).__name__}: {str(ex)[:150]}")
        client.close()


if __name__ == "__main__":
    main()
