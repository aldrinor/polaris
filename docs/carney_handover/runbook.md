# POLARIS Runbook (Carney Handover)

**Operational owner from 2026-09-06 onward:** Carney's office operations team (per `docs/blockers.md` §6).
**Warm-support window (2026-09-06 → 2026-10-06):** POLARIS build team responds same-day to bug reports; supplementary to your team's ownership, not a substitute.
**After 2026-10-06:** best-effort responses from POLARIS build team only.
**Author of this runbook:** POLARIS build team, 2026-09 (placeholder; final fill at Phase 5)

---

## 1. What's running where

| Component | Host | Region | Notes |
|---|---|---|---|
| Frontend (Next.js 16) | (TBD CDN) | Canada-East POP | static + SSE proxy to backend |
| Backend (FastAPI 0.136) | OVH BHS | Canada (sovereign) | uvicorn, exposes /health /runs /stream /ambiguity /scope/check /upload /runs/{id}/bundle |
| Queue (Dramatiq + Redis 7.4) | OVH BHS | Canada (sovereign) | StubBroker in dev; RedisBroker in prod |
| LLM serving (vLLM or SGLang per Phase 0.7 bakeoff) | OVH BHS H200 (8×) | Canada (sovereign, Beauharnois) | DeepSeek V4 Flash generator (Path C LOCKED per Plan v13 §F + blockers.md §3) + Gemma 4 31B verifier (different lineage; `openrouter_client.check_family_segregation` invariant) |
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

Active pairing (LOCKED per Plan v13 §F):
- **DeepSeek V4 Flash (DeepSeek lineage) + Gemma 4 31B (Google lineage)** — Path C, sovereign cluster

Per Plan v13 §F "no SILENT fallback" semantics — alternate pairings below are NOT auto-fallbacks. They are halt-and-decide options if the active pairing becomes unavailable (e.g., model deprecation, license revocation). When that happens, the orchestrator emits a halt marker; user explicitly authorizes one of:

- DeepSeek V4 + Llama 4 (Meta lineage) — option if Gemma 4 deprecated
- Qwen 3.5 (Alibaba lineage) + Gemma 4 — option if DeepSeek deprecated

Either switch requires user-signed canonical reconciliation commit (Plan v13 §A); the orchestrator does not silently swap models.

**Forbidden:** any pair from the same lineage (e.g., DeepSeek + DeepSeek-Coder; Gemma + Gemma-Code) — `family_segregation` invariant raises RuntimeError at construction.

### To rotate
1. Pull new weights to a staging volume.
2. Run benchmark suite: `pytest tests/v6/test_benchmark_schema.py` + the Phase 3 industry benchmark adapters against the live model.
3. Run sycophancy CI: `pytest tests/v6/test_sycophancy_ci.py` + the 7 paired-prompt fixtures.
4. Run pin replay against last-known-good fixtures:
   ```
   python scripts/v6/run_pin_replay.py \
       --baseline-dir tests/v6/fixtures/baseline_pins/ \
       --candidate-dir outputs/replay/$(date +%F)/
   ```
   Exit 0 = no regression; exit 1 = at least one regression detected; exit 2 = missing dir.
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

To diff a stored original pin against a freshly-replayed pin:
```
python scripts/v6/replay_pin.py \
    --original  s3/polaris-pins-bhs/<pin_id>.json \
    --replay    outputs/replay/<pin_id>.json
```

Add `--json` for machine-consumable PinDiff output. Exit 1 if `is_regression=True`.

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

Your operations team has owned the following since 2026-09-06 handover (per `docs/blockers.md` §6) — warm support did not change ownership:
- Daily health checks
- Monthly model-rotation evaluation
- Quarterly benchmark re-run
- Pin replay on every model swap
- Incident response per §7

What 2026-10-06 changes is only the build team's response level: same-day bug-report turnaround drops to best-effort.

POLARIS source-code authoritative reference: GitHub repo at handover. Commit history is the audit trail.
