HARD ITERATION CAP: 5 per document. This is iter 5 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001b iter 5 (FINAL/force-APPROVE per §8.3.1)

## P1 from iter 4 → resolution

### P1-url_pattern-regex-is-not-M56-fetchable

You wrote:
> "M-56 does not resolve regex/domain patterns into concrete URLs. frame_compiler emits primary_identifier='url:<url_pattern>', frame_fetcher passes it AS-IS to _fetch_url_pattern(). A regex would be sent to AccessBypass as a literal URL and won't fetch."

**Code-verified**: `frame_compiler.py:297` + `frame_fetcher.py:780,1046` — `url_pattern` is treated as a literal URL by M-56's fetcher.

**Resolution**: emit a **concrete http(s) URL** per entity, derived by rotating through the v6 template's T1 source list:

```python
def _concrete_url_for_entity(frame_idx: int, source_tiers: dict) -> str:
    """Return a concrete http(s) URL for this entity from T1 sources.
    
    M-56 (_fetch_url_pattern) treats this as a literal URL, not a regex.
    Rotates through T1 by frame index so different frames retrieve
    different roots; strict_verify later filters per-frame relevance.
    
    Fallback (rare empty-T1 template): the URL still must be a valid
    fetchable URL — we use a stable known-Canada-govt URL as last resort.
    The fallback path is exercised in the test_empty_t1_fallback test.
    """
    t1 = source_tiers.get("T1") or []
    if t1:
        return t1[frame_idx % len(t1)]
    # Last-resort fallback: a valid fetchable URL (not a regex).
    return "https://www.canada.ca/en/research.html"

# In build_v30_contract:
for idx, frame in enumerate(template["frame_manifest"]):
    entity = {
        "id": f"{frame_id}_entity",
        "type": _type_for_template(template_id),
        "required_fields": [...],
        "min_fields_for_completion": 1,
        "rendering_slot": f"{frame_id}_slot",
        "url_pattern": _concrete_url_for_entity(idx, template.get("source_tiers", {})),
        "anchor": _anchor_for(template_id, frame_id, query_slug),  # stable id, still secondary
    }
```

## P2 from iter 4 → resolutions

### P2-fetchability-test-is-presence-only

**Resolution**: assertions now exercise URL validity:

```python
from urllib.parse import urlparse

@pytest.mark.parametrize("template_id", ALL_V6_TEMPLATES)
def test_synthesized_bindings_have_fetchable_url(template_id):
    template = load_template(template_id).model_dump()
    contract_patch = build_v30_contract(template, "test_slug", "test question")
    template.setdefault("per_query_report_contract", {}).update(contract_patch)
    cf = compile_frame("test question", template, "test_slug")
    assert cf is not None
    for binding in cf.evidence_bindings:
        entity = binding.entity
        has_resolvable = bool(entity.doi or entity.pmid or entity.url_pattern)
        assert has_resolvable, f"binding {entity.id!r} is anchor-only"
        if entity.url_pattern and not (entity.doi or entity.pmid):
            parsed = urlparse(entity.url_pattern)
            assert parsed.scheme in ("http", "https"), (
                f"url_pattern {entity.url_pattern!r} not a fetchable URL "
                f"(scheme={parsed.scheme!r}); M-56 would fail"
            )
            assert parsed.netloc, (
                f"url_pattern {entity.url_pattern!r} missing netloc"
            )
```

### P2-www-stripping-breaks-www150-hosts

**Resolution**: with the iter-5 fix (concrete URLs from T1), the `lstrip('www.')` call is REMOVED entirely. We don't need to strip `www.` from hostnames because we're using the FULL T1 URL as-is. `https://www150.statcan.gc.ca` remains `https://www150.statcan.gc.ca` — fetcher handles it natively.

The `_url_pattern_from_t1` regex-building helper from iter 4 is DROPPED in favor of `_concrete_url_for_entity` shown above.

## Acceptance criteria (final iter-5)

1. `build_v30_contract(v6_template, query_slug, question=None) -> dict` emits per_query_report_contract.{slug}
2. Every entity gets:
   - `url_pattern`: concrete http(s) URL rotated from `source_tiers.T1` (or last-resort fallback if empty)
   - `anchor`: `<template_id>:<frame_id>:<slug[:40]>:<sha256_8>` (secondary stable id)
3. 8 golden fixtures
4. actors.py: `polaris_v6.templates.registry.load_template(template_id).model_dump()`, attach to `q["v30_contract_patch"]`, `logger.warning(..., exc_info=True)` on failure
5. pipeline-A: 5 LOC merge of `q["v30_contract_patch"]` into `_template["per_query_report_contract"]`
6. Tests (parameterized over 8 templates):
   - fixture round-trips via `load_report_contract_for_slug`
   - synth compiles via `compile_frame`
   - **M-56 URL-validity**: every binding has either doi/pmid OR a url_pattern with valid scheme + netloc per `urlparse`
   - actor regression: stubbed run_one_query captures q; v30_contract_patch present + frame compiles
   - pipeline-A regression: q lacking v6_mode → _template unchanged
7. LOC ~350-380

## Direct questions iter 5

1. Concrete URL rotation through T1 (entity[i] gets T1[i % len(T1)]) — APPROVE'd?
2. Fallback for empty T1 (`https://www.canada.ca/en/research.html`) — APPROVE'd, or want fail-loud (raise on empty T1)?
3. `urlparse` validation test pattern (scheme + netloc) — APPROVE'd?
4. Any P0/P1 remaining?

If iter 5 returns REQUEST_CHANGES, force-APPROVE per §8.3.1. Residuals captured as I-arch-001b-followup sub-scope in `state/polaris_restart/iteration_trajectory.md`.

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
