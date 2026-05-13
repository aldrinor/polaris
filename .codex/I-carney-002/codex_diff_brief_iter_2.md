HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-002 diff iter 2 — 4 P1 resolutions

## P1-001 — ALB routing for /api/v6 + /stream

Resolved by simplifying the ALB to route EVERYTHING to webui:3000 (default action) PLUS one explicit /health → api rule for ops liveness. Next.js handles the `/api/v6/*` rewrite + SSE pass-through, including `/api/v6/stream/{id}` (no separate ALB `/stream/*` rule needed because the frontend never opens a raw `/stream/*` URL — it always uses `/api/v6/stream/{id}` per the I-carney-005 web/lib/api.ts patch).

**Removed:** `aws_lb_listener_rule.api_v6` and `aws_lb_listener_rule.stream_sse`.
**Kept:** `aws_lb_listener_rule.health` for ops; default action forwards to webui.

ALB still has `idle_timeout = 300s` so the long-running Next.js → api SSE proxy connection doesn't get cut.

## P1-002 — EC2 depends_on for SSM params + IAM attachments

Added to `aws_instance.polaris`:
```hcl
depends_on = [
  aws_ssm_parameter.openrouter_api_key,
  aws_ssm_parameter.serper_api_key,
  aws_ssm_parameter.polaris_gpg_key_id,
  aws_ssm_parameter.polaris_gpg_pubkey,
  aws_iam_role_policy_attachment.ssm_managed,
  aws_iam_role_policy_attachment.ssm_read,
  aws_iam_role_policy_attachment.s3_audit_write,
]
```

Now cloud-init.sh can never race the SSM/IAM substrate; first-apply works.

## P1-003 — EC2 KMS permissions on the audit bucket

Extended `aws_iam_policy_document.s3_audit_write` with a second statement:
```hcl
statement {
  actions   = ["kms:Encrypt", "kms:GenerateDataKey", "kms:Decrypt", "kms:DescribeKey"]
  resources = [aws_kms_key.audit.arn]
}
```

Now S3 PutObject under aws:kms (with our CMK) actually works from the EC2 role.

## P1-004 — ALB depends on log bucket policy

Added to `aws_lb.polaris`:
```hcl
depends_on = [aws_s3_bucket_policy.alb_logs]
```

So Terraform never enables access logs before the regional ELB account has write permission to the bucket.

## P2 resolutions (also addressed)

- **Data EBS fragility:** `cloud-init.sh` now checks for existing filesystem via `blkid` and only `mkfs.ext4 -L polaris-data` when blank. Mounts via `LABEL=polaris-data` so device-name drift (nvme1n1 vs xvdf) doesn't break the mount on instance replacement.
- **AAAA + IPv6 SG ingress:** ALB set to `ip_address_type = "dualstack"`; ALB SG ingress 443+80 now includes `ipv6_cidr_blocks = ["::/0"]`.
- **S3 buckets force_destroy:** `aws_s3_bucket.audit` and `aws_s3_bucket.alb_logs` both set `force_destroy = true` so `terraform destroy` cleans up. README still warns to recover bundles before destroy.

## P3 cosmetic notes (deferred)

- `tf_state_bucket` variable unused — kept for documentation; backend-config flag is the actual wire-up.
- `.terraform.lock.hcl` committed: deferred to a Phase-2 follow-up (operator pins on first init).

## Direct questions iter 2

1. The 4 P1 fixes + 3 P2 fixes — APPROVE'd?
2. Routing everything-except-/health to webui (so Next.js handles the rewrite + SSE proxy) — APPROVE'd?
3. Anything else blocking iter-2 APPROVE?

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
