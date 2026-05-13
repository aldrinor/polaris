HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001c — scope_domain mapping at actor boundary

GH#465. Day 4-6 of I-carney-001 Posture C plan. Parallel with I-arch-001b (PR #476 merged).

## Scope refinement (correcting I-arch-001a iter-3 over-mapping)

Per Codex APPROVE iter 3 of I-arch-001a brief, the week-1 mapping collapses ALL 7 non-clinical v6 templates to `policy`:

```python
# Current (from PR #475)
TEMPLATE_TO_SCOPE_DOMAIN = {
    "ai_sovereignty": "policy",   # ← but scope_gate.SUPPORTED_DOMAINS already has this
    "canada_us": "policy",         # ← already supported
    "climate": "policy",           # ← NOT supported
    "clinical": "clinical",
    "defense": "policy",           # ← NOT supported
    "housing": "policy",           # ← NOT supported
    "trade": "policy",             # ← NOT supported
    "workforce": "policy",         # ← already supported
}
```

**Code-verified** at `src/polaris_graph/nodes/scope_gate.py:69-72`:

```python
SUPPORTED_DOMAINS = frozenset({
    "clinical", "policy", "tech", "due_diligence", "custom",
    # Carney delivery templates (I-tpl-006/7/8 trio complete).
    "ai_sovereignty", "canada_us", "workforce",
})
```

Three of the seven templates are **already** in SUPPORTED_DOMAINS but were over-mapped to `policy` in I-arch-001a. Their scope templates (`config/scope_templates/<domain>.yaml`) exist with per-domain rubrics, frame_manifests, identity. Mapping them to `policy` loses that specificity.

## I-arch-001c proposed mapping

```python
TEMPLATE_TO_SCOPE_DOMAIN = {
    "ai_sovereignty": "ai_sovereignty",  # FIX: promote — SUPPORTED_DOMAINS member
    "canada_us":     "canada_us",        # FIX: promote
    "workforce":     "workforce",        # FIX: promote
    "clinical":      "clinical",         # unchanged
    # Domains NOT in SUPPORTED_DOMAINS (no scope_template yet) → fall back to "policy".
    # Per-domain template authoring (housing/trade/defense/climate.yaml) is Phase 2.
    "climate":       "policy",
    "defense":       "policy",
    "housing":       "policy",
    "trade":         "policy",
}
```

The fallback to `policy` for housing/trade/defense/climate stays intentional and **documented** as a Phase 2 follow-up: each needs a real `config/scope_templates/<domain>.yaml` + addition to `SUPPORTED_DOMAINS`.

## Files I have ALSO checked and they're clean (§-1.2 #2)

- `src/polaris_graph/nodes/scope_gate.py:69-72` — SUPPORTED_DOMAINS confirmed
- `src/polaris_graph/nodes/scope_gate.py:202-205, 339-345` — domain validation at scope template load + classification gate (raises if not in SUPPORTED_DOMAINS)
- `scripts/run_honest_sweep_r3.py:772-776` — `_SCOPE_LLM_SUPPORTED_DOMAINS = ("clinical", "policy", "tech", "due_diligence",)` — this is the LLM classifier's closed taxonomy; ai_sovereignty/canada_us/workforce can't be SELECTED by the LLM classifier, but the deterministic template-driven `run_scope_gate` accepts them via SUPPORTED_DOMAINS
- `src/polaris_v6/queue/actors.py:34-43` — current mapping (the one this Issue refines)
- `config/scope_templates/`:
  - `ai_sovereignty.yaml`, `canada_us.yaml`, `workforce.yaml` exist (verified)
  - `housing.yaml`, `trade.yaml`, `defense.yaml`, `climate.yaml` — do NOT exist (Phase 2 authoring deferred)

## Acceptance criteria

1. `actors.py:TEMPLATE_TO_SCOPE_DOMAIN` updated to promote 3 already-supported domains:
   - `ai_sovereignty → ai_sovereignty`
   - `canada_us → canada_us`
   - `workforce → workforce`
2. Comment block in actors.py documents the 4 deferred-to-Phase-2 domains (housing/trade/defense/climate → policy fallback) and links to follow-up work
3. New test `tests/polaris_v6/queue/test_template_to_scope_domain.py` verifying:
   - Every v6 template_id (8 total) has a mapping
   - Every mapping value is a member of `SUPPORTED_DOMAINS`
   - Promoted-domain mappings are identity (ai_sovereignty → ai_sovereignty, etc.)
   - Fallback mappings (housing/trade/defense/climate) all → "policy"
   - Clinical → clinical
4. LOC budget: ~30 (4 lines changed in actors.py + ~25 LOC test). Well under cap.

## Direct questions iter 1

1. Promote 3 templates (ai_sovereignty/canada_us/workforce) to identity mapping — APPROVE'd?
2. Keep 4 templates (housing/trade/defense/climate) at `policy` fallback with explicit Phase 2 follow-up comment — APPROVE'd, or want to author the 4 scope_templates in this Issue (substantially larger scope)?
3. Test pattern (each mapping value ∈ SUPPORTED_DOMAINS) — APPROVE'd?
4. Anything else blocking iter-1 APPROVE?

## Resource discipline

Tiny scope. No long-running processes; pure unit test work.

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
