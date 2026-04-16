# S3 Root Cause Diagnosis — 73% Analyzer Batch Failure (PG_TEST_090)

**Date:** 2026-04-12
**Evidence sources:**
- `logs/pg_test_061_run4.log` (2.5 MB)
- `logs/pg_trace_PG_TEST_090.jsonl` (31 MB)
- `logs/empirical_e1_e4_results.json`, `empirical_e1_retry_e5_e6_results.json`, `empirical_e4_long_results.json`

---

## Evidence

### Failure numbers
- 275 batches submitted (batch_size=2, 549 sources after dedup/filter)
- 74 batches produced evidence (27% real success)
- 201 batches failed (73% failure)
- 151 SDK-level "completed" events (includes ~77 zombie completions after client-side cancel)
- 248 first-attempt `timed out after 120s` warnings; 74 retry-failure errors

### Duration distribution (151 SDK completions, `structured:SourceAnalysisBatch`)
| Bin | N | Mean reasoning tok | Mean output tok |
|---|---|---|---|
| 0–30s | 77 | 995 | 1,903 |
| 30–60s | 54 | 1,177 | 2,779 |
| 60–90s | 12 | 1,687 | 3,574 |
| 90–120s | 4 | 1,944 | 4,843 |
| 120–150s | 3 | 1,545 | 3,763 |
| 150–200s | 1 | 10,813 | 10,708 |

- **p50 = 29.8s, p95 = 90.4s, p99 = 138.4s, max = 171.8s**
- Client-side timeout = 120s → clips p95–p99 when server is under load

### Signature of server queue saturation
At T=0 (13:20:39), 30 batches hit the semaphore simultaneously. At T+120s:
```
13:22:39,564  Batch 3/275 timed out
13:22:39,587  Batch 9/275 timed out
13:22:39,590  Batch 10/275 timed out
...
13:22:39,640  Batch 30/275 timed out
```
**23 of first 30 batches timed out within 76 ms of each other** — classic server-side queue-exhaustion fingerprint, not independent per-batch slowness.

### Reasoning is always on — override confirmed
`src/polaris_graph/llm/openrouter_client.py:800`
```python
if self.model in _ALWAYS_REASON_MODELS:
    body["reasoning"] = {"effort": reasoning_effort or "high", "exclude": False}
```
Analyzer passes `reasoning_enabled=False` (analyzer.py:1953). Trace confirms it's ignored:
```
call_type: structured:SourceAnalysisBatch
  reasoning_enabled: False      ← caller intent
  reasoning_tokens: 806-940     ← what actually happened
```

### Empirical: GLM-5.1 cannot be forced off reasoning mode
| Test | Mechanism | Duration | reason_tok | Valid JSON |
|---|---|---|---|---|
| E1-retry | `reasoning.max_tokens=2048` (no effort) | 30.9s | 1905 | Yes (5 facts) |
| E5 | Omit reasoning block entirely | 26.3s | 2351 | Yes (5 facts) |
| E6 | `reasoning.exclude=true` | 25.6s | 2091 | Yes (6 facts) |

Reasoning tokens still burn 1,900–2,400 per call regardless. **Server always reasons**; `exclude=true` only hides the reasoning field in the response.

---

## Root cause

Three compounding factors produce the 73% batch failure:

1. **Server-side queue saturation under 30-concurrent load** (dominant factor).
   30 simultaneous reasoning-mode requests overload the Chutes fp8 provider (sole provider for GLM-5.1). Server queues extra work, which inflates wall-clock latency for all first-wave batches uniformly. The 120 s client-side timer fires before queued calls dispatch.

2. **Client-side timeout too tight for p99** (120 s vs 138 s measured p99).
   Even without queue saturation, ~1 in 100 batches naturally takes >120 s. Under saturation this is closer to 1 in 5.

3. **Reasoning cannot be disabled** (architectural constraint).
   GLM-5.1 always performs chain-of-thought server-side. `reasoning.max_tokens=2048` is accepted by the API (E1-retry PASS) but only caps the reasoning length — total call duration depends on output tokens × provider queue depth.

**Not the cause:** rate limiting (E3 showed no 429s at 30 concurrent), batch input size (timeouts occurred for both 2.5 k and 15 k input), stream/non-stream path (all extraction goes through streaming path).

---

## Fixes (ordered by impact, evidence-backed)

### Stage 1: env-only, no code (ship first — independent of override)
- `PG_ANALYSIS_CONCURRENCY`: 30 → 8
  - Reduces server queue depth ~4× → durations stabilize near p50.
- `PG_ANALYSIS_BATCH_TIMEOUT`: 120 → 300
  - Covers p99 (138 s) with 2× margin.
- Expected: extraction success 27 % → ~70 % on same content mix.

### Stage 2: unlock override so caller reasoning params take effect
**Blocker:** `openrouter_client.py:800-803` hard-replaces the entire `reasoning` dict.
```python
if self.model in _ALWAYS_REASON_MODELS:
    body["reasoning"] = {"effort": reasoning_effort or "high", "exclude": False}
```
This clobbers any caller-passed `max_tokens` or `exclude`. Must be changed to merge:
build the reasoning dict from (a) caller-specified keys, (b) ALWAYS_REASON defaults
only for keys the caller didn't set. Add two params to `_build_body` / the chat
methods: `reasoning_max_tokens: int | None = None`, `reasoning_exclude: bool | None = None`.

Current call surface already passes `reasoning_enabled` and `reasoning_effort`; extend
it so extraction callers can pass `reasoning_max_tokens=2048` and S1 section-write
callers can pass `reasoning_exclude=True`.

### Stage 3: apply the new levers at call sites
- Extraction (analyzer.py:1947, analyzer.py:2113, storm_interviews.py:476/718/814):
  `reasoning_max_tokens=2048`. Caps the runaway-reasoning tail (p99 max=10 k→≤2 k).
- Section-write (synthesizer.py prose path): `reasoning_exclude=True`.
  Empirically verified by E4-LONG: 1,292 words, 0 scaffolding, 34 citations, clean.

### Not recommended
- Removing GLM-5.1 from `_ALWAYS_REASON_MODELS` → would break analytical/synthesis calls that genuinely need reasoning.
- Trying to disable reasoning → E5/E6 prove the server reasons anyway.
- Regex scrubbing reasoning out of content → already failed (FIX-GLM5-COT three failed strategies).

---

## S1 bonus — prose scaffolding fix empirically confirmed

**E4-LONG (1200-word section-write with 10 evidence pieces):**
- `reasoning.exclude=true` + `max_tokens=16384`
- Result: 1,292 words, 0 scaffolding markers, 34 citations, clean ending, 157.6 s
- Reasoning hidden server-side (4,860 reasoning_tokens burned, 0 visible chars)

**S1 primary mechanism validated for production use.** The FIX-GLM5-COT regex scrubbers can be retired in favor of API-level `reasoning.exclude=true`.

---

## Implementation order
1. Apply S3 env changes (concurrency, timeout) — immediate 4× reduction in timeout rate.
2. Add `reasoning.max_tokens=2048` to extraction calls — modest additional win.
3. Implement S1: switch section-write path to `reasoning.exclude=true`, remove regex scrubbers.
4. Re-run production test; expect extraction success rate to rise from 27 % toward 85–95 %.
