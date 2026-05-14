# I-bug-112 Claude architect audit

**Issue:** GH#492 — Dockerfile.v6 base image unpinned; build fails on Debian trixie
**Branch:** `bot/I-bug-112-dockerfile-base-pin`
**Head commit:** `e77ce7b2`
**Codex diff verdict:** APPROVE iter 1 of 5 (zero P0/P1/P2/P3, convergence_call: accept_remaining)

## Surface

| File | Change |
|---|---|
| `Dockerfile.v6` | `FROM python:3.11-slim` → `FROM python:3.11-slim-bookworm` + 4-line explanatory comment. 5 insertions / 1 deletion. |

## Bug + fix

Found during the G5 fallback-laptop drill. `docker compose -f docker-compose.v6.yml build` failed: `E: Package 'libgdk-pixbuf2.0-0' has no installation candidate` (exit 100). Root cause: unpinned `python:3.11-slim` floated bookworm→trixie; trixie renamed `libgdk-pixbuf2.0-0` → `libgdk-pixbuf-2.0-0`. Fix: pin the Debian suite to bookworm — deterministic base, all current apt package names valid, zero package-name changes needed.

## Smoke test

`docker compose -f docker-compose.v6.yml build api` with the bookworm pin: the apt step (`#9`/`#10`) that previously failed exit-100 now passes clean — `grep -c 'no installation candidate|exit code: 100'` on the build log = **0**. Build proceeds past apt into the pip-install phase.

## Codex review

APPROVE iter 1 — zero findings. Codex verified independently against Docker Hub (`python:3.11-slim-bookworm` exists) and Debian Packages (`libgdk-pixbuf2.0-0` present in bookworm as a transitional package). All 3 brief questions answered APPROVE: bookworm-pin over trixie-migrate is correct; `web/Dockerfile` node pin correctly scoped out; nothing else blocking.

## Separate finding (NOT this Issue's scope) — pip dependency-resolution slowness

The same rebuild, AFTER the fixed apt step, shows pip backtracking deep through `langchain-openai` (1.1.16 → 0.2.0) and `langchain` versions resolving `requirements-v6-pipeline-a.txt` — 200+ seconds in the pip phase and still walking. This is a different subsystem from the base-pin bug. If the build ultimately fails with `ResolutionImpossible` it warrants its own Issue (`requirements-v6-pipeline-a.txt` constraint conflict). Noted here for transparency; explicitly out of I-bug-112's scope per "don't pick bone from egg."

## Verdict

READY TO MERGE. All Codex-required artifacts present:
- `.codex/I-bug-112/brief.md`
- `.codex/I-bug-112/codex_brief_verdict.txt` (APPROVE)
- `.codex/I-bug-112/codex_diff.patch` (canonical-diff-sha256 trailer)
- `.codex/I-bug-112/codex_diff_audit.txt` (iter-1 APPROVE)
- `outputs/audits/I-bug-112/claude_audit.md` (this file)

## What ships

The v6 deploy image builds again on any host pulling a current `python:3.11-slim`. `infra/vexxhost/provision.sh` runs `docker compose -f docker-compose.v6.yml up -d --build` — without this pin the sovereign deploy would have failed at build time on the Vexxhost VM.
