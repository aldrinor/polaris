"""One-off diagnostic: live-test every website-access / content-fetch backend
in src/tools/access_bypass.py + the legal-OA resolvers (Unpaywall, CORE).

Makes REAL (small) network calls. Authorized per operator task 2026-06-08.
Writes NO commits. Cleans only its own child PIDs.
"""
import asyncio
import json
import os
import sys
import time
import traceback

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from src.tools.access_bypass import AccessBypass  # noqa: E402
from src.tools import core_client  # noqa: E402

MIN_CHARS = 100


def _summ(content):
    if content is None:
        return 0
    return len(content)


async def probe_per_backend():
    """Invoke each fetch backend method DIRECTLY for clean attribution."""
    ab = AccessBypass()
    results = {}

    # ---- HARD test URLs ----
    # control: easy static page
    control = "https://example.com/"
    # JS-only / dynamic page (renders client-side)
    js_only = "https://quotes.toscrape.com/js/"
    # Cloudflare / anti-bot protected
    cloudflare = "https://www.g2.com/products/notion/reviews"
    # Paywalled journal (NEJM landing)
    paywall = "https://www.nejm.org/doi/full/10.1056/NEJMoa2032183"
    # A PDF (arXiv OA)
    pdf_url = "https://arxiv.org/pdf/1706.03762"

    urls = {
        "control_example": control,
        "js_only_quotes": js_only,
        "cloudflare_g2": cloudflare,
        "paywall_nejm": paywall,
        "pdf_arxiv": pdf_url,
    }

    # ---------- crawl4ai ----------
    for label, url in [("control_example", control), ("js_only_quotes", js_only),
                       ("cloudflare_g2", cloudflare)]:
        key = f"crawl4ai::{label}"
        t0 = time.time()
        try:
            r = await ab._try_crawl4ai(url)
            n = _summ(r.content if r else None)
            results[key] = {
                "fired": r is not None,
                "chars": n,
                "produced": n >= MIN_CHARS,
                "method": getattr(r, "access_method", None) if r else None,
                "success_flag": getattr(r, "success", None) if r else None,
                "elapsed_s": round(time.time() - t0, 1),
                "error": None if (r and n >= MIN_CHARS) else (
                    (getattr(r, "metadata", {}) or {}).get("error")
                    or "below_min_or_none" if r else "returned_none"),
            }
        except Exception as e:
            results[key] = {"fired": False, "chars": 0, "produced": False,
                            "elapsed_s": round(time.time() - t0, 1),
                            "error": f"{type(e).__name__}: {e}"}

    # ---------- jina_reader ----------
    for label, url in [("js_only_quotes", js_only), ("cloudflare_g2", cloudflare),
                       ("paywall_nejm", paywall)]:
        key = f"jina_reader::{label}"
        t0 = time.time()
        try:
            r = await ab._try_jina_reader(url)
            n = _summ(r.content if r else None)
            results[key] = {
                "fired": r is not None,
                "chars": n,
                "produced": n >= MIN_CHARS,
                "method": getattr(r, "access_method", None) if r else None,
                "success_flag": getattr(r, "success", None) if r else None,
                "elapsed_s": round(time.time() - t0, 1),
                "error": None if (r and n >= MIN_CHARS) else (
                    (getattr(r, "metadata", {}) or {}).get("error")
                    or ("below_min" if r else "returned_none")),
            }
        except Exception as e:
            results[key] = {"fired": False, "chars": 0, "produced": False,
                            "elapsed_s": round(time.time() - t0, 1),
                            "error": f"{type(e).__name__}: {e}"}

    # ---------- firecrawl (paid, .env-disabled -> test the METHOD directly) ----------
    key = "firecrawl::cloudflare_g2"
    t0 = time.time()
    try:
        r = await ab._try_firecrawl(cloudflare)
        n = _summ(r.content if r else None)
        results[key] = {
            "fired": r is not None,
            "chars": n,
            "produced": n >= MIN_CHARS,
            "method": getattr(r, "access_method", None) if r else None,
            "success_flag": getattr(r, "success", None) if r else None,
            "elapsed_s": round(time.time() - t0, 1),
            "error": None if (r and n >= MIN_CHARS) else (
                (getattr(r, "metadata", {}) or {}).get("error")
                or ("below_min" if r else "returned_none")),
        }
    except Exception as e:
        results[key] = {"fired": False, "chars": 0, "produced": False,
                        "elapsed_s": round(time.time() - t0, 1),
                        "error": f"{type(e).__name__}: {e}"}

    # ---------- trafilatura ----------
    for label, url in [("control_example", control), ("paywall_nejm", paywall)]:
        key = f"trafilatura::{label}"
        t0 = time.time()
        try:
            r = await ab._try_trafilatura(url)
            n = _summ(r.content if r else None)
            results[key] = {
                "fired": r is not None,
                "chars": n,
                "produced": n >= MIN_CHARS,
                "method": getattr(r, "access_method", None) if r else None,
                "elapsed_s": round(time.time() - t0, 1),
                "error": None if (r and n >= MIN_CHARS) else (
                    "below_min" if r else "returned_none"),
            }
        except Exception as e:
            results[key] = {"fired": False, "chars": 0, "produced": False,
                            "elapsed_s": round(time.time() - t0, 1),
                            "error": f"{type(e).__name__}: {e}"}

    # ---------- direct httpx/aiohttp ----------
    for label, url in [("control_example", control), ("cloudflare_g2", cloudflare)]:
        key = f"direct::{label}"
        t0 = time.time()
        try:
            r = await ab._direct_fetch(url)
            n = _summ(r.content if r else None)
            results[key] = {
                "fired": r is not None,
                "chars": n,
                "produced": n >= MIN_CHARS,
                "method": getattr(r, "access_method", None) if r else None,
                "success_flag": getattr(r, "success", None) if r else None,
                "elapsed_s": round(time.time() - t0, 1),
                "error": None if (r and n >= MIN_CHARS) else (
                    (getattr(r, "metadata", {}) or {}).get("error")
                    or ("below_min" if r else "returned_none")),
            }
        except Exception as e:
            results[key] = {"fired": False, "chars": 0, "produced": False,
                            "elapsed_s": round(time.time() - t0, 1),
                            "error": f"{type(e).__name__}: {e}"}

    # ---------- archive.org ----------
    key = "archive_org::nytimes_old"
    t0 = time.time()
    try:
        r = await ab._try_archive_org("https://www.nytimes.com/2020/01/01/science/")
        n = _summ(r.content if r else None)
        results[key] = {
            "fired": r is not None,
            "chars": n,
            "produced": n >= MIN_CHARS,
            "method": getattr(r, "access_method", None) if r else None,
            "elapsed_s": round(time.time() - t0, 1),
            "error": None if (r and n >= MIN_CHARS) else (
                (getattr(r, "metadata", {}) or {}).get("error")
                or ("below_min" if r else "returned_none")),
        }
    except Exception as e:
        results[key] = {"fired": False, "chars": 0, "produced": False,
                        "elapsed_s": round(time.time() - t0, 1),
                        "error": f"{type(e).__name__}: {e}"}

    # ---------- PDF cracker (docling/PyMuPDF) ----------
    key = "pdf_cracker::arxiv"
    t0 = time.time()
    try:
        txt = await ab._extract_pdf_text(pdf_url)
        n = _summ(txt)
        results[key] = {
            "fired": txt is not None,
            "chars": n,
            "produced": n >= MIN_CHARS,
            "elapsed_s": round(time.time() - t0, 1),
            "error": None if n >= MIN_CHARS else "below_min_or_empty",
        }
    except Exception as e:
        results[key] = {"fired": False, "chars": 0, "produced": False,
                        "elapsed_s": round(time.time() - t0, 1),
                        "error": f"{type(e).__name__}: {e}"}

    # ---------- pmc_bioc full text ----------
    key = "pmc_bioc::PMC7382107"
    t0 = time.time()
    try:
        txt = await ab._try_pmc_bioc_fulltext("PMC7382107")
        n = _summ(txt)
        results[key] = {
            "fired": txt is not None,
            "chars": n,
            "produced": n >= MIN_CHARS,
            "elapsed_s": round(time.time() - t0, 1),
            "error": None if (txt and n >= MIN_CHARS) else (
                "below_min" if txt else "returned_none"),
        }
    except Exception as e:
        results[key] = {"fired": False, "chars": 0, "produced": False,
                        "elapsed_s": round(time.time() - t0, 1),
                        "error": f"{type(e).__name__}: {e}"}

    return results, urls


