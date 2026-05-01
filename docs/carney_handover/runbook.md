# POLARIS Runbook (Carney Handover)

**Owners after 2026-10-06:** Carney's office operations team
**Author of this runbook:** POLARIS build team, 2026-09 (placeholder; final fill at Phase 5)

---

## 1. What's running where

| Component | Host | Region | Notes |
|---|---|---|---|
| Frontend (Next.js 16) | (TBD CDN) | Canada-East POP | static + SSE proxy to backend |
| Backend (FastAPI 0.136) | OVH BHS | Canada (sovereign) | uvicorn, exposes /health /runs /stream /ambiguity /scope/check /upload /runs/{id}/bundle |
| Queue (Dramatiq + Redis 7.4) | OVH BHS | Canada (sovereign) | StubBroker in dev; RedisBroker in prod |
| LLM serving (vLLM) | OVH BHS H200 | Canada (sovereign) | DeepSeek V4 (Flash or Pro per Path A/B/C) generator + Gemma 4 31B verifier |
| ChromaDB (workspace memory) | OVH BHS | Canada (sovereign) | Phase 2B substrate |
| Observability (OTEL) | (TBD US dashboards) | US (brainless) | trace IDs only; CAN_REAL data redacted |

---

## 2. Daily operations

### Start
```
docker compose -f docker-compose.sovereign.yml up -d
```

### Health
```
curl https://polaris.gc.ca/health
# expect: {"status":"ok","version":"6.2.0"}
```

### Stop
```
docker compose -f docker-compose.sovereign.yml down
```

---

## 3. Model rotation

Generator + verifier MUST come from different lineages (CLAUDE.md §9.1 invariant 1). The `openrouter_client.check_family_segregation` raises `RuntimeError` at construction if violated.

Approved pairings:
- DeepSeek V4 Pro / Flash (DeepSeek lineage) + Gemma 4 31B (Google lineage) — current
- DeepSeek V4 + Llama 4 (Meta lineage) — fallback if Gemma 4 deprecated
- Qwen 3.5 (Alibaba lineage) + Gemma 4 — fallback if DeepSeek deprecated

**Forbidden:** any pair from the same lineage (e.g., DeepSeek + DeepSeek-Coder; Gemma + Gemma-Code).

### To rotate
1. Pull new weights to a staging volume.
2. Run benchmark suite: `pytest tests/v6/test_benchmark_schema.py` + the Phase 3 industry benchmark adapters against the live model.
3. Run sycophancy CI: `pytest tests/v6/test_sycophancy_ci.py` + the 7 paired-prompt fixtures.
4. Run pin replay against last-known-good fixtures: `python scripts/v6/run_pin_replay.py --against=goldens`.
5. Cutover via `POLARIS_V6_GENERATOR_MODEL` + `POLARIS_V6_VERIFIER_MODEL` env vars.

---

## 4. Evaluator-failure escalation

If the Layer-3 paid sample evaluator returns a fail-grade on a benchmark dimension:
1. Triage: which dimension? See `BenchmarkScore.dimensions` in the report.
2. Reproduce: run the failing question on the staging cluster.
3. Pin the failing run for replay.
4. Open a fix-plan issue tagged with the dimension.
5. Do NOT ship a fix that improves the failing dimension while regressing another by >5% (per `M-D9` regression-lab CI gate, locked from prior milestone).

---

## 5. Cost monitoring

Per-run cost is recorded on the EvidenceContract `cost_usd` field. Aggregate via:
```
python scripts/v6/cost_summary.py --since 2026-10-01
```
Hard ceiling: `PG_MAX_COST_PER_RUN` (default $50/run; raise via env var with sign-off).

---

## 6. Backup + replay

Pins are append-only and never deleted. Backed up daily to encrypted Canadian S3-compatible storage at `s3://polaris-pins-bhs/` (key custody with Carney's office IT).

To replay an old pin:
```
python scripts/v6/replay_pin.py --pin-id <pin_id>
```

The diff output (PinDiff schema) flags any regression vs the original pin.

---

## 7. Incident response

| Severity | Examples | Response time | Notify |
|---|---|---|---|
| P0 | Two-family invariant FAIL persisting; CAN_REAL data leaked outside Canadian infra | 30 min | Build team + your CISO |
| P1 | Pipeline_status going abort_* on >50% runs; cluster down | 2 h | Build team |
| P2 | Sycophancy drift > threshold on one template | 1 day | Build team |
| P3 | UI styling regression; non-blocking | next sprint | tracker only |

Build team contact during 30-day warm support: (TBD email at handover).

---

## 8. End of warm support (2026-10-06)

After this date, your operations team owns:
- Daily health checks
- Monthly model-rotation evaluation
- Quarterly benchmark re-run
- Pin replay on every model swap
- Incident response per §7

POLARIS source-code authoritative reference: GitHub repo at handover. Commit history is the audit trail.
