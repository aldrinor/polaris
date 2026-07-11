"""W1 acceptance harness for the agentic outliner loop (I-outline-agent).

Runs TWO real, live scenarios against src/polaris_graph/outline/outline_agent.py:

  (a) THIN  — seed evidence covers ONLY part of the research question (efficacy), the question
      itself also asks about long-term cardiovascular safety. Acceptance: the checklist names
      the gap, search_more_evidence fires a real scoped query, new rows fold in with
      collision-free ids + S2 stamps, the outline mutates (ev_ids grow / new gap-covering rows
      cited).

  (b) SATURATED — a narrow question whose seed evidence already fully covers it (negative
      control). Acceptance: retrieval stays at ZERO (no search_more_evidence tool call ever
      fires) — the checklist should find nothing to search for and finish_outline should be
      accepted quickly.

FAIL LOUD: any exception is allowed to propagate and print a full traceback — this harness never
swallows an error to fake a pass (LAW II).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/workspace/outline_agent_wt")

from dotenv import load_dotenv  # noqa: E402
load_dotenv("/workspace/POLARIS/.env", override=True)

os.environ["PG_OUTLINE_AGENT"] = "1"
os.environ.setdefault("PG_OUTLINE_MAX_TOKENS", "131072")
os.environ.setdefault("PG_OUTLINE_REASONING_MAX_TOKENS", "32768")
# Keep the acceptance run FAST: small turn/wall budgets are fine for W1 proof (the design's
# defaults are 24 turns / 900s for a full production run; the smoke here just needs the loop to
# fire at least once on the thin case and zero times on the saturated case).
os.environ.setdefault("PG_OUTLINE_AGENT_MAX_TURNS", "6")
os.environ.setdefault("PG_OUTLINE_AGENT_WALL_SECONDS", "420")

from src.polaris_graph.outline import outline_agent as oa  # noqa: E402
from src.polaris_graph.retrieval.live_retriever import run_live_retrieval  # noqa: E402


def _bootstrap_seed(query: str, max_serper: int = 6) -> list[dict]:
    """A real, live, narrow-scoped retrieval call used ONLY to bootstrap a small realistic seed
    pool for the harness (not part of the agent loop itself)."""
    result = run_live_retrieval(
        research_question=query, max_serper=max_serper, fetch_cap=10, anchor_seed=True,
    )
    rows = list(result.evidence_rows or [])
    print(f"[bootstrap] query={query!r} -> {len(rows)} evidence rows "
          f"(fetched={result.candidates_fetched}, failed={result.candidates_failed_fetch})")
    return rows


async def run_thin() -> dict:
    print("\n" + "=" * 80)
    print("THIN RUN — seed covers only 'efficacy', question also asks 'long-term CV safety'")
    print("=" * 80)
    seed_rows = _bootstrap_seed(
        "tirzepatide 15mg HbA1c reduction efficacy SURPASS trial results", max_serper=6,
    )
    if len(seed_rows) < 3:
        raise RuntimeError(f"bootstrap seed too thin to test with ({len(seed_rows)} rows) — "
                            "live retrieval may be degraded; not faking a pass")

    question = (
        "What is the HbA1c-lowering efficacy of tirzepatide 15mg AND what is known about its "
        "long-term cardiovascular safety (major adverse cardiovascular events, SURMOUNT-MMO "
        "or equivalent outcome trial data)?"
    )
    evidence = list(seed_rows)
    ev_before = {r.get("evidence_id") for r in evidence if isinstance(r, dict)}

    t0 = time.monotonic()
    parse_result, retry_attempted, in_tok, out_tok = await oa.run_outline_agent_or_legacy(
        question, evidence, oa.outliner_code_model(), 0.2, 131072,
    )
    elapsed = time.monotonic() - t0

    stats = parse_result.digest_stats.get("outline_agent", {})
    seed_ev_by_title = {t: set(v) for t, v in stats.get("seed_ev_by_title", {}).items()}
    final_ev_by_title = {t: set(v) for t, v in stats.get("final_ev_by_title", {}).items()}
    outline_mutated = (
        set(seed_ev_by_title.keys()) != set(final_ev_by_title.keys())
        or any(
            seed_ev_by_title.get(t, set()) != final_ev_by_title.get(t, set())
            for t in final_ev_by_title
        )
    )
    update_outline_calls = sum(
        1 for d in stats.get("disclosures", []) if d.startswith("update_outline:")
    )
    print(f"\n--- THIN RUN RESULT (elapsed {elapsed:.1f}s) ---")
    print(f"outline_mutated={outline_mutated} update_outline_calls={update_outline_calls}")
    print(f"seed_ev_by_title={ {t: len(v) for t, v in seed_ev_by_title.items()} }")
    print(f"final_ev_by_title={ {t: len(v) for t, v in final_ev_by_title.items()} }")
    print(f"turns={stats.get('turns')} ev_before={len(ev_before)} "
          f"ev_after={stats.get('ev_store_size')} new_evidence={stats.get('new_evidence_count')}")
    print("gap_ledger:")
    for t in stats.get("gap_ledger", []):
        print(f"  {t}")
    print("disclosures:")
    for d in stats.get("disclosures", []):
        print(f"  - {d}")
    print("final outline plans:")
    for p in parse_result.plans:
        print(f"  - {oa._plan_field(p, 'title', '')!r}: "  # noqa: SLF001 — harness, same-repo reuse
              f"{len(oa._plan_field(p, 'ev_ids', []) or [])} ev_ids")

    search_calls = sum(
        1 for d in stats.get("disclosures", []) if d.startswith("search_more_evidence[")
    )
    checklist_gaps = sum(
        1 for d in stats.get("disclosures", []) if d.startswith("checklist[")
    )
    return {
        "elapsed_s": round(elapsed, 1),
        "turns": stats.get("turns"),
        "ev_before": len(ev_before),
        "ev_after": stats.get("ev_store_size"),
        "new_evidence_count": stats.get("new_evidence_count"),
        "search_more_evidence_calls": search_calls,
        "checklist_gap_events": checklist_gaps,
        "unfilled_gaps": stats.get("unfilled_gaps"),
        "outline_mutated": outline_mutated,
        "update_outline_calls": update_outline_calls,
        "final_section_ev_counts": {
            oa._plan_field(p, "title", ""): len(oa._plan_field(p, "ev_ids", []) or [])  # noqa: SLF001
            for p in parse_result.plans
        },
        "disclosures": stats.get("disclosures"),
    }


async def run_saturated() -> dict:
    print("\n" + "=" * 80)
    print("SATURATED RUN (negative control) — narrow single-fact question, wide seed pool")
    print("=" * 80)
    # Deliberately narrow to ONE verifiable fact (completion year) with a WIDE multi-angle seed
    # (the fact itself, construction history, engineering details) so a genuine checklist has
    # little real room to invent a plausible sub-topic gap — unlike the first attempt's implicit
    # "capital + population" 2-part question, which correctly triggered real historical/subgroup
    # gaps (that was a harness design flaw, not an outline_agent bug).
    seed_rows_a = _bootstrap_seed(
        "Eiffel Tower completion year 1889 construction history", max_serper=6,
    )
    seed_rows_b = _bootstrap_seed(
        "Eiffel Tower built engineer Gustave Eiffel opening date facts", max_serper=6,
    )
    seen_urls: set[str] = set()
    seed_rows: list[dict] = []
    for r in seed_rows_a + seed_rows_b:
        u = str(r.get("source_url") or r.get("url") or "")
        if u and u in seen_urls:
            continue
        if u:
            seen_urls.add(u)
        seed_rows.append(r)
    if len(seed_rows) < 3:
        raise RuntimeError(f"bootstrap seed too thin for saturated control ({len(seed_rows)} rows)")

    question = "In what year was the Eiffel Tower completed?"
    evidence = list(seed_rows)
    ev_before = {r.get("evidence_id") for r in evidence if isinstance(r, dict)}
    t0 = time.monotonic()
    parse_result, retry_attempted, in_tok, out_tok = await oa.run_outline_agent_or_legacy(
        question, evidence, oa.outliner_code_model(), 0.2, 131072,
    )
    elapsed = time.monotonic() - t0

    stats = parse_result.digest_stats.get("outline_agent", {})
    print(f"\n--- SATURATED RUN RESULT (elapsed {elapsed:.1f}s) ---")
    print(f"turns={stats.get('turns')} ev_before={len(ev_before)} "
          f"ev_after={stats.get('ev_store_size')} new_evidence={stats.get('new_evidence_count')}")
    print("gap_ledger:")
    for t in stats.get("gap_ledger", []):
        print(f"  {t}")
    print("disclosures:")
    for d in stats.get("disclosures", []):
        print(f"  - {d}")

    search_calls = sum(
        1 for d in stats.get("disclosures", []) if d.startswith("search_more_evidence[")
    )
    checklist_ran = any(d.startswith("checklist[seed]") for d in stats.get("disclosures", []))
    finish_accepted = any(
        d.startswith("finish_outline ACCEPTED") for d in stats.get("disclosures", [])
    )
    plans_nonempty = len(parse_result.plans) > 0
    zero_searches = search_calls == 0
    # Iter-2: found via a real live run (not anticipated) — `_call_outline`'s OWN pre-existing
    # section-count-floor validation is a SECOND, upstream way this question can legitimately
    # stay at zero retrieval: for a genuinely single-fact question, the outline LLM sometimes
    # returns 0-2 sections (below the floor), `_call_outline` marks it invalid even after its own
    # retry, `run_outline_agent_or_legacy`'s fail-open early-return fires (`not parse_result.plans`
    # -> return before the agent loop is ever constructed), and `digest_stats["outline_agent"]` is
    # never populated (`stats == {}`). That is EVEN STRONGER evidence of "no runaway retrieval"
    # than a full loop that finishes with zero searches — the loop never got a chance to run at
    # all. The ORIGINAL definition below (checklist_ran + finish_accepted) assumed the agent loop
    # always starts, so it mis-scored this legitimate path as invalid. Read what actually
    # happened, don't just check a boolean (§-1.1): a stats=={} outcome with search_calls==0 is
    # disclosed as its OWN distinct pass path, never conflated with the full-loop pass path.
    seed_outline_invalid_early_return = not stats  # stats=={} iff the early-return branch fired
    valid_negative_control = zero_searches and (
        seed_outline_invalid_early_return
        or (plans_nonempty and stats.get("turns", 0) >= 1 and checklist_ran and finish_accepted)
    )
    print(f"valid_negative_control={valid_negative_control} "
          f"(seed_outline_invalid_early_return={seed_outline_invalid_early_return}, "
          f"plans_nonempty={plans_nonempty}, turns>=1={stats.get('turns', 0) >= 1}, "
          f"checklist_ran={checklist_ran}, finish_accepted={finish_accepted}, "
          f"zero_searches={zero_searches} [search_calls={search_calls}])")
    if seed_outline_invalid_early_return:
        print(f"  (seed outline reason_codes={getattr(parse_result, 'reason_codes', None)}, "
              f"ok={getattr(parse_result, 'ok', None)})")

    return {
        "elapsed_s": round(elapsed, 1),
        "turns": stats.get("turns"),
        "ev_before": len(ev_before),
        "ev_after": stats.get("ev_store_size"),
        "new_evidence_count": stats.get("new_evidence_count"),
        "search_more_evidence_calls": search_calls,
        "valid_negative_control": valid_negative_control,
        "seed_outline_invalid_early_return": seed_outline_invalid_early_return,
        "seed_reason_codes": (
            list(getattr(parse_result, "reason_codes", []) or [])
            if seed_outline_invalid_early_return else None
        ),
        "disclosures": stats.get("disclosures"),
    }


async def main() -> None:
    # Iter-2: allow re-verifying a single scenario (``--only thin`` / ``--only saturated``) so a
    # targeted fix to one path doesn't force re-spending on the other, already-passing scenario.
    # Default (no arg) runs BOTH, unchanged, and writes the full acceptance_result.json.
    only = None
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        if idx + 1 < len(sys.argv):
            only = sys.argv[idx + 1].strip().lower()

    result: dict = {}
    if only in (None, "thin"):
        result["thin"] = await run_thin()
    if only in (None, "saturated"):
        result["saturated"] = await run_saturated()
    print("\n" + "#" * 80)
    print("ACCEPTANCE SUMMARY")
    print("#" * 80)
    print(json.dumps(result, indent=2, default=str))
    out_path = (
        "/workspace/outline_agent_wt/acceptance_result.json" if only is None
        else f"/workspace/outline_agent_wt/acceptance_result_{only}.json"
    )
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)


if __name__ == "__main__":
    asyncio.run(main())
