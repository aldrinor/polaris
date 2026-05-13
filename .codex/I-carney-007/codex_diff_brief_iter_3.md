HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-007 diff iter 3 — fallback laptop ssm/sm split + sudo tee

## P1-3 final (iter-2 carry-over) — resolved

Two issues in iter 2:
1. Wrong service: OPENROUTER_API_KEY / SERPER_API_KEY / POLARIS_GPG_KEY_ID are in **SSM Parameter Store** (`infra/aws/ssm_parameters.tf`), not Secrets Manager. JWT_SECRET / static_accounts_yaml / gpg_private_key_armored ARE in Secrets Manager.
2. `sudo bash -c "sm_get ..."` started a new shell that didn't see the function. Static_accounts file might not get written.

### Fix (runbook §5)

- Two helpers: `ssm_get` (Parameter Store with --with-decryption) + `sm_get` (Secrets Manager).
- API keys + GPG fingerprint use `ssm_get`.
- JWT secret + static accounts + GPG private key use `sm_get`.
- Write static_accounts.yaml via `sm_get ... | sudo tee /etc/polaris/static_accounts.yaml > /dev/null` — pipe runs in the caller's shell (function visible), sudo only elevates the tee.

## Direct questions iter 3

1. ssm_get vs sm_get split matches infra/aws/{ssm_parameters,secretsmanager}.tf — APPROVE'd?
2. `sm_get ... | sudo tee file > /dev/null` pattern — APPROVE'd?
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
