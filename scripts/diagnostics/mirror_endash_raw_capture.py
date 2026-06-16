#!/usr/bin/env python3
"""I-run11-006 (#1050) root-cause capture: print the Mirror PASS-1 RAW output for nemotron on the
brynjolfsson pair, RAW (U+2013 en-dash) vs unicode-normalized, so we SEE exactly how the en-dash
changes the model's <co> citation behavior (no <co> emitted? different doc_id? truncation?). The
binding guard is doc_id-based (_validate_citation_binding), so the en-dash must change the model's
OUTPUT, not a text comparison — this confirms which. Evidence before fix (no guessing).

Reads OPENROUTER_API_KEY from env/.env (never printed). Run from repo root. ~4 live calls.
"""
from __future__ import annotations
import os, sys, json, unicodedata

os.environ.setdefault("PG_MIRROR_REASONING", "false")
os.environ.setdefault("PG_SENTINEL_MAX_TOKENS", "4000")
os.environ.setdefault("PG_FOUR_ROLE_TRANSPORT", "openrouter")
os.environ["PG_MIRROR_MODEL"] = "nvidia/nemotron-3-super-120b-a12b"
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

_MAP = {"–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"', " ": " ", "…": "..."}


def normalize(text: str) -> str:
    for k, v in _MAP.items():
        text = text.replace(k, v)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def load():
    e = json.load(open("outputs/audits/I-run11-004/m25_bakeoff/evidence_pool.json", encoding="utf-8"))
    it = next(x for x in e if "brynjolfsson" in str(x.get("evidence_id", "")).lower())
    return it.get("statement") or it.get("title"), (it.get("direct_quote") or "")


def cap(label: str, claim: str, quote: str) -> None:
    docs = [EvidenceDocument(doc_id="brynjolfsson_genai_at_work", text=quote[:2000])]
    req = build_mirror_pass1_request(claim, docs, model_slug="nvidia/nemotron-3-super-120b-a12b")
    transport = OpenRouterRoleTransport(httpx.Client(timeout=180.0))
    try:
        resp = transport.complete(req)
        raw = resp.raw_text or ""
        has_co = "<co" in raw
        print(f"[{label}] served={resp.served_model} len={len(raw)} has_<co>={has_co}")
        print(f"    raw_text: {raw[:600]!r}")
    except Exception as ex:  # noqa: BLE001 — diagnostic: surface the failure verbatim
        print(f"[{label}] EXC {type(ex).__name__}: {str(ex)[:200]}")


def main():
    claim, q_raw = load()
    q_clean = normalize(q_raw)
    print(f"claim={claim!r}\nraw has en-dash at idx {q_raw.find(chr(0x2013))}\n")
    cap("RAW(en-dash)", claim, q_raw)
    print()
    cap("CLEAN(ascii)", claim, q_clean)


if __name__ == "__main__":
    main()
