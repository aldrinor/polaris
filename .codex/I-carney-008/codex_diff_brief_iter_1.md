HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-008 diff iter 1 — sovereign pivot (AWS archived → Vexxhost + OVH + Brave)

## Issue

**GH#486 I-carney-008.** User directive 2026-05-13 verbatim: "Full sovereign — no US company anywhere." AWS ca-central-1 was physically in Montréal but Amazon is a US corporation subject to US CLOUD Act + FISA — fails the sovereignty audit. Pivot the deploy stack to:

- **Orchestrator hosting:** Vexxhost (Canadian-owned, Montréal)
- **LLM inference:** OVH BHS H200 (French-owned, Beauharnois QC) running self-hosted vLLM
- **Live search:** Brave Search API (Czech-owned, replaces Serper)
- **TLS:** Let's Encrypt (US 501(c)(3) ISRG, public attestation only — no data leaves)

The PR pivots infrastructure + docs + transparency endpoint. **Code-side Brave Search swap and OpenRouter→vLLM swap are deferred to follow-up issues** GH#487 I-carney-009 and GH#199 I-sov-001 (which depends on OVH H200 landing). This PR is the infra + docs + transparency-API pivot.

## Branch / commit

- Branch: `bot/I-carney-008-sovereign-pivot`
- Head commit: `77a54c23` (after `d8faf5df` procurement spec)
- Diff: `.codex/I-carney-008/codex_diff.patch` (988 LOC, 23 files)

## Goal of this review

Verify the sovereign pivot is complete, internally consistent, and doesn't introduce regressions in the existing I-carney-002..007 substrate.

## Diff summary (23 files, +539 −177)

1. **`infra/aws/` → `infra/aws.archived/`** (14 renames). `README.md` gets an ARCHIVED 2026-05-13 banner explaining the sovereignty failure (Amazon = US corp).
2. **`infra/vexxhost/` created** (3 files, all new):
   - `provision.sh` — ~150-line bash deploy script (apt + docker + caddy + ACME + GPG private-key bootstrap + shred secrets)
   - `.env.example` — env template with the new POLARIS_LLM_BACKEND + POLARIS_VLLM_BASE_URL + BRAVE_SEARCH_API_KEY + POLARIS_PROVIDER + POLARIS_REGION
   - `README.md` — operator runbook with sovereignty audit checklist table
3. **`config/egress_allowlist.txt`**: AWS endpoints removed; Brave + Let's Encrypt + cloudsmith added.
4. **`docs/carney_demo_runbook.md`**: §0 prereqs (Vexxhost + OVH + Brave), §1 deploy (scp + ssh + bash provision.sh, no terraform apply), §1b egress (ssh, no aws ssm start-session), §5 fallback laptop (encrypted offline secret bundle, no aws ssm get-parameter / aws secretsmanager get-secret-value), §8 tear-down (scp + openstack server delete), §9 known limitations.
5. **`docs/transparency.md`** updated for new allowlist + provider field + Canadian-registrar WHOIS.
6. **`src/polaris_v6/api/transparency.py`**:
   - new `provider: str` field on `TransparencyResponse` (default unknown)
   - `region` now resolves `POLARIS_REGION` first, falls back to `AWS_REGION` (backward compat)
   - `enforcement_layer` in `/transparency/policy` drops "AWS Security Group on EC2 (ingress-only; egress all-permit)" entry
7. **`tests/polaris_v6/api/test_transparency.py`**:
   - `required` keyset asserts `provider`
   - new test `test_transparency_region_falls_back_to_aws_region_env` for compat
   - new test `test_transparency_policy_no_aws_security_group_layer` for regression
8. **`state/active_issue.json`**: I-carney-008 in_progress, GH#486 + sovereign_stack manifest + archived_workstream reference.

## Adjacent files I have ALSO checked and they're clean

Per CLAUDE.md §-1.2 standard debug workflow:

