HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-001 brief_v2 iter 1 — Posture C: live submission + 3-4 week timeline

## Reset reason — user scope pivot 2026-05-12

The first brief asked you to pick a 1-week demo posture (A/B/C/D, GH#462). You converged across iters 1-4 on "ship posture A (canonical library) + capture live-submission alignment as post-demo I-arch-001." Your iter-4 findings established why live submission is not a 1-week item:

- v6 API UUID run_id ≠ pipeline-A SWEEP_xxx slug (no bridge)
- V30 strict AuditIR loader needs `manifest.frame_coverage_report` + `per_query_report_contract` — only canonical pre-defined slugs have these
- Registry allowlist `_PHASE_A_ALLOWLIST` is one path; new runs invisible

**User chose Posture C (live submission, 3-4 week timeline) over your recommendation.** Boss directive 2026-05-12: "real, anyone around Mark can use it" interpreted as live submission, not canonical library exploration. Demo slip from 2026-05-19 → ~2026-06-09 accepted.

This brief restarts the Codex review thread for the wider scope. All your iter 1-4 technical findings carry forward (Dockerfile PYTHONPATH, entrypoint subcommands, broker init order, POLARIS_V6_REDIS_URL explicit, shared volumes, Next rewrites build-time ARG, GPG hygiene, run_store.mark_failed, mutex compare-and-delete) — they are real regardless of posture and are integrated below.

## Posture C scope

Carney's office staff log into a Canadian-hosted POLARIS instance and:
1. **Submit any in-scope public-policy question** through a web form
2. **Watch it run live** with SSE progress updates (4-15 min for typical questions, $2-5 OpenRouter spend)
3. **Receive a real audit-grade report** with per-claim §-1.1 verdicts, F-snowball graph, Inspector 5-view exploration, GPG-signed audit bundle export
4. **Compare runs** across templates / questions via M-13 compare endpoint
5. **Browse a canonical library** of pre-rehearsed Q1-Q5 as the "known-good demo wedge" + their own new submissions

Sovereignty (c): Canadian-hosted app + state + artifacts; foreign API egress for OpenRouter/Serper/Semantic Scholar permitted because scope is public-policy research (no PHI, no client docs). Public footer + `/transparency` endpoint discloses egress honestly.

## Critical-path sub-issues (revised for Posture C)

Tighter sequencing because the architecture work (I-arch-001) is now the early-critical-path long pole:

| ID | Title | Days | Start gate |
|---|---|---|---|
| I-arch-001 | UUID/slug/V30 contract reconciliation — bridge v6 API run_ids to pipeline-A artifacts that load via strict AuditIR | 1-10 | Now |
| I-carney-005 | Deploy substrate — Dockerfile (PYTHONPATH+gnupg), entrypoint (`api`/`worker` subcommands), broker init order, compose (redis+worker+webui+shared volumes), Next rewrites build-time ARG | 11-13 | I-arch-001 partial (UUID-routable artifacts) |
| I-carney-002 | AWS Canada infra — VPC/EC2 m7i-flex.4xlarge/ALB/ACM/Route 53/SSM/EBS snapshots/S3 canonical bucket | 14 | I-carney-005 local-green |
| I-carney-003 | Sovereignty + transparency endpoint + egress controls + OpenRouter ZDR config | 14-16 | parallel with 002 |
| I-carney-004 | Static_accounts auth + GPG demo key + AWS Secrets Manager wiring | 17-18 | I-carney-002 |
| I-carney-006 | Live-submission rehearsal — submit Q1-Q5 + 5 fresh staff-style questions; full §-1.1 audit on each output | 19-22 | I-carney-004 |
| I-carney-007 | Demo runbook + transparency.md + fallback laptop + 30-min internal rehearsal + Codex sign-off | 23-24 | I-carney-006 |

Total 24 days = 3.5 weeks. Target demo ~2026-06-05 to ~2026-06-09. Buffer days 25-28 for unforeseen.

## I-arch-001 technical plan (the new critical-path long pole)

### Problem statement (from your iter 4)

1. `polaris_v6.api.runs:25` generates UUID; `scripts.run_honest_sweep_r3:1128-1130` generates `SWEEP_<timestamp>` — UUIDs never reach pipeline-A
2. `polaris_graph.audit_ir.loader:620-627` requires `manifest.frame_coverage_report`
3. `polaris_graph.v30_sweep_integration:285-298` only merges V30 when slug has `per_query_report_contract`
4. `polaris_graph.audit_ir.registry:40,161` allowlist tuple-of-one; rebuilt only at module import

### Resolution plan

**1. UUID/slug bridge**:
- `actors.py:enqueue_research_run(run_id, payload)` no longer stub. Calls `polaris_graph.graph_v4.build_and_run_v4(run_id=run_id, payload=payload, out_root=...)`.
- `build_and_run_v4` derives a deterministic sweep slug from run_id: `sweep_slug = f"v6_{run_id[:8]}"` and pins it via the existing run_one_query slug parameter (which CURRENTLY auto-generates but accepts override).
- New env `POLARIS_V6_SWEEP_SLUG_PREFIX=v6` controls the prefix.
- After completion, `actors.py` writes `state/run_id_to_sweep_slug.json` mapping for the registry to consume.

**2. V30 contract synthesizer for ad-hoc questions**:
- New module `src/polaris_graph/v30_contract_synthesizer.py`:
  - Inputs: question text, template_id, domain
  - Outputs: `per_query_report_contract` dict (frames list, completeness checklist, scope constraints) — derived from `config/v6_templates/{template_id}.yaml`
- Wire into `scripts/run_honest_sweep_r3.py:1889-1892` — when sweep is invoked with `POLARIS_V6_MODE=1`, build contract from synthesizer instead of expecting it pre-defined.

**3. Frame-coverage-report builder for ad-hoc questions**:
- After pipeline-A run completes, `actors.py` calls new helper `polaris_graph.frame_coverage_builder.build(sweep_slug, contract)` which scans the strict_verify output + contract and writes `frame_coverage_report.json` next to `manifest.json`.
- Without this, `loader.py:620-627` rejects the artifacts.

**4. Registry replacement**:
- Replace `_PHASE_A_ALLOWLIST` tuple + frozen `_RUNS` with a workspace-scoped lookup:
  - `polaris_v6.run_store` returns sweep_slug for given UUID
  - `polaris_graph.audit_ir.registry.find_run_by_id(uuid)` reads run_store → sweep_slug → scans the artifact dir → loads RunSummary
  - Canonical V30 dir stays accessible by its canonical slugs (no UUID lookup)

**5. SSE progress updates for live run watching**:
- `scripts/run_honest_sweep_r3.py` already emits stage events; pipe them into `src/polaris_v6/api/stream.py` SSE channel keyed by run_id.
- Frontend Next `/api/stream/{run_id}` proxied per Next rewrites.

### I-arch-001 risk and acceptance criteria

- **Risk**: pipeline-A's run_one_query may have hidden assumptions about slug shape (e.g., canonical-domain detection). I'll grep these in I-arch-001 brief #1 (smoke test offline per §-1.2 #3).
- **Acceptance**: `POST /runs {"question": "X", "template_id": "Y"}` → UUID → 4-15 min later → `GET /api/runs/{uuid}/graph` returns a real GraphPayload with real claims/sources/contradictions for question X; `GET /api/runs/{uuid}/audit-bundle` returns GPG-signed tar.gz.

## Carry-forward from brief v1 iters 1-4 (already converged)

These are decisions you APPROVE'd or pinned in iters 1-4; integrated into Posture C without re-debate:

- **Sovereignty (c)**: Canadian-hosted public-policy research, foreign egress permitted, transparency endpoint discloses
- **Vendor: AWS ca-central-1 Montréal**: m7i-flex.4xlarge EC2 (16 vCPU, 64 GB RAM, 500 GB gp3 EBS), single instance, docker-compose stack — sufficient because concurrency target stays 1 active run + N viewers
- **Auth: static_accounts** — pre-provisioned named accounts, admin/operator/viewer roles, RBAC enforcement
- **Concurrency cap = 1** via Redis mutex + worker `--processes 1 --threads 1`
- **Dockerfile PYTHONPATH=/app/src:/app**
- **scripts/docker_entrypoint.sh** adds `api`, `worker` subcommands
- **Broker init order**: api `create_app()` and new `polaris_v6.queue.run_worker` module both call `get_broker()` BEFORE importing actors
- **Compose**: api + worker + redis + chromadb + webui services; named volumes for state/data; bind-mount `./outputs` (for canonical V30 artifacts)
- **Next rewrites build-time ARG INTERNAL_API_URL**: defaults http://api:8000 (compose internal); AWS uses same default since api+webui colocate
- **GPG signing**: gnupg installed in image; key mounted from compose secret (local) / AWS Secrets Manager (AWS); entrypoint verifies `gpg --list-secret-keys $POLARIS_GPG_KEY_ID` succeeds
- **Redis mutex hygiene**: nx+ex acquire, Lua compare-and-delete on release
- **run_store.mark_failed** added (was missing)
- **Logging/observability**: AWS X-Ray via ADOT sidecar on EC2; CloudWatch logs; v6 OTEL stack already pinned per #123
- **Transparency wording**: "Canadian-hosted public-policy research; inference services (OpenRouter, Serper, Semantic Scholar) reside outside Canada; no PHI/client-confidential content sent" — never claims "sovereign Canadian AI"

## Direct questions for iter 1 (this brief)

1. I-arch-001 plan (UUID/slug bridge + V30 contract synthesizer + frame-coverage builder + registry replacement + SSE) — APPROVE'd as the architecturally-honest path, or is there a simpler alternative I'm missing?
2. 24-day calendar / ~2026-06-05 to ~2026-06-09 demo target — APPROVE'd? Anything that should change order?
3. SSE channel: pipe pipeline-A stage events into v6 stream endpoint — APPROVE'd, or does the v6 stream already have a different event protocol that I should not bridge to?
4. Risk of hidden pipeline-A slug-shape assumptions — am I missing a known assumption (canonical-domain detection, template-id lookup-by-slug, RuntimeError on UUID-shaped slug, etc.)?
5. Posture A canonical library STILL ships as the "known-good demo wedge" backup (Q1-Q5 available even if live submission misbehaves on demo day) — APPROVE'd?
6. The architecture work needs `tests/polaris_v6/test_uuid_to_graph_e2e.py` end-to-end test from POST /runs through GET /api/runs/{uuid}/graph — APPROVE'd, or do you want a stricter contract test (e.g., golden artifact byte-equality)?
7. Anything else I haven't surfaced?

## Resource discipline note (per CLAUDE.md §8.4)

For I-arch-001 work I will not run pipeline-A end-to-end during dev iteration (single run = 4-15 min + $2-5 OpenRouter spend). Use the `--dry-run` smoke flag (or write one) + small fixture pinned at `tests/fixtures/v6_e2e_pinned/`. Full pipeline-A invocation only at I-carney-006 rehearsal.

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
