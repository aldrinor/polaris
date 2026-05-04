# Slice 001 — Clinical Scope Discovery + Ambiguity Detection
# Architecture Proposal v1

**Slice:** slice_001_clinical_scope_discovery
**Author:** Claude (drafted under bot/slice-001-architecture-proposal)
**Status:** DRAFT — awaiting user approval
**Slice spec authority:** polaris-controls/slices/slice_001_clinical_scope_discovery.md
**Date:** 2026-05-04

---

## What this proposal commits to

The slice spec (polaris-controls) defines the WHAT (objective, in-scope files, golden test acceptance). This proposal defines the HOW: data shapes, module boundaries, function signatures, test strategy, implementation order. User reviews + approves before any production code is written.

## Pipeline overview (slice 001 portion)

```
┌─────────────────────┐
│ User types question │   POST /api/intake { question: str }
└──────────┬──────────┘
           ↓
┌─────────────────────────────┐
│ question_normalizer.py      │   normalize whitespace, unicode NFC,
│ → NormalizedQuestion        │   strip control chars, len bounds
└──────────┬──────────────────┘
           ↓
┌─────────────────────────────┐
│ clinical_classifier.py      │
│   1. regex_layer            │   fast-path on canonical PICO patterns
│      → in_scope|out|maybe   │
│   2. llm_fallback (if maybe)│   one OpenRouter call, low temp
│      → in_scope|out_of_scope│
│ → ScopeClass + provenance   │
└──────────┬──────────────────┘
           ↓
┌─────────────────────────────┐
│ ambiguity_detector_clinical │   PICO axes (population, intervention,
│ → AmbiguityAxes             │   outcome) — each axis: 0|1|>1 plausible
└──────────┬──────────────────┘   interpretations
           ↓
┌─────────────────────────────┐
│ scope_decision.py           │   assemble final ScopeDecision
│ → ScopeDecision             │   { status, scope_class, ambiguity_axes,
└──────────┬──────────────────┘     clarifications_needed, provenance }
           ↓
┌─────────────────────────────┐
│ Frontend                    │   Server-rendered intake page;
│   /intake route             │   ScopeDecisionView OR AmbiguityModal
│   (Next.js 16 SSR)          │   based on status
└─────────────────────────────┘
```

No retrieval. No generation. No verifier. No audit bundle. Those are slices 2-4.

---

## Data shapes

### `NormalizedQuestion` (Pydantic-style)

```python
class NormalizedQuestion(BaseModel):
    raw: str                    # original user input
    normalized: str             # unicode-NFC, whitespace-collapsed
    lang: Literal["en"]         # slice 1 is English-only
    char_count: int             # post-normalization
    detected_at_utc: datetime
```

### `ScopeClass`

```python
ScopeClassValue = Literal[
    "clinical_efficacy",
    "clinical_safety",
    "clinical_diagnosis",
    "clinical_prognosis",
    "out_of_scope",
    "uncertain",  # only when both regex + LLM fallback fail
]

class ScopeClass(BaseModel):
    value: ScopeClassValue
    confidence: float           # [0,1]; regex=1.0 on hit, llm-derived otherwise
    provenance: Literal["regex", "llm_fallback"]
    matched_pattern: str | None # for regex hits, the pattern name
```

### `AmbiguityAxes`

```python
class AmbiguityAxis(BaseModel):
    axis: Literal["population", "intervention", "outcome"]
    plausible_interpretations: list[str]  # at most 5
    needs_clarification: bool             # True iff len(plausible) > 1

class AmbiguityAxes(BaseModel):
    population: AmbiguityAxis
    intervention: AmbiguityAxis
    outcome: AmbiguityAxis
    is_ambiguous: bool          # any axis needs_clarification
```

### `ScopeDecision`

```python
ScopeStatus = Literal[
    "in_scope",
    "out_of_scope",
    "ambiguous_needs_clarification",
    "refused",  # adversarial framing detected
]

class ScopeDecision(BaseModel):
    status: ScopeStatus
    scope_class: ScopeClassValue | None  # None if out_of_scope or refused
    ambiguity_axes: list[AmbiguityAxis]
    clarifications_needed: list[str]     # human-readable
    provenance: dict[str, str]           # classifier_layer, ambiguity_detector_layer
    decision_id: str                     # uuid4
    decided_at_utc: datetime
    latency_ms: int
```

This shape exactly matches the golden test expected_scope_decision schema (see `polaris-controls/golden/slice_001/manifest.md`).

---

## Module boundaries

