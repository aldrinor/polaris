# I-carney-003 Claude architect audit

**Issue:** GH#471 — Sovereignty + transparency endpoint + egress controls
**Branch:** `bot/I-carney-003-sovereignty-transparency`
**Codex brief verdict:** APPROVE (force-approved per §8.3.1 — design accepted)
**Codex diff verdict:** APPROVE iter 3 of 5

## Surface

8 files (7 new + 3 patches). Adds reviewer-visible audit endpoints + iptables egress lockdown.

| File | LOC | Purpose |
|---|---|---|
| `src/polaris_v6/api/transparency.py` | 224 | NEW: 3 routes (`/transparency`, `/transparency/pubkey.asc`, `/transparency/policy`). Pubkey fallback chain: env path → `gpg --armor --export` → 503. POLARIS_GIT_COMMIT env over .git/HEAD probe. |
| `src/polaris_v6/api/app.py` | +2 | mount transparency_router |
| `web/next.config.ts` | +11 | rewrites for `/transparency` + `/transparency/:path*` → api |
| `config/egress_allowlist.txt` | 37 | 18 allowed domains (LLM + retrieval + Docker + AWS SSM + build-time) |
| `scripts/egress_lockdown.sh` | 114 | idempotent iptables installer; chains in BOTH OUTPUT + DOCKER-USER |
| `docs/transparency.md` | 95 | 6-section public reference for reviewers |
| `infra/aws/cloud-init.sh` | +20 | persists armored pubkey to disk + copies allowlist to /etc/polaris/ + injects POLARIS_GIT_COMMIT + AWS_REGION into .env |
| `tests/polaris_v6/api/test_transparency.py` | 138 | 6 tests covering all routes + 503 path + production-default path shape |

## Codex iteration trail

| Doc | Iter | Outcome | Real findings |
|---|---|---|---|
| brief | 1 | REQUEST_CHANGES | P1-001 ALB doesn't route /transparency; P1-002 cloud-init doesn't write pubkey file; P1-003 OUTPUT doesn't constrain containers; P1-004 SSM endpoints missing |
| brief | 2 | REQUEST_CHANGES (Codex conflating brief vs diff stage; checking filesystem) | "files not yet present" |
| diff | 1 | REQUEST_CHANGES | P1-004 container can't see /etc/polaris/* (host-only path); P2 log location overpromise; P3 unused Any import |
| diff | 2 | REQUEST_CHANGES | P1 git_commit unresolvable in container (Dockerfile.v6 doesn't COPY .git); P2 AWS SG not actually egress allowlist; P2 domain count mismatch |
| diff | 3 | **APPROVE** | zero P0/P1; 1 P2 non-blocking (docs:71 layer-summary cosmetic); 1 P3 cosmetic (stale build-arg reference) |

## P1 resolutions

1. **P1-001 (ALB → /transparency):** Two Next.js rewrites added for `/transparency` + `/transparency/:path*` → `${INTERNAL_API_URL}/transparency*`. Browser hits webui → Next.js proxies to api:8000.
2. **P1-002 (pubkey file path):** `cloud-init.sh` writes the armored ASCII to `/var/lib/polaris/gpg/polaris_demo_pubkey.asc` after `gpg --import`. Compose bind-mount surfaces it inside container at `/app/gpg/polaris_demo_pubkey.asc`. Endpoint reads via `POLARIS_GPG_PUBKEY_PATH` env (default `/app/gpg/...`), falls back to `gpg --armor --export` if absent.
3. **P1-003 (Docker DOCKER-USER chain):** `egress_lockdown.sh` installs TWO chains: `POLARIS_EGRESS_HOST` into OUTPUT (host outbound) AND `POLARIS_EGRESS_DOCKER` into DOCKER-USER (container forwarded). Bridge-network container traffic now constrained.
4. **P1-004 (allowlist coverage + container path):**
   - Allowlist now includes `google.serper.dev`, `ssm.ca-central-1.amazonaws.com`, `ssmmessages.ca-central-1.amazonaws.com`, `ec2messages.ca-central-1.amazonaws.com`, `s3.ca-central-1.amazonaws.com`, `pypi.org`, `files.pythonhosted.org`, `deb.debian.org`, `security.debian.org`, `registry.npmjs.org`, `github.com`, `codeload.github.com`, `registry-1.docker.io`, `auth.docker.io`, `production.cloudflare.docker.com`, `openrouter.ai`, `api.openrouter.ai`, `api.semanticscholar.org` (18 total).
   - **Container path fix (iter-1 diff):** default changed to `/app/config/egress_allowlist.txt` (baked by Dockerfile.v6's `COPY config/ config/`) so `/transparency` returns the real list in production. New regression test `test_transparency_egress_allowlist_default_path_is_in_container` asserts path shape.
   - **git_commit fix (iter-2 diff):** `POLARIS_GIT_COMMIT` env override (set by cloud-init from `POLARIS_REPO_COMMIT` tfvar) → falls back to `.git/HEAD` probe for local dev.
   - **enforcement_layer honesty (iter-2 diff P2):** AWS SG description corrected to `"AWS Security Group on EC2 (ingress-only; egress all-permit)"` — egress allowlist enforcement is iptables, not SG.

## Test evidence

```
$ python -m pytest tests/polaris_v6/api/test_transparency.py
6 passed in 2.26s
```

## Verdict

READY TO MERGE. All Codex artifacts present:
- `.codex/I-carney-003/brief.md` + `brief_iter_2.md`
- `.codex/I-carney-003/codex_brief_verdict.txt` (APPROVE)
- `.codex/I-carney-003/codex_diff.patch`
- `.codex/I-carney-003/codex_diff_audit_iter_3.txt` (APPROVE)
- `outputs/audits/I-carney-003/claude_audit.md` (this file)
