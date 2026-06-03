"""I-run11-002 L1 — multi-fixture LIVE discrimination smoke for the NON-INVERTED benchmark Sentinel.

Proves granite-4.1-8b + the new non-inverted (prompt, parser) discriminates ROBUSTLY before run 12
(the probe was n=1). Calls the REAL production path: build_sentinel_request in noninverted mode ->
_normalize_messages -> live OpenRouter granite -> parse_sentinel_grounded_token. LAW VI: key from env.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.getcwd())
os.environ["PG_SENTINEL_GROUNDEDNESS_MODE"] = "noninverted"

from src.polaris_graph.roles.role_transport import EvidenceDocument  # noqa: E402
from src.polaris_graph.roles.sentinel_adapter import build_sentinel_request  # noqa: E402
from src.polaris_graph.roles.sentinel_contract import parse_sentinel_grounded_token  # noqa: E402
from src.polaris_graph.roles.openai_compatible_transport import _normalize_messages  # noqa: E402

MODEL = "ibm-granite/granite-4.1-8b"


def _key() -> str:
    for ln in open(".env", encoding="utf-8", errors="replace"):
        if ln.startswith("OPENROUTER_API_KEY="):
            return ln.split("=", 1)[1].strip()
    k = os.getenv("OPENROUTER_API_KEY")
    if not k:
        raise SystemExit("OPENROUTER_API_KEY missing (.env or env) — cannot run live smoke (LAW II).")
    return k


def _doc_text() -> str:
    pool = json.load(open("outputs/q1_run11/evidence_pool.json", encoding="utf-8"))
    items = pool if isinstance(pool, list) else pool.get("evidence") or list(pool.values())
    for it in items:
        if isinstance(it, dict) and "autor" in json.dumps(it).lower() and "polariz" in json.dumps(it).lower():
            return (it.get("direct_quote") or it.get("text") or it.get("content") or "")[:4000]
    # fallback: any item mentioning polarization
    for it in items:
        if isinstance(it, dict) and "polariz" in json.dumps(it).lower():
            return (it.get("direct_quote") or it.get("text") or it.get("content") or "")[:4000]
    raise SystemExit("could not find autor polarization doc in evidence_pool.json")


def _call(claim: str, doc: str, key: str) -> str:
    docs = [EvidenceDocument(doc_id="autor_why_still_jobs", text=doc)]
    req = build_sentinel_request(claim, docs, model_slug=MODEL)
    messages = _normalize_messages(req)
    body = {"model": MODEL, "messages": messages, "max_tokens": 32, "temperature": 0.0}
    r = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=60) as resp:
        data = json.loads(resp.read())
    return (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""


def main() -> None:
    key = _key()
    doc = _doc_text()
    print(f"doc[:120]={doc[:120]!r}\n")
    # verbatim grounded claim = first ~25 words of the doc
    grounded = " ".join(doc.split()[:28])
    fixtures = [
        ("1_grounded_verbatim", grounded, "GROUNDED"),
        ("2_fabricated_numeric", "AI raised US median wages by exactly 14 percent in 2024.", "UNGROUNDED"),
        ("3_qualitative_negation", "The study found NO polarization of the labor market.", "UNGROUNDED"),
        ("4_paraphrase_true", "Wage gains were concentrated at the top and bottom of the skill distribution, not the middle.", "GROUNDED"),
    ]
    results = []
    for name, claim, expect in fixtures:
        runs = []
        for _ in range(2):
            try:
                raw = _call(claim, doc, key)
                v = parse_sentinel_grounded_token(raw)
                runs.append((raw.strip()[:40], v.verdict.value, v.parsed_ok))
            except Exception as e:  # noqa: BLE001
                runs.append((f"ERR:{type(e).__name__}:{str(e)[:40]}", "?", False))
        verdicts = {r[1] for r in runs}
        ok = (verdicts == {expect.lower()})
        results.append((name, expect, ok, runs))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: expect {expect} -> {runs}")
    all_ok = all(r[2] for r in results)
    print(f"\nVERDICT: granite+non-inverted discriminates robustly = {all_ok}")
    print("qualitative-negation (#3) is the hardest case; it MUST be UNGROUNDED.")


if __name__ == "__main__":
    main()