async def probe_oa_resolvers():
    ab = AccessBypass()
    out = {}
    # Known OA DOI: "Attention Is All You Need" is not a DOI; use a known OA journal DOI.
    # JEP open-access article (American Economic Assoc, OA) + a PMC-backed clinical DOI.
    oa_dois = {
        "jep_oa": "10.1257/jep.33.2.3",
        "plos_oa": "10.1371/journal.pmed.1003583",
    }

    # ----- Unpaywall (path 1: _try_unpaywall) -----
    for label, doi in oa_dois.items():
        key = f"unpaywall::{label}"
        t0 = time.time()
        try:
            url = await ab._try_unpaywall(doi)
            out[key] = {
                "fired": True,
                "oa_url": url,
                "produced": bool(url),
                "elapsed_s": round(time.time() - t0, 1),
                "error": None if url else "no_oa_url_returned",
            }
        except Exception as e:
            out[key] = {"fired": False, "produced": False,
                        "elapsed_s": round(time.time() - t0, 1),
                        "error": f"{type(e).__name__}: {e}"}

    # ----- CORE -----
    core_tests = {
        "jep_oa": ("10.1257/jep.33.2.3",
                   "Artificial Intelligence, Automation, and Work"),
        "plos_oa": ("10.1371/journal.pmed.1003583", None),
    }
    for label, (doi, title) in core_tests.items():
        key = f"core::{label}"
        t0 = time.time()
        try:
            content, src = core_client.fetch_core_oa_fulltext(
                doi, expected_title=title)
            n = _summ(content)
            out[key] = {
                "fired": True,
                "chars": n,
                "source_url": src,
                "produced": n >= MIN_CHARS,
                "elapsed_s": round(time.time() - t0, 1),
                "error": None if n >= MIN_CHARS else "empty_or_below_min",
            }
        except Exception as e:
            out[key] = {"fired": False, "chars": 0, "produced": False,
                        "elapsed_s": round(time.time() - t0, 1),
                        "error": f"{type(e).__name__}: {e}"}

    return out


