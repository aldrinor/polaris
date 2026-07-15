"""S5 LIVE COMPOSE (ghost-free) — produce the FIRST clean cp5 with REAL composed prose.

Reuses the real drb_72 checkpoints:
  cp2 corpus snapshot  -> evidence_pool (evidence_for_gen rows, with spans)
  cp3 basket snapshot  -> consolidated baskets (member evidence_ids)  [NO re-run of the
                          ~996-member LLM basket assembly; that is the s3 loop's locked checkpoint]
  cp4 outline snapshot -> section plans (title / focus / ev_ids)

Runs the REAL production per-section compose unit (multi_section_generator._run_section) with the
ghost-free settings ON:
  PG_COMPOSE_NO_RAW_SPAN_FALLBACK=1  (no verbatim raw-span dump on failure)
  PG_SECTION_BASKET_MAP=1            (deterministic basket->section placement)
  PG_SYNTH_PRIMARY=1                 (abstractive LLM writer is the PRIMARY body producer)
  PG_STRICT_VERIFY_ENTAILMENT=enforce (CONTEXT-level NLI entailment is the faithfulness leg)

The lexical content-word-overlap gate + verbatim-fallback-copy (the "ghost") is DELETED at
commit 4879680; this script must NOT reintroduce it.

GENERALIZATION: nothing here is drb_72-specific. It reads whatever cp2/cp3/cp4 are passed. No
question branch, no corpus-tuned constant, no cap/target/thinner.
"""
import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path


def _text_of(row: dict) -> str:
    return str((row or {}).get("direct_quote") or (row or {}).get("statement") or "")