```
src/polaris_graph/intake/
  __init__.py
  question_normalizer.py    # ~100 LOC; NormalizedQuestion factory
  schemas.py                # ~50 LOC; shared types if needed

src/polaris_graph/scope/
  __init__.py
  clinical_classifier.py    # ~250 LOC across regex + LLM layer
  ambiguity_detector_clinical.py  # ~200 LOC; PICO axes
  scope_decision.py         # ~80 LOC; assembly + ScopeDecision schema
  patterns/
    pico_patterns.yaml      # canonical PICO regex (data, not code)
    out_of_scope_patterns.yaml  # refusal-bait + out-of-domain markers

src/polaris_graph/api/
  intake.py                 # ~120 LOC; FastAPI route POST /api/intake

web/app/intake/
  page.tsx                  # ~150 LOC; SSR intake page
  components/
    AmbiguityModal.tsx      # ~80 LOC
    ScopeDecisionView.tsx   # ~100 LOC

tests/polaris_graph/
  intake/test_question_normalizer.py
  scope/test_clinical_classifier.py
  scope/test_ambiguity_detector.py
  scope/test_scope_decision.py
  api/test_intake_route.py

tests/web/intake/
  test_intake_page.spec.ts  # Playwright
```

Total estimated LOC: 1100-1400 across ~14 source files + ~6 test files. Distributed across 8 PRs at ≤200 LOC each per slice spec.

---

## Implementation order (8 PRs)

