# Resume plan — salvaging the dead drb_72_ai_labor run (operator ask)

**Operator ask:** "resume from the point we are dead, by a temporary pipeline that starts from that point, with reasonable timeout first."

## What the dead run actually completed (from the VM artifacts)
The run got 95% of the way before dying. On disk at `/home/ubuntu/polaris_run/outputs/honest_sweep_r3/workforce/drb_72_ai_labor/`:
- **Retrieval DONE** — 740 corpus sources, 1428.6s (the single biggest I/O cost), `retrieval_cache.sqlite` + `authority_enrich.sqlite` populated.
- **Weight + consolidate + select DONE** — 803 sources accepted, 656→collapsed=0, 649/649 selected, dropped 0. (`live_corpus_dump.json`, `evidence_pool.json`, `corpus_credibility_disclosure.json`.)
- **Contradiction + 4-role partial** — `contradictions.json` (3.5MB), `four_role_role_calls.jsonl` (276 calls), `verification_details.json`, `nli_verification.json`.
- **DIED** composing the V30 narrative section: the 600s smoke wall-clock killed the DeepSeek `generate()` mid-stream x2; bare `gather` discarded everything. `status=error_unexpected`, $6.74/$25, 12002s.

## The honest truth about "resume from the exact middle"
The run had **NO stage checkpoints** (g5 + h1 + h4 confirmed: the sqlite files are fetch/enrich ACCELERATORS, not reloadable stage state; `live_corpus_dump.json` omits the final evidence selection + later mutations). So there is no saved "middle state" to inject into a temp pipeline. Reconstructing it from the 1622 `llm_io` captures would be fragile AND would bypass the faithfulness gates — **rejected** (violates the §-1.3 hard-gate invariant).

## The pragmatic resume (chosen) — cache-reuse re-run
After **A1 (crash isolation)** + **A2 (timeout/token sizing)** land and the VM redeploys, re-run the SAME query with the SAME `--out-root`:
- **Retrieval + fetch + authority-enrich replay from the on-disk caches** — the 24-minute I/O part becomes near-instant (the caches are keyed by URL/query and already warm from this run).
- **Generation now COMPLETES** — the V30 section that died gets the real ~6500s LLM / ~11000s wall budget instead of the smoke 600s, and even a stalled section degrades to a visible gap-stub (A1) instead of crashing.
- **All faithfulness gates run fresh** — strict_verify / NLI / 4-role / D8 are NOT bypassed. No verdict is carried over.
- **Re-paid cost:** only the LLM generation + verification (retrieval I/O is free from cache). Far cheaper than the cold $6.74-to-death path, and it actually finishes.

This needs **zero new salvage code** — it is just "land A1+A2, redeploy, re-run." That is the correct "temporary pipeline from the middle": the cache IS the middle.

## The better resume (A3, follow-up) — data checkpoints
A3 adds a `corpus_snapshot` checkpoint after retrieval + per-section draft snapshots. On resume it reloads the corpus + generated drafts as DATA and **re-runs every faithfulness gate** (HARD INVARIANT: checkpoints carry DATA, never VERDICTS). That skips even the generation re-pay. Built after A1/A2 since it is not needed to unblock the first successful run.

## Dependency / sequence
```
A1 (crash isolation)  ── Codex diff-gate IN FLIGHT (.codex/I-arch-004/A1_crash_isolation/)
A2 (timeout+token sizing + preflight fail-loud floor)   ── next
A3 (corpus_snapshot + resume flag)                       ── follow-up
   ↓ redeploy VM (polaris_run @ new HEAD, keep the drb_72 out-root + caches)
RESUME RUN: same query, same --out-root, full /home/ubuntu/polaris_run/.env (Zyte key present)
```
**Resume is GATED behind A1+A2** — re-running today with the broken 600s wall would just die again at the same section. Do NOT fire a paid resume until A2's preflight fail-loud floor confirms the timeouts resolve above the calculated minimum.

## Run command (once fixes land + VM redeployed)
```
docker exec -d arch002_runner sh /app/launch.sh   # same slug, same --out-root, full polaris_run/.env
```
Monitor: `tail run_status.json` + `retrieval_trace.jsonl`; expect retrieval to fly (cache hits), generation to actually complete, real acceptance = §-1.1 line-by-line audit of the output.
