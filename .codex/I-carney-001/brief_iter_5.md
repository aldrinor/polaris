HARD ITERATION CAP: 5 per document. This is iter 5 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-001 iter 5 — FINAL: demo posture A (canonical library) + 5-cap convergence

This is the binding iter. If iter 5 = REQUEST_CHANGES, Claude force-APPROVE's per §8.3.1 + captures residuals as follow-up Issues.

Decisions from iters 1-4 carry forward: sovereignty (c), AWS ca-central-1, static_accounts, concurrency 1, 7-day phasing, single-EC2 docker-compose topology.

## Scope pivot acknowledging iter-4 architectural finding

Iter 4 P1-live-run-graph-contract + P1-v30-artifact-shape established that **live `POST /runs` → graph payload does NOT cleanly work in the current architecture** without multi-week alignment work:

| Component | UUID-shape (v6 API) | Slug-shape (pipeline A + V30) |
|---|---|---|
| run_id | `runs.py:25` generates UUID | `run_honest_sweep_r3.py:1128-1130` generates `SWEEP_<timestamp>` |
| manifest.frame_coverage_report | not produced | only when slug has `per_query_report_contract` |
| AuditIR strict loader | rejects | accepts for canonical slugs |
| registry allowlist | one path | `(CANONICAL_DEMO_DIR,)` |

**Iter 4 P2 #4 recommended ship-pivot**: "Yes, ship the canonical precomputed fallback path for demo day, but it is not a substitute for fixing the live run_id/artifact registration contract above."

**Iter 5 plan adopts this**. Demo posture for Carney 2026-05-19:

### Demo posture A — Canonical pre-computed research library (1-week-feasible)

