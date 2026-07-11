"""MATCHED plain-vs-agentic comparison — real AI-labor DRB-72 corpus, IDENTICAL seed.

Fable iter-2 P0 direction (verbatim): "Run a MATCHED plain-vs-agentic comparison on the real
AI-labor corpus using the SAME seed — pass the real deliverable_spec so the plain seed equals the
canonical 4-section DRB-72 structure, run plain cp4 and agentic cp4 from that identical seed, and
show the agentic side adds genuine on-topic coverage the plain lacks (not a single-section pad)."

CANONICAL STRUCTURE (config/benchmark/task_output_contracts.yaml drb_72_ai_labor.required_sections
-- verbatim from the DeepResearch-Bench-II gold task72 prompt: "positive views, negative views,
specific challenges, and future opportunities" as separate sections):
  ["Positive Views", "Negative Views", "Specific Challenges", "Future Opportunities"]

PLAIN  = _call_outline(...) directly, PG_OUTLINE_AGENT unset (legacy single-shot outline call),
         deliverable_spec.required_sections = the 4 titles above.
AGENTIC = run_outline_agent_or_legacy(...) with PG_OUTLINE_AGENT=1, IDENTICAL question/evidence/
         domain/clusters/same_work_groups/deliverable_spec — the only variable is agent ON/OFF.

Both start from a DEEP COPY of the SAME 654-row cp2 evidence + 41-basket cp3 snapshot (run_id
SWEEP_workforce_drb_72_ai_labor_1783476454) so the comparison is apples-to-apples: same corpus,
same required structure, same model family. FAIL LOUD on any exception (LAW II).
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import random
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, "/workspace/outline_agent_wt")

from dotenv import load_dotenv  # noqa: E402
load_dotenv("/workspace/POLARIS/.env", override=True)

os.environ.setdefault("PG_OUTLINE_MAX_TOKENS", "131072")
os.environ.setdefault("PG_OUTLINE_REASONING_MAX_TOKENS", "32768")
# Production defaults (docs/fsr_build_plan.md AGENTIC OUTLINER LOOP section): 24 turns / 900s wall.
# Matched comparison uses the REAL production budget, not an artificially shrunk smoke budget.
os.environ.setdefault("PG_OUTLINE_AGENT_MAX_TURNS", "24")
os.environ.setdefault("PG_OUTLINE_AGENT_WALL_SECONDS", "900")

CP2_PATH = "/workspace/s2s3_wt/outputs/s2s3_iter1/s2/cp2_corpus_snapshot.json"
CP3_PATH = "/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json"
OUT_DIR = "/workspace/outline_agent_wt/outputs/matched_comparison_run"

REQUIRED_SECTIONS = ["Positive Views", "Negative Views", "Specific Challenges", "Future Opportunities"]


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


def _section_ev_counts(plans, plan_field) -> dict:
    return {
        plan_field(p, "title", ""): len(plan_field(p, "ev_ids", []) or [])
        for p in plans
    }


async def run_plain(question, evidence, domain, clusters, same_work_groups, deliverable_spec) -> dict:
    from src.polaris_graph.generator.multi_section_generator import _call_outline

    ev_ids_before = {str(r.get("evidence_id")) for r in evidence if r.get("evidence_id")}
    t0 = time.monotonic()
    parse_result, retry_attempted, in_tok, out_tok = await _call_outline(
        question, evidence, "deepseek/deepseek-v4-pro", 0.2, 131072,
        domain=domain, finding_clusters=clusters, deliverable_spec=deliverable_spec,
        same_work_groups=same_work_groups,
    )
    elapsed = time.monotonic() - t0
    titles = [str(getattr(p, "title", "")) for p in parse_result.plans]
    section_counts = {
        str(getattr(p, "title", "")): len(getattr(p, "ev_ids", []) or [])
        for p in parse_result.plans
    }
    print(f"\n=== PLAIN RUN RESULT (elapsed {elapsed:.1f}s) ===")
    print(f"titles={titles}")
    print(f"ok={parse_result.ok} reason_codes={getattr(parse_result, 'reason_codes', None)}")
    for t, c in section_counts.items():
        print(f"  - {t!r}: {c} ev_ids")
    return {
        "elapsed_s": round(elapsed, 1),
        "ok": parse_result.ok,
        "reason_codes": list(getattr(parse_result, "reason_codes", []) or []),
        "titles": titles,
        "seed_evidence_rows": len(ev_ids_before),
        "final_evidence_rows": len(ev_ids_before),  # plain never fetches new rows
        "section_ev_counts": section_counts,
        "retry_attempted": retry_attempted,
    }


async def run_agentic(question, evidence, domain, clusters, same_work_groups, deliverable_spec) -> dict:
    os.environ["PG_OUTLINE_AGENT"] = "1"
    from src.polaris_graph.outline import outline_agent as oa

    ev_ids_before = {str(r.get("evidence_id")) for r in evidence if r.get("evidence_id")}
    t0 = time.monotonic()
    parse_result, retry_attempted, in_tok, out_tok = await oa.run_outline_agent_or_legacy(
        question, evidence, oa.outliner_code_model(), 0.2, 131072,
        domain=domain, finding_clusters=clusters, deliverable_spec=deliverable_spec,
        same_work_groups=same_work_groups, checkpoint_dir=OUT_DIR,
    )
    elapsed = time.monotonic() - t0
    stats = parse_result.digest_stats.get("outline_agent", {})
    titles = [oa._plan_field(p, "title", "") for p in parse_result.plans]  # noqa: SLF001
    section_counts = {
        oa._plan_field(p, "title", ""): len(oa._plan_field(p, "ev_ids", []) or [])  # noqa: SLF001
        for p in parse_result.plans
    }
    print(f"\n=== AGENTIC RUN RESULT (elapsed {elapsed:.1f}s) ===")
    print(f"titles={titles}")
    print(f"turns={stats.get('turns')} ev_before={len(ev_ids_before)} "
          f"ev_after={stats.get('ev_store_size')} new_evidence={stats.get('new_evidence_count')}")
    for t, c in section_counts.items():
        print(f"  - {t!r}: {c} ev_ids")
    print("disclosures:")
    for d in stats.get("disclosures", []):
        print(f"  - {d}")
    seed_ev_by_title = stats.get("seed_ev_by_title", {})
    return {
        "elapsed_s": round(elapsed, 1),
        "turns": stats.get("turns"),
        "seed_evidence_rows": len(ev_ids_before),
        "final_evidence_rows": stats.get("ev_store_size"),
        "new_evidence_count": stats.get("new_evidence_count"),
        "titles": titles,
        "section_ev_counts": section_counts,
        "seed_section_ev_counts": {t: len(v) for t, v in seed_ev_by_title.items()},
        "search_more_evidence_calls": sum(
            1 for d in stats.get("disclosures", []) if d.startswith("search_more_evidence[")
        ),
        "sections_touched_by_search": sorted({
            d.split("section '")[1].split("'")[0]
            for d in stats.get("disclosures", [])
            if d.startswith("auto-assign: routed") and "section '" in d
        }),
        "unfilled_gaps": stats.get("unfilled_gaps"),
        "disclosures": stats.get("disclosures"),
        "gap_ledger": stats.get("gap_ledger"),
    }


async def run_scenario(
    label: str, base_evidence: list[dict], baskets: list[dict], question: str, domain: str,
    same_work_groups, deliverable_spec,
) -> dict:
    ev_id_to_idx = {
        str(row.get("evidence_id")): i for i, row in enumerate(base_evidence)
        if row.get("evidence_id")
    }
    print(f"\n{'#' * 80}\n[matched-comparison] SCENARIO: {label} "
          f"(evidence_rows={len(base_evidence)})\n{'#' * 80}")

    # Independent deep copies so neither run's in-place mutation touches the other's corpus.
    evidence_plain = copy.deepcopy(base_evidence)
    evidence_agentic = copy.deepcopy(base_evidence)
    clusters_plain = _build_clusters(baskets, ev_id_to_idx)
    clusters_agentic = _build_clusters(baskets, ev_id_to_idx)

    plain_result = await run_plain(
        question, evidence_plain, domain, clusters_plain, same_work_groups, deliverable_spec,
    )
    agentic_result = await run_agentic(
        question, evidence_agentic, domain, clusters_agentic, same_work_groups, deliverable_spec,
    )

    # §-1.1 HONESTY FIX (found via a real live run, not anticipated): raw final-ev_id-COUNT delta
    # between plain and agentic is a CONTAMINATED signal — `run_plain` and `run_agentic` each call
    # `_call_outline` as an INDEPENDENT, nondeterministic LLM sample from the SAME 654-row pool,
    # so a per-section count difference can be pure seed-call sampling noise, not anything the
    # agent loop did. The uncontaminated, structurally-guaranteed signal for "the agentic side
    # added genuine coverage the plain side structurally CANNOT have" is `new_evidence_count`:
    # plain NEVER calls search_more_evidence (it has no loop), so ANY genuinely new fetched row
    # (new URL, beyond the original 654) is unambiguous agentic value-add, immune to seed noise.
    # A zero-search agentic run (checklist correctly found nothing missing) is DISCLOSED as
    # exactly that — not silently reframed as "gain" via the noisy count delta.
    new_ev_by_section: dict[str, int] = {}
    for d in agentic_result.get("disclosures", []) or []:
        if d.startswith("auto-assign: routed") and "section '" in d:
            n = int(d.split("routed")[1].split("new")[0].strip())
            sec = d.split("section '")[1].split("'")[0]
            new_ev_by_section[sec] = new_ev_by_section.get(sec, 0) + n
    genuine_new_evidence_count = agentic_result.get("new_evidence_count") or 0
    sections_with_genuine_gain = sorted(new_ev_by_section.keys())

    delta = {}
    for title in REQUIRED_SECTIONS:
        plain_c = plain_result["section_ev_counts"].get(title, 0)
        agentic_c = agentic_result["section_ev_counts"].get(title, 0)
        delta[title] = {
            "plain": plain_c, "agentic": agentic_c,
            "raw_count_delta_CONTAMINATED_BY_SEED_NOISE": agentic_c - plain_c,
            "genuine_new_fetched_rows": new_ev_by_section.get(title, 0),
        }

    result = {
        "question_prefix": question[:300],
        "domain": domain,
        "required_sections": REQUIRED_SECTIONS,
        "plain": plain_result,
        "agentic": agentic_result,
        "section_delta": delta,
        "genuine_new_evidence_count": genuine_new_evidence_count,
        "sections_with_genuine_gain": sections_with_genuine_gain,
        "single_section_pad_only": len(sections_with_genuine_gain) <= 1,
        "no_genuine_gain_this_run": genuine_new_evidence_count == 0,
    }
    result["scenario"] = label
    print(f"\n=== [{label}] SECTION TABLE (raw counts are SEED-NOISE-CONTAMINATED — "
          f"read genuine_new_fetched_rows) ===")
    for t, d in delta.items():
        print(f"  {t!r}: plain={d['plain']} agentic={d['agentic']} "
              f"raw_delta(noisy)={d['raw_count_delta_CONTAMINATED_BY_SEED_NOISE']:+d} "
              f"genuine_new_fetched_rows={d['genuine_new_fetched_rows']}")
    print(f"genuine_new_evidence_count={genuine_new_evidence_count} "
          f"(search_more_evidence_calls={agentic_result.get('search_more_evidence_calls')})")
    print(f"sections_with_genuine_gain={sections_with_genuine_gain}")
    print(f"no_genuine_gain_this_run={result['no_genuine_gain_this_run']} "
          "(True means: on THIS seed, the checklist correctly found nothing missing — "
          "report honestly, do not spin the noisy count delta as evidence of agentic value)")
    return result


async def main() -> None:
    with open(CP2_PATH, encoding="utf-8") as fh:
        cp2 = json.load(fh)
    with open(CP3_PATH, encoding="utf-8") as fh:
        cp3 = json.load(fh)

    full_evidence = list(cp2["evidence_for_gen"])
    question = str(cp2.get("question") or cp3.get("question") or "")
    domain = str(cp2.get("domain") or cp3.get("domain") or "")
    payload = cp3["payload"]
    same_work_groups = payload.get("same_work_groups")
    baskets = payload["baskets"]
    deliverable_spec = {"required_sections": REQUIRED_SECTIONS}

    print(f"[matched-comparison] run_id={cp2.get('run_id')} domain={domain!r} "
          f"evidence_rows={len(full_evidence)} baskets(raw)={len(baskets)} "
          f"required_sections={REQUIRED_SECTIONS}")
    print(f"[matched-comparison] question (first 200 chars): {question[:200]!r}")

    full_result = await run_scenario(
        "FULL_CORPUS (654 rows)", full_evidence, baskets, question, domain,
        same_work_groups, deliverable_spec,
    )

    # THINNED scenario: deterministic ~18% subsample (fixed seed=42, reproducible) of the SAME
    # real corpus. Gives the loop genuine headroom to demonstrate real value-add — the full
    # corpus already densely covers all 4 required facets (proven by the FULL_CORPUS run above:
    # genuine_new_evidence_count=0, checklist correctly declined), so that scenario alone cannot
    # show what a THIN corpus + working agentic loop does. Baskets whose members fall outside the
    # subsample are dropped from the cluster list (same_work_groups threads through unchanged —
    # it's read-only corroboration metadata, not filtered).
    rng = random.Random(42)
    thin_evidence = list(full_evidence)
    rng.shuffle(thin_evidence)
    thin_n = max(60, len(thin_evidence) // 5)  # ~18% of 654 ~= 120 rows
    thin_evidence = thin_evidence[:thin_n]
    thin_ids = {str(r.get("evidence_id")) for r in thin_evidence if r.get("evidence_id")}
    thin_baskets = [
        b for b in baskets
        if str(b.get("representative_evidence_id")) in thin_ids
        and all(str(m) in thin_ids for m in (b.get("member_evidence_ids") or []))
    ]
    print(f"\n[matched-comparison] THINNED subsample: {len(thin_evidence)} of "
          f"{len(full_evidence)} rows (seed=42), {len(thin_baskets)} of {len(baskets)} "
          "baskets survive intact")

    thin_result = await run_scenario(
        f"THINNED_CORPUS ({len(thin_evidence)} rows, seed=42)", thin_evidence, thin_baskets,
        question, domain, same_work_groups, deliverable_spec,
    )

    combined = {"full_corpus": full_result, "thinned_corpus": thin_result}
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "matched_comparison_result.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(combined, fh, indent=2, default=str)
    print(f"\n[matched-comparison] wrote {out_path}")
    print("\n" + "#" * 80)
    print("FINAL SUMMARY (both scenarios)")
    print("#" * 80)
    for label, r in combined.items():
        print(f"  {label}: genuine_new_evidence_count={r['genuine_new_evidence_count']} "
              f"sections_with_genuine_gain={r['sections_with_genuine_gain']} "
              f"no_genuine_gain_this_run={r['no_genuine_gain_this_run']}")


if __name__ == "__main__":
    asyncio.run(main())