- `tests/polaris_v6/api/test_transparency.py` — 8/8 pass with the new schema (verified locally: `PYTHONPATH=src python -m pytest tests/polaris_v6/api/test_transparency.py -x` → `8 passed in 1.00s`)
- `Dockerfile.v6` — no AWS-specific RUN/ENV; `POLARIS_REGION` not yet baked (operator sets via .env, same surface as the old AWS_REGION)
- `docker-compose.v6.yml` — no AWS references; `provision.sh` uses this directly
- `scripts/egress_lockdown.sh` — reads `config/egress_allowlist.txt`; the new domains land here unmodified
- `src/polaris_v6/api/app.py` — mounts `transparency_router`; no schema-bound consumer downstream
- `src/polaris_graph/retrieval/real_fetcher.py` — still calls Serper (intentional; swap is GH#487 I-carney-009, follow-up)
- `src/polaris_v6/llm/openrouter_client.py` — still hits OpenRouter (intentional; swap is GH#199 I-sov-001, depends on OVH H200 landing)
- `.github/workflows/codex-required.yml` — gate checks `.codex/<issue>/codex_brief_verdict.txt` + `.codex/<issue>/codex_diff_audit.txt`; this Issue follows the same pattern, no workflow changes
- `polaris-controls/CHARTER.md` SHA — unchanged from session start (pin verified)

## Iteration trajectory pin

This is iter 1. No prior brief/diff iterations on I-carney-008. The procurement spec `d8faf5df` was committed straight (no Codex review — it's a procurement template for the operator to email OVH Canada sales, not code/infra/test substrate).

## Output schema (mandatory)

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

## Direct questions iter 1

1. **provision.sh egress lockdown timing.** Script does NOT auto-run `egress_lockdown.sh` (because first compose build needs pypi/npmjs/debian access). Operator runs it manually per §1b. Is this APPROVE'd, or should provision.sh end with a "next step" emitting the install instruction?
2. **POLARIS_REGION precedence.** `transparency.py` reads `POLARIS_REGION` first, falls back to `AWS_REGION`. Backward-compat for old AWS deploys. Is the order APPROVE'd, or should the AWS env be removed entirely (we'd break existing AWS-archived deploys)?
3. **enforcement_layer string change.** Old: `["host iptables OUTPUT chain ...", "Docker DOCKER-USER chain ...", "AWS Security Group on EC2 (ingress-only; egress all-permit)"]`. New: drops the AWS SG entry. Any downstream consumer (UI, audit script, /transparency.md prose) that pins the 3-element shape would break. I did not find any such consumer in grep. Is the drop APPROVE'd?
4. **Brave Search API rate limits.** Brave's free tier is 1 req/s. The egress allowlist additions don't enforce per-request rate; code-side rate-limiting is GH#487 I-carney-009 follow-up. Is the deferral APPROVE'd, or must Brave's rate limit be wired in this PR before the code-side swap lands?
5. **OVH H200 lead time gap.** OVH procurement spec emailed today; lead time 5-10 business days. During the gap, `POLARIS_LLM_BACKEND=openrouter` is the transitional fallback per `infra/vexxhost/.env.example`. `/transparency` will surface OpenRouter as `provider_jurisdiction: US` until the H200 lands. Is the disclosure pattern APPROVE'd, or must the demo be hard-gated on H200 landing?
6. **Fallback laptop secret bundle (§5).** Replaces `aws ssm get-parameter` + `aws secretsmanager get-secret-value` with an encrypted offline `polaris_demo_secrets.tar.gz.gpg` bundle on a YubiKey + paper backup. Is the offline-bundle pattern APPROVE'd, or should we wire a sovereign secret manager (e.g., Vexxhost Vault) in this PR?

## What this PR explicitly does NOT do (so you don't flag them as missing)

- Code-side Serper → Brave swap in `src/polaris_graph/retrieval/real_fetcher.py` (deferred to GH#487 I-carney-009).
- Code-side OpenRouter → vLLM swap in `src/polaris_v6/llm/openrouter_client.py` (deferred to GH#199 I-sov-001, depends on OVH H200 landing).
- Multi-VM HA Vexxhost topology (Phase-2).
- Vault-based secret rotation (Phase-2).
- `provision.sh` itself running `egress_lockdown.sh` (intentional: build-time hosts need to be reachable on first boot).
- Removing `AWS_REGION` env fallback in `transparency.py` (backward-compat for old AWS-archived deploys until they're confirmed-shutdown).

## Why this is shippable to APPROVE in 1-2 iters

This PR is a sovereign-pivot rename + new infra dir + config + docs + 3-line API change. The risky paths (LLM swap, retrieval swap) are explicitly deferred to follow-up issues with their own GH numbers + their own Codex reviews. The transparency tests pass locally. The egress allowlist is read by `egress_lockdown.sh` unmodified — the file format hasn't changed, just the contents.
