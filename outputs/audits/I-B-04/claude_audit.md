# I-B-04 / GH#623 — Claude architect audit

**Issue:** clean Docker build (#494) — Seq 1 of the Carney-demo breakdown.
**Branch:** `bot/I-B-04-clean-docker-build`.

## What changed (7 files)

| File | Change | Maps to |
|---|---|---|
| `requirements.txt` | langchain/langgraph pins upper-capped | F1 |
| `requirements-v6.txt` | `pydantic-settings>=2.10.1,<3.0.0`; `bcrypt==4.0.1` | F2 |
| `requirements.lock` | NEW — 284-pkg uv-compiled deterministic lockfile | F3 |
| `Dockerfile.v6` | pip installs from `requirements.lock` | F4 |
| `web/Dockerfile` | healthcheck `127.0.0.1` + `ENV HOSTNAME=0.0.0.0` | F5 |
| `docker-compose.v6.yml` | worker redis-reachability healthcheck override | F6 |
| `.gitattributes` | NEW — `*.sh` + `Dockerfile*` forced `eol=lf` | F7 |

## Verification

- **Build:** `docker build -f Dockerfile.v6` on the OVH box → **`BUILD_EXIT=0`**.
  All 13 stages completed, incl. `pip install -r requirements.lock` (the #494
  resolver-runaway concern) and the `COPY scripts/v6_entrypoint.sh` ENTRYPOINT.
- **Lockfile:** `uv pip compile` on the box, python-3.11 target, v6-stripped
  input. Key pins verified: `bcrypt==4.0.1`, `pydantic-settings==2.14.1`,
  `langchain==0.3.30`, `langchain-core==0.3.86`, `protobuf==6.33.6`;
  `google-generativeai` correctly excluded.
- **F8 finding:** the repo `.sh`/`Dockerfile` blobs were verified already-LF
  via `git cat-file` (raw, no smudge) — the box's CRLF entrypoint failure came
  from the deploy transfer, not the repo. `.gitattributes` (F7) is the guard.

## Risk

Low. requirements.lock is large (1058 lines) but generated; the hand-authored
change is ~30 lines. The build empirically passes. The lock is now the single
install source — if a future requirement edit lands without regenerating the
lock, the build uses the stale lock (mitigation: I-B-04 establishes the
regenerate-on-requirements-change convention; documented in the Dockerfile.v6
comment).

## Verdict

Diff matches the Codex-APPROVED brief (`.codex/I-B-04/brief.md`). Build-verified.
Ready for Codex diff review.
