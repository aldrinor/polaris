# SECTION 1 = FETCH — LOCKED

Branch: `bot/I-deepfix-relaunch`. Date locked: 2026-07-10 (I-fetch-lock).

This is the first locked section of the POLARIS pipeline. The fetch section is
the part that goes out to the web and pulls down the source content. Its job is
done when it has a set of fetched sources. Everything after it (tier weighting,
off-topic screening, dedup, composition, faithfulness) is a later section and is
NOT locked by this record.

The faithfulness engine is untouched. Every change here is fetch concurrency or
a fetch fallback. It never relaxes a claim gate.

---

## 1. Why we lock it — the acceptance evidence

A full fetch of the drb_72 corpus (921 sources) was run at two worker counts.

- **14 workers: 846 of 921 fetched = 91.9% success. ZERO crawler exceptions.**
- 48 workers: 573 of 921 = 62% success, 249 crawler exceptions. The crawler
  crashed and the container hit its process cap (cgroup pids.max 12544) from too
  many headless browsers fanning out at once.

So 14 workers is both safer and higher-yield than 48. That is the settled,
acceptance-MET value. We lock it.

### Tool-win breakdown at 14 workers (which backend recovered each source)

| Tool | Wins | Share |
|---|---|---|
| Jina | 537 | 64% |
| PDF extractors | 152 | 18% |
| crawl4ai | 55 | ~6.5% |
| Trafilatura | 49 | ~5.8% |
| PMC (PubMed Central) | 41 | ~4.8% |
| Zyte (paid) | 8 | 0.9% |

The cascade is healthy: legal open-access first (PMC / Unpaywall), then PDF
extractors, then crawl4ai + Jina raced, then Zyte paid as the genuine last
resort. Jina and PDF carry the run; the paid tail is rare.

### Known residual

Junk is about 5% of accepted rows (a span-cleanup leak — chrome / boilerplate
that slips in). It is caught downstream by the junk-deletion carve-out
(CLAUDE.md §-1.3.1), not inside the fetch section. Fetch does not try to be the
junk gate.

---

## 2. The locked config

### Concurrency = 14 (band 14–16, env-overridable)

Two knobs, both set to 14. Both are FLOORS an operator may RAISE; neither is
silently lowered.

- `src/polaris_graph/retrieval/live_retriever.py` — `_FETCH_WORKERS_CEILING`
  changed 48 → 14. This is the code default worker count when the env var is
  unset. The pool = `min(ceiling, max(floor=8, candidates // 16))`, so a large
  corpus now lands at 14.
- `scripts/dr_benchmark/run_gate_b.py` — the real production run slate
  `_FULL_CAPABILITY_BENCHMARK_SLATE["PG_LIVE_RETRIEVER_MAX_WORKERS"]` changed
  `"48"` → `"14"`. This is the value the actual benchmark pipeline reads, so the
  real pipeline no longer fetches at ~48. The 429/breadth step-down monitor now
  reads 14 as its ceiling and can only step DOWN from there.

Override at runtime with `PG_LIVE_RETRIEVER_MAX_WORKERS=<n>` (band 14–16). The
per-host politeness cap (`PG_LIVE_RETRIEVER_PER_HOST_CONCURRENT`, default 6) is
unchanged — same-host crawl rate is not touched.

### Cascade order (unchanged, confirmed healthy)

1. Legal open access — PMC-BioC / Unpaywall / PDF extractors.
2. Concurrent quality-scored group — crawl4ai + Jina raced, first clean win.
3. Direct HTTP, institutional proxy, Archive.org, timeout-retry.
4. Sci-Hub — disabled by default (`PG_SCIHUB_ENABLED=0`).
5. Zyte paid — the genuine last resort, only after the free chain fails, strict
   no-op with zero spend when `ZYTE_API_KEY` is absent.

### Paid-tail retry (added — Fable's one improvement)

On a source that the whole cascade would mark `fetch_failed`, run ONE final
exhaustive pass through Zyte + Archive.org before final give-up. The Zyte pass
BYPASSES the circuit breaker for this single last-ditch attempt — the
`fetch_failed` bucket was under-exercised on Zyte because a mid-cascade
breaker-open skipped it.

- Flag: `PG_FETCH_PAID_TAIL_RETRY`, default ON. Set to `0` => zero extra network
  calls, byte-identical to the old behaviour.
- Code: `src/tools/access_bypass.py` — `_try_zyte(..., bypass_circuit_breaker=…)`
  plus the new `AccessBypass._paid_tail_retry` helper called at the cascade
  give-up point in `fetch_with_bypass`.
- Test: `tests/polaris_graph/test_fetch_paid_tail_retry.py` (3 cases, GREEN).
- Faithfulness-neutral: recovers only RAW content, routed through the same
  extractor + strict_verify / 4-role gates as every other backend.

---

## 3. Resume checkpoint note

The output of the fetch section is the **fetched-content set** — the set of
sources with their pulled body text. That set is the boundary. It is the point
BEFORE tier weighting and BEFORE off-topic screening.

If a run crashes after fetch, resume from this fetched-content set (the corpus
snapshot), not from a fresh web pull. Re-running the whole fetch wastes the
91.9% already recovered. The replay harness `scripts/fetch_corpus_replay.py`
(with `--resume`) reads exactly this boundary set.
