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
| LLM serving (vLLM, locked I-cd-007) | OVH BHS H200 (8×) + OVH H100 (4×) | non-US (sovereign) | DeepSeek V4 Pro 1.6T generator on 8× H200 + Gemma 4 31B-it evaluator on 4× H100 (different lineage; `openrouter_client.check_family_segregation` invariant). Carney demo lock per I-cd-009 (GH#624). |
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

Active pairing (LOCKED per I-cd-009 / GH#624 Carney demo):
- **DeepSeek V4 Pro 1.6T (DeepSeek lineage) + Gemma 4 31B-it (Google lineage)** — sovereign cluster

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

## 6. Backup + restore

### Orchestrator state (run store + audit artifacts)

The v6 orchestrator keeps two pieces of durable state: the SQLite run store
(`state/v6_runs.sqlite`, on the `shared_state` volume) and the run artifact
directories (`outputs/v6_runs/<run_id>/`, from which signed audit bundles
are rebuilt on demand). `scripts/v6/backup_orchestrator_state.py` snapshots
both into one portable, sha256-stamped `tar.gz`.

Stop the stack first — the DB snapshot is online-safe, but the artifact
tree is not atomic against running workers:

```
docker compose -f docker-compose.v6.yml stop

docker compose -f docker-compose.v6.yml run --rm \
  -v "$PWD/backups:/backups" --entrypoint python api \
  scripts/v6/backup_orchestrator_state.py backup \
  --db /app/state/v6_runs.sqlite --artifact-root /app/outputs/v6_runs --dest /backups

docker compose -f docker-compose.v6.yml start
```

The archive lands in `./backups/polaris_v6_state_<utc>.tar.gz` on the host
(plus a `.sha256` sidecar). **Off-box step (operator):** copy that archive
to genuinely separate Canadian storage — a second VM, a mounted volume, or
an offline disk. Run the backup at least daily; keep ≥ 7 days of archives.

To restore (e.g. onto a fresh VM), with the stack stopped:

```
docker compose -f docker-compose.v6.yml run --rm \
  -v "$PWD/backups:/backups" --entrypoint python api \
  scripts/v6/backup_orchestrator_state.py restore \
  --archive /backups/polaris_v6_state_<utc>.tar.gz \
  --db /app/state/v6_runs.sqlite --force
```

Restore verifies the archive sha256 before extracting and fails loud on a
mismatch. `--force` replaces an existing DB / artifact dir (it never
merges); omit it on a fresh VM.

### Replay-pin diff

To diff a stored original pin against a freshly-replayed pin:
```
python scripts/v6/replay_pin.py \
    --original  <original_pin>.json \
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
