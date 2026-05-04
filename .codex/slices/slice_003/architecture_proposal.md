# Slice 003 — Generator with strict-verify
# Architecture Proposal v1

**Slice:** slice_003_generator_strict_verify
**Author:** Claude (architect-reviewer)
**Status:** DRAFT
**Slice spec authority:** polaris-controls/slices/slice_003_generator_strict_verify.md (pending user signed-commit; same draft-then-sign pattern as slices 001 + 002)
**Date:** 2026-05-04
**Window per PLAN.md §3:** weeks 8-11 (2026-06-29 to 2026-07-26)

---

## What this slice ships

A user-typed clinical question that has survived slice 001 (in_scope) and
produced an adequate slice 002 EvidencePool gets routed through a
generator that:

1. Produces clinical prose grounded in the EvidencePool's sources
2. Tags every sentence with `[#ev:<evidence_id>:<start>-<end>]` provenance
3. Runs `strict_verify` per CLAUDE.md §9.1 (numeric match + ≥2 content-word
   overlap with the cited span; >=40% sentences verified per section)
4. Drops unverified sentences before returning the report
5. Aborts with `abort_no_verified_sections` if every section fails verify

This is the BPEI back half. After this slice, POLARIS produces verified
clinical research output end-to-end.

**This slice does NOT ship:**
- Audit bundle export (slice 004)
- BEAT-BOTH benchmark vs ChatGPT/Gemini DR (slice 005)
- Multi-template generation beyond clinical_default

---

## Pipeline overview (slice 003 portion)

```
Slice 002 output                Slice 003 (THIS)              User-visible output
┌────────────────────┐    ┌────────────────────────────┐   ┌──────────────────────┐
│ EvidencePool       │    │  process_generation()      │   │ VerifiedReport       │
│ adequacy=True      │ →  │                            │ → │ sections: [Section]  │
│ sources: [...]     │    │                            │   │ verified_sentences   │
└────────────────────┘    └────────────────────────────┘   └──────────────────────┘
                                          │
                          ┌───────────────┼─────────────────┐
                          ↓               ↓                 ↓
                  ┌──────────────┐  ┌────────────┐  ┌────────────────┐
                  │section_blue- │  │ generator  │  │ strict_verify  │
                  │ print        │  │ (LLM call) │  │ per-sentence   │
                  │ (4 sections) │  │ provenance │  │ numeric+overlap│
                  └──────────────┘  └────────────┘  └────────────────┘
                                                            ↓
                                                  ┌──────────────────┐
                                                  │ section adequacy │
                                                  │ (>=40% verified) │
                                                  └──────────────────┘
```

---

## Module boundaries

### `polaris_graph.generator2` (NEW package)

**Note:** heritage `src/polaris_graph/generator/` (multi_section, live_deepseek,
provenance) is kept per PLAN.md §4 substrate but is NOT extended by slice 003.
Slice 003 builds a fresh, EvidencePool-aware generator that consumes the
slice-002 output schema directly.

#### `verified_report.py` — output schema

```python
class VerifiedSentence(BaseModel):
    section_id: str
    sentence_text: str
    provenance_tokens: list[str]  # [#ev:src_id:1200-1450] format
    verifier_pass: bool
    drop_reason: str | None  # 'numeric_mismatch' | 'overlap_too_low' | 'invalid_token'

class Section(BaseModel):
    section_id: str
    section_title: str
    verified_sentences: list[VerifiedSentence]
    section_verify_pass_rate: float  # 0.0 - 1.0
    section_status: Literal["verified", "regenerated", "dropped"]

class VerifiedReport(BaseModel):
    report_id: str
    pool_id: str
    decision_id: str
    sections: list[Section]
    overall_verify_pass_rate: float
    pipeline_verdict: Literal["success", "abort_no_verified_sections"]
    generator_model: str
    verifier_pass_threshold: float  # default 0.40
    started_at_utc: datetime
    finished_at_utc: datetime
    latency_ms: int
    cost_usd: float
```

#### `section_blueprint.py` — clinical-template section plan

Static blueprint per scope_class:
- clinical_efficacy: ["Population", "Intervention", "Outcomes", "Limitations"]
- clinical_safety: ["Population", "AdverseEvents", "RiskFactors", "Monitoring"]
- clinical_diagnosis: ["TestCharacteristics", "Population", "Comparators", "ClinicalUtility"]
- clinical_prognosis: ["Population", "PrognosticFactors", "Outcomes", "Confounders"]

#### `provenance.py` — token format + parser

```python
PROVENANCE_RE = re.compile(r"\[#ev:([a-f0-9-]+):(\d+)-(\d+)\]")

def extract_tokens(sentence: str) -> list[ProvenanceToken]: ...
def strip_tokens(sentence: str) -> str: ...
def validate_token_against_pool(
    token: ProvenanceToken, pool: EvidencePool
) -> bool: ...
```

#### `strict_verify.py` — per-sentence check (CLAUDE.md §9.1 invariant 3)

```python
def verify_sentence(
    sentence: VerifiedSentence,
    pool: EvidencePool,
    min_content_overlap: int = 2,
) -> tuple[bool, str | None]:
    """Returns (pass, drop_reason). Per CLAUDE.md §9.1:
    1. Every provenance token must reference a source_id in the pool
    2. span_start <= span_end <= len(source.full_text)
    3. Every decimal in the sentence MUST appear in the cited span
    4. Sentence and span share >= min_content_overlap content words
    """
```

#### `generator.py` — orchestrator

