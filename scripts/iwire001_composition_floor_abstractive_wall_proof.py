#!/usr/bin/env python3
"""FORCED-STALL teardown proof that the W6 outer wall-deadline ABANDONS an UNCANCELLABLE basket task
and that ``asyncio.run`` then completes with ZERO pending tasks (no shutdown hang), instead of wedging
the whole process at interpreter teardown.

WHY AN UNCANCELLABLE WEDGE (I-wire-001 W6 #1314): a plain ``await asyncio.sleep(30)`` is CANCELLABLE —
a bare ``t.cancel()`` tears it down, so it does NOT exercise the force-close path and is NOT a real
regression guard. The proven hang class is a task whose cancellation is SWALLOWED (httpx client teardown
that re-blocks, or any ``except CancelledError`` that awaits again). ``asyncio.run``'s shutdown calls
``_cancel_all_tasks`` which ``gather``-awaits EVERY still-pending task BEFORE ``loop.close()`` — so one
uncancellable task hangs the process at exit. This proof's stub catches CancelledError in the stuck
basket and RE-BLOCKS in a ``finally`` (await again) — so bare ``t.cancel()`` is provably insufficient.
The fix under test is the ported access_bypass detach/force-close (``_coro.close()`` raises GeneratorExit,
finalizing the task synchronously) applied at abandon time, which excludes the task from the await-list.

PROOF (mechanical, the one that failed before): "zero pending at shutdown" is NOT queryable after
``asyncio.run`` returns (the loop is closed). So we run ``asyncio.run(abstractive_pre_pass(...))`` in a
DAEMON THREAD and ``join(timeout)``: if the thread is still alive after the timeout, ``asyncio.run`` HUNG
at ``_cancel_all_tasks`` awaiting the uncancellable task -> FAIL LOUD. We ALSO assert the module-level
``_DETACHED_WRITER_TASKS`` set drained empty (the force-close discarded the finalized task).

Asserts: (1) ``asyncio.run`` COMPLETES (thread joins) well under the timeout -> zero wedged pending at
shutdown; (2) the detached-task set is EMPTY after teardown; (3) the stuck basket is ABSENT from out
(-> K-span fallback); (4) >=1 healthy basket IS drafted (abandon didn't kill healthy work).

No real API key needed — the writer is monkeypatched.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

os.environ["PG_ABSTRACTIVE_WRITER"] = "1"
os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
os.environ.setdefault("PG_GENERATOR_MODEL", "z-ai/glm-5.2")
os.environ["PG_ABSTRACTIVE_WRITER_CONCURRENCY"] = "4"
os.environ["PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S"] = "60"  # ABOVE the wall -> per-call deadline does NOT fire
os.environ["PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S"] = "8"   # the binding bound under test
os.environ["PG_ABSTRACTIVE_WRITER_MAX_RETRIES"] = "0"

_GOLD = _REPO / "tests" / "fixtures" / "iwire001" / "compose_gold_corrected.json"
WALL = 8.0
# Generous: wall(8) + abandon force-close + asyncio.run shutdown. If asyncio.run instead HANGS on the
# uncancellable task, the thread stays alive PAST this and join() returns with is_alive()=True -> FAIL.
JOIN_TIMEOUT_S = 40.0


def _materialize(gold, n):
    from src.polaris_graph.synthesis.credibility_pass import (
        BasketMember, ClaimBasket, MEMBER_TIER_ENTAILMENT_VERIFIED,
    )

    def _member(eid, span, tier, weight):
        return BasketMember(
            evidence_id=eid, source_url=f"https://corpus/{eid}", source_tier=tier or "T1",
            origin_cluster_id=f"o::{eid}", credibility_weight=weight, authority_score=weight,
            span=(0, len(span)), direct_quote=span, span_verdict="SUPPORTS",
            member_tier=MEMBER_TIER_ENTAILMENT_VERIFIED,
        )

    pool = dict(gold["evidence_pool"])
    out = []
    for b in gold["baskets"][:n]:
        members = [_member(m["eid"], m["span"], m["tier"], m["weight"]) for m in b["members"]]
        out.append(ClaimBasket(
            claim_cluster_id=b["claim_cluster_id"], claim_text=b["claim_text"],
            subject=b["subject"], predicate="finding", supporting_members=members,
            refuter_cluster_ids=(), weight_mass=float(len(members)),
            total_clustered_origin_count=len(members),
            verified_support_origin_count=len(members), basket_verdict="full",
        ))
    return out, pool


def main():
    gold = json.loads(_GOLD.read_text(encoding="utf-8", errors="replace"))
    from src.polaris_graph.generator import abstractive_writer as aw
    from src.polaris_graph.generator.provenance_generator import verify_sentence_provenance
    from src.polaris_graph.generator.verified_compose import build_verified_span_draft

    baskets, pool = _materialize(gold, 3)
    stuck_key = aw._basket_key(baskets[0])
    stuck_eid = str(getattr(baskets[0].supporting_members[0], "evidence_id", ""))
    healthy_keys = [aw._basket_key(b) for b in baskets[1:]]

    async def _uncancellable_wedge() -> None:
        # The proven hang class: cancellation is SWALLOWED and the frame RE-BLOCKS. A bare t.cancel()
        # cannot finalize this — only _coro.close() (GeneratorExit) can. shield() keeps the inner await
        # alive across the cancel; the finally re-blocks so even the post-shield CancelledError can't end it.
        try:
            await asyncio.shield(asyncio.sleep(3600))
        except asyncio.CancelledError:
            # Re-block: swallow the cancel and await again, exactly like an httpx teardown that wedges.
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                await asyncio.sleep(3600)  # and again — uncancellable by design
        return None

    async def _stub(members, evidence_pool, **kw):
        eid = str(getattr(members[0], "evidence_id", ""))
        if eid == stuck_eid:
            await _uncancellable_wedge()   # UNCANCELLABLE stall (swallows CancelledError, re-blocks)
            return ""
        for b in baskets[1:]:              # healthy baskets return their real verbatim K-span draft
            if str(getattr(b.supporting_members[0], "evidence_id", "")) == eid:
                return build_verified_span_draft(b, evidence_pool) or ""
        return ""

    orig = aw._call_writer
    aw._call_writer = _stub
    aw._DETACHED_WRITER_TASKS.clear()
    writer_verify = aw.make_writer_verify_fn(verify_sentence_provenance)

    result: dict = {}

    def _run_in_thread() -> None:
        # asyncio.run on a fresh loop in this thread: if _cancel_all_tasks at shutdown awaits the
        # uncancellable task, THIS thread never returns and join() below will report is_alive()=True.
        result["out"] = asyncio.run(
            aw.abstractive_pre_pass(baskets, pool, writer_verify_fn=writer_verify)
        )

    th = threading.Thread(target=_run_in_thread, name="prepass_asyncio_run", daemon=True)
    t0 = time.time()
    th.start()
    th.join(JOIN_TIMEOUT_S)
    dt = time.time() - t0
    aw._call_writer = orig

    print(f"[prove_teardown] asyncio.run thread alive_after_join={th.is_alive()} in {dt:.1f}s", flush=True)
    ok = True
    if th.is_alive():
        print(f"FAIL: asyncio.run HUNG at shutdown ({dt:.1f}s >= {JOIN_TIMEOUT_S}s join timeout) — the "
              f"uncancellable task wedged _cancel_all_tasks (force-close did NOT finalize it)", flush=True)
        # The process itself will not exit cleanly because of the daemon thread's wedged loop; fail loud.
        print("FAIL prove_teardown", flush=True)
        os._exit(1)
    out = result.get("out", {})
    remaining = len(aw._DETACHED_WRITER_TASKS)
    if remaining != 0:
        print(f"FAIL: {remaining} detached task(s) NOT drained after teardown (force-close/discard leak)", flush=True); ok = False
    if stuck_key in out:
        print(f"FAIL: stuck basket {stuck_key} should be ABSENT (abandoned), but is in out", flush=True); ok = False
    if not any(k in out for k in healthy_keys):
        print(f"FAIL: no healthy basket drafted; healthy_keys={healthy_keys}", flush=True); ok = False
    print(("PASS prove_teardown: asyncio.run COMPLETED with ZERO pending at shutdown despite an "
           "UNCANCELLABLE wedged basket (force-close finalized it); detached set drained empty; stuck "
           "basket ABANDONED to K-span; healthy baskets drafted.") if ok else "FAIL prove_teardown", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
