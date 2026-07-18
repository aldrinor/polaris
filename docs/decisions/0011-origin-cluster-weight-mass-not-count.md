# 0011. Aggregate corroboration by origin-cluster weight-mass, not source count

Status: accepted

Date: 2026-06-07

## Context

Counting corroboration by number of sources is unsafe when sources are copies. The vaccine adversarial fixture showed the failure: 50 near-verbatim copies of one press release masquerade as 50 independent corroborations. A COUNT-based rule (`covered_count >= target`, `DEFAULT_MIN_DISTINCT_JOURNALS = 12`) is fooled by syndication. Weight must beat count, and independence must be collapsed BEFORE the vote (`credibility_weighted_sourcing_redesign_plan_2026_06_07.md`, L5/Phase 6, Codex iter-2/3).

## Decision

Replace count aggregation with origin-cluster weight-mass. An independence-collapse step designates ONE canonical origin per cluster. `cluster_mass = authority_score(canonical origin)`. Copy and derivative members are attributed for disclosure but contribute ZERO mass — even when a republisher's own authority is HIGHER than the canonical origin's.

Binding invariants: for a dated cluster, `weight_mass(rows + copy) == weight_mass(rows)`; for an all-undated cluster the canonical is the lowest-authority member, so mass is monotonically non-increasing. A copied row can NEVER inflate the majority.

This requires L3 to emit a stable `origin_cluster_id` plus a canonical designation, not merely an `independent_origin_count` scalar. The implementation lives in `synthesis/weight_mass.py`.

## Consequences

- Syndication can no longer manufacture a false majority: 50 copies of one origin count as one origin's worth of mass.
- Copies are still disclosed (attributed for transparency), they just carry no voting weight, so the reader sees the syndication without being misled by it.
- The higher-authority-republisher case is handled deliberately: mass follows the canonical origin, not the loudest reprinter, which is counter-intuitive but correct.
- Upstream now owes a stable cluster id and canonical designation; a bare independent-origin count is insufficient and must not be used for the vote.
