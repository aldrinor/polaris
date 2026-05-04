# Slice 002 — Retrieval Against Verified Clinical Sources
# Architecture Proposal v1

**Slice:** slice_002_clinical_retrieval
**Author:** Claude (architect-reviewer; drafted under bot/slice-002-architecture-proposal)
**Status:** DRAFT
**Slice spec authority:** polaris-controls/slices/slice_002_clinical_retrieval.md (to be written by user / signed-commit; pending)
**Date:** 2026-05-04
**Window per PLAN.md §3:** weeks 4-7 (2026-06-01 to 2026-06-28)

---

## What this proposal commits to

PLAN.md §3 row 2 defines the WHAT: "Retrieval against verified clinical sources". This proposal defines the HOW: data shapes, module boundaries, query strategy, source tier classification, adequacy gate, test strategy, implementation order. User reviews + approves before any production code is written. (Approval can be retroactive per established slice 001 pattern, where Claude drafted the proposal and shipped substrate, then user countersigned later.)

---

## Scope (what this slice ships)

A user-typed clinical research question that survives slice 001 (status=`in_scope`) gets routed through slice 002 retrieval, which produces a verified clinical EvidencePool: a structured set of primary sources with tier classification, adequacy verdict, and provenance suitable for downstream slice 003 generation.

**This slice ships:**

1. `EvidencePool` schema — the data structure produced by retrieval, consumed by future slice 003 generator
2. `query_planner.py` — turns a `ScopeDecision` into a set of search queries (Boolean expansion, clinical vocabulary)
3. `clinical_source_registry.py` — knows which domains are T1 (regulatory + Cochrane), T2 (peer-reviewed), T3 (clinical-trials registries, guideline orgs)
4. `clinical_retriever.py` — orchestrator: queries → fetches → tier-classifies → de-duplicates → builds EvidencePool
5. `corpus_adequacy_gate.py` — fails the slice if min sources/tier not met (per template)
6. HTTP `POST /api/retrieval` — accepts a `ScopeDecision`, returns `EvidencePool` or `RetrievalError`
7. `web/app/retrieval/` — UI surface showing live retrieval progress + corpus brief + adequacy verdict

**This slice does NOT ship:**

- Generation (slice 003)
- Strict-verify (slice 003)
- Audit bundle export (slice 004)
- BEAT-BOTH benchmark (slice 005)
- Non-clinical templates (post-MVP)

---

## Pipeline overview (slice 002 portion)

```
        Slice 001 output                Slice 002 (THIS)              Slice 003 input
┌─────────────────────────┐    ┌────────────────────────────┐   ┌──────────────────────┐
│ ScopeDecision           │    │                            │   │ EvidencePool         │
│ status: in_scope        │ →  │  process_retrieval()       │ → │ sources: [Source]    │
│ scope_class: clinical_* │    │                            │   │ adequacy: Verdict    │
└─────────────────────────┘    └────────────────────────────┘   └──────────────────────┘
                                          │
                          ┌───────────────┼─────────────────┐
                          ↓               ↓                 ↓
                  ┌──────────────┐  ┌────────────┐  ┌────────────────┐
                  │query_planner │  │  fetcher   │  │ tier_classifier│
                  │ScopeDecision │  │ HTTP +     │  │ source_registry│
                  │→ Query[]     │  │ throttle   │  │ → T1/T2/T3     │
                  └──────────────┘  └────────────┘  └────────────────┘
                                                            ↓
                                                  ┌──────────────────┐
                                                  │ adequacy_gate    │
                                                  │ min sources/tier │
                                                  └──────────────────┘
```

---

## Module boundaries

### `polaris_graph.retrieval.evidence_pool` (NEW — replaces nothing)

**Note:** the heritage `src/polaris_graph/retrieval/` (live_retriever.py, source_registry.py, etc.) is kept per PLAN §4 as importable substrate but is NOT extended by this slice. Slice 002 builds a fresh, ScopeDecision-aware retrieval orchestrator alongside it. Heritage retrieval continues to serve the legacy honest-rebuild pipeline; slice 002 retrieval serves the BPEI spine.

