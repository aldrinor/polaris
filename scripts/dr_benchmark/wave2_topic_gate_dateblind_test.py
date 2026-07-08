"""I-deepfix-001 drb_72: prove the date-blind topic-gate fix on the FROZEN box2 corpus, 1 real judge call.

Fable design: run classify_topic_relevance with the FIXED (date-blind) prompt against the production
judge model on the seminal on-topic papers + known junk. PASS iff:
  - seminal on-topic rows (GPTs-are-GPTs, World Bank, Humlum, Brynjolfsson) are judged ON
    (topic_offtopic_demoted stamped False by the rescue path — un-buried),
  - genuine junk (funeral / reading-for-pleasure / ocean-alkalinity) is judged OFF (True).
Usage: PYTHONPATH=/c/POLARIS python <this> <corpus_snapshot.json>
Needs OPENROUTER_API_KEY in env (real, tiny, ~1 batch call).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.getcwd())
os.environ.setdefault("PG_SCOPE_TOPIC_GATE", "1")
os.environ.setdefault("PG_TOPIC_GATE_RESCUE_ON_STAMP", "1")

from src.polaris_graph.retrieval import topic_relevance_gate as tg  # noqa: E402
from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: E402

SNAP = sys.argv[1] if len(sys.argv) > 1 else "corpus_snapshot.json"
rows_all = {r.get("evidence_id"): r for r in (json.load(open(SNAP, encoding="utf-8")).get("evidence_for_gen") or [])}

QUESTION = ("The impact of Generative AI on the future labor market — based on academic research "
            "published before June 2023, summarizing positive views, negative views, specific "
            "challenges, and future opportunities regarding Generative AI's impact on employment.")

SEMINAL = ["ev_882", "ev_1018", "ev_1153", "ev_894"]        # must be judged ON
# genuine off-topic: pick rows whose title is clearly a different field
JUNK = [eid for eid, r in rows_all.items()
        if re.search(r"reading for pleasure|ocean alkalinity|funeral|tree.?cover|face.?recogni",
                     (r.get("title") or ""), re.I)][:4]

pick = [e for e in SEMINAL if e in rows_all] + JUNK
sources = [dict(rows_all[e]) for e in pick]  # copies (so we can read the stamp)
print("testing rows:", pick)

import asyncio
model = os.environ.get("PG_SCOPE_TOPIC_MODEL") or os.environ.get("PG_GENERATOR_MODEL") or "z-ai/glm-5.2"


def llm_callable(prompt):
    async def _run():
        c = OpenRouterClient(model=model)
        try:
            r = await c.generate(prompt=prompt, max_tokens=1200, temperature=0.0)
            return (r.content or "").strip()
        finally:
            if hasattr(c, "close"):
                try:
                    await c.close()
                except Exception:
                    pass
    return asyncio.run(_run())


res = tg.classify_topic_relevance(sources, QUESTION, llm_callable=llm_callable, batch_size=25)

fails = []
for e in pick:
    row = next((r for r in sources if r.get("evidence_id") == e), {})
    stamp = row.get("topic_offtopic_demoted")
    is_seminal = e in SEMINAL
    verdict = "ON" if stamp is False else ("OFF" if stamp is True else "UNJUDGED(None)")
    print(f"  {e:8} seminal={is_seminal!s:5} topic_offtopic_demoted={stamp!r:6} -> {verdict}")
    if is_seminal and stamp is True:
        fails.append(f"{e} seminal judged OFF")
    if (not is_seminal) and stamp is not True:
        fails.append(f"{e} junk NOT judged OFF (got {stamp})")

print("\nRESULT:", "GREEN" if not fails else "FAILS=" + "; ".join(fails))
sys.exit(1 if fails else 0)
