# I-cd-002 — Claude architect audit

**Issue:** GH#606 — Redeploy current `polaris` HEAD to the live OVH demo VM.
**Deliverable:** `scripts/redeploy_v6.sh` + a "Redeploying over a running stack"
section in `docs/deploy_runbook.md`.
**Brief:** `.codex/I-cd-002/brief.md` — Codex APPROVE iter 2 (iter 1 was
REQUEST_CHANGES with 2 P1; both fixed).

## What this changes

- New `scripts/redeploy_v6.sh` (169 lines): a six-phase, workstation-driven
  redeploy of the live box. No production *code* path changes — it is deploy
  automation only.
- `docs/deploy_runbook.md` +26 lines: documents how to run it.

## Risk surface + dispositions

- **Live TLS site.** HEAD's tracked `Caddyfile` is env-parameterized
  (`{$POLARIS_DOMAIN}`), but the box `.env` has neither `POLARIS_DOMAIN` nor
  `POLARIS_ACME_EMAIL`. Phase 3 appends them before `up -d` — without that, the
  redeploy would render an empty site address and take TLS down. Caught in the
  brief (§C), encoded in the script.
- **Volume data.** `polaris_shared_state` / `redis_data` / `caddy_data` are
  snapshotted with all writers quiesced (Phase 1). The forward path never runs
  `down -v`, so the named volumes persist; the Let's Encrypt cert in
  `caddy_data` is reused (same volume, project name pinned `-p polaris`).
- **Rollback.** State-aware (Phase 6): restores the OLD compose files in place +
  `up -d --force-recreate`; never an unconditional forward `down`. `-p polaris`
  on every compose call so volume namespacing never drifts.
- **Downtime.** The build runs while the old stack still serves; only the
  `up -d` recreate is ~1-2 min — acceptable for a pre-Carney box (Codex P2-3).

## Verification done

- `bash -n` on the outer script AND all six remote heredoc bodies — clean.
- The script has NOT yet been executed against the box. Execution + evidence
  capture (`live=HEAD`, 4 healthchecked containers healthy, https smoke OK) is
  the post-merge GREEN step for I-cd-002, run once the PR lands so the box
  receives the merged `polaris` HEAD.

## Codex P2 dispositions

All four iter-2 P2s are non-blocking and folded in: ACME email is
caller-provided (no silent default); the auto-rollback guarantee is not
overstated (volume restore is manual); the `caddy_data` snapshot is documented
as best-effort; in-container `curl` is guaranteed by `Dockerfile.v6`.
