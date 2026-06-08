## 8. ITER-2 RESOLUTIONS (formula correction — supersedes §2 / §3 cluster_mass)

Codex iter-2 DIFF caught a CORE FORMULA DRIFT + an inflation bug. Both fixed:
- **`cluster_mass = authority_score(canonical origin)` ONLY** (plan §148), NOT `authority × credibility`. My §2/§3 proposed multiplying by the P2 `credibility_weight`; that DRIFTS from the Codex-plan-approved §148 AND breaks no-inflation: a high-authority / low-credibility origin (0.8×0.1 = 0.08) could be OVERTAKEN by adding a lower-authority copy with NO judgment (0.3×1.0 = 0.3) — adding a copy RAISES the mass. Removed.
- **`credibility_weight` stays a DISCLOSED `OriginContribution` field** (carried for transparency) but is NOT a factor in `cluster_mass`. Credibility influences composition DOWNSTREAM (Phase 7 both-sides weighting / Phase 8 per-claim disclosure), never the independence weight-mass.
- New regression `test_credibility_is_disclosed_not_a_mass_factor_no_inflation`: a high-authority / low-credibility origin is NOT overtaken by a lower-authority no-judgment copy (mass goes 0.8 → 0.3, never inflates).
- AC2 corrected: `weight_mass = 0.8` (authority), not 0.4 (0.8×0.5).

SMOKE after the formula correction: 19 passed.
