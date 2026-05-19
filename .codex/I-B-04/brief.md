HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining non-P0/P1 findings.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex brief review — I-B-04 / GH#623: clean Docker build (#494)

Seq 1 of the Carney-demo breakdown (promoted from Seq 4 — I-A-01's Codex
brief-review found I-A-01 "redeploy HEAD" is blocked on this: HEAD does not
build/run cleanly). Review this **plan**; the diff comes after APPROVE.

## Context — grounded

`state/ovh_infra.md` (the box's deploy record, in the repo) documents that the
live box runs healthy on commit `26d34bcc` + 6 hand-applied fixes that **never
landed in the repo**. HEAD `ab1181ed` still carries the defects. Verified by
direct inspection of HEAD:

1. `requirements.txt:35-40` — langchain pins are all unbounded `>=` (no upper
   cap) → pip/uv resolver runaway (this is the literal #494).
2. `requirements-v6.txt:12` — `pydantic-settings==2.6.1`; `langchain-community`
   needs `>=2.10`. Build-time conflict.
3. `requirements-v6.txt:19` — `passlib[bcrypt]==1.7.4` with no `bcrypt` pin →
   bcrypt 5.0.0 resolves and breaks passlib (`module 'bcrypt' has no attribute
   '__about__'`). Needs `bcrypt==4.0.1`.
4. No `requirements.lock` in the repo → non-deterministic builds.
5. `Dockerfile.v6` — entire file has CRLF line endings; pip step installs
   directly from `requirements*.txt` (resolver runs at build time, not from a
   lock).
6. `web/Dockerfile:53` — HEALTHCHECK probes `http://localhost:3000/`;
   `localhost`→IPv6 `::1`, Next.js standalone binds IPv4 → webui reports
   unhealthy.
7. `docker-compose.v6.yml` worker block — no `healthcheck:` override, so the
   worker inherits `Dockerfile.v6`'s `:8000/health` probe; the worker is a
   Dramatiq consumer with no HTTP server → always "unhealthy".
8. No `.gitattributes`; 9 `scripts/*.sh` have CRLF — including
   `scripts/v6_entrypoint.sh` (the container ENTRYPOINT — CRLF →
   `exec /entrypoint.sh: no such file or directory`).

## Fix plan

- **F1** `requirements.txt` — cap langchain: `langchain<0.4.0`,
  `langchain-openai<0.3.0`, `langchain-community<0.4.0`, `langchain-core<0.4.0`,
  `langchain-google-genai<3.0.0` (lower bounds unchanged).
- **F2** `requirements-v6.txt` — `pydantic-settings` → `>=2.10.1,<3.0.0`;
  append `bcrypt==4.0.1`.
- **F3** `requirements.lock` — add a deterministic lockfile. **Approach:** the
  box has a proven `uv pip compile` lock (282 pkgs) generated against the
  capped requirements; diff HEAD's requirements (post-F1/F2) vs the box's — if
  equivalent, scp the box's proven lock into the repo; if HEAD diverges,
  regenerate with `uv pip compile` ON THE BOX (uv 0.11.14 installed there) so
  the lock is consistent with HEAD-post-F1/F2.
- **F4** `Dockerfile.v6` — strip CRLF → LF; pip step installs from
  `requirements.lock`; keep the `google-generativeai` strip line.
- **F5** `web/Dockerfile:53` — `localhost` → `127.0.0.1`; add `ENV HOSTNAME=0.0.0.0`
  so Next.js standalone binds IPv4.
- **F6** `docker-compose.v6.yml` — add a `worker` healthcheck override
  (`CMD-SHELL` python redis-socket reachability check, the box's proven one).
- **F7** `.gitattributes` (new) — `*.sh text eol=lf`, `Dockerfile* text eol=lf`.
- **F8** Convert the 9 CRLF `scripts/*.sh` to LF.

## Verification

On the box (it has Docker + uv + the build context): `docker compose -f
docker-compose.v6.yml build` completes with no resolver runaway; `up -d` →
all 5 containers reach `healthy`. The box ALREADY runs healthy with the
equivalent of F1-F8 — this issue lands them in the repo so HEAD itself builds.

## 200-LOC cap note

`requirements.lock` (~282 generated lines) + the CRLF→LF whitespace conversion
of 9 scripts dominate the diff line count. The hand-authored code change is
small (~12 lines across requirements + Dockerfiles + compose). Requesting the
standard generated-file / whitespace-only exemption — flag if you disagree.

## Files I have ALSO checked and they are clean / accounted for

- `docker-compose.caddy.yml` (box-local) — not touched; HEAD's
  `docker-compose.v6.yml` already has a `caddy` service + tracked `Caddyfile`,
  so the box-local override is dropped at I-A-01 redeploy, not here.
- `docker-compose.yml` (legacy pipeline-B) — untouched, not in the v6 build.
- `scripts/docker_entrypoint.sh` — pipeline-B legacy; CRLF-converted by F8 for
  hygiene but not on the v6 path.
- webui already has `INTERNAL_API_URL` build arg + `expose: 3000` + no host
  ports (I-rdy-015) — unchanged.

## Open questions for Codex

1. F3: use the box's proven lock, or always regenerate against HEAD? Risk if
   HEAD's requirements diverged from the box's beyond the F1/F2 caps.
2. F5: web/Dockerfile `ENV HOSTNAME` vs a compose `environment:` override —
   which is the cleaner home for it?
3. Any defect in HEAD's build/run path NOT in F1-F8?

## Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
