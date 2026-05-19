HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
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

## §0 — Iter-3 revisions (responding to iter-2 REQUEST_CHANGES)

Iter 1 (1 P1 + 2 P2) and iter 2 (2 P1 + 2 P2) findings are ALL fixed in
`codex_diff.patch` as it now stands. The iter-2 fixes:

- **P1 (Phase 1 could leave the box partially stopped)** — R1 now sets an EXIT
  trap immediately after `stop worker api redis` that restarts those services
  on ANY failure/interruption; the trap is cleared (`trap - EXIT`) only after
  the successful final `start`. The live box is never left down.
- **P1 (masked critical-snapshot failures)** — the `shared_state` and
  `redis_data` tars now run WITHOUT `|| echo` — a failure aborts (via R1's
  `set -e`, which fires the restart trap); only the `caddy_data` tar stays
  best-effort (caddy holds `/data` open).
- **P2 (not repeatable)** — Phase 1 now builds a dynamic `-f` compose list
  (`CF`), so it runs whether or not `docker-compose.caddy.yml` is present (that
  file is removed after a successful native-Caddy redeploy).
- **P2 (rollback did not restore `.env`)** — `rollback()` now restores `.env`
  from the backup too, so Phase-3 `.env` mutations are reverted.

The iter-1 fixes (base64 ACME email; rollback dynamic `-f` list; R3 `set_env`
upsert) remain in place.

## §A — What this is

This diff implements the Codex-APPROVED brief `.codex/I-cd-002/brief.md`. It
adds a six-phase, workstation-driven redeploy script for the live OVH demo VM,
plus a runbook section and the mandatory §8.3.5 iteration-trajectory log entry.

Canonical diff = 3 files: `scripts/redeploy_v6.sh` (NEW, ~190 lines — the
reviewable code surface), `docs/deploy_runbook.md` (+26), and
`state/polaris_restart/iteration_trajectory.md` (+26, the mandatory CLAUDE.md
§8.3.5 log).

**LOC note:** the canonical diff totals ~242 added lines, over the 200 soft cap.
The code is a single cohesive ~190-line deploy script — not meaningfully
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
