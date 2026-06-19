"""I-arch-011 credibility-pass concurrency micro-test.

Reproduces the box4 wedge in isolation: the credibility pass runs N member-verifies
through a ThreadPool(max_workers=max_inflight); each calls the entailment judge, which
spawns its OWN _post_with_total_deadline executor. box4 wedged at max_inflight=16 with
0 connections + 177 threads. This isolates the entailment-judge-under-concurrency
behavior so we pick the lowest deadlock-free max_inflight WITHOUT a 20-min full replay.

Run on a VM (z-ai provider routing already deployed):
  cd /root/polaris_v2 && /root/run_env/bin/python -m scripts.diagnostics.credibility_concurrency_microtest
"""
import concurrent.futures
import os
import sys
import time

sys.path.insert(0, "/root/polaris_v2")

try:
    from dotenv import load_dotenv

    load_dotenv("/root/polaris_v2/.env")
except Exception:  # noqa: BLE001
    pass

# Bound a single hung call tighter than prod so a wedge surfaces fast in the test.
os.environ.setdefault("PG_ENTAILMENT_TOTAL_S", "40")

from src.polaris_graph.llm.entailment_judge import _get_judge  # noqa: E402

SENT = "Deep brain stimulation reduced motor symptoms in advanced Parkinson's disease."
SPAN = (
    "In a randomized controlled trial, deep brain stimulation of the subthalamic nucleus "
    "significantly improved motor function as measured by UPDRS-III compared with best "
    "medical therapy in patients with advanced Parkinson disease over 24 months of follow-up."
)

PER_BATCH_TIMEOUT_S = 120


def _one(i: int):
    j = _get_judge()
    t0 = time.time()
    try:
        v = j.judge(SENT, SPAN)
        return (i, round(time.time() - t0, 1), "ok:" + str(v)[:24])
    except Exception as e:  # noqa: BLE001
        return (i, round(time.time() - t0, 1), "ERR:" + str(e)[:40])


def run_at(k: int) -> bool:
    """Return True if the batch COMPLETED (no wedge), False if it wedged."""
    m = max(k * 2, 4)  # ~2 waves at concurrency k
    t0 = time.time()
    done = []
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=k)
    futs = [pool.submit(_one, i) for i in range(m)]
    try:
        for f in concurrent.futures.as_completed(futs, timeout=PER_BATCH_TIMEOUT_S):
            done.append(f.result())
    except concurrent.futures.TimeoutError:
        dt = time.time() - t0
        durs = sorted(d[1] for d in done)
        print(
            f"K={k:>2}: WEDGED — {len(done)}/{m} done in {dt:.0f}s "
            f"(completed call durations: {durs})",
            flush=True,
        )
        pool.shutdown(wait=False, cancel_futures=True)
        return False
    dt = time.time() - t0
    durs = sorted(d[1] for d in done)
    errs = sum(1 for d in done if d[2].startswith("ERR"))
    pool.shutdown(wait=True)
    print(
        f"K={k:>2}: OK {len(done)}/{m} in {dt:.1f}s | per-call durs={durs} | errs={errs}",
        flush=True,
    )
    return True


if __name__ == "__main__":
    print("=== credibility concurrency micro-test (entailment judge under ThreadPool) ===", flush=True)
    for k in (1, 4, 8, 16):
        ok = run_at(k)
        if not ok:
            print(f"FIRST_WEDGE_AT_K={k}", flush=True)
            # keep going to confirm higher levels also wedge? No — a wedge leaves stuck
            # threads; hard-exit so we don't hang the test process.
            os._exit(0)
    print("MICROTEST_DONE_no_wedge_through_16", flush=True)