```python
def process_generation(
    pool: EvidencePool,
    completion_fn: GeneratorCompletionFn = default_generator_fn,
    verifier_pass_threshold: float = 0.40,
) -> VerifiedReport | GenerationError:
    ...
```

Steps:
1. Reject if `pool.adequacy.is_adequate is False`
2. Resolve section blueprint from `pool.decision_id` → ScopeDecision lookup
   OR carry scope_class through pool.provenance (slice 002 passes it)
3. For each section: build prompt with EvidencePool excerpts → LLM → parse
4. Strip-and-validate provenance tokens from each sentence
5. Run strict_verify per-sentence; drop failures
6. If section pass-rate < threshold: regenerate ONCE; if still <threshold,
   mark section_status="dropped"
7. If every section dropped: return abort_no_verified_sections
8. Else: assemble VerifiedReport

### `polaris_graph.api.generation_route` — FastAPI POST /api/generation

Mirror of slice 001's intake_route + slice 002's retrieval_route. Accepts
an EvidencePool (typically the slice 002 response) and returns a
VerifiedReport (200) or GenerationError (400).

### `web/app/generation/` — UI

- `page.tsx` SSR shell
- `components/generation_runner.tsx` — chains intake → retrieval →
  generation, renders progress
- `components/verified_report_view.tsx` — sections + verified-sentence
  highlighting + provenance-token tooltips on hover

---

## Data contracts

| From → To | Contract |
|---|---|
| Slice 002 → Slice 003 | `EvidencePool { adequacy.is_adequate=True, sources, decision_id }` |
| Slice 003 → Slice 004 | `VerifiedReport { pipeline_verdict='success', sections, decision_id }` |
| Slice 003 abort path | `VerifiedReport { pipeline_verdict='abort_no_verified_sections' }` OR `GenerationError` |

---

## Test strategy

### Unit tests (≥85% coverage)

- `test_verified_report.py` — Pydantic validation, JSON round-trip
- `test_provenance.py` — token regex, parser, validate-against-pool
- `test_strict_verify.py` — numeric-mismatch + overlap-too-low + invalid-token
  + valid-pass paths; edge cases (empty sentence, no tokens, span overflow)
- `test_section_blueprint.py` — scope_class → section list
- `test_generator.py` — orchestrator with stubbed completion_fn:
  - Adequate pool → VerifiedReport
  - Inadequate pool → GenerationError
  - All sections drop → abort_no_verified_sections
  - One section drops, others pass → VerifiedReport with mixed status
  - Regeneration path: first attempt fails, second passes

### HTTP tests

- `test_generation_route.py` — TestClient; happy + error paths; dependency-injected stub completion_fn

### Golden tests (`.codex/slices/slice_003/golden_drafts/test_*.json`)

5 scenarios:
1. Well-formed efficacy pool → 4 sections all verified, pipeline_verdict=success
2. Safety pool with one ambiguous section → mixed status report
3. Pool with sources too short for verification → some sections dropped, others pass
4. Stub generator produces token-less sentences → all sentences dropped → abort
5. Inadequate pool passed in → GenerationError immediate

### Playwright e2e

- /generation page renders verified report with provenance hover tooltips
- Token-less / inadequate / abort paths show structured error UI

---

## Implementation order (~16 PRs, all ≤200 LOC)

| PR | Scope | LOC est. |
|---|---|---|
| 1 | architecture proposal (this doc) | docs only |
| 2 | `verified_report.py` schemas + tests | 150-200 |
| 3 | `provenance.py` token format + parser + tests | 130-180 |
| 4 | `strict_verify.py` per-sentence checks + tests | 180-200 |
| 5 | `section_blueprint.py` + tests | 80-120 |
| 6 | `generator.py` orchestrator (stubbed completion_fn) + tests | 180-200 |
| 7 | Real OpenRouter completion_fn (DeepSeek V4) + tests | 180-200 |
| 8 | `api/generation_route.py` + TestClient tests | 150-200 |
| 9 | Mount /api/generation in polaris_v6 app + tests | 80-120 |
| 10 | `web/lib/api.ts` runGeneration + types | 100-150 |
| 11 | `web/app/generation/page.tsx` SSR + GenerationRunner | 150-200 |
| 12 | `verified_report_view.tsx` (hover tooltips, section UI) | 150-200 |
| 13 | Playwright e2e | 100-150 |
| 14 | Golden fixtures + integration runner | 150-200 |
| 15 | End-to-end smoke: intake → retrieval → generation in one click | 100-150 |
| 16 | Aggregate slice 003 fitness test (1 click → verified report < 60s) | 80-120 |

If any PR exceeds 200 LOC, split. No exceptions.

---

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| LLM produces sentences without provenance tokens | Verifier drops them; if all drop, abort path triggers — already designed in |
| Provenance hallucination (token cites non-existent source_id) | strict_verify rule 1 rejects unknown source_ids |
| Span-bound errors crash verifier | Bounds-checked at parse time; rule 2 rejects out-of-range |
| Decimal hallucination (sentence claims 23%, span has 18%) | Rule 3 numeric-match drops sentence |
| Generator API key missing in test env | Default completion_fn raises NotImplementedError sentinel; tests inject stubs (mirrors slice 002 PR 6 pattern) |
| 200 LOC cap blocks the LLM-prompt machinery | Split prompt-template + completion-loop into separate PRs (6 + 7) |

---

## Definition of "demo-able"

Non-developer opens browser → /generation → types canonical clinical
question → in <60s sees a 4-section report with sentence-level provenance
tooltips on hover. No empty sections. No fabricated decimals. Clicking a
provenance token highlights the cited span in the source-list panel.

---

**End of architecture proposal v1.**
