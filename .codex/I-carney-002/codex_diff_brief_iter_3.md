HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-002 diff iter 3 — P1 IPv6 mismatch + P2 EBS retry

## P1 (iter-2) — dualstack ALB without VPC IPv6 (resolved)

VPC IPv6 isn't enabled in the demo VPC. Two paths: (a) enable IPv6 on VPC + subnets, or (b) drop dualstack + AAAA. Chose (b) for minimal demo scope per Codex hint "drop dualstack + the AAAA record."

### Fix

- `infra/aws/alb.tf:48` → `ip_address_type = "ipv4"` (was `"dualstack"`)
- `infra/aws/alb.tf` ALB SG → removed `ipv6_cidr_blocks` from 443 + 80 ingress
- `infra/aws/route53.tf` → removed `aws_route53_record.polaris_aaaa`

IPv6 reachability is documented as Phase-2 follow-up in route53.tf comment.

## P2 (iter-2) — EBS attachment race (resolved)

`cloud-init.sh:35-44` previously checked once. Race: `aws_volume_attachment` finishes after instance boot, so a slow attachment makes the device probe fail.

### Fix (cloud-init.sh:35-52)

Polling loop with 60 × 2s = 120s timeout:
```bash
for attempt in $(seq 1 60); do
    for candidate in /dev/nvme1n1 /dev/xvdf /dev/sdf; do
        if [ -b "$candidate" ]; then
            DATA_DEV="$candidate"
            break 2
        fi
    done
    echo "[cloud-init] waiting for data EBS to attach (attempt $attempt/60)"
    sleep 2
done
```

Fails loud per LAW II if EBS never attaches.

## P2 acknowledged but deferred

- Docker named volumes (`shared_state`) live on /var/lib/docker (root volume), NOT on `/var/lib/polaris/state` (data EBS). On instance replacement, the named volume + bind mounts in compose all reside on the new root volume; the data EBS `polaris-data` survives. This is intentional: I-carney-005's compose already maps `./outputs ./logs ./data` to host bind paths, and cloud-init creates those paths under `/opt/polaris/` (root volume). Moving them to `/var/lib/polaris/` requires patching `docker-compose.v6.yml` which is out of scope for I-carney-002. **Captured as Phase-2 follow-up Issue:** bind compose volumes to /var/lib/polaris/* for cross-instance persistence.

## Direct questions iter 3

1. Drop dualstack + AAAA (vs enabling VPC IPv6) — APPROVE'd?
2. EBS attachment polling loop (120s timeout) — APPROVE'd?
3. Docker volume persistence Phase-2 follow-up acknowledged out-of-scope — APPROVE'd?
4. Anything else blocking iter-3 APPROVE?

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
