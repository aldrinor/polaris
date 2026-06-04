#!/usr/bin/env python3
"""I-run11-008 (#1053) BAKE-OFF: does reasoning-OFF kill the Mirror's JUDGMENT, or just the blanks?
Operator pushback: setting reasoning=false might make the grounding verifier dumber (false-bind
fabrications). So test reasoning OFF vs reasoning ON on BOTH grounded + ungrounded claims, measuring:
  - blank_count  (want 0)
  - grounded_bind  (bound on GROUNDED claims — higher better, the verifier recognizes real support)
  - false_bind     (bound on UNGROUNDED claims — LOWER better, the §-1.1 lethal direction)
Evidence picks the config: the one with 0 blanks AND low false_bind AND high grounded_bind.

Reads OPENROUTER_API_KEY from .env (never printed). Run from repo root. ~20 live calls.
"""
from __future__ import annotations
import os, sys, json

os.environ.setdefault("PG_FOUR_ROLE_TRANSPORT", "openrouter")
os.environ["PG_MIRROR_MODEL"] = "z-ai/glm-5.1"
os.environ.setdefault("PG_MIRROR_MAX_TOKENS", "6000")
if not os.getenv("OPENROUTER_API_KEY"):
    for line in open(".env", encoding="utf-8"):
        if line.startswith("OPENROUTER_API_KEY="):
            os.environ["OPENROUTER_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'"); break

sys.path.insert(0, ".")
import httpx  # noqa: E402
from src.polaris_graph.roles.openrouter_role_transport import OpenRouterRoleTransport  # noqa: E402
from src.polaris_graph.roles.mirror_adapter import (  # noqa: E402
    run_mirror, MirrorCitationError, MirrorBindingError,
)
from src.polaris_graph.roles.role_transport import EvidenceDocument  # noqa: E402
from src.polaris_graph.roles.openai_compatible_transport import BlankVerdictError  # noqa: E402

ds = json.load(open("outputs/audits/I-run11-005/mirror_labeled_set.json", encoding="utf-8"))
G = ds["grounded"][:5]
U = ds["ungrounded"][:5]


def one(p):
    docs = [EvidenceDocument(doc_id=p["doc_id"], text=p["doc_text"])]
    try:
        run_mirror(OpenRouterRoleTransport(httpx.Client(timeout=180.0)), p["claim"], docs,
                   model_slug="z-ai/glm-5.1")
        return "BOUND"
    except BlankVerdictError:
        return "BLANK"
    except MirrorCitationError:
        return "REFUSED"
    except (MirrorBindingError, Exception):  # noqa: BLE001
        return "ERR"


def run_config(label, reasoning_on):
    os.environ["PG_MIRROR_REASONING"] = "true" if reasoning_on else "false"
    from src.polaris_graph.roles import provider_routing as pr
    pr.reset_cache()
    gres = [one(p) for p in G]
    ures = [one(p) for p in U]
    blank = gres.count("BLANK") + ures.count("BLANK")
    grounded_bind = gres.count("BOUND")
    false_bind = ures.count("BOUND")
    print(f"[{label}] reasoning={'ON' if reasoning_on else 'OFF'}  "
          f"BLANK={blank}  grounded_bind={grounded_bind}/{len(G)}  false_bind={false_bind}/{len(U)}")
    print(f"    grounded: {gres}")
    print(f"    ungrounded: {ures}")
    return {"blank": blank, "grounded_bind": grounded_bind, "false_bind": false_bind}


print("=== Mirror reasoning bake-off (GLM-5.1) ===")
off = run_config("OFF ", reasoning_on=False)
on = run_config("ON  ", reasoning_on=True)
print("\nPICK: reasoning-OFF is safe iff blank=0 AND false_bind <= ON's AND grounded_bind >= ON's.")
print(f"  OFF: {off}\n  ON : {on}")
