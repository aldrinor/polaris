HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. The COMPLETE diff under review is the single
committed file `.codex/I-cd-002/codex_diff.patch` (~259 lines). Read ONLY that
one file. The plan it implements was APPROVED by you at brief iter 2
(`.codex/I-cd-002/brief.md`).

# Codex DIFF review iter 2 — I-cd-002 / GH#606: scripts/redeploy_v6.sh

## §0 — Iter-2 revisions (responding to iter-1 REQUEST_CHANGES)

Iter 1 returned REQUEST_CHANGES: 1 P1 + 2 P2. All three are fixed in
`codex_diff.patch` as it now stands:

- **P1 (R3 remote-env injection)** — `ACME_EMAIL` (operator-supplied) is no
  longer interpolated raw into the SSH command. It is now base64-encoded
  locally (`ACME_B64="$(printf %s "$ACME_EMAIL" | base64 | tr -d '\n')"`) and
  passed as `ACME_B64='...'`; base64 output is `[A-Za-z0-9+/=]` only, so a
  value with a single quote or any shell metacharacter cannot break or inject.
  R3 decodes it remotely: `acme_email="$(printf %s "$ACME_B64" | base64 -d)"`.
  `DOMAIN` (repo constant) and `HEAD_SHA` (hex) are still interpolated directly
  — they cannot contain shell-special characters.
- **P2-1 (rollback assumed `docker-compose.caddy.yml` exists)** — `rollback()`
  now builds the compose `-f` list from files that actually exist after the
  restore: `cf="-f docker-compose.v6.yml"; [[ -e docker-compose.caddy.yml ]] &&
  cf="$cf -f docker-compose.caddy.yml"`.
- **P2-2 (R3 appended but did not update stale values)** — R3 now uses a
  `set_env` upsert (grep-out the old line, append the new) for all three keys,
  so an existing stale `POLARIS_DOMAIN` / `POLARIS_ACME_EMAIL` is corrected,
  not left in place.

## §A — What this is

This diff implements the Codex-APPROVED brief `.codex/I-cd-002/brief.md`. It
adds a six-phase, workstation-driven redeploy script for the live OVH demo VM,
plus a runbook section and the mandatory §8.3.5 iteration-trajectory log entry.

Canonical diff = 3 files: `scripts/redeploy_v6.sh` (NEW, 177 lines — the
reviewable code surface), `docs/deploy_runbook.md` (+26), and
`state/polaris_restart/iteration_trajectory.md` (+26, the mandatory CLAUDE.md
§8.3.5 log).

**LOC note:** the canonical diff totals ~229 added lines, over the 200 soft cap.
The code is a single cohesive ~177-line deploy script — not meaningfully
splittable; the overage is entirely the mandatory runbook doc + trajectory log.
Flagging transparently — if you consider this a blocker say so; otherwise it is
a documented exemption (code surface ~177 LOC, well within reviewer-fatigue
limits).

## §B — How the brief's prior findings are encoded (verify against the diff)

- **Brief P1-1 (redis snapshot consistency)** — Phase 1 (R1 heredoc) stops
  `worker api redis` (all volume writers) before the `tar`, then `start`s them.
- **Brief P1-2 (state-aware rollback)** — `rollback()` restores OLD compose
  files in place, retags `:rollback-<utc>` images to `:latest`, runs `up -d
  --force-recreate`; no forward `down`. `ARMED` flag + `on_exit` EXIT trap, set
  `ARMED=1` only after Phase 2.
- **Brief P2s** — ACME email required (`--acme-email` / `$POLARIS_ACME_EMAIL`,
  `die` if absent); `git archive`+`rsync` sync; in-container `curl`.

## §C — Red-team focus (this script touches the LIVE demo box)

1. Are the iter-1 P1 + 2 P2 fixes (§0) actually correct and complete?
2. Does the script faithfully implement the 6 phases of the APPROVED brief?
3. Rollback: the `ARMED` flag + `on_exit` EXIT trap — fires on (and only on) a
   post-Phase-2 failure? Is `up -d --force-recreate` from the restored OLD
   files sufficient with no forward `down`?
4. Data-loss paths: ANY `down -v`? Are the `rsync --delete` excludes
   (`.env outputs/ logs/ data/ state/`) complete so runtime data is never
   pruned? Volumes are Docker-named — never removed by the forward path?
5. `-p polaris` on EVERY `docker compose` invocation (forward AND rollback)?
6. SSH heredoc safety: the `rsh "VAR='x' bash -se" <<'TAG'` pattern. With the
   base64 fix in place, is any OTHER interpolated value still injection-prone?
7. `set -euo pipefail` interactions: `|| true`, `|| echo`, `[[ ]] && .. || ..`,
   the Phase-5 `ok` poll loop — any masked failure or spurious abort?
8. The new `set_env` upsert in R3 — correct? `grep -v ... > tmp || true` + the
   `mv` — safe if a key is absent, present, or `.env` ends without a newline?
9. Anything that risks `.env`, the GPG mount, `/etc/polaris`, the
   `polaris_caddy_data` Let's Encrypt cert, or `shared_state`/`redis_data`?

## §D — The diff under review

The complete diff is the single committed file `.codex/I-cd-002/codex_diff.patch`
(~259 lines incl. the `# canonical-diff-sha256:` trailer). Read ONLY that file.
Do not open any other repository file.

## §E — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