```python
class SourceTier(str, Enum):
    T1 = "T1"  # regulatory + Cochrane systematic reviews
    T2 = "T2"  # peer-reviewed primary research
    T3 = "T3"  # registries, guidelines, government health agencies

class Source(BaseModel):
    source_id: str               # uuid
    url: HttpUrl
    domain: str                  # e.g. "pubmed.ncbi.nlm.nih.gov"
    tier: SourceTier
    title: str
    publication_date: date | None
    authors: list[str]           # may be empty for institutional sources
    snippet: str                 # short extract (first 500 chars of relevant section)
    full_text_available: bool
    full_text: str | None        # populated when fetched
    fetched_at_utc: datetime
    provenance: dict[str, Any]   # query that surfaced it, retrieval-strategy, etc.

class AdequacyVerdict(BaseModel):
    is_adequate: bool
    sources_per_tier: dict[SourceTier, int]
    min_required_per_tier: dict[SourceTier, int]
    failure_reason: str | None   # populated only when is_adequate=False

class EvidencePool(BaseModel):
    pool_id: str                                # uuid; ties to ScopeDecision.decision_id
    decision_id: str                            # FK to ScopeDecision
    sources: list[Source]
    adequacy: AdequacyVerdict
    queries_executed: list[str]
    retrieval_started_at_utc: datetime
    retrieval_finished_at_utc: datetime
    latency_ms: int
    cost_usd: float                             # cumulative HTTP + (future) LLM cost
```

### `polaris_graph.retrieval.query_planner` (NEW)

Pure function: `ScopeDecision → list[str]` query strings.

Strategy:
- Extract PICO axes from `ambiguity_axes` plausible_interpretations
- Boolean-expand: `(P1 OR P2) AND (I1 OR I2) AND (O1 OR O2)`
- Add scope-class-specific MeSH-like vocabulary (e.g. for `clinical_safety` add "adverse events", "pharmacovigilance", "post-marketing surveillance")
- Cap at 12 queries to bound cost; deduplicate on Jaccard similarity 0.85

### `polaris_graph.retrieval.clinical_source_registry` (NEW)

Static registry mapping domain → SourceTier, plus accept/reject rules. T1 includes: cochrane.org, pubmed.ncbi.nlm.nih.gov (subset: systematic reviews + Cochrane reviews), fda.gov/drugs/labels, ema.europa.eu, hc-sc.gc.ca, who.int. T2 includes: nejm.org, thelancet.com, jama.ama-assn.org, bmj.com, jamanetwork.com, plos.org, biomedcentral.com (peer-reviewed primary research). T3 includes: clinicaltrials.gov, who.int/ictrp, nice.org.uk, uptodate.com (excerpts), guidelines.gov.

Out: blogs, social media, news aggregators, .com/.org with no editorial provenance.

### `polaris_graph.retrieval.clinical_retriever` (NEW)

```python
def process_retrieval(
    decision: ScopeDecision,
    fetch_fn: HttpFetchFn = default_http_fetcher,
    template: ClinicalTemplate = clinical_default,
) -> EvidencePool | RetrievalError:
    ...
```

Steps:
1. Reject if `decision.status != "in_scope"` or `scope_class not in clinical_*`
2. Generate queries via `query_planner`
3. Execute queries against allowed-domain search backends (Serper API filtered to allowlist + Semantic Scholar API)
4. For each result, classify tier via `clinical_source_registry`; drop unclassified
5. De-duplicate by canonical URL + DOI
6. Run `corpus_adequacy_gate.assess()` on the pool
7. Assemble `EvidencePool`

### `polaris_graph.retrieval.corpus_adequacy_gate` (NEW)

```python
def assess(
    sources: list[Source],
    template: ClinicalTemplate,
) -> AdequacyVerdict:
    ...
```

For clinical_default template: min T1=2, T2=4, T3=2. If any tier short, return `is_adequate=False` with `failure_reason="not enough T2 peer-reviewed sources (got 1, need 4)"`.

### `polaris_graph.api.retrieval_route` (NEW)

```python
@router.post("/retrieval")
def post_retrieval(req: RetrievalRequest) -> RetrievalResponse:
    decision = ScopeDecision.model_validate(req.decision)
    result = process_retrieval(decision)
    if isinstance(result, RetrievalError):
        raise HTTPException(400, detail={...})
    return RetrievalResponse(pool=result.model_dump(mode="json"), ...)
```

### `web/app/retrieval/` (NEW)

- `page.tsx` — accepts ?decision_id=… or full ScopeDecision via state
- `components/retrieval_progress.tsx` — live progress (queries fired, sources found, tier breakdown)
- `components/corpus_brief.tsx` — final EvidencePool summary with adequacy verdict
- `tests/e2e/retrieval.spec.ts` — Playwright

---

## Data contracts

| From → To | Contract |
|---|---|
| Slice 001 → Slice 002 | `ScopeDecision { status: "in_scope", scope_class: "clinical_*", decision_id }` |
| Slice 002 → Slice 003 | `EvidencePool { sources, adequacy: {is_adequate: True}, decision_id }` |
| Slice 002 abort path | `RetrievalError` or `EvidencePool { adequacy: {is_adequate: False} }` — slice 003 must not run |

