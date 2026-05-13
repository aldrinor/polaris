HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-003 diff iter 3 — git_commit injection + enforcement_layer honesty

## P1 (iter-2) — git_commit unresolvable in container (resolved)

Dockerfile.v6 doesn't COPY .git/ (and shouldn't — bloats image). cloud-init doesn't mount /opt/polaris into the api container, so `Path("/opt/polaris/.git/HEAD")` doesn't exist from inside.

### Fix

1. `src/polaris_v6/api/transparency.py:_git_commit` — first checks `POLARIS_GIT_COMMIT` env var, then falls back to `.git/HEAD` probe, then `"unknown"`.
2. `infra/aws/cloud-init.sh:.env generation` — exports `POLARIS_GIT_COMMIT=$POLARIS_REPO_COMMIT` and `AWS_REGION=$AWS_REGION` so the container env_file has them. Pipeline-A's terraform var `polaris_repo_commit` (already pinned in terraform.tfvars) flows through.

## P2 (iter-2) — enforcement_layer honesty (resolved)

AWS SG on EC2 only filters INGRESS (3000+8000 from ALB SG). Egress is all-permit per `infra/aws/ec2.tf:114-120`. Listing it as an "egress enforcement layer" is misleading.

### Fix

`src/polaris_v6/api/transparency.py:217` — changed to `"AWS Security Group on EC2 (ingress-only; egress all-permit)"`. Honest description.

## P2 (iter-2) — domain count mismatch (resolved)

config has 18 (counted `security.debian.org`); docs said 17.

### Fix

`docs/transparency.md:69` — added `security.debian.org` to the build-time list and noted "Full count: 18 entries."

## P3 cosmetic (resolved)

`src/polaris_v6/api/transparency.py:_load_egress_allowlist` docstring now references `/app/config/egress_allowlist.txt`.

## Test results

```
$ python -m pytest tests/polaris_v6/api/test_transparency.py
6 passed in 2.26s
```

## Direct questions iter 3

1. `POLARIS_GIT_COMMIT` env injection via cloud-init `.env` (vs Dockerfile.v6 build ARG) — APPROVE'd?
2. AWS SG description corrected to "ingress-only; egress all-permit" — APPROVE'd?
3. Anything else blocking iter-3 APPROVE?

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
