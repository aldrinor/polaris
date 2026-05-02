M-10 curated template router with confidence gating — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-9 GREEN-locked across 4 review rounds. M-10 is the curated template
router — Phase B mitigation for FINAL_PLAN Risk #13 (query-to-template
misrouting / unsupported-query overclaim). With one production
template (v30_clinical) the routing problem is "is this query in
scope: yes/maybe/no", NOT multi-template intent classification.

## What landed (commit 219444e)

**`src/polaris_graph/audit_ir/template_catalog.py`** (~150 lines):
- `CuratedTemplate` frozen dataclass: template_id, display_name,
  description, scope_summary, scope_keywords, scope_examples
- `TEMPLATE_CATALOG` tuple with one entry: `v30_clinical`
- `list_catalog()` / `get_template()` accessors
- v30_clinical scope_summary documents both IN-scope and OUT-of-scope
  (FINAL_PLAN scope-page reinforcement mitigation)
- scope_keywords: ~50 entries blending clinical-trial framing
  ("efficacy", "randomized", "fda"), drug families ("glp-1",
  "tirzepatide", ...), conditions ("diabetes", ...), and broader
  medical-domain words ("treatment", "drug", ...) so medical-but-
  off-scope queries land in operator_review (not unsupported)
- scope_examples: 8 concrete real-shape questions

**`src/polaris_graph/audit_ir/template_classifier.py`** (~250 lines):
- Discrete-tier scorer; deterministic; no model state
- Tokenizer: lowercase, hyphen-preserving (so "glp-1" stays one token),
  drops 1-char non-digit tokens
- For each template: keyword set-subset matches + max Jaccard against
  scope_examples
- Cascade returns score in [0, 1]:
    tier A (ex_jac ≥ 0.4 AND n_kw ≥ 2)         → routed
    tier B (ex_jac ≥ 0.3)                       → routed-ish
    tier C (n_kw ≥ 3)                           → operator_review
    tier D (1-2 keyword hits OR weak example)   → operator_review
    tier E (nothing)                            → unsupported
- Verdict tiers (RoutingVerdict enum):
    score ≥ floor_high  → ROUTED
    score ≥ floor_review → OPERATOR_REVIEW
    score < floor_review → UNSUPPORTED
- Defaults: floor_high=0.55, floor_review=0.30
- `RouterConfig.from_env()` reads `PG_TEMPLATE_ROUTER_FLOOR_HIGH` /
  `PG_TEMPLATE_ROUTER_FLOOR_REVIEW` (LAW VI). Garbage env values
  fall back to defaults; review_floor is clamped ≤ high_floor.
- Empty/whitespace queries return UNSUPPORTED (not 400) so the UI
  can surface the same scope-page CTA in every off-scope branch.

**`inspector_router.py`** — two new endpoints:
- `GET /api/inspector/templates/catalog` — scope-page data source
- `POST /api/inspector/templates/route` — advisory query
  classification, returns `{verdict, template_id, confidence,
  candidates, rationale}`. Does NOT enqueue. UI flow: call /route,
  surface verdict, on confirm call /api/inspector/jobs.

**Tests: 36 new (9 catalog + 18 classifier + 9 API), all green.**
Phase B suite: 144 → 180.

Test cases of note (verdict semantics):
- "What's the weather today?" → UNSUPPORTED
- "Treatment options for chronic pain" → OPERATOR_REVIEW (medical
  framing alone isn't enough for routed)
- "FDA drug trial" → OPERATOR_REVIEW (keyword-only without exemplar
  match)
- "What is the efficacy of tirzepatide for type 2 diabetes?" → ROUTED
- "Studies on metformin for diabetes" → ROUTED
- Empty / whitespace / punctuation-only → UNSUPPORTED
- Unicode/HTML/null-byte garbage → no crash
- Same query → same verdict (deterministic)
- Confidence ∈ [0, 1] for any input

## Your job

Code review for M-10. Verdict: GREEN / PARTIAL / DISAGREE.

## Specific things to validate

1. **Risk #13 framing.** With ONE template, the failure mode is
   false-positive (auto-routing off-scope queries to v30_clinical).
   Defaults bias toward UNSUPPORTED. Is the threshold/scoring
   conservative enough? Are there obvious bypasses where an off-
   scope query would score above 0.55?

2. **Scoring algorithm.** Discrete-tier cascade — is this defensible
   for Phase B, or do you want a single continuous formula? Any
   degenerate inputs that trip the tiers wrong?

3. **Tokenization.** I preserve hyphens ("glp-1"), drop 1-char non-
   digit tokens, lowercase everything. Is the regex `[a-z0-9][a-z0-9-]*`
   too lax/strict? Will Unicode pass through cleanly? (Test exists
   for unicode passthrough but the tokens are all ASCII-pinned.)

4. **Catalog data quality.** v30_clinical scope_keywords blends
   clinical-specific terms with broader medical-domain words.
   That's deliberate — medical-but-off-scope queries land in
   operator_review band. But it might allow over-routing of generic
   medical questions. Worth pruning to clinical-trial-specific only?

5. **Threshold env knobs.** `PG_TEMPLATE_ROUTER_FLOOR_HIGH` /
   `..._REVIEW` overridable per LAW VI. Garbage values fall back to
   defaults; review clamped ≤ high. Is this enough or should I add
   structured validation (Pydantic) at config load time?

6. **API surface.** /catalog + /route. /route is advisory — no
   enqueue. UI must call /jobs explicitly with `template_id`. Is
   this the right separation, or should /route also offer an
   "enqueue if routed" form?

7. **Determinism.** Same query → same result asserted. Any chance
   of nondeterminism via dict ordering, set iteration order, etc.?

8. **Anything else you'd push back on.**

## Output

Write to `outputs/codex_findings/m10_review/findings.md`:

```markdown
# Codex review of M-10

## Verdict
GREEN / PARTIAL / DISAGREE

## Specific issues
File:line bugs / gaps.

## Risk #13 mitigation strength
Is the false-positive direction adequately guarded?

## Recommended changes
If PARTIAL.

## M-11 readiness
Is the catalog/router infrastructure ready for bounded-upload
template additions?

## Final word
GREEN to lock M-10 / PARTIAL with edits / DISAGREE.
```

Be terse. Under 250 lines.
