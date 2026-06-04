#!/usr/bin/env python3
"""DEFINITIVE model-vs-config test (I-run11-005): reproduce the EXACT production Mirror config that
blanked in runs 14/15 — reasoning ON (the _ROLE_REASONING_DEFAULT mirror=True default, which
run_gate_b.py does NOT override) + PG_VERIFIER_REASONING_MAX_TOKENS=16384 (default) + a realistic
multi-document payload. My earlier bakeoff/pre-merge tests all ran reasoning-OFF at 4000 tokens — a
DIFFERENT config — so they never exercised what actually failed.

Captures raw_text + reasoning length + blank status, for GLM-5.1 and nemotron, reasoning ON. If GLM
blanks here (adequate 16k budget) while nemotron emits, the blank is GLM's reasoning-first exhaustion
(model). If GLM also emits, the production blank had another (seam/transient) cause. Honest either way.

Reads OPENROUTER_API_KEY from env/.env (never printed). Run from repo root. ~4-6 live calls.
"""
from __future__ import annotations
import os, sys, json

# PRODUCTION config: do NOT set PG_MIRROR_REASONING (defaults to True for mirror) and do NOT lower
# the reasoning token budget (defaults to 16384) — exactly what run_gate_b.py uses.
os.environ.pop("PG_MIRROR_REASONING", None)
os.environ.pop("PG_SENTINEL_MAX_TOKENS", None)
os.environ.setdefault("PG_FOUR_ROLE_TRANSPORT", "openrouter")
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
from src.polaris_graph.roles.openrouter_role_transport import (  # noqa: E402
    OpenRouterRoleTransport, role_reasoning_enabled,
)
from src.polaris_graph.roles.mirror_adapter import build_mirror_pass1_request  # noqa: E402
from src.polaris_graph.roles.role_transport import EvidenceDocument  # noqa: E402

CLAIM = ("Automation has historically displaced workers from specific tasks while complementary "
         "forces and new task creation kept aggregate labor demand from collapsing.")


def realistic_docs():
    e = json.load(open("outputs/audits/I-run11-004/m25_bakeoff/evidence_pool.json", encoding="utf-8"))
    # a realistic seam payload: several FULL evidence docs (not truncated to 2000), like production
    docs = []
    for x in e:
        q = x.get("direct_quote") or ""
        if len(q) > 200 and x.get("evidence_id"):
            docs.append(EvidenceDocument(doc_id=x["evidence_id"], text=q))
        if len(docs) >= 5:
            break
    return docs


def run_one(slug: str, docs):
    os.environ["PG_MIRROR_MODEL"] = slug
    reasoning = role_reasoning_enabled("mirror", slug)  # confirm production default
    req = build_mirror_pass1_request(CLAIM, docs, model_slug=slug)
    transport = OpenRouterRoleTransport(httpx.Client(timeout=300.0))
    try:
        resp = transport.complete(req)
        raw = resp.raw_text or ""
        reasoning_txt = getattr(resp, "reasoning", None) or ""
        print(f"[{slug}] reasoning_enabled={reasoning} served={resp.served_model}")
        print(f"    content_len={len(raw)} reasoning_len={len(reasoning_txt)} "
              f"has_<co>={'<co' in raw} blank={len(raw.strip()) == 0}")
        print(f"    raw_text[:300]={raw[:300]!r}")
    except Exception as ex:  # noqa: BLE001 — diagnostic: surface the failure verbatim
        print(f"[{slug}] reasoning_enabled={reasoning} EXC {type(ex).__name__}: {str(ex)[:180]}")


def main():
    docs = realistic_docs()
    total = sum(len(d.text) for d in docs)
    print(f"payload: {len(docs)} full docs, {total} chars (realistic seam size)\n")
    for slug in ["z-ai/glm-5.1", "nvidia/nemotron-3-super-120b-a12b"]:
        run_one(slug, docs)
        print()


if __name__ == "__main__":
    main()
