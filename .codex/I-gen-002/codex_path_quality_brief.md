Quality-impact comparison: Path A vs Path B for GH#423 duplicate-fact redundancy. Output YAML.

# Context

POLARIS multi_section_generator.py emits 5 sections in parallel via `asyncio.gather`. Each section retrieves+synthesizes from the evidence_pool independently. Tier-1 pilot Q5 (PR #421) showed 40% of audit-grade claims are duplicate-fact instances across sections (same 3%/1.6%/0.7% regressivity fact appears in 4 sections; same 8.7%/4.8% OOP-2007 in 3 sections; etc.).

This is invisible to per-claim audit (each instance individually VERIFIED) but visible to a reader of the report as filler.

# Two paths to consider — pick on QUALITY IMPACT alone, not speed

## Path A — Post-generation dedup pass

After all 5 sections generate (current parallel behavior preserved), but **BEFORE strict_verify** drops bad sentences:

1. Extract numeric-token signature per sentence (decimals to 2dp + dollar buckets within ±5% + years).
2. Group sentences across all sections by signature.
3. For each group with len > 1: first-section instance = PRIMARY, others = REDUNDANT.
4. Single LLM call rewrites REDUNDANT sentences as cross-references ("as noted under Efficacy [ev_X]").
5. Replace REDUNDANT in section drafts; continue to strict_verify (which now sees rewrites).

Cost: +1 LLM call per report ($0.001, +30s wall-clock). Preserves parallel section generation.

## Path B — Sequential section refactor

Change 4 `asyncio.gather` call sites to serial `for section in plan: await ...`. Thread `facts_emitted_so_far` through section calls.

1. Section 1 generates with empty facts_emitted_so_far → emits its sentences.
2. Extract numeric-token signatures from section 1 sentences (verified ones).
3. Section 2 generates with facts_emitted_so_far = section 1 facts → prompt says "Facts already established: [list]. Cross-reference instead of restate."
4. Continue serially through 5 sections.
5. Each section's prose is generated WITH knowledge of prior sections' established facts.

Cost: Lose parallelism (~5× section calls × ~10s = +40s wall-clock). No extra LLM call cost.

# Quality-impact angles to evaluate

1. **Narrative coherence**: Does Path B's "section knows what prior sections established" produce more coherent cross-references than Path A's "rewrite-after-the-fact"?
2. **Risk of degraded prose**: Path A's rewrite step could produce awkward "as noted in Efficacy" boilerplate; Path B's section-aware prompt could produce too-terse "see section X" stubs.
3. **strict_verify interaction**: Path A rewrites BEFORE strict_verify — rewrites with invalid provenance get dropped (good safety). Path B's section 2 references facts established in section 1 but section 1's facts could later FAIL strict_verify, leaving section 2 dangling.
4. **Fact-signature precision**: Path A groups by raw numeric token; Path B groups by what section 1 actually said. Path A may over-group (catch genuine non-duplicates with shared decimals); Path B doesn't have this risk.
5. **Audit trail / reproducibility**: Path A is single-pass-with-rewrite (one LLM call → can replay); Path B's section-to-section state-passing is harder to replay deterministically.
6. **Maintenance cost long-term**: Path A is a separable module; Path B is a deeper change to the production generator.
7. **Failure modes if generator misbehaves**: Path A — if rewrite call returns garbage, fallback to PRIMARY-only (drop redundant entirely) is safe. Path B — if section 2 misreads prior-facts list, may invent cross-references that don't exist.
8. **Reader experience**: Carney is a non-developer reader. Which path produces a report that reads more like a coherent research synthesis vs a multi-section concatenation?

# Question

For QUALITY IMPACT on the Carney delivery (the report reads coherent, no factual redundancy, no orphan cross-references), which path wins?

Output YAML:

```yaml
verdict: path_a_better | path_b_better | tied | hybrid
reasoning: "3-5 sentences with specific quality-impact analysis"
quality_dimensions_compared:
  - dimension: ...
    path_a_score: 0-10
    path_b_score: 0-10
    why: ...
risk_assessment:
  path_a_main_risk: "..."
  path_b_main_risk: "..."
recommended_path: A | B | hybrid
hybrid_definition_if_applicable: "..."
confidence: 0.0 - 1.0
```

Output the YAML directly. No commentary outside.
