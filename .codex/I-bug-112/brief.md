# I-bug-112 brief — pin Dockerfile.v6 base to bookworm

**GH:** #492
**Branch:** `bot/I-bug-112-dockerfile-base-pin`
**Head commit:** `e77ce7b2`

## What

One-line fix: `Dockerfile.v6:10` `FROM python:3.11-slim` → `FROM python:3.11-slim-bookworm`, with a 4-line comment explaining why.

## Bug

Found during the G5 fallback-laptop drill. `docker compose -f docker-compose.v6.yml build` fails:

```
#9 5.530 E: Package 'libgdk-pixbuf2.0-0' has no installation candidate
ERROR: process "/bin/sh -c apt-get update && apt-get install ... libgdk-pixbuf2.0-0 ..." exit code: 100
```

## Root cause

`Dockerfile.v6:10` was `FROM python:3.11-slim` — **no Debian suite pin**. The `python:3.11-slim` tag floated from Debian bookworm (12) to **trixie (13)**. In trixie, `libgdk-pixbuf2.0-0` was renamed to `libgdk-pixbuf-2.0-0` (extra hyphen). The apt block at `Dockerfile.v6:17-26` still uses the bookworm-era name → no install candidate → exit 100.

Built fine when I-carney-005 (PR #469) shipped because `python:3.11-slim` was bookworm then. Classic floating-base-image breakage — not reproducible without the pin.

## Fix

`FROM python:3.11-slim-bookworm` — pins the Debian suite. Deterministic base; all current apt package names in the block (`gnupg curl build-essential libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev libcairo2`) are valid in bookworm. No package-name changes needed — pinning the suite is the whole fix.

## Smoke test (done)

`docker compose -f docker-compose.v6.yml build api` with the pinned base:
- The apt step (`#9`/`#10`) that previously failed exit-100 now **passes clean** — `grep -c 'no installation candidate|exit code: 100'` on the build log = **0**.
- Build proceeds past apt into the pip-install phase (`#11` — `requirements-v6-pipeline-a.txt`), which is the expected next stage and unrelated to the libgdk-pixbuf issue.

## Files I have ALSO checked and they're clean

- `web/Dockerfile` — uses `node:20-alpine` (3 stages: deps/builder/runner). Alpine package names are stable across alpine releases; not affected by the Debian-suite float. Left as-is — pinning node to a patch is a separate hygiene concern, not this bug.
- `Dockerfile` (legacy pipeline-B) — not in the v6 deploy path (`docker-compose.v6.yml` only builds `Dockerfile.v6` + `web/Dockerfile`); out of scope.
- `docker-compose.v6.yml` — references `Dockerfile.v6` for `api` + `worker`; no change needed there, the fix is entirely in the Dockerfile base line.
- The apt package list itself — all 8 packages exist under the same names in bookworm; verified the failure was specifically + only `libgdk-pixbuf2.0-0`'s trixie rename.

## Out of scope

- Migrating the image to Debian trixie + updating all renamed package names — that's a deliberate base upgrade, a separate Issue if wanted. The demo needs a working build now; pinning bookworm is the minimal correct fix.
- Pinning `web/Dockerfile`'s `node:20-alpine` to a patch tag — hygiene, not this bug.

## Direct questions for Codex

1. Is pinning to `python:3.11-slim-bookworm` the right call vs migrating to trixie + renaming the package? My reasoning: the demo is 3 weeks out, bookworm is still in Debian LTS, and a suite pin is a 1-line deterministic fix vs a multi-package migration with its own test surface. APPROVE the pin?
2. Should `web/Dockerfile`'s `node:20-alpine` also be pinned in this PR, or is that correctly a separate hygiene Issue? I scoped it out to keep this a focused 1-line P0 fix.
3. Anything else blocking APPROVE?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
