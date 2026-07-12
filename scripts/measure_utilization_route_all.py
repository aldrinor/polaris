#!/usr/bin/env python3
"""GHOST MEASUREMENT — basket UNDER-UTILIZATION, isolated deterministically.

Builds REAL, verifiable ClaimBaskets from the corrected corpus (evidence_id + verbatim
direct_quote so ``build_verified_span_draft`` emits a real [#ev]-tokened sentence that
re-passes the UNCHANGED strict_verify), a FIXED thematic outline, and a sparse per-section
primary assignment (mimicking the live LLM outline that assigns only a handful of ev_ids
per section). Then measures, with NO LLM and NO network (PG_STRICT_VERIFY_ENTAILMENT off),
the compose-side utilization A/B:

  ARM A  route_all OFF (banked default)  -> baskets rendered, verified sentences, words
  ARM B  route_all ON  (PG_ROUTE_ALL_BASKETS=1) -> same

The ONLY variable between arms is ``PG_ROUTE_ALL_BASKETS`` (and its companion off-topic
delete gate), so the delta is a CLEAN, confound-free measurement of the utilization lever
(the live agentic run varies its outline+retrieval between runs, which confounds a live
A/B — see WHEEL_PROGRESS STEP 3). Faithfulness is byte-identical between arms: every
rendered sentence is a verbatim corpus span carrying its own [#ev] token.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

# Deterministic verification only — no entailment judge, no network.
os.environ.pop("PG_STRICT_VERIFY_ENTAILMENT", None)

from src.polaris_graph.generator.provenance_generator import verify_sentence_provenance  # noqa: E402
from src.polaris_graph.generator.verified_compose import (  # noqa: E402
    _compose_section_per_basket,
    _section_baskets_for_compose,
    build_verified_span_draft,
    route_orphan_baskets_to_section_plans,
)
from src.polaris_graph.generator.multi_section_generator import SectionPlan  # noqa: E402
from src.polaris_graph.synthesis.credibility_pass import (  # noqa: E402
    BasketMember,
    ClaimBasket,
    CredibilityAnalysis,
    MEMBER_TIER_ENTAILMENT_VERIFIED,
)

_STOP = frozenset(
    "the and for that this with from have has had was were are been will would could "
    "should their there these those which while when where what who whom into than then "
    "such also not but its our your his her they them some more most over under between "
    "among per via about each any all study studies effect effects".split()
)
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")


def _cw(text: str) -> set:
    return {w.lower() for w in _WORD.findall(text or "") if w.lower() not in _STOP}


# A FIXED thematic outline (titles+focus mirror the banked step3_control report so the
# section->basket topical routing is realistic; NOTHING task-specific is hardcoded into the
# compose engine — these are just plan objects handed to the SAME production functions).
_OUTLINE = [
    ("Task-Based Frameworks and Displacement-Reinstatement",
     "automation tasks displacement reinstatement labor demand framework"),
    ("Occupational Exposure and Susceptibility to AI",
     "occupational exposure susceptibility generative AI large language models tasks"),
    ("Empirical Evidence on Employment and Labor Demand",
     "employment labor demand jobs empirical estimates workers hiring"),
    ("Productivity Effects of Generative AI",
     "productivity augmentation output performance generative AI workers gains"),
    ("Wage Inequality, Skill Demand, and Labor Polarization",
     "wage inequality skill demand polarization earnings distribution workers"),
    ("Policy Implications and Frameworks for Managing Disruption",
     "policy regulation reskilling training transition governance frameworks"),
    ("Cross-Study Synthesis and Contradictions",
     "cross study synthesis agreement disagreement contradiction convergence conflict findings"),
]


def _build_baskets(corpus):
    ev = corpus["evidence"]
    pool = {}
    for r in ev:
        eid = str(r.get("evidence_id") or "")
        if eid:
            pool[eid] = r
    baskets = []
    for cl in corpus.get("finding_clusters") or []:
        try:
            midx = json.loads(cl["member_indices"]) if isinstance(cl["member_indices"], str) else cl["member_indices"]
        except Exception:
            continue
        rep = int(cl.get("representative_index", midx[0] if midx else 0))
        members = []
        seen = set()
        for i in midx:
            if not (0 <= i < len(ev)):
                continue
            row = ev[i]
            eid = str(row.get("evidence_id") or "")
            if not eid or eid in seen:
                continue
            seen.add(eid)
            quote = str(row.get("direct_quote") or row.get("statement") or "").strip()
            if not quote:
                continue
            members.append(BasketMember(
                evidence_id=eid, source_url=str(row.get("source_url") or ""),
                source_tier=str(row.get("tier") or ""), origin_cluster_id=eid,
                credibility_weight=1.0, authority_score=1.0,
                span=(0, len(quote)), direct_quote=quote, span_verdict="SUPPORTS",
                member_tier=MEMBER_TIER_ENTAILMENT_VERIFIED,
            ))
        if not members:
            continue
        rep_row = ev[rep] if 0 <= rep < len(ev) else ev[midx[0]]
        claim = str(rep_row.get("statement") or rep_row.get("title") or "").strip()
        baskets.append(ClaimBasket(
            claim_cluster_id=str(cl.get("claim_group_id") or f"cg_{rep}"),
            claim_text=claim, subject=claim[:120], predicate="",
            supporting_members=members, refuter_cluster_ids=(),
            weight_mass=float(len(members)), total_clustered_origin_count=len(members),
            verified_support_origin_count=len(members),
            basket_verdict="full",
        ))
    return pool, baskets


def _assign_primary(baskets, pool, cap_per_section):
    """Sparse per-section primary assignment: each basket's rep member is scored against every
    section by claim/title content-word overlap; the top ``cap_per_section`` baskets per section
    (highest overlap) contribute their member ev_ids. Mimics the live LLM outline that lists only
    a handful of ev_ids per section (the throttle that stranded ~90% of baskets)."""
    plans = [SectionPlan(title=t, focus=f, ev_ids=[]) for t, f in _OUTLINE]
    plan_words = [_cw(t + " " + f) for t, f in _OUTLINE]
    scored = [[] for _ in plans]
    for b in baskets:
        bw = _cw(b.claim_text)
        best_i, best_o = -1, 0
        for i, pw in enumerate(plan_words):
            o = len(bw & pw)
            if o > best_o:
                best_o, best_i = o, i
        if best_i >= 0:
            scored[best_i].append((best_o, b))
    for i, plan in enumerate(plans):
        top = sorted(scored[i], key=lambda x: x[0], reverse=True)[:cap_per_section]
        ids = []
        for _o, b in top:
            for m in b.supporting_members:
                if m.evidence_id not in ids:
                    ids.append(m.evidence_id)
        plan.ev_ids = ids
    return plans


def _writer_null(_basket, _pool):
    return ""  # force the production K-span verbatim fallback (deterministic)


def _compose_and_count(plans, cred, pool):
    rendered_baskets = set()
    total_sentences = 0
    total_words = 0
    per_section = []
    for plan in plans:
        sb = _section_baskets_for_compose(plan, cred, evidence_pool=pool)
        composed = _compose_section_per_basket(
            sb, pool, writer_fn=_writer_null, verify_fn=verify_sentence_provenance,
        )
        sec_sents = 0
        sec_words = 0
        sec_rendered = 0
        for b, text in zip(sb, composed):
            if text and text.strip():
                sec_rendered += 1
                rendered_baskets.add(b.claim_cluster_id)
                n = len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()])
                sec_sents += n
                sec_words += len(text.split())
        total_sentences += sec_sents
        total_words += sec_words
        per_section.append((plan.title, len(sb), sec_rendered, sec_sents, sec_words))
    return {
        "baskets_rendered": len(rendered_baskets),
        "sentences": total_sentences,
        "words": total_words,
        "per_section": per_section,
    }


def main():
    corpus_path = _REPO / "data/cp4_corpus_s3gear_329.corrected.json"
    corpus = json.loads(corpus_path.read_text())
    pool, baskets = _build_baskets(corpus)
    cap = int(os.getenv("CAP_PER_SECTION", "6"))
    print(f"corpus baskets built (verifiable) = {len(baskets)} / {len(corpus.get('finding_clusters') or [])}"
          f"  | evidence rows = {len(pool)}  | cap_per_section = {cap}")

    cred = CredibilityAnalysis(
        credibility_by_evidence={}, origin_by_evidence={}, claims=[], edges=[],
        weight_mass=[], baskets=baskets,
    )

    # ARM A — route_all OFF
    os.environ["PG_ROUTE_ALL_BASKETS"] = "0"
    plans_a = _assign_primary(baskets, pool, cap)
    a = _compose_and_count(plans_a, cred, pool)

    # ARM B — route_all ON (companion off-topic delete gate uses corpus judge dispositions; none here)
    os.environ["PG_ROUTE_ALL_BASKETS"] = "1"
    plans_b = _assign_primary(baskets, pool, cap)
    plans_b = route_orphan_baskets_to_section_plans(
        plans_b, cred, section_plan_cls=SectionPlan,
    )
    b = _compose_and_count(plans_b, cred, pool)

    def _fmt(tag, r):
        print(f"\n=== ARM {tag} ===")
        print(f"  baskets_rendered = {r['baskets_rendered']}   verified_sentences = {r['sentences']}   words = {r['words']}")
        for title, nsb, nren, ns, nw in r["per_section"]:
            print(f"    - {title[:46]:46}  baskets_in_section={nsb:3}  rendered={nren:3}  sents={ns:3}  words={nw:4}")

    _fmt("A route_all=OFF", a)
    _fmt("B route_all=ON ", b)
    print("\n=== DELTA (B - A) ===")
    print(f"  baskets_rendered: {a['baskets_rendered']} -> {b['baskets_rendered']}  (+{b['baskets_rendered']-a['baskets_rendered']})")
    print(f"  verified_sentences: {a['sentences']} -> {b['sentences']}  (+{b['sentences']-a['sentences']})")
    print(f"  words: {a['words']} -> {b['words']}  (+{b['words']-a['words']})")
    out = {"corpus_baskets": len(baskets), "cap_per_section": cap, "arm_a_route_off": a, "arm_b_route_on": b}
    (_REPO / "outputs").mkdir(exist_ok=True)
    (_REPO / "outputs" / "utilization_route_all_measure.json").write_text(json.dumps(out, indent=2))
    print("\nWROTE outputs/utilization_route_all_measure.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
