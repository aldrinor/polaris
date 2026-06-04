#!/usr/bin/env python3
"""I-run11-005 PHASE-4 reproduction: does GLM-5.1 Mirror blank at MAX reasoning on HARD claims, and
does a bigger token budget fix it? Hypothesis (from mirror_production_config_test: GLM used 12210 of
16384 reasoning tokens on a SIMPLE claim): on a HARD multi-part claim, xhigh reasoning consumes the
whole budget → no room for the verdict → BlankVerdictError. If true, the runs-14/15/16 blanks are
token-budget starvation (a config/seam fix: raise PG_VERIFIER_REASONING_MAX_TOKENS), NOT the model.

Goes through the REAL complete() path (incl. the blank-recovery ladder), so the captured result is
the END state the seam would see. Sweeps the budget per claim. Reads OPENROUTER_API_KEY from .env
(never printed). Run from repo root. ~8 live calls.
"""
from __future__ import annotations
import os, sys, json

os.environ.pop("PG_MIRROR_REASONING", None)   # production default: reasoning ON for mirror
os.environ["PG_MIRROR_MODEL"] = "z-ai/glm-5.1"
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
from src.polaris_graph.roles.openrouter_role_transport import OpenRouterRoleTransport  # noqa: E402
from src.polaris_graph.roles.mirror_adapter import build_mirror_pass1_request  # noqa: E402
from src.polaris_graph.roles.role_transport import EvidenceDocument  # noqa: E402

# a SIMPLE control + HARD multi-part claims (force lots of grounding reasoning across many docs)
CLAIMS = {
    "simple": "Automation can displace workers from specific tasks.",
    "hard_multipart": (
        "Across these studies automation simultaneously displaced workers from routine tasks, "
        "depressed relative wages for the middle of the skill distribution, complemented high-skill "
        "labor, and—alongside generative-AI assistance that raised customer-support productivity "
        "by about 15% concentrated among less-experienced agents—netted out to no collapse in "
        "aggregate labor demand over the period studied."
    ),
    "hard_numeric": (
        "Industrial-robot adoption reduced both employment and wages in local US labor markets, with "
        "each additional robot per thousand workers lowering the employment-to-population ratio and "
        "average wages by a quantified amount, even after accounting for complementary task creation."
    ),
}


def docs():
    e = json.load(open("outputs/audits/I-run11-004/m25_bakeoff/evidence_pool.json", encoding="utf-8"))
    out = []
    for x in e:
        q = x.get("direct_quote") or ""
        if len(q) > 200 and x.get("evidence_id"):
            out.append(EvidenceDocument(doc_id=x["evidence_id"], text=q))
        if len(out) >= 5:
            break
    return out


def run(claim_label: str, claim: str, budget: int, ev):
    os.environ["PG_VERIFIER_REASONING_MAX_TOKENS"] = str(budget)
    req = build_mirror_pass1_request(claim, ev, model_slug="z-ai/glm-5.1")
    transport = OpenRouterRoleTransport(httpx.Client(timeout=300.0))
    try:
        resp = transport.complete(req)
        raw = resp.raw_text or ""
        rlen = len(getattr(resp, "reasoning", None) or "")
        print(f"  [{claim_label} @ budget={budget}] content={len(raw)} reasoning={rlen} "
              f"has_<co>={'<co' in raw} blank={len(raw.strip()) == 0}")
    except Exception as ex:  # noqa: BLE001 — diagnostic
        print(f"  [{claim_label} @ budget={budget}] {type(ex).__name__}: {str(ex)[:120]}")


def main():
    ev = docs()
    print(f"payload {len(ev)} docs; GLM-5.1 reasoning ON (xhigh); sweeping budget\n")
    for label, claim in CLAIMS.items():
        for budget in (16384, 40000):
            run(label, claim, budget, ev)
        print()


if __name__ == "__main__":
    main()
