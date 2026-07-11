"""Real-corpus agentic outliner run — AI-labor DRB-72 corpus (654 cp2 rows, 41 multi-member
cp3 baskets), operator-directed real-run report (not part of the W1 acceptance harness).

Loads the ACTUAL cp2 evidence (evidence_for_gen) + cp3 basket/same_work_groups snapshot for
run_id SWEEP_workforce_drb_72_ai_labor_1783476454, and drives run_outline_agent_or_legacy with
PG_OUTLINE_AGENT=1 (GLM-5.2 driver, DeepSeek-v4-pro seed/code model per lock). FAIL LOUD on any
exception (LAW II) — never fakes a pass.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, "/workspace/outline_agent_wt")

from dotenv import load_dotenv  # noqa: E402
load_dotenv("/workspace/POLARIS/.env", override=True)

os.environ["PG_OUTLINE_AGENT"] = "1"
os.environ.setdefault("PG_OUTLINE_MAX_TOKENS", "131072")
os.environ.setdefault("PG_OUTLINE_REASONING_MAX_TOKENS", "32768")
os.environ.setdefault("PG_OUTLINE_AGENT_MAX_TURNS", "10")
os.environ.setdefault("PG_OUTLINE_AGENT_WALL_SECONDS", "1500")

from src.polaris_graph.outline import outline_agent as oa  # noqa: E402

CP2_PATH = "/workspace/s2s3_wt/outputs/s2s3_iter1/s2/cp2_corpus_snapshot.json"
CP3_PATH = "/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json"
OUT_DIR = "/workspace/outline_agent_wt/outputs/real_corpus_agent_run"


def _build_clusters(baskets: list[dict], ev_id_to_idx: dict[str, int]) -> list[SimpleNamespace]:
    clusters = []
    dropped = 0
    for b in baskets:
        if int(b.get("member_count", 1)) < 2:
            continue
        rep_id = b.get("representative_evidence_id")
        member_ids = list(b.get("member_evidence_ids") or [])
        if rep_id not in ev_id_to_idx or any(m not in ev_id_to_idx for m in member_ids):
            dropped += 1
            continue
        clusters.append(SimpleNamespace(
            representative_index=ev_id_to_idx[rep_id],
            member_indices=[ev_id_to_idx[m] for m in member_ids],
            corroboration_count=int(b.get("corroboration_count", len(member_ids))),
            member_hosts=list(b.get("member_hosts") or []),
        ))
    print(f"[bank] built {len(clusters)} clusters from {len(baskets)} baskets "
          f"(dropped {dropped} — id not resolvable in cp2 evidence)")
    return clusters


async def main() -> None:
    with open(CP2_PATH, encoding="utf-8") as fh:
        cp2 = json.load(fh)
    with open(CP3_PATH, encoding="utf-8") as fh:
        cp3 = json.load(fh)

    evidence = list(cp2["evidence_for_gen"])
    question = str(cp2.get("question") or cp3.get("question") or "")
    domain = str(cp2.get("domain") or cp3.get("domain") or "")
    payload = cp3["payload"]
    same_work_groups = payload.get("same_work_groups")
    ev_id_to_idx = {
        str(row.get("evidence_id")): i for i, row in enumerate(evidence) if row.get("evidence_id")
    }
    clusters = _build_clusters(payload["baskets"], ev_id_to_idx)

    print(f"[real-corpus] run_id={cp2.get('run_id')} domain={domain!r} "
          f"evidence_rows={len(evidence)} baskets={len(clusters)} "
          f"same_work_groups={len(same_work_groups or [])}")
    print(f"[real-corpus] question (first 200 chars): {question[:200]!r}")
    print(f"[real-corpus] agent_model={oa.outliner_agent_model()} "
          f"code_model={oa.outliner_code_model()} "
          f"max_turns={os.environ['PG_OUTLINE_AGENT_MAX_TURNS']} "
          f"wall_s={os.environ['PG_OUTLINE_AGENT_WALL_SECONDS']}")

    ev_ids_before = {str(r.get("evidence_id")) for r in evidence if r.get("evidence_id")}

    t0 = time.monotonic()
    parse_result, retry_attempted, in_tok, out_tok = await oa.run_outline_agent_or_legacy(
        question, evidence, oa.outliner_code_model(), 0.2, 131072,
        domain=domain, finding_clusters=clusters, same_work_groups=same_work_groups,
        checkpoint_dir=OUT_DIR,
    )
    elapsed = time.monotonic() - t0

    stats = parse_result.digest_stats.get("outline_agent", {})
    print(f"\n=== REAL-CORPUS RUN RESULT (elapsed {elapsed:.1f}s) ===")
    print(f"turns={stats.get('turns')} ev_before={len(ev_ids_before)} "
          f"ev_after={stats.get('ev_store_size')} "
          f"new_evidence={stats.get('new_evidence_count')}")
    print("\nGAP LEDGER:")
    for t in stats.get("gap_ledger", []):
        print(f"  {t}")
    print("\nDISCLOSURES:")
    for d in stats.get("disclosures", []):
        print(f"  - {d}")
    print("\nFINAL OUTLINE:")
    for p in parse_result.plans:
        title = oa._plan_field(p, "title", "")  # noqa: SLF001 — harness, same-repo reuse
        ev_ids = oa._plan_field(p, "ev_ids", []) or []  # noqa: SLF001
        print(f"  - {title!r}: {len(ev_ids)} ev_ids")

    search_calls = sum(
        1 for d in stats.get("disclosures", []) if d.startswith("search_more_evidence[")
    )
    checklist_events = sum(
        1 for d in stats.get("disclosures", []) if d.startswith("checklist[")
    )
    result = {
        "run_id": cp2.get("run_id"),
        "question_prefix": question[:300],
        "domain": domain,
        "elapsed_s": round(elapsed, 1),
        "seed_evidence_rows": len(ev_ids_before),
        "baskets_fed": len(clusters),
        "turns": stats.get("turns"),
        "ev_before": len(ev_ids_before),
        "ev_after": stats.get("ev_store_size"),
        "new_evidence_count": stats.get("new_evidence_count"),
        "search_more_evidence_calls": search_calls,
        "checklist_events": checklist_events,
        "unfilled_gaps": stats.get("unfilled_gaps"),
        "final_section_ev_counts": {
            oa._plan_field(p, "title", ""): len(oa._plan_field(p, "ev_ids", []) or [])  # noqa: SLF001
            for p in parse_result.plans
        },
        "disclosures": stats.get("disclosures"),
        "gap_ledger": stats.get("gap_ledger"),
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "real_corpus_result.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    print(f"\n[real-corpus] wrote {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