| # | Branch | Files | LOC est | Deps |
|---|---|---|---|---|
| 1 | bot/slice-001-question-normalizer | intake/question_normalizer.py + schemas.py + tests | ~150 | none |
| 2 | bot/slice-001-scope-decision-schema | scope/scope_decision.py + tests | ~130 | PR 1 (shared types) |
| 3 | bot/slice-001-classifier-regex | scope/clinical_classifier.py (regex layer) + patterns/*.yaml + tests | ~200 | PRs 1, 2 |
| 4 | bot/slice-001-classifier-llm-fallback | clinical_classifier.py (LLM layer) + tests | ~150 | PR 3 |
| 5 | bot/slice-001-ambiguity-detector | scope/ambiguity_detector_clinical.py + tests | ~200 | PRs 1, 2 |
| 6 | bot/slice-001-intake-orchestrator | api/intake.py wiring + tests | ~150 | PRs 3, 4, 5 |
| 7 | bot/slice-001-frontend-page | web/app/intake/page.tsx + AmbiguityModal.tsx + Playwright | ~200 | PR 6 |
| 8 | bot/slice-001-golden-test-integration | golden test runner + final demo polish | ~150 | PR 7 |

PRs 1, 2, 3, 4 can be done in week 1. PRs 5, 6 in week 2. PRs 7, 8 in week 3.

---

## Key design decisions (with reasoning)

### 1. Two-layer classifier (regex first, LLM fallback)

Most clinical research questions match canonical PICO patterns ("effect of X on Y in Z population", "diagnostic accuracy of T for D", etc.). Regex is fast (sub-millisecond), deterministic, free, and explainable. LLM fallback handles edge cases.

**Tradeoff:** regex bias toward Cochrane-style phrasing. Mitigation: golden test 005 (refusal bait) and golden test 002 (population ambiguity in informal phrasing) catch this. If regex layer wins too easily on golden tests, LLM fallback isn't being exercised — that's a signal to add adversarial test patterns.

### 2. PICO axes for ambiguity (not free-form)

Cochrane systematic reviews use PICO (Population/Intervention/Comparator/Outcome) as the canonical scope axes. Slice 1 uses P/I/O (skips Comparator — that's a slice 2+ retrieval concern). Three axes is enough granularity for golden tests; users get specific clarifications.

**Tradeoff:** doesn't generalize beyond clinical. Slice 1 is clinical-only by design. Other domains in v1.0 (housing, energy, etc.) need different axis frameworks.

### 3. ScopeStatus discriminated union (not boolean)

`status: ScopeStatus` (literal union of 4 values) instead of separate `is_in_scope: bool` + `needs_clarification: bool`. Forces explicit handling of all four states downstream; refusal is first-class (not "out_of_scope with extra metadata").

### 4. SSR (Server-Side Rendering) for intake page

Next.js 16's `app/` directory + Server Components. No client-side state for the initial render. AmbiguityModal hydrates as a client component when needed. Reasoning: faster TTFB, better screen-reader handling for the modal, simpler debugging.

### 5. Frontend tests via Playwright (not Jest/Vitest)

Playwright tests the actual UI flow against a running dev server. Verifies:
- Submit a question → see decision view OR ambiguity modal
- Modal interaction → resolved decision
- Latency budget (<3 seconds)

Per slice spec acceptance: "non-developer types one of 5 reference questions; gets correct scope decision OR ambiguity modal; in <3 seconds." Playwright is the natural framework for this.

---

## Test strategy

### Unit tests per module
- `question_normalizer`: NFC normalization, whitespace, length bounds, control-char stripping. ~10 cases.
- `clinical_classifier` (regex): each pattern hit + miss, ambiguous cases, regex overflow. ~20 cases.
- `clinical_classifier` (LLM fallback): mocked OpenRouter response; LLM-returns-malformed handling; LLM-times-out handling. ~8 cases.
- `ambiguity_detector_clinical`: each PICO axis, multi-axis ambiguity, no-ambiguity case. ~15 cases.
- `scope_decision`: assembly correctness, status transitions. ~10 cases.

### Integration test
- `test_intake_route.py`: POST /api/intake with each of the 5 golden questions; verify ScopeDecision shape + status + latency.

### End-to-end (Playwright)
- `test_intake_page.spec.ts`: 5 golden questions; verify UI shows correct decision view OR modal; latency budget.

### Golden master gate
- CI runs the 5 `polaris-controls/golden/slice_001/test_*.json` against the deployed pipeline. PR cannot merge until ALL 5 produce expected outputs.

---

## Risk areas

| Risk | Mitigation |
|---|---|
| Regex layer too greedy → misses ambiguity | Golden test 002 + 003 (specifically ambiguous questions) catch this |
| LLM fallback latency blows the 3s budget | Use OpenRouter with low-temp small model; fail-fast on >2s with "uncertain" status |
| Ambiguity detector false positives → annoying modal on every question | Golden test 001 (well-formed in_scope) MUST pass with `is_ambiguous: false` on outcome axis only |
| Frontend hydration races (modal flashes) | SSR by default; Playwright test catches flash |
| Refusal bait classifier fooled by paraphrasing | Golden test 005 + add adversarial training queries during dev |
| Cross-language Unicode (NFC vs NFD) | question_normalizer enforces NFC; tests cover both forms |
| LLM fallback cost overrun (each fallback = 1 API call) | Regex hits should cover ~70%+; budget per-task cost limit per CLAUDE.md §9.2 |

---

## What this proposal does NOT cover

- Retrieval (slice 2)
- Generator + strict-verify (slice 3)
- Audit bundle export (slice 4)
- BEAT-BOTH benchmark integration (slice 5)
- Multi-domain support (post-Sep 6, full v1.0)
- Advanced ambiguity (Cochrane Comparator dimension, time-bound questions, multi-population)
- Internationalization (slice 1 is English-only)
- Authenticated sessions / rate limiting (deferred — not on the tracer-bullet path)
- Database persistence of decisions (in-memory for slice 1; persistent in slice 2+ when retrieval state needs storing)

---

## What I need from the user before slice 1 implementation begins

1. **Approve this architecture proposal** (or push back on specific decisions). User commits the approval as a signed commit on `polaris-controls` updating slice spec to reference this architecture proposal SHA, OR signs an explicit approval doc in `.codex/slices/slice_001/`.

2. **Author the 5 `test_*.json` golden test files** in `polaris-controls/golden/slice_001/` from real Cochrane Library questions. Per slice spec these MUST be user-authored (not LLM-generated).

3. **Carney reframe conversation** must be confirmed before any product code lands. Slice 1 is the front of the tracer-bullet; if Sep 6 deliverable shifts back to "full v1.0," this slice's scope and pace need re-thinking.

After (1), (2), (3): I open PR 1 (question_normalizer) on `bot/slice-001-question-normalizer` and slice 1 implementation begins.

---

## Open questions

- **OpenRouter model for LLM fallback?** I'd default to a small low-temp model (e.g., `gpt-4o-mini` or `claude-3-haiku`). User: any preference / cost-tier directive?
- **Cost ceiling per intake call?** Slice 1 has no real cost (regex + 1 LLM call). Setting `PG_MAX_COST_PER_INTAKE` ~$0.005 leaves margin. User: confirm or override.
- **Should the intake page require user authentication?** Slice 1 demos to a non-developer. Auth-free is faster. But Carney's office may want session continuity. User: defer auth to slice 2+, or include now?
- **Logging / observability?** Slice 1 needs to emit structured events for the audit bundle (slice 4). Should the events conform to OpenTelemetry GenAI semconv now, or add that in slice 4? Recommend now (OpenTelemetry already pinned per CLAUDE.md §0.10).

User answers these in `.codex/slices/slice_001/decision.md` after reviewing this proposal.
