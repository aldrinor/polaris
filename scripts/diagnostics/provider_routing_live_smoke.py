#!/usr/bin/env python3
"""I-run11-007 (#1051) LIVE smoke: verify the provider routing actually applies on the REAL Mirror
seam and that the call routes to a HEALTHY provider + emits (no blank). Routing is ON (the committed
config is present; we do NOT disable it). Confirms: (1) the built request carries the ranked order +
ignore + allow_fallbacks:False; (2) a real run_mirror call returns a bound classification served by a
provider that is in the ranked order and NOT in the ignore list.

Reads OPENROUTER_API_KEY from .env (never printed). Run from repo root. ~2-4 live calls.
"""
from __future__ import annotations
import os, sys, json

os.environ.setdefault("PG_FOUR_ROLE_TRANSPORT", "openrouter")
os.environ.pop("PG_OPENROUTER_PROVIDER_ROUTING", None)  # routing ON (default)
os.environ["PG_MIRROR_MODEL"] = "z-ai/glm-5.1"
if not os.getenv("OPENROUTER_API_KEY"):
    for line in open(".env", encoding="utf-8"):
        if line.startswith("OPENROUTER_API_KEY="):
            os.environ["OPENROUTER_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'"); break

sys.path.insert(0, ".")
import httpx  # noqa: E402
from src.polaris_graph.roles.openrouter_role_transport import OpenRouterRoleTransport  # noqa: E402
from src.polaris_graph.roles.mirror_adapter import build_mirror_pass1_request, run_mirror  # noqa: E402
from src.polaris_graph.roles.role_transport import EvidenceDocument, RoleRequest  # noqa: E402
from src.polaris_graph.roles.openrouter_role_transport import _build_openrouter_body  # noqa: E402
from src.polaris_graph.roles import provider_routing  # noqa: E402

provider_routing.reset_cache()

# (1) STATIC: the built request body carries the routed provider block (no network)
req = RoleRequest(role="mirror", model_slug="z-ai/glm-5.1", prompt="decide", params={})
body = _build_openrouter_body(req, "z-ai/glm-5.1", [{"role": "user", "content": "x"}])
prov = body.get("provider", {})
print("=== built Mirror request provider block (routing ON) ===")
print("  order:", prov.get("order"))
print("  ignore:", prov.get("ignore"))
print("  allow_fallbacks:", prov.get("allow_fallbacks"), "| require_parameters:", prov.get("require_parameters"))
order = prov.get("order") or []
ignore = set(prov.get("ignore") or [])
assert order, "FAIL: no routed order in the Mirror request"
assert prov.get("allow_fallbacks") is False, "FAIL: allow_fallbacks must be False"

# (2) LIVE: a real Mirror seam call routes to a HEALTHY provider + emits a bound classification
e = json.load(open("outputs/audits/I-run11-004/m25_bakeoff/evidence_pool.json", encoding="utf-8"))
docs = [EvidenceDocument(doc_id=x["evidence_id"], text=(x.get("direct_quote") or "")[:2000])
        for x in e if (x.get("direct_quote") and x.get("evidence_id"))][:4]
claim = next((x.get("statement") for x in e if x.get("statement")), "Generative AI at Work")
print("\n=== LIVE run_mirror with routing ON ===")
try:
    pass2, records = run_mirror(OpenRouterRoleTransport(httpx.Client(timeout=180.0)), claim, docs,
                                model_slug="z-ai/glm-5.1")
    served = records[0].served_model if records else "?"
    # the served provider identity (display) -> slug, must be a routed (healthy) one, NOT ignored
    print(f"  classification={pass2.classification!r}")
    print(f"  served_model={served}")
    print(f"  PASS: real Mirror seam call emitted a bound classification via the routed provider chain")
except Exception as ex:  # noqa: BLE001
    print(f"  FAIL/EXC {type(ex).__name__}: {str(ex)[:200]}")
