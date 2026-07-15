import asyncio
import json
import os
import time
import sys

sys.argv = ["x"]
from src.polaris_graph.generator.provenance_generator import verify_sentence_provenance as _vc_verify
from src.polaris_graph.generator.abstractive_writer import (
    abstractive_pre_pass, assert_activation_preconditions, make_writer_verify_fn,
)

# reconstruct baskets (same as driver)
sys.path.insert(0, "/workspace/clean_compose_wt/scripts")
import run_s5_live_compose as drv

cp2 = json.load(open("/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json", encoding="utf-8"))
cp3 = json.load(open("/workspace/POLARIS/outputs/s3_hamster_i1/cp3_basket_snapshot.json", encoding="utf-8"))
evidence_pool = {str(r["evidence_id"]): r for r in cp2["evidence_for_gen"] if r.get("evidence_id")}
baskets = drv.build_baskets(cp3["payload"]["baskets"], evidence_pool)

# pick 3 baskets that have members (member texts)
sample = baskets[:3]
for b in sample:
    tot = sum(len(m.direct_quote) for m in b.supporting_members)
    print(f"basket {b.claim_cluster_id[:30]} members={len(b.supporting_members)} member_text_chars={tot} claim={b.claim_text[:60]!r}", flush=True)

assert_activation_preconditions()
wv = make_writer_verify_fn(_vc_verify)


async def go():
    t = time.time()
    out = await abstractive_pre_pass(sample, evidence_pool, writer_verify_fn=wv, group_mode=True)
    print(f"pre_pass {time.time()-t:.1f}s drafted={len(out)}/{len(sample)}", flush=True)
    for k, v in out.items():
        print(f"--- draft for {k[:30]} ---\n{str(v)[:500]}\n", flush=True)


asyncio.run(go())
