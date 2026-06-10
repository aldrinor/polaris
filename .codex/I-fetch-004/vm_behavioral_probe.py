"""I-fetch-004 (#1185) VM behavioral probe — real Zyte, ~cents.

Run ON the VM with the polaris-beatboth venv (aiohttp + trafilatura present).
ZYTE_API_KEY is read from ~/polaris_run/.env (the keyed env).

Two legs:
  A. free_chain_unaffected (ZERO spend, run first): key UNSET, a tracer wraps
     _try_zyte; fetch a plainly-fetchable URL via fetch_with_bypass; the tracer
     must NEVER fire and the result must succeed via a FREE method.
  B. zyte_recovered (real spend): key SET; call _try_zyte DIRECTLY on a
     free+bot-blocked demonstrator URL (the case Zyte exists to win) and on the
     real failing DOI. zyte_recovered is TRUE iff at least one returns usable
     non-empty content. Paywall-rejection (error=unusable_content/paywall) is
     the feature working correctly, NOT a recovery.
"""

import asyncio
import json
import os
import sys

# ---- load ZYTE_API_KEY from the keyed env file -------------------------------
_KEY = None
_ENV_PATH = os.path.expanduser("~/polaris_run/.env")
with open(_ENV_PATH, "r", encoding="utf-8", errors="replace") as fh:
    for line in fh:
        line = line.strip()
        if line.startswith("ZYTE_API_KEY="):
            _KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

if not _KEY:
    print(json.dumps({"fatal": "ZYTE_API_KEY not found in ~/polaris_run/.env"}))
    sys.exit(2)

import src.tools.access_bypass as ab  # noqa: E402
from src.tools.access_bypass import AccessBypass  # noqa: E402


# A plainly-fetchable, free, NON-bot-blocked URL for the free-chain leg.
_FREE_URL = "https://en.wikipedia.org/wiki/Tirzepatide"

# Demonstrator for Zyte recovery: free scholarly content that is frequently
# bot-blocked to naive clients but NOT paywalled (JS / anti-bot, browserHtml-
# recoverable). dx.doi.org redirect + a known bot-blocked open host.
_BOT_BLOCKED_DEMOS = [
    # ESC abstract supplement — the real failing URL from the run.
    "http://dx.doi.org/10.1093/eurheartj/ehad655.2803",
    # A free, JS/anti-bot host that naive fetchers commonly get blocked on.
    "https://www.semanticscholar.org/paper/Tirzepatide",
    # PMC open-access full text (free, but cloudfronted/bot-sensitive).
    "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9925098/",
]


async def leg_a_free_chain_unaffected():
    """Key UNSET. Tracer on _try_zyte must never fire; free method must win."""
    os.environ.pop("ZYTE_API_KEY", None)

    fired = {"zyte": False}
    orig = AccessBypass._try_zyte

    async def _tracer(self, url):
        fired["zyte"] = True
        return await orig(self, url)

    AccessBypass._try_zyte = _tracer
    try:
        bypass = AccessBypass(use_archive_org=False, institutional_proxy=None)
        result = await bypass.fetch_with_bypass(_FREE_URL)
    finally:
        AccessBypass._try_zyte = orig

    return {
        "url": _FREE_URL,
        "zyte_invoked": fired["zyte"],
        "success": bool(result.success),
        "access_method": result.access_method,
        "content_len": len(result.content or ""),
    }


async def leg_b_zyte_recovered():
    """Key SET. Direct _try_zyte on bot-blocked demonstrators (real spend)."""
    os.environ["ZYTE_API_KEY"] = _KEY
    bypass = AccessBypass(use_archive_org=False, institutional_proxy=None)

    attempts = []
    recovered = False
    for url in _BOT_BLOCKED_DEMOS:
        try:
            res = await bypass._try_zyte(url)
            rec = {
                "url": url,
                "success": bool(res.success),
                "access_method": res.access_method,
                "content_len": len(res.content or ""),
                "metadata": res.metadata,
            }
            attempts.append(rec)
            if res.success and (res.content or ""):
                recovered = True
                break  # one genuine recovery is enough; stop spending
        except Exception as e:  # never crash the probe
            attempts.append({"url": url, "exception": repr(e)[:300]})
    return {"recovered": recovered, "attempts": attempts}


async def main():
    leg_a = await leg_a_free_chain_unaffected()
    leg_b = await leg_b_zyte_recovered()

    free_chain_unaffected = (
        leg_a["zyte_invoked"] is False
        and leg_a["success"] is True
        and leg_a["access_method"] != "zyte"
    )
    zyte_recovered = leg_b["recovered"] is True

    out = {
        "zyte_recovered": zyte_recovered,
        "free_chain_unaffected": free_chain_unaffected,
        "leg_a_free_chain": leg_a,
        "leg_b_zyte": leg_b,
    }
    print("PROBE_JSON_START")
    print(json.dumps(out, indent=2))
    print("PROBE_JSON_END")


if __name__ == "__main__":
    asyncio.run(main())
