# Codex DIFF review — I-perm-005 (#1199) SLICE 1: claim_labeler keystone

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope
A NEW PURE module `src/polaris_graph/generator/claim_labeler.py` + its test. INERT — nothing imports it yet, zero production behavior change. The render/keep-and-label wiring (replacing the redactor DELETE under PG_ALWAYS_RELEASE) is a LATER slice. Review the pure bucket logic + the §-1.1 invariant.

## THE §-1.1 invariant to verify (the only P0 class here)
A non-VERIFIED claim can NEVER render `high`. Verify against the code: `confidence_bucket` returns `no-source-found` when `has_cited_evidence` is False, else delegates to `disclosure_population._certainty_label(is_verified, origin_count, credibility)` which returns `low` for `is_verified=False` (so non-verified can never be high or moderate). Unknown credibility (`None`) -> `low`. If you can construct args where a non-VERIFIED or unknown-credibility claim returns `high`/`moderate`, that is a P0.

## Claims ledger
| # | Claim | Where | Status |
|---|---|---|---|
| C1 | non-verified never high/moderate | delegates to `_certainty_label`, which returns `low` for not-verified | claims-true |
| C2 | unknown credibility -> low | `_certainty_label` returns low when credibility is None | claims-true |
| C3 | no cited evidence -> no-source-found | first branch of `confidence_bucket` | claims-true |
| C4 | thresholds reused (no drift) | imports `_certainty_label`; test asserts equality | claims-true |
| C5 | marker fail-safe | unknown bucket -> low wording; `render_confidence_marker` | claims-true |
| C6 | pure | no LLM/IO/global; lazy import of the threshold fn only | claims-true |

## Note on reusing a private symbol
`confidence_bucket` imports `disclosure_population._certainty_label` (a leading-underscore name) deliberately — to guarantee the high/moderate/low thresholds are the SAME as the already-shipped disclosure pipeline (no drift / no second source of truth). Flag if you think this coupling should instead be a shared public helper (P2/P3, not blocking).

## Files (full diff: `.codex/I-perm-005/slice1_codex_diff.patch`)
- `src/polaris_graph/generator/claim_labeler.py` (new, pure).
- `tests/polaris_graph/generator/test_claim_labeler_iperm005.py` (new, 6 tests).

## Test evidence: 6 passed (no-source-found; non-verified never high across all cred/origin combos; verified-high requires cred AND >=2 origins; unknown-cred -> low; marker unmistakable + fail-safe; bucket == shared disclosure thresholds).

Review the diff. Confirm C1/C2 (non-verified/unknown-cred can never be high). Hunt any arg combo that returns high for a non-verified claim.
