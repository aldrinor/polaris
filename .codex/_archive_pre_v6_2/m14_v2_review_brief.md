M-14 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-14 v1 verdict: DISAGREE with 4 critical issues:

1. Pure Jaccard flattens negation/scope/pending mismatches
   ("approved" vs "not approved" → 0.667 → false convergence).
2. Bullet bodies splice raw upstream prose; smuggled
   "regulators worldwide" survives the divergence template.
3. `[ev_id]` citation contract conflicts with V30 strict_verify
   token format.
4. Convergence canonical + citation order depend on input
   permutation.

All 4 integrated in v2 (commit d193425).

## What changed in v2

`_force_divergence()` — pre-Jaccard hard guards:
- NEGATION_TOKENS: not, no, never, without, contraindicated,
  withheld, denied, rejected, withdrawn, suspended.
- PENDING_TOKENS: pending, review, ongoing, preliminary,
  interim, provisional.
- SCOPE_LIMITER_TOKENS: only, exclusively, restricted, limited.
  Asymmetric presence (one value has the token, another doesn't)
  → forced DIVERGENCE regardless of Jaccard.
- Numeric-mismatch guard: different decimals/integers in prose
  force divergence (catches "5 mg" vs "10 mg" + asymmetric
  numeric presence).

Default convergence_floor: 0.5 → 0.7.

Citation contract:
- `[cite:ev_id]` (renderer-only) instead of bare `[ev_id]`.
- Pipeline-native code uses `FieldVerdict.bound_ev_ids`, never
  regex.

Convergence determinism:
- Canonical: sorted by (-len, jurisdiction_alpha) then take
  first. Tied lengths → alphabetical jurisdiction wins.
- Citations: sorted by jurisdiction_alpha.
- Result is invariant under input permutation.

Smuggled-flattening guard:
- `_strip_flattening_phrases()` rewrites "regulators worldwide",
  "globally approved", "international consensus", "all
  jurisdictions", etc. to "[this jurisdiction]" inside both
  convergence and divergence bullet bodies.

Tests: 13 new. M-14 module 21 → 34 green.
- 4 parametrized negation cases (approved vs not approved,
  contraindicated vs not, approved vs withheld, approved vs
  rejected).
- Scope limiter ("adults only" vs "adults and adolescents").
- Pending status ("approved" vs "pending Phase 4 review").
- Numeric mismatch ("5 mg" vs "10 mg"; numeric asymmetric).
- Permutation invariance (reverse input → identical synthesis).
- Canonical tiebreak by jurisdiction-alpha.
- Smuggled flattening phrase neutralized to [this jurisdiction]
  in divergence bullet.
- Citation format `[cite:ev_id]` only; bare `[ev_id]` blocked.
- bound_ev_ids ordering follows jurisdiction-alpha.

## Your job

Final verdict on M-14. GREEN / PARTIAL / DISAGREE.

Probe with:
- More negation phrasings the guard might miss
- Scope-mismatch phrasings ("for adults only" vs "for all
  adults")
- Numeric-similar-but-different cases
- Anything else

If GREEN, M-14 is locked and Phase C proceeds to M-15a.

## Output

Write to `outputs/codex_findings/m14_v2_review/findings.md`:

```markdown
# Codex re-review of M-14 v2

## Verdict
GREEN / PARTIAL / DISAGREE

## v1 fix integration
- [x/no] Negation/pending/scope/numeric guards force divergence
  before Jaccard
- [x/no] Citation contract decoupled from strict_verify (cite:
  prefix)
- [x/no] Convergence canonical + citation order deterministic
- [x/no] Smuggled flattening prose neutralized

## New issues
none / list

## Final word
GREEN to lock M-14 + proceed to M-15a / PARTIAL with edits.
```

Be terse. Under 150 lines.
