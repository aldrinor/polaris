#!/usr/bin/env python3
"""Pre-merge gate (I-run11-005): isolate WHY nemotron + glm-5.1 both blanked on the brynjolfsson
grounded pair. The artifact is a legitimate U+2013 EN DASH ("generative AI-based"), NOT corruption.

A/B test: run the REAL 2-pass Mirror (run_mirror) for each model on the brynjolfsson pair, RAW vs
UNICODE-NORMALIZED (typographic dashes/quotes -> ASCII). If normalization clears the blank, the
blank is an INPUT/unicode bug (fixable in a sanitizer, and a SEPARATE production-blank contributor
to the GLM model pathology), and nemotron's blank=0 case for the Mirror swap holds. If it still
blanks, the model is unreliable on this input and we keep glm + widen the slate.

Reads OPENROUTER_API_KEY from env/.env (never printed). Run from repo root. ~8 live calls.
"""
from __future__ import annotations
import os, sys, json, unicodedata

os.environ.setdefault("PG_MIRROR_REASONING", "false")
os.environ.setdefault("PG_SENTINEL_MAX_TOKENS", "4000")
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
from src.polaris_graph.roles.mirror_adapter import (  # noqa: E402
    run_mirror, MirrorCitationError, MirrorBindingError,
)
from src.polaris_graph.roles.role_transport import EvidenceDocument  # noqa: E402
from src.polaris_graph.roles.openai_compatible_transport import BlankVerdictError  # noqa: E402

# typographic -> ASCII (en/em dash, curly quotes, NBSP); then NFKD to fold residual compatibility chars.
_MAP = {"–": "-", "—": "-", "‘": "'", "’": "'",
        "“": '"', "”": '"', " ": " ", "…": "..."}


def normalize(text: str) -> str:
    for k, v in _MAP.items():
        text = text.replace(k, v)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def load_pair():
    e = json.load(open("outputs/audits/I-run11-004/m25_bakeoff/evidence_pool.json", encoding="utf-8"))
    item = next(x for x in e if "brynjolfsson" in str(x.get("evidence_id", "")).lower())
    claim = item.get("statement") or item.get("title")
    quote = item.get("direct_quote") or ""
    return item.get("evidence_id"), claim, quote


def run_one(slug: str, claim: str, quote: str) -> str:
    os.environ["PG_MIRROR_MODEL"] = slug
    transport = OpenRouterRoleTransport(httpx.Client(timeout=180.0))
    docs = [EvidenceDocument(doc_id="brynjolfsson_genai_at_work", text=quote[:2000])]
    try:
        pass2, _ = run_mirror(transport, claim, docs, model_slug=slug)
        return f"BOUND classification={pass2.classification!r}"
    except BlankVerdictError:
        return "BLANK (BlankVerdictError)"
    except MirrorCitationError:
        return "REFUSED (MirrorCitationError — no grounded citation)"
    except MirrorBindingError:
        return "UNBOUND (MirrorBindingError)"
    except Exception as ex:  # noqa: BLE001 — diagnostic: surface any other failure verbatim
        return f"ERROR {type(ex).__name__}: {str(ex)[:120]}"


def main():
    eid, claim, quote_raw = load_pair()
    quote_clean = normalize(quote_raw)
    n_bad = sum(1 for c in quote_raw if ord(c) > 127)
    print(f"item={eid} | claim={claim!r}")
    print(f"raw non-ascii chars={n_bad} | cleaned non-ascii chars={sum(1 for c in quote_clean if ord(c) > 127)}")
    print(f"raw[55:75]={quote_raw[55:75]!r}  ->  clean[55:75]={quote_clean[55:75]!r}\n")
    for slug in ["nvidia/nemotron-3-super-120b-a12b", "z-ai/glm-5.1"]:
        raw_out = run_one(slug, claim, quote_raw)
        clean_out = run_one(slug, claim, quote_clean)
        verdict = "INPUT-DRIVEN (normalize fixes)" if ("BLANK" in raw_out and "BLANK" not in clean_out) \
            else ("STILL BLANKS (model-driven)" if "BLANK" in clean_out else "no blank either way")
        print(f"[{slug}]")
        print(f"    RAW   : {raw_out}")
        print(f"    CLEAN : {clean_out}")
        print(f"    => {verdict}\n")


if __name__ == "__main__":
    main()