CLI isolation per CLAUDE.md LAW VII: slice 002 reads from slice 001 output (in-memory or via `outputs/scope_decisions/{decision_id}.json`), writes to `outputs/evidence_pools/{pool_id}.json`. Module imports across slice boundaries forbidden (only schemas + JSON contracts).

---

## Test strategy

### Unit tests (per module, ≥85% line coverage)

- `test_evidence_pool.py` — Pydantic validation, serialization round-trip, tier enum
- `test_query_planner.py` — given canonical ScopeDecision, asserts query count + content
- `test_clinical_source_registry.py` — domain → tier mappings, allowlist/denylist
- `test_corpus_adequacy_gate.py` — given source list, asserts verdict
- `test_clinical_retriever.py` — integration with stubbed fetch_fn (no network); asserts orchestration

### HTTP tests

- `test_retrieval_route.py` — FastAPI TestClient; POSTs ScopeDecision, expects EvidencePool

### Golden tests (in polaris-controls/golden/slice_002/)

5 reference scenarios:
1. Well-formed in-scope clinical efficacy → EvidencePool with ≥8 sources, adequacy=True
2. In-scope clinical safety → EvidencePool emphasizing T1 (FDA labels, FAERS) + T2
3. In-scope but obscure (rare disease) → EvidencePool with adequacy=False, fallback narrative
4. Slice 001 returned status≠in_scope → RetrievalError immediate
5. All sources fail adequacy → EvidencePool with adequacy=False, failure_reason populated

### Playwright e2e

- Submit query at /intake → in_scope decision → click "Run retrieval" → /retrieval renders progress → adequacy verdict displayed in <30s

---

## Implementation order (~14 PRs, all ≤200 LOC)

| PR | Scope | LOC est. |
|---|---|---|
| 1 | architecture proposal (this doc) | ~250 docs only |
| 2 | `evidence_pool.py` Pydantic schemas + tests | 150-200 |
| 3 | `query_planner.py` + tests | 130-180 |
| 4 | `clinical_source_registry.py` + tests | 150-200 |
| 5 | `corpus_adequacy_gate.py` + tests | 80-120 |
| 6 | `clinical_retriever.py` orchestrator (with stubbed fetch_fn) + tests | 150-200 |
| 7 | Real HTTP fetch backend (Serper + Semantic Scholar) + rate limiting + tests | 180-200 |
| 8 | `api/retrieval_route.py` FastAPI + tests | 100-150 |
| 9 | Wire `/api/retrieval` into the existing FastAPI app + integration tests | 80-120 |
| 10 | `web/lib/api.ts` retrieval client + types | 80-120 |
| 11 | `web/app/retrieval/page.tsx` SSR shell + retrieval-progress client | 150-200 |
| 12 | `corpus_brief.tsx` view + adequacy-verdict UI | 130-180 |
| 13 | Playwright e2e for retrieval flow | 100-150 |
| 14 | Golden test integration + 5 scenario fixtures | 100-150 |

If any PR exceeds 200 LOC, it splits.

---

## Risks + mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| External APIs (Serper, Semantic Scholar) rate-limit during dev | high | bake in rate-limit handling + cache from PR 7; use stubbed fetch_fn for unit + golden tests |
| T1/T2/T3 classification produces false positives (a junk site at peer-reviewed domain) | medium | strict allowlist regex including path patterns (e.g. nejm.org/doi/* only) |
| Adequacy gate too strict → most real questions fail | medium | per-template overrides; `clinical_default` is conservative, can relax via signed-commit template change |
| Latency exceeds 30s for breadth queries | medium | parallel fetches with bounded concurrency (heritage `fetch_limiter.py` pattern); 30s upper bound enforced |
| Slice 001 changes break the contract | low | EvidencePool depends only on `ScopeDecision` Pydantic schema; contract tests catch drift |

---

## Definition of "demo-able" for slice 002

Non-developer opens browser → /intake → types canonical clinical question → in_scope decision → clicks "Run retrieval" → /retrieval shows live progress → corpus brief renders with: source count by tier, list of T1 sources (titles + URLs), adequacy verdict. Sub-30s end-to-end. No code knowledge required.

---

## What requires user signed-commit before slice 002 is "approved"

1. Slice spec at `polaris-controls/slices/slice_002_clinical_retrieval.md` (mirrors slice 001 format)
2. Golden test bundle at `polaris-controls/golden/slice_002/test_*.json`

Until those exist, all slice 002 substrate built in POLARIS is **PROVISIONAL** and may be reshaped by the eventual signed slice spec. This proposal is the non-binding architect's pitch; signed slice spec is the contract.

---

**End of architecture proposal v1.**
