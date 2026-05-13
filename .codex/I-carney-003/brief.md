HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Don't bank for iter 6 — it doesn't exist.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-003 — Sovereignty + transparency endpoint + egress controls

GH#471. Critical-path day 15. The user-visible substrate that lets reviewers (incl. Carney's office) verify the deploy is sovereign: GET /transparency returns deploy provenance (region, signing key, sovereignty filter coverage, dependency list); transparency.md spec describes how to audit.

## Files I have ALSO checked clean (§-1.2 #2)

- `src/polaris_v6/api/app.py` — FastAPI app factory; routers mounted via `include_router`. transparency router will follow the same pattern.
- `src/polaris_v6/api/health.py` (referenced from app.py:81) — simplest existing endpoint to mirror (small Pydantic response + version string + lifecycle check).
- `src/polaris_graph/audit_ir/manifest_augment.py` (used by I-arch-001a) — already threads `sovereignty` field into manifest; reusable as the source of `coverage` in the transparency response.
- `src/polaris_v6/api/artifact_to_slice_chain.py` (from I-arch-001d) — `_normalize_tier` + `legal_cleared` logic already encodes sovereignty filtering. Transparency endpoint surfaces these constants for reviewers.
- `infra/aws/ssm_parameters.tf` (from I-carney-002) — `polaris_gpg_pubkey` is plain-text SSM param; EC2 cloud-init imports the public key. Transparency endpoint reads from a file path the operator writes (or directly from a GPG command).
- `outputs/polaris_demo_pubkey.asc` (from I-carney-005 bootstrap) — published verbatim at `/transparency/pubkey.asc`.
- `docker-compose.v6.yml` — egress controls happen at the host level (iptables / docker network policies) — NOT in the v6 backend code. This Issue documents the egress policy in transparency.md and provides an operator-runnable verification script; the actual iptables config lives in a `scripts/egress_lockdown.sh` helper.

## Scope

5 NEW files + 1 PATCH:

1. **NEW `src/polaris_v6/api/transparency.py`** (~120 LOC):
   - `GET /transparency` → JSON: `region`, `git_commit`, `deploy_timestamp`, `signing_key_id`, `signing_key_fingerprint`, `sovereignty_filter` (the `legal_cleared` policy + `T1`/`T2`/`T3` definitions from `artifact_to_slice_chain`), `egress_allowlist` (read from `/etc/polaris/egress_allowlist.txt` if present, else docs the policy as 'unrestricted'), `evaluator_models` (read from env: PG_GENERATOR_MODEL + PG_EVALUATOR_MODEL).
   - `GET /transparency/pubkey.asc` → `text/plain` returning the contents of `/app/gpg/polaris_demo_pubkey.asc` (mounted at deploy time via cloud-init).
   - `GET /transparency/policy` → JSON: the full sovereignty + egress policy with version string (e.g., `v1.0`) for reviewer programmatic audit.

2. **NEW `docs/transparency.md`** — the public-facing audit reference:
   - Section 1: Sovereignty filter — what tiers are accepted, how non-cleared sources cascade
   - Section 2: Evaluator models — generator + evaluator pair + two-family verification
   - Section 3: GPG signing — how to verify a bundle's signature (gpg --verify)
   - Section 4: Egress allowlist — domains the deploy can reach (operator-configured)
   - Section 5: Code provenance — git commit + container image SHA + Terraform module SHA
   - Section 6: How to file a sovereignty escalation (mailto + reviewer form)

3. **NEW `scripts/egress_lockdown.sh`** — operator-runnable iptables script:
   - Reads `/etc/polaris/egress_allowlist.txt` (one domain per line)
   - Resolves each to A records via getent
   - Builds an OUTPUT chain that allows 443 to allowlisted IPs + denies all other 443/80 outbound
   - Allows DNS (53) + NTP (123) + AWS metadata (169.254.169.254)
   - Idempotent: flushes the POLARIS_EGRESS chain before reapplying
   - Logs to /var/log/polaris-egress.log

4. **NEW `config/egress_allowlist.txt`** — the canonical allowlist for the Carney demo:
   - openrouter.ai (LLM API)
   - google.com + serpapi.com / serper.dev (Serper retrieval)
   - api.semanticscholar.org
   - github.com (Docker pulls + repo clones)
   - registry-1.docker.io + auth.docker.io (Docker registry)
   - ca-central-1.amazonaws.com + s3.ca-central-1.amazonaws.com (SSM + S3 audit upload)
   - pypi.org + files.pythonhosted.org (pip install during boot)

5. **NEW tests** `tests/polaris_v6/api/test_transparency.py` (~80 LOC):
   - GET /transparency returns valid Pydantic shape
   - GET /transparency/pubkey.asc returns text/plain with armored block
   - GET /transparency/policy returns version string + sovereignty_filter sections
   - Missing pubkey file → 503 (LAW II fail-loud)

6. **PATCH `src/polaris_v6/api/app.py`** — mount transparency router

## Acceptance criteria

1. `GET /transparency` returns JSON with all 7 required keys
2. `GET /transparency/pubkey.asc` returns 200 + `text/plain; charset=us-ascii` + `-----BEGIN PGP PUBLIC KEY BLOCK-----` prefix
3. `GET /transparency/policy.version == "v1.0"`
4. Missing pubkey path → 503, NOT 200 with empty body (LAW II)
5. `egress_lockdown.sh` shellcheck-clean + idempotent (`set -eo pipefail`)
6. `docs/transparency.md` has all 6 sections
7. New tests at `tests/polaris_v6/api/test_transparency.py` pass
8. Existing v6 test suite (396 passed) does not regress

## Direct questions iter 1

1. transparency endpoint reads pubkey from `/app/gpg/polaris_demo_pubkey.asc` (cloud-init writes here) — APPROVE'd? Or want it served directly from S3 (the audit bucket from I-carney-002)?
2. egress_lockdown.sh operates at iptables level on the EC2 host (NOT at AWS VPC level via NACLs). Acceptable, or want VPC NACLs added in I-carney-002 follow-up?
3. config/egress_allowlist.txt covers the 8 domains listed — anything to add (e.g., LangSmith if instrumented)?
4. Anything else blocking iter-1 APPROVE?

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