def build_baskets(cp3_baskets, evidence_pool):
    """Reconstruct ClaimBasket objects from cp3 (member evidence_ids) + the evidence_pool (spans).

    Each member's own span text is the evidence row's verified span (direct_quote|statement), so the
    downstream _member_global_span locates it at offset 0 and the region gate is the whole row; the
    binding faithfulness check is strict_verify (numeric + NLI entailment) per composed sentence.
    """
    from src.polaris_graph.synthesis.credibility_pass import (
        BasketMember,
        ClaimBasket,
        MEMBER_TIER_ENTAILMENT_VERIFIED,
    )
    baskets = []
    seen = {}
    for i, b in enumerate(cp3_baskets):
        rep = str(b.get("representative_evidence_id", "") or "")
        cid = rep if (rep and rep not in seen) else f"{rep or 'b0'}#{i}"
        seen[cid] = True
        members = []
        for eid in (b.get("member_evidence_ids") or []):
            eid = str(eid)
            row = evidence_pool.get(eid)
            if not row:
                continue
            text = _text_of(row)
            if not text.strip():
                continue
            members.append(BasketMember(
                evidence_id=eid,
                source_url=str(row.get("source_url") or ""),
                source_tier=str(row.get("tier") or ""),
                origin_cluster_id=eid,
                credibility_weight=1.0,
                authority_score=1.0,
                span=(0, len(text)),
                direct_quote=text,
                span_verdict="SUPPORTS",
                member_tier=MEMBER_TIER_ENTAILMENT_VERIFIED,
            ))
        if not members:
            continue
        baskets.append(ClaimBasket(
            claim_cluster_id=cid,
            claim_text=str(b.get("representative_statement", "") or ""),
            subject="",
            predicate="",
            supporting_members=members,
            refuter_cluster_ids=(),
            weight_mass=float(b.get("corroboration_count", 0) or 0) or 1.0,
            total_clustered_origin_count=len(members),
            verified_support_origin_count=len(members),
            basket_verdict="full",
        ))
    return baskets


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cp2", required=True)
    ap.add_argument("--cp3", required=True)
    ap.add_argument("--cp4", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only-section", type=int, default=-1, help="smoke: run only this section index")
    args = ap.parse_args()

    from src.polaris_graph.generator.multi_section_generator import SectionPlan, _run_section
    from src.polaris_graph.synthesis.credibility_pass import CredibilityAnalysis
    from src.polaris_graph.synthesis.section_basket_map import (
        build_section_basket_map,
        section_basket_map_enabled,
    )

    cp2 = json.load(open(args.cp2, encoding="utf-8"))
    cp3 = json.load(open(args.cp3, encoding="utf-8"))
    cp4 = json.load(open(args.cp4, encoding="utf-8"))

    question = cp2.get("question") or ""
    evidence_rows = cp2["evidence_for_gen"]
    # SPAN-SIZE bound (LAW VI, env-configurable) — a prompt-context tractability bound applied
    # UNIFORMLY to every source, NOT a source/breadth cap (§-1.3): a handful of rows carry a
    # ~25k-char full-document over-extraction in `direct_quote` that balloons the per-basket writer
    # prompt to ~18k tokens and stalls the call under shared-account contention. Truncating the SPAN
    # a source is synthesized-from to its leading `span_cap` chars keeps the substantive content
    # (abstract/intro) while making the call tractable; strict_verify still checks entailment against
    # this same span. Generalizes to any question — never drops a source, never targets a number.
    span_cap = int(os.environ.get("PG_S5_SPAN_CHAR_CAP", "8000"))
    evidence_pool = {}
    for r in evidence_rows:
        eid = r.get("evidence_id")
        if not eid:
            continue
        r = dict(r)
        dq = str(r.get("direct_quote") or "")
        if len(dq) > span_cap:
            r["direct_quote"] = dq[:span_cap]
        evidence_pool[str(eid)] = r
    cp3_baskets = cp3["payload"]["baskets"]
    plans_raw = cp4["payload"]["final_plans"]

    print(f"[load] question_len={len(question)} evidence_pool={len(evidence_pool)} "
          f"cp3_baskets={len(cp3_baskets)} plans={len(plans_raw)}", flush=True)

    baskets = build_baskets(cp3_baskets, evidence_pool)
    print(f"[baskets] reconstructed ClaimBaskets={len(baskets)} "
          f"(members total={sum(len(b.supporting_members) for b in baskets)})", flush=True)

    cred = CredibilityAnalysis(
        credibility_by_evidence={}, origin_by_evidence={}, claims=[], edges=[], weight_mass=[],
        baskets=baskets,
    )

    plans = [SectionPlan(title=str(p.get("title", "")), focus=str(p.get("focus", "")),
                         ev_ids=[str(e) for e in (p.get("ev_ids") or [])]) for p in plans_raw]

    # Deterministic basket->section map (same objects => cluster-id consistent).
    print(f"[map] section_basket_map_enabled={section_basket_map_enabled()}", flush=True)
    sbm_map = build_section_basket_map(baskets, plans, evidence_pool=evidence_pool)
    print(f"[map] stranded={sbm_map.stranded_count} residual_index={sbm_map.residual_section_index} "
          f"per_section_views={{k:len(v) for k,v in sbm_map.views_by_section.items()}}"
          .replace("{k:len(v) for k,v in sbm_map.views_by_section.items()}",
                   str({k: len(v) for k, v in sbm_map.views_by_section.items()})), flush=True)
    for idx, p in enumerate(plans):
        p._section_index = idx
        p._section_basket_map = sbm_map

    model = os.environ.get("PG_GENERATOR_MODEL", "z-ai/glm-5.2")
    section_max_tokens = int(os.environ.get("PG_SECTION_MAX_TOKENS", "64000"))
    section_temperature = float(os.environ.get("PG_SECTION_TEMPERATURE", "0.3"))
    min_kept_fraction = float(os.environ.get("PG_MIN_KEPT_FRACTION", "0.4"))

    sec_sema = asyncio.Semaphore(int(os.environ.get("PG_MAX_PARALLEL_SECTIONS", "2")))

    async def _compose_one(idx, section):
        async with sec_sema:
            t0 = time.time()
            print(f"[section {idx}] START title={section.title!r} ev_ids={len(section.ev_ids)}", flush=True)
            res = await _run_section(
                section, evidence_pool,
                model=model,
                temperature=section_temperature,
                max_tokens_per_section=section_max_tokens,
                min_kept_fraction=min_kept_fraction,
                credibility_analysis=cred,
                research_question=question,
            )
            dt = time.time() - t0
            vt = res.verified_text or ""
            print(f"[section {idx}] DONE {dt:.0f}s verified_chars={len(vt)} "
                  f"sentences_verified={res.sentences_verified} dropped={res.sentences_dropped} "
                  f"error={res.error!r} gap_stub={getattr(res,'is_gap_stub',False)}", flush=True)
            print(f"[section {idx}] OPENING: {vt[:600]}", flush=True)
            return {
                "section_index": idx,
                "title": res.title,
                "focus": res.focus,
                "ev_ids_assigned": res.ev_ids_assigned,
                "verified_text": vt,
                "sentences_verified": res.sentences_verified,
                "sentences_dropped": res.sentences_dropped,
                "regen_attempted": res.regen_attempted,
                "dropped_due_to_failure": res.dropped_due_to_failure,
                "is_gap_stub": getattr(res, "is_gap_stub", False),
                "error": res.error,
            }

    tasks = []
    for idx, section in enumerate(plans):
        if args.only_section >= 0 and idx != args.only_section:
            continue
        tasks.append(asyncio.ensure_future(_compose_one(idx, section)))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    section_drafts = []
    for r in results:
        if isinstance(r, dict):
            section_drafts.append(r)
        else:
            print(f"[section] EXCEPTION: {r!r}", flush=True)
    section_drafts.sort(key=lambda d: d["section_index"])

    cp3_sha = hashlib.sha256(Path(args.cp3).read_bytes()).hexdigest()
    cp4_sha = hashlib.sha256(Path(args.cp4).read_bytes()).hexdigest()
    cp2_sha = hashlib.sha256(Path(args.cp2).read_bytes()).hexdigest()
    envelope = {
        "schema_version": 1,
        "stage": "s5_generation_live_compose",
        "question_sha": cp4.get("question_sha"),
        "flag_slate": {k: os.environ.get(k) for k in [
            "PG_COMPOSE_NO_RAW_SPAN_FALLBACK", "PG_SECTION_BASKET_MAP", "PG_SYNTH_PRIMARY",
            "PG_ABSTRACTIVE_WRITER", "PG_VERIFIED_COMPOSE", "PG_VERIFIED_COMPOSE_MULTICITED",
            "PG_STRICT_VERIFY_ENTAILMENT", "PG_GENERATOR_MODEL", "PG_ENTAILMENT_MODEL",
        ]},
        "upstream": [
            {"stage": "corpus", "checkpoint": args.cp2, "sha": cp2_sha},
            {"stage": "basket", "checkpoint": args.cp3, "sha": cp3_sha},
            {"stage": "outline", "checkpoint": args.cp4, "sha": cp4_sha},
        ],
        "faithfulness_note": (
            "REAL live compose. Abstractive LLM writer drafts synthesis prose per basket; every "
            "composed sentence re-passes the UNCHANGED strict_verify (numeric + CONTEXT-level NLI "
            "entailment). The lexical content-word-overlap gate + verbatim raw-span fallback (the "
            "ghost) are DELETED at commit 4879680 and NOT reintroduced."
        ),
        "stats": {
            "evidence_pool": len(evidence_pool),
            "claim_baskets": len(baskets),
            "sections": len(section_drafts),
            "stranded_count": sbm_map.stranded_count,
        },
        "payload": {"section_drafts": section_drafts},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[WROTE] {args.out} bytes={Path(args.out).stat().st_size} sections={len(section_drafts)}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
