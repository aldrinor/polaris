#!/usr/bin/env python3
"""Standalone recovery of evidence cards LOST to the reasoning-first token-truncation bug.

WHY THIS EXISTS
---------------
The evidence miner (scripts/evidence_miner.py) mines with z-ai/glm-5.2, a reasoning-first
("always reason") model. Its per-chunk extraction call is `llm(prompt, max_tokens=6000)`
(evidence_miner.py ~L1786 / L2122). GLM-5.2 is in `_ALWAYS_REASON_MODELS`, so in
openrouter_client._generate_impl it takes BRANCH 1 (~L1953): reasoning runs with
`effort:high` and the OVERALL ceiling is `max_tokens` (floored at PG_GLM5_MIN_MAX_TOKENS=4096).
On the LARGEST / densest chunks (esp. "tables"), the reasoning pass consumes nearly all of the
6000-token ceiling, the content field is starved, and the promotion leg raises
`ReasoningFirstTruncationError` (I-bug-089 / FX-01, ~L3203). That chunk then yields NO card.

THE FIX (per-call, standalone — the shared miner/client are NOT touched)
------------------------------------------------------------------------
`max_tokens` is the single lever: it is the overall completion ceiling that reasoning AND
content share. Raise it and both fit. We re-mine ONLY the truncated chunks with:

    max_tokens          = RECOVERY_BUDGET      (default 22000; task-suggested 16000-24000)
    reasoning_max_tokens = int(budget * 0.40)  (default 8800)

For a reasoning-first model, passing `reasoning_max_tokens` makes the 40/60 split EXPLICIT:
branch 1 sets `reasoning.max_tokens` (replacing effort:high) so reasoning is asked to stay
inside 40% and ~60% is reserved for the cited-cards content. Even where the provider does not
hard-enforce the reasoning cap, the 3.6x-larger overall ceiling gives content ample headroom.
On a still-truncation we escalate the ceiling once (RECOVERY_BUDGET_HIGH, default 32000) and,
if it STILL truncates, we LOG and COUNT it (never silently drop).

Everything else goes through the SAME production chain as the main mine:
prov().migrate(corpus) -> the same _mining_units identity/binding preskip -> chunk_document ->
harvest -> mine_prompt -> gate_card. Only the token budget of the extraction call differs.

OUTPUT: outputs/recovered_table_cards.json  (NEVER evidence_cards_v2.json). Re-runnable /
idempotent: chunks already recovered are skipped; still-truncated / unmapped chunks are retried.

RUN (while the main mine is up, or at mine-end to sweep the rest):

    cd /home/polaris/wt/flywheel
    PG_MAX_COST_PER_RUN=100000 PYTHONPATH=scripts:src \
        python scripts/recover_truncated_tables.py \
        --truncated /path/to/truncated_chunks.txt

Constraints honoured: does not touch evidence_cards_v2.json / blobs / the ledger, does not edit
the miner or client, uses only --workers (default 2) concurrent LLM calls so the main mine keeps
its OpenRouter throughput.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent import futures
from datetime import datetime, timezone
from pathlib import Path

# ── the production miner, imported (NOT modified) ────────────────────────────────────────────────
import evidence_miner as em
from evidence_miner import (
    chunk_document,
    gate_card,
    harvest,
    load_contract,
    mine_prompt,
    paper_window,
    prov,
    jparse,
    MODEL,
)

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = REPO / "outputs" / "journal_corpus_content.json"
DEFAULT_OUT = REPO / "outputs" / "recovered_table_cards.json"
DEFAULT_TRUNCATED = Path(
    "/tmp/claude-1000/-home-polaris-polaris-project/"
    "21e87760-8436-4090-870d-99ef2121882e/scratchpad/truncated_chunks.txt"
)

RECOVERY_BUDGET = int(os.getenv("PG_RECOVERY_BUDGET", "22000"))
RECOVERY_BUDGET_HIGH = int(os.getenv("PG_RECOVERY_BUDGET_HIGH", "32000"))
REASONING_FRACTION = float(os.getenv("PG_RECOVERY_REASONING_FRACTION", "0.40"))

_print_lock = threading.Lock()


def say(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── the raised-budget extraction call — mirrors evidence_miner.llm() but with a big ceiling and an
#    explicit 40% reasoning cap. Returns (content, still_truncated: bool, budget_used). ──────────────
def raised_llm(prompt: str, budget: int) -> tuple[str | None, bool]:
    import asyncio

    from src.polaris_graph.llm.openrouter_client import (
        OpenRouterClient,
        ReasoningFirstTruncationError,
    )

    reasoning_cap = max(int(budget * REASONING_FRACTION), 100)

    async def _run() -> tuple[str | None, bool]:
        c = OpenRouterClient(model=MODEL)
        try:
            try:
                r = await c.generate(
                    prompt=prompt,
                    max_tokens=budget,
                    temperature=0.0,
                    reasoning_max_tokens=reasoning_cap,
                )
            except ReasoningFirstTruncationError:
                return None, True
            if isinstance(r, str):
                return r, False
            content = getattr(r, "content", None)
            if content is not None:
                return content, False
            return (r.get("content") if isinstance(r, dict) else str(r)), False
        finally:
            cl = getattr(c, "close", None)
            if cl:
                try:
                    res = cl()
                    if hasattr(res, "__await__"):
                        await res
                except Exception:
                    pass

    return asyncio.run(_run())


# ── parse truncated_chunks.txt: "<doi> chunk <idx> (<section>)" ──────────────────────────────────
_LINE = re.compile(r"^\s*(?P<doi>\S+)\s+chunk\s+(?P<idx>\d+)\s+\((?P<section>[^)]*)\)\s*$")


def parse_truncated(path: Path) -> list[dict]:
    targets: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for raw in path.read_text().splitlines():
        if not raw.strip():
            continue
        m = _LINE.match(raw)
        if not m:
            say(f"  [warn] unparseable line skipped: {raw!r}")
            continue
        doi = m.group("doi")
        idx = int(m.group("idx"))
        key = (doi, idx)
        if key in seen:
            continue
        seen.add(key)
        targets.append({"doi": doi, "chunk_idx": idx, "section": m.group("section")})
    return targets


def key_of(doi: str, idx: int) -> str:
    return f"{doi}|{idx}"


# ── map a target doi to a graph mining-unit (paper dict). Flexible because the mine log truncates
#    doc_id to 28 chars, so the provided list may carry a shortened doi. ───────────────────────────
def build_doi_index(units: list[dict]) -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for u in units:
        d = u.get("doi") or ""
        if d:
            idx[d] = u
    return idx


def match_unit(doi: str, doi_index: dict[str, dict], units: list[dict]) -> dict | None:
    if doi in doi_index:
        return doi_index[doi]
    # prefix either way (handles a doi shortened to doc_id[:28] in the log, or trailing clip)
    cands = [
        u
        for u in units
        if u.get("doi")
        and (u["doi"].startswith(doi) or doi.startswith(u["doi"]) or doi[:28] == (u["doi"] or "")[:28])
    ]
    if len(cands) == 1:
        return cands[0]
    return None


# ── mine ONE chunk through the production chain with the raised budget. ──────────────────────────
def mine_one_chunk(paper: dict, target_idx: int, contract, graph, policy) -> dict:
    """Returns a result record: status in {recovered, no_cards, chunk_not_found, still_truncated,
    llm_error}, plus n_cards and the cards themselves (tagged for provenance/idempotency)."""
    mid = paper["manifestation_id"]
    m = graph.manifestations[mid]
    src = m.text
    doc_id = (paper.get("doi") or paper.get("title", ""))[:80]

    view, chunks = chunk_document(doc_id, src)
    if not chunks:
        return {"status": "chunk_not_found", "n_cards": 0, "cards": [], "detail": "no chunks"}

    ch = next((c for c in chunks if c.idx == target_idx), None)
    if ch is None:
        return {
            "status": "chunk_not_found",
            "n_cards": 0,
            "cards": [],
            "detail": f"chunk idx {target_idx} not in {len(chunks)} chunks",
        }

    # deterministic harvest exactly as mine_paper does
    for c in chunks:
        c.candidates = harvest(c, contract)
    pw = paper_window(view, chunks, paper)

    facet_line = ""
    if contract.probes:
        facet_line = (
            "\nTHE REVIEW NEEDS THESE QUESTIONS ANSWERED OF EVERY SOURCE. Prefer evidence that answers\n"
            "one of them -- but NEVER invent a value to fit one. An unanswered facet is a real,\n"
            "reportable gap; a fabricated one is a lie:\n"
            + "\n".join(f"  - {p}" for p in contract.probes[:8])
            + "\n"
        )

    # cand_block — copied verbatim from mine_paper's per-chunk block so the prompt is identical
    cand_block = ""
    if ch.candidates:
        q = [c for c in ch.candidates if c["quantitative"]]
        ql = [c for c in ch.candidates if not c["quantitative"]]
        parts = []
        if q:
            lines = "\n".join(
                f'  - {c["text"][:260]}' for c in sorted(q, key=lambda c: -c["score"])[:12]
            )
            parts.append(
                "A DETERMINISTIC SCAN FLAGGED THESE SENTENCES IN THE EXCERPT AS CARRYING QUANTITIES.\n"
                "They are a hint, not a quota. Some are not findings.\n" + lines
            )
        if ql:
            lines = "\n".join(
                f'  - [{",".join(c["families"])[:44]}] {c["text"][:240]}'
                for c in sorted(ql, key=lambda c: -c["score"])[:8]
            )
            parts.append(
                "AND THESE AS CARRYING A HOLDING, A RECOMMENDATION, A NULL RESULT, A STATED LIMITATION\n"
                "OR A QUALITATIVE RESULT. The bracketed type is a GUESS by a regex — you decide.\n" + lines
            )
        if parts:
            cand_block = "\n" + "\n\n".join(parts) + "\nCopy spans from the EXCERPT, not from these lists.\n"

    p = mine_prompt(
        title=paper.get("title", ""),
        authors=", ".join(paper.get("authors", []) or []),
        venue=paper.get("venue", ""),
        year=paper.get("year", ""),
        section=ch.section.upper(),
        facet_line=facet_line,
        text=ch.text,
        cand_block=cand_block,
    )

    # raised-budget call, with one ceiling escalation on a genuine reasoning-first truncation
    arr = None
    budget_used = RECOVERY_BUDGET
    still_truncated = False
    last_err = ""
    for budget in (RECOVERY_BUDGET, RECOVERY_BUDGET_HIGH):
        budget_used = budget
        try:
            content, truncated = raised_llm(p, budget)
        except Exception as e:  # transport / API error — record and stop
            last_err = f"{type(e).__name__}: {e}"
            still_truncated = False
            arr = None
            break
        if truncated:
            still_truncated = True
            arr = None
            continue  # escalate the ceiling
        still_truncated = False
        arr = jparse(content)
        break

    if still_truncated:
        return {
            "status": "still_truncated",
            "n_cards": 0,
            "cards": [],
            "budget": budget_used,
            "detail": f"ReasoningFirstTruncationError at budget<={budget_used}",
        }
    if last_err:
        return {"status": "llm_error", "n_cards": 0, "cards": [], "detail": last_err}
    if not isinstance(arr, list):
        return {
            "status": "no_cards",
            "n_cards": 0,
            "cards": [],
            "budget": budget_used,
            "detail": "model returned no parseable card array",
        }

    rejects = em.new_rejects()
    cards: list[dict] = []
    for rawc in arr:
        if not isinstance(rawc, dict):
            continue
        card = gate_card(rawc, view, ch, paper, pw, contract, rejects, graph=graph, source_policy=policy)
        if card:
            card["_recovered_from"] = {
                "doi": paper.get("doi", ""),
                "manifestation_id": mid,
                "chunk_idx": target_idx,
                "section": ch.section,
                "budget": budget_used,
                "recovered_at": _now(),
            }
            cards.append(card)

    status = "recovered" if cards else "no_cards"
    return {
        "status": status,
        "n_cards": len(cards),
        "cards": cards,
        "budget": budget_used,
        "proposed": len(arr),
        "detail": "" if cards else "all proposals rejected by gate_card",
    }


def load_state(out_path: Path) -> dict:
    if out_path.exists():
        try:
            st = json.loads(out_path.read_text())
            st.setdefault("cards", [])
            st.setdefault("attempts", {})
            return st
        except Exception as e:
            say(f"  [warn] could not read existing {out_path.name} ({e}); starting fresh")
    return {"cards": [], "attempts": {}}


def write_state(out_path: Path, state: dict) -> None:
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    tmp.replace(out_path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--truncated", type=Path, default=DEFAULT_TRUNCATED)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--question-file", type=Path, default=Path("/home/polaris/polaris_project/task72_prompt.txt"))
    ap.add_argument("--workers", type=int, default=2, help="concurrent LLM calls (keep 2-3 to not starve the main mine)")
    ap.add_argument("--force", action="store_true", help="re-mine even chunks already recovered")
    args = ap.parse_args()

    if str(args.out).endswith("evidence_cards_v2.json"):
        say("REFUSING: --out must not be evidence_cards_v2.json (the main mine owns it).")
        return 2

    workers = max(1, min(args.workers, 3))  # HARD cap at 3 — the main mine needs the throughput

    question = args.question_file.read_text().strip() if args.question_file.exists() else ""
    say(f"[recover] model={MODEL}  budget={RECOVERY_BUDGET}->{RECOVERY_BUDGET_HIGH}  "
        f"reasoning_cap={int(RECOVERY_BUDGET*REASONING_FRACTION)} ({REASONING_FRACTION:.0%})  workers={workers}")

    targets = parse_truncated(args.truncated)
    say(f"[recover] {len(targets)} distinct truncated chunk(s) in {args.truncated.name}")
    if not targets:
        say("[recover] nothing to do.")
        return 0

    # SAME production chain as mine(): corpus -> contract -> prov.migrate -> _mining_units preskip
    say("[recover] building the provenance graph (prov().migrate) ...")
    corpus = json.loads(args.corpus.read_text())
    contract = load_contract(question)
    P = prov()
    graph = P.migrate(corpus)
    policy = contract.source_policy
    units, _skipped = em._mining_units(graph, corpus, policy)
    doi_index = build_doi_index(units)
    say(f"[recover] graph: {len(graph.manifestations)} manifestations, {len(units)} minable units, "
        f"source policy={policy.name}")

    state = load_state(args.out)
    attempts: dict = state["attempts"]

    todo: list[dict] = []
    for t in targets:
        k = key_of(t["doi"], t["chunk_idx"])
        prev = attempts.get(k)
        if prev and prev.get("status") == "recovered" and not args.force:
            continue  # idempotent: already recovered, skip
        todo.append(t)

    say(f"[recover] {len(todo)} chunk(s) to (re-)mine "
        f"({len(targets) - len(todo)} already recovered, skipped)")
    if not todo:
        say("[recover] all listed chunks already recovered. Output is up to date.")
        return 0

    lock = threading.Lock()
    # cards keyed by chunk so a re-mine REPLACES that chunk's prior cards (no duplication)
    cards_by_key: dict[str, list] = {}
    for c in state["cards"]:
        rf = c.get("_recovered_from") or {}
        ck = key_of(rf.get("doi", ""), rf.get("chunk_idx", -1))
        cards_by_key.setdefault(ck, []).append(c)

    counts = {"recovered": 0, "no_cards": 0, "still_truncated": 0, "unmapped": 0,
              "chunk_not_found": 0, "llm_error": 0}
    total_cards = 0

    def work(t: dict) -> None:
        nonlocal total_cards
        k = key_of(t["doi"], t["chunk_idx"])
        unit = match_unit(t["doi"], doi_index, units)
        if unit is None:
            with lock:
                counts["unmapped"] += 1
                attempts[k] = {"status": "unmapped", "section": t["section"],
                               "detail": "doi not among minable graph units", "ts": _now()}
            say(f"  [unmapped] {t['doi']} chunk {t['chunk_idx']} ({t['section']}) — not a minable unit")
            return
        try:
            res = mine_one_chunk(unit, t["chunk_idx"], contract, graph, policy)
        except Exception as e:
            import traceback
            with lock:
                counts["llm_error"] += 1
                attempts[k] = {"status": "llm_error", "section": t["section"],
                               "detail": f"{type(e).__name__}: {e}", "ts": _now()}
            say(f"  [error] {t['doi']} chunk {t['chunk_idx']}: {type(e).__name__}: {e}")
            traceback.print_exc()
            return
        with lock:
            counts[res["status"]] = counts.get(res["status"], 0) + 1
            attempts[k] = {"status": res["status"], "section": t["section"],
                           "n_cards": res["n_cards"], "budget": res.get("budget"),
                           "detail": res.get("detail", ""), "ts": _now()}
            if res["cards"]:
                cards_by_key[k] = res["cards"]  # replace prior cards for this chunk
                total_cards += res["n_cards"]
        tag = {"recovered": "OK", "no_cards": "no-cards", "still_truncated": "STILL-TRUNCATED",
               "chunk_not_found": "chunk-missing", "llm_error": "error"}.get(res["status"], res["status"])
        say(f"  [{tag}] {unit['doi'][:34]:<34} chunk {t['chunk_idx']:>3} ({t['section']:<10}) "
            f"-> {res['n_cards']} card(s)  budget={res.get('budget')}"
            + (f"  ({res.get('detail')})" if res.get("detail") else ""))

    t0 = time.time()
    with futures.ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, todo))

    # flatten and persist
    state["cards"] = [c for cards in cards_by_key.values() for c in cards]
    state["meta"] = {
        "model": MODEL,
        "budget": RECOVERY_BUDGET,
        "budget_high": RECOVERY_BUDGET_HIGH,
        "reasoning_fraction": REASONING_FRACTION,
        "reasoning_cap": int(RECOVERY_BUDGET * REASONING_FRACTION),
        "last_run": _now(),
        "workers": workers,
        "source_policy": policy.name,
        "truncated_list": str(args.truncated),
    }
    write_state(args.out, state)

    say("")
    say("=" * 78)
    say(f"  RECOVERY COMPLETE in {round(time.time()-t0,1)}s — {workers} worker(s)")
    say(f"  re-mined this run : {len(todo)} chunk(s)")
    say(f"  recovered chunks  : {counts['recovered']}   (+{total_cards} card(s) this run)")
    say(f"  no cards          : {counts['no_cards']}   (mined OK but gate/model produced none)")
    say(f"  STILL truncated   : {counts['still_truncated']}   (logged, NOT dropped — retry later)")
    say(f"  unmapped doi      : {counts['unmapped']}")
    say(f"  chunk not found   : {counts['chunk_not_found']}")
    say(f"  llm/transport err : {counts['llm_error']}")
    say(f"  total cards in {args.out.name}: {len(state['cards'])}")
    say(f"  output: {args.out}")
    say("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