async def probe_full_cascade():
    """Run the REAL fetch_with_bypass on a few hard URLs; report winning method."""
    ab = AccessBypass()
    out = {}
    urls = {
        "control_example": "https://example.com/",
        "js_only_quotes": "https://quotes.toscrape.com/js/",
        "cloudflare_g2": "https://www.g2.com/products/notion/reviews",
        "paywall_nejm_doi": "https://www.nejm.org/doi/full/10.1056/NEJMoa2032183",
    }
    for label, url in urls.items():
        t0 = time.time()
        try:
            r = await ab.fetch_with_bypass(url)
            n = _summ(r.content if r else None)
            out[label] = {
                "winning_method": getattr(r, "access_method", None) if r else None,
                "chars": n,
                "produced": n >= MIN_CHARS,
                "success_flag": getattr(r, "success", None) if r else None,
                "elapsed_s": round(time.time() - t0, 1),
            }
        except Exception as e:
            out[label] = {"winning_method": None, "chars": 0, "produced": False,
                          "elapsed_s": round(time.time() - t0, 1),
                          "error": f"{type(e).__name__}: {e}"}
    return out


async def main():
    print("=== PER-BACKEND DIRECT PROBE ===", flush=True)
    per, urls = await probe_per_backend()
    print(json.dumps(per, indent=2), flush=True)

    print("\n=== OA RESOLVERS (Unpaywall + CORE) ===", flush=True)
    oa = await probe_oa_resolvers()
    print(json.dumps(oa, indent=2), flush=True)

    print("\n=== FULL CASCADE (which backend wins) ===", flush=True)
    casc = await probe_full_cascade()
    print(json.dumps(casc, indent=2), flush=True)

    all_out = {"per_backend": per, "oa_resolvers": oa, "full_cascade": casc,
               "test_urls": urls}
    with open(os.path.join("outputs", "probe_website_access_tools_result.json"),
              "w", encoding="utf-8") as f:
        json.dump(all_out, f, indent=2)
    print("\nWROTE outputs/probe_website_access_tools_result.json", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
