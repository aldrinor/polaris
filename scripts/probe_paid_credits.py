"""Live credit/quota check for every paid or metered website-access provider.
Real (small) API calls. Authorized 2026-06-08. No commits.
"""
import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

out = {}


def add(name, **kw):
    out[name] = kw


# ---------------- Firecrawl (PAID, .env-disabled but key present) -------------
fc_key = os.getenv("FIRECRAWL_API_KEY")
if not fc_key:
    add("firecrawl", status="no_key", detail="FIRECRAWL_API_KEY missing")
else:
    try:
        r = httpx.get(
            "https://api.firecrawl.dev/v1/team/credit-usage",
            headers={"Authorization": f"Bearer {fc_key}"},
            timeout=20,
        )
        if r.status_code == 200:
            d = r.json().get("data", {})
            add("firecrawl", status="key_valid", http=200,
                remaining_credits=d.get("remaining_credits"),
                plan_credits=d.get("plan_credits"),
                raw=d)
        else:
            add("firecrawl", status=f"http_{r.status_code}", http=r.status_code,
                body=r.text[:300])
    except Exception as e:
        add("firecrawl", status="error", detail=f"{type(e).__name__}: {e}")


# ---------------- Serper (PAID, ACTIVE) --------------------------------------
# No public balance endpoint; validate key + read X-Credits headers / cost field
# from a minimal live search. The response 'credits' field = credits used by
# this call; remaining balance is dashboard-only.
serper_key = os.getenv("SERPER_API_KEY")
if not serper_key:
    add("serper", status="no_key")
else:
    try:
        r = httpx.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
            json={"q": "polaris research probe", "num": 1},
            timeout=20,
        )
        hdrs = {k: v for k, v in r.headers.items()
                if "credit" in k.lower() or "balance" in k.lower()
                or "ratelimit" in k.lower()}
        if r.status_code == 200:
            j = r.json()
            add("serper", status="key_valid", http=200,
                credits_used_this_call=j.get("credits"),
                credit_headers=hdrs or None)
        elif r.status_code in (401, 403):
            add("serper", status="key_invalid", http=r.status_code,
                body=r.text[:200])
        elif r.status_code == 429:
            add("serper", status="exhausted_or_rate_limited", http=429,
                body=r.text[:200])
        else:
            add("serper", status=f"http_{r.status_code}", http=r.status_code,
                body=r.text[:200])
    except Exception as e:
        add("serper", status="error", detail=f"{type(e).__name__}: {e}")


# ---------------- OpenRouter (credits/key limit) -----------------------------
or_key = os.getenv("OPENROUTER_API_KEY")
if not or_key:
    add("openrouter", status="no_key")
else:
    try:
        r = httpx.get(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {or_key}"},
            timeout=20,
        )
        if r.status_code == 200:
            d = r.json().get("data", {})
            limit = d.get("limit")
            usage = d.get("usage")
            remaining = (limit - usage) if (limit is not None and usage is not None) else None
            add("openrouter", status="key_valid", http=200,
                usage=usage, limit=limit, limit_remaining=d.get("limit_remaining"),
                computed_remaining=remaining,
                is_free_tier=d.get("is_free_tier"), raw=d)
        elif r.status_code in (401, 403):
            add("openrouter", status="key_invalid", http=r.status_code,
                body=r.text[:200])
        else:
            add("openrouter", status=f"http_{r.status_code}", http=r.status_code,
                body=r.text[:200])
    except Exception as e:
        add("openrouter", status="error", detail=f"{type(e).__name__}: {e}")


# ---------------- Jina (metered if key) --------------------------------------
jina_key = os.getenv("JINA_API_KEY")
if not jina_key:
    add("jina", status="no_key_free_tier", detail="works keyless at 20 RPM")
else:
    # Jina exposes balance at https://embeddings-dashboard-api.jina.ai or via
    # the r.jina.ai response when authed. Try the token-balance API.
    got = False
    for url in [
        "https://api.jina.ai/v1/rate_limit",
        "https://r.jina.ai/https://example.com",
    ]:
        try:
            r = httpx.get(url, headers={"Authorization": f"Bearer {jina_key}"},
                          timeout=20)
            if r.status_code == 200:
                # r.jina.ai returns content; rate_limit returns json
                hdrs = {k: v for k, v in r.headers.items()
                        if "token" in k.lower() or "balance" in k.lower()
                        or "credit" in k.lower() or "ratelimit" in k.lower()}
                add("jina", status="key_valid", http=200, endpoint=url,
                    balance_headers=hdrs or None,
                    body_head=(r.text[:160] if "rate_limit" in url else "fetch_ok"))
                got = True
                break
            elif r.status_code in (401, 403):
                add("jina", status="key_invalid", http=r.status_code, endpoint=url)
                got = True
                break
        except Exception:
            continue
    if not got:
        add("jina", status="key_present_balance_unknown",
            detail="no public balance endpoint reachable; key did not 401")


# ---------------- Semantic Scholar (rate-limit/key) --------------------------
s2_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
try:
    headers = {"x-api-key": s2_key} if s2_key else {}
    r = httpx.get(
        "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1257/jep.33.2.3"
        "?fields=title",
        headers=headers, timeout=20)
    if r.status_code == 200:
        add("semantic_scholar",
            status=("key_valid" if s2_key else "keyless_ok"),
            http=200, title=r.json().get("title"))
    elif r.status_code in (401, 403):
        add("semantic_scholar", status="key_invalid", http=r.status_code)
    elif r.status_code == 429:
        add("semantic_scholar", status="rate_limited", http=429)
    else:
        add("semantic_scholar", status=f"http_{r.status_code}", http=r.status_code)
except Exception as e:
    add("semantic_scholar", status="error", detail=f"{type(e).__name__}: {e}")


# ---------------- CORE (free registered key; quota) --------------------------
core_key = os.getenv("CORE_API_KEY")
if not core_key:
    add("core", status="no_key")
else:
    try:
        # CORE v3 search; rate-limit info is in X-RateLimit headers.
        r = httpx.post(
            "https://api.core.ac.uk/v3/search/works",
            headers={"Authorization": f"Bearer {core_key}"},
            json={"q": "machine learning", "limit": 1},
            timeout=25,
        )
        hdrs = {k: v for k, v in r.headers.items()
                if "ratelimit" in k.lower() or "retry" in k.lower()}
        if r.status_code == 200:
            j = r.json()
            add("core", status="key_valid", http=200,
                total_hits=j.get("totalHits"),
                ratelimit_headers=hdrs or None)
        elif r.status_code in (401, 403):
            add("core", status="key_invalid", http=r.status_code, body=r.text[:200])
        elif r.status_code == 429:
            add("core", status="rate_limited_exhausted", http=429,
                ratelimit_headers=hdrs or None, body=r.text[:200])
        else:
            add("core", status=f"http_{r.status_code}", http=r.status_code,
                body=r.text[:200])
    except Exception as e:
        add("core", status="error", detail=f"{type(e).__name__}: {e}")


print(json.dumps(out, indent=2))
with open(os.path.join("outputs", "probe_paid_credits_result.json"),
          "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
print("\nWROTE outputs/probe_paid_credits_result.json")
