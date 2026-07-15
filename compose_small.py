"""Focused, reliable REAL compose of a handful of section-0 baskets via the production
abstractive writer path, writing a cp5 with real composed synthesis prose.

Uses the SAME ghost-free production modules (abstractive_writer group_mode + strict_verify
entailment). Small-basket subset keeps the call count low enough to complete inside a
throttle-open window on the shared OpenRouter account.
"""
import asyncio
import json
import os
import time
import sys

sys.argv = ["x"]
from src.polaris_graph.generator.provenance_generator import verify_sentence_provenance as _vc_verify
from src.polaris_graph.generator.verified_compose import _compose_section_per_basket
from src.polaris_graph.generator.abstractive_writer import (
    abstractive_pre_pass, assert_activation_preconditions, make_writer_verify_fn,
    make_abstractive_writer_fn,
)
sys.path.insert(0, "/workspace/clean_compose_wt/scripts")
import run_s5_live_compose as drv

CP2 = "/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json"
CP3 = "/workspace/POLARIS/outputs/s3_hamster_i1/cp3_basket_snapshot.json"
CP4 = "/workspace/POLARIS/outputs/s4_downstream_iter2/cp4_outline_snapshot.json"
OUT = "/workspace/POLARIS/outputs/s5_clean_compose_opus/cp5_generation_snapshot.json"
SPAN_CAP = int(os.environ.get("PG_S5_SPAN_CHAR_CAP", "6000"))
MAXB = int(os.environ.get("MAXB", "6"))

cp2 = json.load(open(CP2, encoding="utf-8"))
cp3 = json.load(open(CP3, encoding="utf-8"))
cp4 = json.load(open(CP4, encoding="utf-8"))
question = cp2.get("question") or ""

pool = {}
for r in cp2["evidence_for_gen"]:
    eid = r.get("evidence_id")
    if not eid:
        continue
    r = dict(r)
    dq = str(r.get("direct_quote") or "")
    if len(dq) > SPAN_CAP:
        r["direct_quote"] = dq[:SPAN_CAP]
    pool[str(eid)] = r

baskets = drv.build_baskets(cp3["payload"]["baskets"], pool)
# section 0 ev_ids
plan0 = cp4["payload"]["final_plans"][0]
sec_ev = {str(e) for e in plan0.get("ev_ids", [])}
# baskets whose members intersect section 0, preferring SMALL member text (fast, throttle-friendly)
cand = []
for b in baskets:
    mem = {m.evidence_id for m in b.supporting_members}
    if mem & sec_ev:
        tot = sum(len(m.direct_quote) for m in b.supporting_members)
        cand.append((tot, b))
cand.sort(key=lambda x: x[0])
chosen = [b for _, b in cand[:MAXB]]
print(f"section0 title={plan0['title']!r} candidate_baskets={len(cand)} chosen={len(chosen)}", flush=True)
for b in chosen:
    print("  basket", b.claim_cluster_id[:34], "chars", sum(len(m.direct_quote) for m in b.supporting_members), flush=True)

assert_activation_preconditions()
wv = make_writer_verify_fn(_vc_verify)


async def go():
    t = time.time()
    pre = await abstractive_pre_pass(chosen, pool, writer_verify_fn=wv, group_mode=True)
    print(f"pre_pass {time.time()-t:.1f}s drafted={len(pre)}/{len(chosen)}", flush=True)
    writer_fn = make_abstractive_writer_fn(pre)
    # compose the section from these baskets (tokened + strict-verified per sentence)
    composed = _compose_section_per_basket(
        chosen, pool, writer_fn=writer_fn, verify_fn=wv, research_question=question,
    )
    body = composed if isinstance(composed, str) else " ".join(composed) if composed else ""
    print(f"composed_chars={len(body)}", flush=True)
    print("COMPOSED OPENING:", body[:900], flush=True)
    env = {
        "schema_version": 1,
        "stage": "s5_generation_live_compose_focused",
        "question_sha": cp4.get("question_sha"),
        "note": ("REAL live compose (focused small-basket subset of section 0) via the production "
                 "abstractive writer + strict_verify entailment; ghost removed at commit 4879680. "
                 "Subset chosen only to fit the shared-account OpenRouter throttle window; NOT a "
                 "quality/breadth cap."),
        "flag_slate": {k: os.environ.get(k) for k in [
            "PG_COMPOSE_NO_RAW_SPAN_FALLBACK", "PG_SECTION_BASKET_MAP", "PG_SYNTH_PRIMARY",
            "PG_ABSTRACTIVE_WRITER", "PG_STRICT_VERIFY_ENTAILMENT", "PG_GENERATOR_MODEL"]},
        "payload": {"section_drafts": [{
            "section_index": 0, "title": plan0["title"], "focus": plan0.get("focus", ""),
            "n_baskets": len(chosen), "n_drafted": len(pre),
            "verified_text": body,
        }]},
    }
    from pathlib import Path
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    Path(OUT).write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUT, "bytes", Path(OUT).stat().st_size, flush=True)


asyncio.run(go())
