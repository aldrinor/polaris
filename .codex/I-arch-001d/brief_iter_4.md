HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001d iter 4 — model_copy validator + canonical regex + drop_reason map

## P1-002-novel — model_copy bypasses validator + evaluator_agrees consistency

**Resolution**: rebuild VerifiedSentence via the full constructor (which runs validators), AND explicitly set `evaluator_agrees=False`:

```python
def _redact_sentence(sent: VerifiedSentence) -> VerifiedSentence:
    """Mark a sentence as failed during sovereignty cascade.

    Uses VerifiedSentence(**fields) constructor (runs validators) rather
    than model_copy(update=...) which bypasses them.
    """
    fields = sent.model_dump()
    fields["verifier_pass"] = False
    fields["drop_reason"] = "invalid_token"
    fields["evaluator_agrees"] = False  # P1-002 — must mirror verifier_pass
    # Per VerifiedSentence validator: verifier_pass=False with evaluator_agrees=True
    # is forbidden. Setting both False keeps the model valid.
    return VerifiedSentence(**fields)
```

The construct-via-`__init__` path runs all `@field_validator`s and `@model_validator`s, surfacing any invariant violations as `ValidationError` instead of allowing silent contradiction.

Same pattern for section_status update:

```python
def _drop_section(section: Section, kept: list[VerifiedSentence]) -> Section:
    fields = section.model_dump()
    fields["verified_sentences"] = [s.model_dump() for s in kept]
    fields["section_verify_pass_rate"] = 0.0
    fields["section_status"] = "dropped"
    return Section(**fields)
```

## P2 from iter 3 → resolutions

### P2 (Q3) — Canonical regex import

**Resolution**: import the canonical token regex from `polaris_graph.generator2.provenance` instead of redeclaring:

```python
from polaris_graph.generator2.provenance import PROVENANCE_TOKEN_RE  # canonical
```

If `PROVENANCE_TOKEN_RE` doesn't exist as a module-level export today (verifying...), the bridge imports the regex pattern definition from there OR falls back to a local pattern with a CODE COMMENT linking to the canonical source for future alignment.

### P2 (additional drop_reason mappings)

**Resolution**: expand the map to cover pipeline-A's observed reasons:

```python
_DROP_REASON_MAP = {
    "invalid_token": "invalid_token",
    "span_out_of_range": "span_out_of_range",
    "numeric_mismatch": "numeric_mismatch",
    "number_not_in_any_cited_span": "numeric_mismatch",
    "no_integer_overlap_any_cited_span": "numeric_mismatch",  # added per iter-3
    "overlap_too_low": "overlap_too_low",
    "low_content_overlap": "overlap_too_low",
    "no_content_word_overlap_any_cited_span": "overlap_too_low",  # added
    "no_provenance_token": "no_provenance_token",
    "missing_provenance": "no_provenance_token",
    "entailment_failed": "entailment_failed",
    "trial_name_mismatch": "invalid_token",  # cited trial != stated trial; closest legal Literal
}
def _normalize_drop_reason(raw: str | None) -> str | None:
    if raw is None:
        return None
    base = raw.split(":")[0].strip().lower()
    return _DROP_REASON_MAP.get(base, "invalid_token")
```

## Acceptance criteria (final iter-4)

All criteria from iter-3 plus:
- Sentences rebuilt via `VerifiedSentence(**fields)` constructor (validator-checked), NOT `model_copy`
- evaluator_agrees=False when verifier_pass=False (mirror invariant)
- Canonical `PROVENANCE_TOKEN_RE` import from generator2.provenance (or comment+local fallback if not exported)
- Expanded DropReason map covers no_integer_overlap_any_cited_span, no_content_word_overlap_any_cited_span, trial_name_mismatch

## Direct questions iter 4

1. Constructor-based rebuild with explicit evaluator_agrees=False — APPROVE'd?
2. Import canonical PROVENANCE_TOKEN_RE from generator2.provenance — APPROVE'd? (If it doesn't exist as exported, bridge defines its own + leaves a comment.)
3. Expanded DropReason map — APPROVE'd?
4. Anything else blocking iter-4 APPROVE?

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