- Carney's staff log in via static_accounts (admin / operator / viewer roles)
- Browse pre-computed canonical questions Q1-Q5 (already audit-complete per GH#400 I-beat-001) + extend library to Q6-Q10 in week 1 if time permits
- Each question opens the Inspector with 5 views: contradiction matrix, frame coverage, methods + provenance, source tier mix, executive summary
- F-snowball claim-graph view available on each (already shipped, GH#458-461)
- Audit bundle export (GPG-signed, .tar.gz) per question — gives reviewers a tamper-evident record
- Compare endpoint (M-13 shipped) lets staff diff two runs across all dimensions
- Public transparency page documents foreign-API egress under (c) sovereignty

**What's "real" about this**: every claim in every report is per-sentence verified against actual source content via `strict_verify` (POLARIS §9.1 invariant 3); every span quote is reachable + per-claim audit verdict (VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE) per §-1.1. This is audit-grade output that ChatGPT/Gemini Deep Research demonstrably cannot match (per #275 GH#400 I-beat-001 BEAT-BOTH §-1.1 audit). For Carney's office making policy decisions, a small library of provably-audited reports is more valuable than a large library of self-confident but fabrication-prone reports.

**What's NOT in posture A**: staff cannot submit a new question and watch it run live during the demo. They request via a feedback form; the request goes to a Codex-reviewed backlog for post-demo computation. Architectural item I-arch-001 (UUID/slug/V30 reconciliation) lifts this restriction post-demo.

### Captured architectural follow-up — I-arch-001 (post-demo)

GH#TBD opened post-Carney-demo:
- Reconcile v6 UUID run_id ↔ pipeline-A SWEEP_xxx slug naming
- Implement V30-compatible artifact builder for ad-hoc questions (not just canonical slugs)
- Replace `_PHASE_A_ALLOWLIST` static tuple with a workspace-scoped registry table
- Add a Dramatiq actor → pipeline-A bridge that emits frame_coverage_report + per_query_report_contract
- Estimated 2-3 weeks; staffed after demo

## P1 from iter 4 → iter-5 resolutions

### P1.1 — PYTHONPATH for v6 import

Add to Dockerfile:

```dockerfile
ENV PYTHONPATH=/app/src:/app
```

Verifies via `python -c "import polaris_v6"` exit 0 inside the image.

### P1.2 — POLARIS_V6_REDIS_URL explicit in compose

```yaml
services:
  api:
    environment:
      - POLARIS_V6_REDIS_URL=redis://redis:6379/0
      - POLARIS_OUTPUT_ROOT=/app/outputs
      # ... other env
  worker:
    environment:
      - POLARIS_V6_REDIS_URL=redis://redis:6379/0
      - POLARIS_OUTPUT_ROOT=/app/outputs
```

Explicit, not implicit. Compose Redis service is the canonical broker.

### P1.3 — Live run graph contract: DROPPED for week-1; canonical library only

Per scope pivot above. `actors.py` stays in stub mode for the demo. POST /runs accepted from staff is recorded as a request for the post-demo backlog (run_store.mark_queued), NOT executed live. This is documented in:

- The runbook (I-carney-007)
- The transparency endpoint
- The web UI: "Submit a question for review" — the queue isn't backed by live compute

If user/Codex want live submission for the demo, that's an explicit timeline extension to 3-4 weeks for I-arch-001 to land first.

### P1.4 — V30 artifact shape: only canonical slugs in demo

Library is locked to the canonical Q1-Q5 slugs already in `_PHASE_A_ALLOWLIST` plus any new canonical slugs we add to the allowlist before demo (Q6-Q10 if produced from scratch via existing `sweep` subcommand using known templates). NO ad-hoc UUID slugs. Eliminates the V30-incompatible-artifact failure mode.

### P1.5 — Canonical output artifact seeding

Bind-mount `./outputs:/app/outputs` (not named volume) so canonical V30 demo dir is reachable from the container. AWS deploy: `aws s3 sync s3://polaris-canonical-artifacts/v30/ /opt/polaris/outputs/v30/` on EC2 first-boot via UserData; then bind-mount via docker-compose. Compose for local dev:

```yaml
services:
  api:
    volumes:
      - ./outputs:/app/outputs  # canonical V30 artifacts (bind, not named volume)
      - polaris_state:/app/state  # SQLite shared between api+worker
      - polaris_data:/app/data
  worker:
    volumes:
      - ./outputs:/app/outputs
      - polaris_state:/app/state
      - polaris_data:/app/data

volumes:
  polaris_state: {}
  polaris_data: {}
  chroma_data: {}
  redis_data: {}
```

## P2 from iter 4 → resolutions

### P2.1 — Add `run_store.mark_failed`

Add to `src/polaris_v6/queue/run_store.py`:

```python
def mark_failed(run_id: str, error: str) -> None:
    """Mark a run as failed with error string. Idempotent."""
    with _conn() as cx:
        cx.execute(
            "UPDATE runs SET status = ?, error = ?, completed_at = ? WHERE run_id = ?",
            ("failed", error, time.time(), run_id),
        )
```

Plus test in `tests/polaris_v6/queue/test_run_store.py`.

(Note: actor in stub mode doesn't call `mark_failed` anyway. The function is added for the future I-arch-001 work but is small enough to land now for completeness.)

### P2.2 — Redis mutex hygiene

Use the already-installed broker's client + compare-and-delete (Lua):

```python
# Use already-installed broker
broker = dramatiq.get_broker()
redis_client = broker.client  # type: ignore[attr-defined]

lock_key = "polaris:research:active_lock"
acquired = redis_client.set(lock_key, run_id, nx=True, ex=35 * 60)
if not acquired:
    raise Retry("active run in progress", delay=10_000)

try:
    # ... actor body ...
finally:
    # Compare-and-delete via Lua to avoid releasing someone else's lock
    redis_client.eval(
        "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
        1, lock_key, run_id,
    )
```

(This is wired into the actor body for I-arch-001; in stub-mode demo posture A it's not exercised — but I'll add it so the test framework has the code.)

### P2.3 — GPG entrypoint hygiene

In `scripts/docker_entrypoint.sh`, before exec uvicorn:

```bash
# GPG signer init (api command only)
if [ -n "${POLARIS_GPG_KEY_ID}" ] && [ -f "${POLARIS_GPG_KEY_FILE:-}" ]; then
    export GNUPGHOME="${GNUPGHOME:-/tmp/polaris_gnupg}"
    mkdir -p "$GNUPGHOME"
    chmod 700 "$GNUPGHOME"
    gpg --batch --import "$POLARIS_GPG_KEY_FILE" 2>&1 || { echo "GPG key import failed"; exit 1; }
    if ! gpg --batch --list-secret-keys "$POLARIS_GPG_KEY_ID" >/dev/null 2>&1; then
        echo "ERROR: POLARIS_GPG_KEY_ID=$POLARIS_GPG_KEY_ID not found in keyring after import"
        exit 1
    fi
    echo "GPG signing key $POLARIS_GPG_KEY_ID loaded"
fi
```

Worker doesn't need GPG (audit-bundle export endpoint is API-side). The path fails loud if key import or list verify fails.

### P2.4 — Canonical pre-computed fallback shipped (posture A)

This IS the demo posture per scope pivot. No fallback; this is the only path.

## Sub-issues — final list (open immediately on iter-5 APPROVE)

| ID  | Title | Scope | Day(s) |
|---|---|---|---|
| I-carney-005 | Deploy substrate: Dockerfile PYTHONPATH + api/worker entrypoint + compose redis/worker/webui + Next rewrites + GPG bootstrap | All P1 + P2 fixes above | 1-3 |
| I-carney-002 | AWS infra (VPC/EC2/ALB/ACM/SG/SSM/Route 53/EBS snapshots/S3 canonical artifact bucket) | Provision + smoke after 005 local-green | 1 |
| I-carney-003 | Sovereignty + transparency endpoint + egress controls + public footer copy | docs/transparency.md + /transparency route + OpenRouter ZDR enabled where supported | 1-2 |
| I-carney-004 | Static accounts auth + demo GPG signing key + AWS Secrets Manager wiring | 5 pre-provisioned accounts (1 admin, 4 viewer), passwords in 1Password, GPG key in Secrets Manager | 2 |
| I-carney-006 | Canonical Carney library — Q1-Q5 verified + extend to Q6-Q10 if time + line-by-line §-1.1 rehearsal | All published reports pass §-1.1 audit; M-D9 dimension scores recorded | 3-5 |
| I-carney-007 | Demo runbook + fallback laptop + transparency.md + 30-min walkthrough rehearsal + Codex sign-off | Internal user runs through the 30-min demo cold | 6 |
| I-arch-001 (post-demo) | UUID/slug/V30 contract reconciliation; live-submission path | Multi-week; opened but blocked-on-post-demo | — |

## Direct questions (last round before binding)

1. Demo posture A (canonical library only, no live submission in week 1) — APPROVE'd?
2. I-arch-001 captured as post-demo follow-up (not week-1 scope) — APPROVE'd?
3. PYTHONPATH + bind-mount outputs + explicit POLARIS_V6_REDIS_URL — APPROVE'd?
4. GPG entrypoint loud-fail on key import/list missing — APPROVE'd?
5. Anything else blocking?

## Local smoke before opening I-carney-002 (AWS)

- `docker compose build --no-cache`
- `docker compose up -d redis chromadb api worker webui`
- `curl http://localhost:8000/health` 200
- `curl http://localhost:3000/health` 200 via Next rewrite
- `curl http://localhost:3000/api/runs/<canonical_v30_slug>/graph` returns the canonical GraphPayload (the existing canonical demo dir is reachable through registry)
- Browser visits `http://localhost:3000/runs/<canonical_v30_slug>/graph` → cytoscape canvas renders
- `curl -X POST http://localhost:8000/api/audit-bundle ...` returns signed tar.gz for canonical run
- `pytest tests/polaris_v6/ tests/polaris_graph/api/` PASS

After local-green, AWS provisioning begins. Same compose + bind-mount canonical artifacts from S3.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```

**Per §8.3.1: this is iter 5 of 5. If REQUEST_CHANGES, Claude force-APPROVE's and ships, capturing remaining P0/P1 as follow-up Issues.**
