HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. The COMPLETE diff under review is the single
committed file `.codex/I-cd-008/codex_diff.patch` (~381 lines incl. trailer).
Read ONLY that one file. The probe-output JSON artifact
(`outputs/audits/I-cd-008/probe_result.json`, 1493 lines) is excluded from
the canonical diff (per the standard `outputs/audits/<id>/` exclude); it
is the raw evidence artifact + does not need diff review.

# Codex DIFF review — I-cd-008 / GH#640: GPU topology + OVH capacity probe

## §A — What this is

The diff implements the Codex-APPROVED brief `.codex/I-cd-008/brief.md`
(iter 2 APPROVE, iter 1 RC found exactly the gap Seq-8 was designed to
surface — h100-1520 quota=0 + h200-1920 absent from project flavor list).
Three files in the canonical diff:

- `scripts/ovh_gpu_topology_probe.py` (NEW, ~221 LOC) — read-only OVH API
  probe. 5 independent signals (catalog @ CA, project flavor unfiltered +
  client-side filter per iter-1 P2, per-region quota +
  `/region/{regionName}/quota/allowed` per iter-1 P2 path correction,
  `/cloud/order/rule/availability` per iter-1 P2 additional signal).
  Reads `OVH_*` from `.env`. NEVER ECHOES SECRET VALUES.
- `docs/models/gpu_topology.md` (NEW, ~132 LOC) — topology design + the
  honest "NOT OBTAINABLE NOW" verdict + operator-action escalation +
  reconciled memory contradiction + provisioning gotchas for
  I-cd-037/I-cd-038.
- `state/polaris_restart/iteration_trajectory.md` (~+10) — §8.3.5 log.

The 1493-line `outputs/audits/I-cd-008/probe_result.json` is the raw
probe output (NOT in this canonical diff — `outputs/audits/<id>/` is
excluded). It is committed in this PR alongside the canonical diff
content as the operator's traceability evidence per
`feedback_verify_primary_sources_before_relying_2026_05_15`.

## §B — Red-team focus

1. **Probe safety: NEVER ECHOES SECRET VALUES.** Confirm
   `scripts/ovh_gpu_topology_probe.py` reads `OVH_*` from `.env`
   privately and prints/writes only catalog facts (SKU names, regions,
   availability flags, quota numbers). Verify the printed summary +
   JSON artifact never carry the application key / secret / consumer
   key values.
2. **Endpoint correctness per iter-1+2 P2 corrections**:
   - `GET /cloud/project/{serviceName}/region/{regionName}/quota/allowed`
     (note the `/region/{regionName}/` prefix — script line ~104).
   - Unfiltered `GET /cloud/project/{serviceName}/flavor` + client-side
     filter by name+region (NOT region-filtered URL).
   - `/cloud/order/rule/availability` per SKU as the additional signal.
3. **APIError resilience**: `_catalog_skus()` returns a dict with `error`
   key on `BadParametersError` (the `ovh-ca` endpoint rejects
   `ovhSubsidiary=FR`); `_region_quota` / `_region_quota_allowed` /
   `_order_rule_availability` wrap in try/except. Probe never crashes
   the full run on a single-endpoint failure.
4. **Verdict logic**: `target_skus_obtainable_now = False` iff no
   project-flavor row for either target SKU has `available=True AND
   quota>=1`. Blockers explicitly named. Doc records the verdict honestly.
5. **Doc framing**: §F verdict table makes the gap unambiguous — no
   GREEN-washing.
6. **Scope discipline**: this PR ships the probe + doc + the JSON
   artifact. It does NOT open the OVH support ticket (operator action),
   does NOT rightsize Box 2, does NOT hold inventory, does NOT order.
7. **Memory contradiction reconciliation** in §C is logically sound
   (catalog presence ≠ project-region flavor allowlist ≠ per-region
   quota — three distinct gates).

## §C — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
