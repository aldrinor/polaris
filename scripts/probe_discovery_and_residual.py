"""Enumeration-completion probe: discovery backends + pubmed efetch + the
trafilatura WRAPPER (not just the lib) + archive.org re-confirm.
Real small network calls. Authorized 2026-06-08. No commits.
"""
import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from src.polaris_graph.retrieval import domain_backends as db  # noqa: E402
from src.polaris_graph.retrieval import live_retriever as lr  # noqa: E402
from src.tools.access_bypass import AccessBypass  # noqa: E402

out = {}


def add(name, **kw):
    out[name] = kw


# ---------------- DISCOVERY backends (free) ----------------------------------
def run_search(name, fn, query):
    try:
        cands = fn(query)
        n = len(cands) if cands else 0
        sample = None
        if n:
            c = cands[0]
            sample = {"title": (getattr(c, "title", "") or "")[:70],
                      "url": (getattr(c, "url", "") or "")[:90],
                      "source": getattr(c, "source", None)}
        add(name, fired=True, candidates=n, produced=n > 0,
            sample=sample, error=None if n else "zero_candidates")
    except Exception as e:
        add(name, fired=False, candidates=0, produced=False,
            error=f"{type(e).__name__}: {e}")


run_search("openalex_search", db.openalex_search, "tirzepatide cardiovascular outcomes")
run_search("europe_pmc_search", db.europe_pmc_search, "tirzepatide cardiovascular outcomes")
run_search("arxiv_search", db.arxiv_search, "attention transformer architecture")
run_search("sec_edgar_search", db.sec_edgar_search, "Apple Inc 10-K annual report")
run_search("github_search_repos", db.github_search_repos, "retrieval augmented generation")

# Serper discovery (PAID) via domain_backends site-scoped wrapper
try:
    cands = db.policy_targeted_serper("GLP-1 receptor agonist guideline", limit=3)
    n = len(cands) if cands else 0
    add("serper_discovery", fired=True, candidates=n, produced=n > 0,
        sample=({"url": (cands[0].url or "")[:90]} if n else None),
        error=None if n else "zero_candidates")
except Exception as e:
    add("serper_discovery", fired=False, candidates=0, produced=False,
        error=f"{type(e).__name__}: {e}")


# ---------------- pubmed efetch abstract (free) ------------------------------
try:
    # PMID 32678530 = a real PubMed record
    abstract = lr._pubmed_fetch_abstract("32678530")
    n = len(abstract) if abstract else 0
    add("pubmed_efetch", fired=True, chars=n, produced=n >= 100,
        head=(abstract[:120] if abstract else None),
        error=None if n >= 100 else "empty_or_below_min")
except Exception as e:
    add("pubmed_efetch", fired=False, chars=0, produced=False,
        error=f"{type(e).__name__}: {e}")


# ---------------- trafilatura WRAPPER on an easy article ---------------------
async def traf_and_archive():
    ab = AccessBypass()
    wiki = "https://en.wikipedia.org/wiki/Tirzepatide"
    r = await ab._try_trafilatura(wiki)
    n = (len(r.content) if (r and r.content) else 0)
    add("trafilatura_wrapper", fired=r is not None, chars=n, produced=n >= 100,
        method=(getattr(r, "access_method", None) if r else None),
        error=None if (r and n >= 100) else ("returned_none" if r is None else "below_min"))

    # archive.org re-confirm on a URL Wayback definitely has snapshots for
    r2 = await ab._try_archive_org("https://www.bbc.com/news")
    n2 = (len(r2.content) if (r2 and r2.content) else 0)
    add("archive_org_reconfirm", fired=r2 is not None, chars=n2, produced=n2 >= 100,
        method=(getattr(r2, "access_method", None) if r2 else None),
        error=None if (r2 and n2 >= 100) else ((r2.metadata or {}).get("error") if r2 else "returned_none"))


asyncio.run(traf_and_archive())


# ---------------- non-firing-by-design rows (report explicitly) --------------
add("scihub", fired=False, produced=False,
    status="disabled_by_design",
    detail="PG_SCIHUB_ENABLED default 0 (not in .env) + hard-rejected downstream in "
           "frame_fetcher._fetch_url_pattern. NOT fired on purpose.")
add("institutional_proxy", fired=False, produced=False,
    status="not_configured",
    detail="AccessBypass() constructed with no institutional_proxy in production; "
           "self.proxy is None so _try_proxy is skipped. NOT fired on purpose.")
add("unpaywall_path2_live_resolver", fired=False, produced=None,
    status="enabled_shares_proven_v2_api",
    detail="live_retriever._unpaywall_get_oa_urls gates on PG_ENABLE_LIVE_OA_RESOLVER "
           "(code default '1', not overridden in .env => ON) + PG_UNPAYWALL_EMAIL "
           "(set in .env). Shares the Unpaywall v2 API + parser proven working in path 1. "
           "Not separately fired; env-confirmed enabled.")
add("unpaywall_path3_frame_fetcher", fired=False, produced=None,
    status="enabled_shares_proven_v2_api",
    detail="frame_fetcher._call_unpaywall shares the same Unpaywall v2 endpoint + "
           "_parse_unpaywall_response parser proven in path 1. Reached whenever a DOI "
           "is present in the frame path. Env-confirmed enabled (PG_UNPAYWALL_EMAIL set).")

print(json.dumps(out, indent=2))
with open(os.path.join("outputs", "probe_discovery_residual_result.json"),
          "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
print("\nWROTE outputs/probe_discovery_residual_result.json")
