# I-cred-004b (#1161) — undated-cluster copy-invariance spec decision + missing-evidence_id stable id — BRIEF for Codex

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining-non-P0/P1; do not bank issues for iter 6.
- Surface any held-back P1 NOW. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

This is a DESIGN/SPEC decision, not a diff. You raised this at the P4 (#1153) iter-5 cap. I need your ruling on the undated-cluster policy before Phase 6 (#1155) wires `cluster_mass`.

## The problem you flagged (P4 iter-5)

`src/polaris_graph/synthesis/independence_collapse.py` `_order_key`: for an ALL-undated cluster the canonical is the LOWEST-`authority_score` member. This makes `cluster_mass = authority(canonical)`:
- **Inflation direction FULLY blocked** — a higher-authority copy can never become canonical, so `weight_mass(rows + higher_auth_copy) == weight_mass(rows)`. ✓ (the vax-defense property)
- **But NOT strict equality for a LOWER-authority copy** — adding a copy whose authority is below the current min makes it the new canonical and LOWERS the mass. The plan §148 states `weight_mass(rows + copied_row) == weight_mass(rows)` for ANY copier authority.

Plus: when a canonical row has no `evidence_id`, `origin_cluster_id` falls back to `origin::idx{canonical_index}` (input-position-relative → a prepend shifts it).

## Why strict equality is unachievable for undated differing-authority clusters

For DATED clusters it IS achievable: canonical = earliest CALENDAR date; a copy is same/later/undated and can never be earlier, so the origin + its authority are invariant. ✓ (already implemented + tested.)

For an ALL-undated cluster of near-duplicate content with DIFFERING authority, there is no date and no guaranteed-monotonic identity to mark "the original." Any member-authority-based mass function that is invariant to adding an arbitrary-authority element is either a constant (throws away the signal) or ignores the new element (requires a stable original-identity we do not have). So "strict equality for ANY copier authority" cannot hold for undated clusters without either (a) requiring dates, or (b) not collapsing differing-authority undated near-dups at all.

## My proposed resolution (your ruling requested)

**1. Undated-cluster policy = conservative MIN authority (the current behaviour), documented as deliberate.** Rationale: it blocks the only DANGEROUS direction (inflation) exactly, and a lower-authority copy LOWERING the represented authority is honest information — the same content also appearing on a less-authoritative source means the claim is not exclusive to high-authority origins, so a lower mass is arguably MORE faithful, not a bug. Amend the plan to state: strict equality holds for DATED clusters; undated clusters use conservative-min (equality for copies of authority ≥ min; safe monotonic-lowering otherwise; inflation impossible for any copier authority).

**2. Missing-`evidence_id` → fail-loud** (raise a clear error) per LAW II, since real evidence rows always carry `evidence_id` and a missing one is a data bug — rather than a position-relative fallback. (Alternative: a content-hash fallback; I prefer fail-loud.)

**3. Align the module docstring** (it still says authority is never consulted; the undated path consults it in the anti-inflation direction).

## Questions for you

1. Is the **conservative-min undated policy** acceptable as the spec, or do you require TRUE equality — in which case the choice is (a) treat undated differing-authority near-dups as SEPARATE origins (no collapse), or (b) require a date/monotonic-id precondition and fail-loud otherwise? Pick one.
2. Missing-`evidence_id`: **fail-loud** vs content-hash fallback?
3. Anything else that must hold before Phase 6 multiplies `authority(canonical)` by the P2 credibility weight over origin clusters?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
