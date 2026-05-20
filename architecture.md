# POLARIS Architecture — Current State

**Document date**: 2026-04-18
**Supersedes**: `archive/2026-04-18-pre-audit-cleanup/docs/architecture_legacy_2026-01-31.md`

This document describes what actually exists in the repo as of
2026-04-18. The legacy 135KB architecture document described a
13-phase "P0-P12" pipeline that no longer exists in the code (and
may never have fully matched the code). That document has been
archived. See `docs/live_code_audit.md` for the evidence that
motivated this rewrite.

---

## 1. Three parallel pipelines

POLARIS currently contains three distinct research pipelines that
coexist in the same repository.

### Pipeline A — Honest-rebuild (active)

**Purpose**: clean-room, honest-by-construction research pipeline.
Turns a plain-language research question into a grounded markdown
report with per-sentence provenance verification, external-evaluator
review, and a cost ledger.

**Entry**: `python -m scripts.run_honest_sweep_r3` (also
`scripts/run_r6_validation.py` for a 4-query validation slice).

**Active modules** (23 files under `src/polaris_graph/`):

```
src/polaris_graph/
├── nodes/
│   ├── scope_gate.py                — research-question scope gate
│   ├── corpus_approval_gate.py      — tier-distribution approval
│   ├── corpus_adequacy_gate.py      — minimum-sources gate
│   └── completeness_checker.py      — topic-coverage checklist
├── retrieval/
│   ├── live_retriever.py            — Serper + S2 + DDG orchestrator
│   ├── tier_classifier.py           — T1-T7 + UNKNOWN source tiering
│   ├── domain_backends.py           — arXiv / SEC EDGAR / policy-site backends
│   ├── scope_query_validator.py     — per-query scope guard
│   ├── contradiction_detector.py    — numeric-claim contradiction detection
│   ├── prefetch_offtopic_filter.py  — early off-topic filter
│   └── fetch_limiter.py             — rate limiter
├── generator/
│   ├── multi_section_generator.py   — outline → parallel sections → assemble
│   ├── live_deepseek_generator.py   — DeepSeek V3.2-Exp adapter
│   └── provenance_generator.py      — [#ev:id:start-end] + strict_verify
├── evaluator/
│   ├── external_evaluator.py        — rule-based evaluator shell
│   └── live_judge.py               — judge model (separate family)
├── llm/
│   └── openrouter_client.py         — OpenRouter gateway + family segregation
├── agents/
│   └── nli_verifier.py              — NLI verification helper
└── tracing.py                       — JSONL trace writer
```

**Plus**: `src/providers/llm_provider.py`, `scripts/run_honest_sweep_r3.py`,
`scripts/run_r6_validation.py`, `scripts/codex_loop_parse.py`,
`scripts/audit_live_code.py`.

**Data flow**:

```
research_question
    │
    ▼
scope_gate ──────────────────► if off-topic → abort_scope_rejected
    │
    ▼
live_retriever ──► corpus_adequacy_gate ──► if too thin → abort_corpus_inadequate
    │                 (tier mix check)
    ▼
corpus_approval_gate ──► if rubber-stamp on material deviation → abort_corpus_approval_denied
    │                  (human note required when corpus deviates)
    ▼
contradiction_detector  ──► contradictions.json
    │
    ▼
multi_section_generator (DeepSeek V3.2-Exp)
    │   — outline → parallel sections → per-sentence provenance tokens
    │
    ▼
provenance_generator.strict_verify   ──► drop sentences whose span
    │                                    doesn't contain numeric claim
    │                                    AND ≥2 content-word overlap
    │                                    If zero verified → abort_no_verified_sections
    ▼
live_judge (judge model, separate family from generator)
    │
    ▼
external_evaluator.run_external_evaluation
    │
    ▼
report.md + manifest.json + bibliography.json + contradictions.json
```

**Invariants stress-tested through 5-round Codex↔Claude audit** (2026-04-18):

- **Semantic grounding**: non-numeric claims need ≥2 content-word overlap
  (default `PG_PROVENANCE_MIN_CONTENT_OVERLAP=2`)
- **Corpus-approval enforcement**: rubber-stamp note on material
  deviation aborts before any generator call
- **Zero-verified abort**: if every section fails strict_verify,
  emit pipeline-verdict artifact instead of a pseudo-content report
- **Budget cap**: `PG_MAX_COST_PER_RUN` holds even when OpenRouter
  omits `usage.cost` (token-based imputation; negatives clamped)
- **Delimiter sanitization**: NFKD + Mn/Mc strip + invisible-char
  strip + narrow Cyrillic/Greek confusable map in a view-only
  pass, with byte-preservation of legitimate non-delimiter content

Full audit: `outputs/codex_findings/round_{1..5}/`.

**Output contract** — `outputs/<sweep_name>/<slug>/`:

```
report.md            — the verified findings + bibliography
manifest.json        — status, costs, gate outcomes, section stats
corpus_approval.json — tier distribution + approval decision
contradictions.json  — numeric-claim contradictions
protocol.json        — the scope protocol used
```

### Pipeline B — UI web server (active)

**Purpose**: FastAPI single-page app users hit via HTTP to run one
research vector interactively. This is what the default Docker
entrypoint (`serve`) boots.

**Entry**: `uvicorn scripts.live_server:app` (Docker default).

**Active modules**:

- `scripts/live_server.py` — 214KB FastAPI app + SSE streaming
- `src/polaris_graph/graph.py` — LangGraph v1
- `src/polaris_graph/graph_v2.py` — LangGraph v2 (CRAG pipeline)
- `src/polaris_graph/graph_v3.py` — LangGraph v3 (ReAct agent)
- `src/polaris_graph/memory/{campaign_store,content_cache,cross_vector}.py`
- `src/polaris_graph/document_ingester.py`
- `src/polaris_graph/checkpoint_manager.py`
- `src/auth/*` — auth routes + middleware

**Note**: pipeline B is a separate code path from pipeline A. They
share the `src/polaris_graph/llm/` client and some retrieval helpers
but otherwise are distinct orchestrators.

### Pipeline C — CLI research (FROZEN 2026-03-16)

**Purpose**: historical CLI research orchestrator. Invoked by the
Docker `research` subcommand.

**Entry**: `python -m scripts.full_cycle`

**Status**: frozen. No commits in 33+ days. `scripts/full_cycle.py`
imports `scripts/final_audit.py` and `scripts/run_ragas_v3.py` which
no longer exist — so this pipeline is partially broken.

**Disposition**: see `src/orchestration/FROZEN_SINCE_2026-03-16.md`
for the retire-vs-repair-vs-leave decision tree.

---

## 2. Two-family evaluator constraint

Per `src/polaris_graph/llm/openrouter_client.py:check_family_segregation`,
generator and evaluator **must** be from different training lineages.
This prevents the self-bias pathology (Play Favorites arXiv:2508.06709,
DeepHalluBench arXiv:2601.22984).

Current default pair (re-pinned 2026-05-19 per I-cd-009 / GH#624 Carney demo lock):

- **Generator**: `deepseek/deepseek-v4-pro` (family: `deepseek`; 1.6T total / 49B active MoE)
- **Evaluator**: `google/gemma-4-31b-it` (family: `gemma`)

Attempting to set both to the same family raises `RuntimeError` at
client construction. Hyphenated org prefixes (`deepseek-ai/...`) are
normalized and caught.

---

## 3. Retrieval architecture

### Source tiers (T1-T7 + UNKNOWN)

Defined in `src/polaris_graph/retrieval/tier_classifier.py`. Summary:

| Tier | Character | Example domains |
|------|-----------|------------------|
| T1   | Primary peer-reviewed | PubMed, NEJM, Nature, Cell |
| T2   | Systematic review / meta-analysis | Cochrane, review journals |
| T3   | Government / official | .gov, WHO, FDA, OECD |
| T4   | Preprint / working paper | arXiv, bioRxiv, SSRN |
| T5   | Industry analyst | Gartner, Forrester, McKinsey reports |
| T6   | Trade press / quality journalism | FT, Reuters, Bloomberg |
| T7   | Blog / opinion / unverified | |
| UNKNOWN | Unclassifiable | |

The `corpus_approval_gate` reads the scope template's expected tier
distribution and refuses to proceed if the actual corpus is materially
skewed toward lower tiers unless the operator attaches a substantive
rationale.

### Retrieval fan-out

Per `live_retriever.py`:

- **Web (Serper)**: primary, 10 results/query
- **Academic (Semantic Scholar)**: API-key required, 1 RPS cap
- **arXiv**: for technical domains
- **SEC EDGAR**: for due-diligence domains
- **Policy sites**: for government/regulatory queries
- **DuckDuckGo**: fallback when Serper returns zero

Query amplification: 10-25 variants per seed question. Web concurrency
20, academic concurrency 1.

---

## 4. Generation architecture

### Provenance tokens

Each generated sentence carries a provenance token:

```
The STEP-1 trial reported a 14.9% mean weight loss at week 68
[#ev:ev_step1:57-77].
```

The token identifies the evidence ID and the character span inside
the evidence's `direct_quote` that backs the sentence.

### Strict verify

`provenance_generator.strict_verify()` drops any sentence that fails:

1. **Evidence existence**: `ev_id` must be in the provided pool
2. **Span bounds**: `start` and `end` must be valid indices
3. **Numeric match**: every decimal / integer in the sentence must
   appear verbatim inside the span
4. **Content-word overlap**: the sentence and the span must share ≥N
   content words (default N=2; `PG_PROVENANCE_MIN_CONTENT_OVERLAP`)

If **every** section drops to zero, the orchestrator emits a
pipeline-verdict `report.md` and `manifest.json.status =
abort_no_verified_sections`.

### Multi-section assembly

`multi_section_generator.py`:

1. **Outline**: single generator call produces N section plans
2. **Sections**: parallel generator calls fill each section with
   provenance-tokenized prose
3. **Verify**: per-section `strict_verify`
4. **Revise**: one regeneration attempt on sections with <40% kept
5. **Assemble**: merge bibliographies (`_merge_bibliographies`) and
   remap per-section citation numbers to a global sequence
   (`_remap_section_markers_to_global`). The same `ev_001` gets the
   same `[1]` across every section.
6. **Limitations (R-1)**: one extra generator call produces the
   Limitations paragraph, using the pipeline telemetry block as data
   (not as instructions)

---

## 5. Prompt-injection defense

`provenance_generator.sanitize_evidence_text()` runs two passes on
every piece of evidence text before wrapping:

1. **Injection-directive pass** on raw text: redacts phrases matching
   `_INJECTION_PATTERNS` (e.g. "ignore previous instructions",
   `system:` lines, Claude/OpenAI channel markers).
2. **Delimiter-literal pass** via a normalized view with index
   projection: builds a separate view where NFKD-decomposed chars,
   invisible codepoints (including tag chars, variation selectors,
   bidi isolates, CGJ, MVS), combining marks (Mn/Mc), and the narrow
   Cyrillic/Greek confusable map are applied. Delimiter regexes run
   on the view, and matched ranges are redacted in the **original**
   text. Non-delimiter content is byte-preserved.

The wrapper `wrap_evidence_for_prompt()` emits:

```
<<<evidence:ev_001>>>
tier: T1
url: https://...
statement: ...
direct_quote: ...
<<<end_evidence>>>
```

And the Gap-3 telemetry block uses `<<<pipeline_telemetry>>>` /
`<<<end_telemetry>>>`. The generator system prompt tells the model
that text between these delimiters is DATA, not INSTRUCTIONS.

---

## 6. Budget guard

`openrouter_client.check_run_budget()` enforces
`PG_MAX_COST_PER_RUN` (default $5.00 per sweep). Every LLM call
contributes to the running total via `_add_run_cost()`.

When OpenRouter omits `usage.cost` from the response,
`_impute_cost_from_tokens()` computes an imputation from the token
count using a per-model price table (falling back to an Opus-tier
worst-case for unknown models). Negative token counts are clamped to
zero to prevent a corrupted response from silently shrinking the
budget.

---

## 7. Evaluator (two-family)

Separate from the in-pipeline `strict_verify`, an LLM evaluator
(different model family from the generator) runs after generation:

- `external_evaluator.run_external_evaluation`: rule-table
  evaluation (per-section coverage, citation density, etc.)
- `live_judge.judge_report`: LLM judge (different family from
  generator) scores the report

Both outputs are written to the manifest.

---

## 8. Configuration (env vars)

| Var | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | (required) | OpenRouter gateway auth |
| `OPENROUTER_DEFAULT_MODEL` | `deepseek/deepseek-v4-pro` | Generator model |
| `PG_GENERATOR_MODEL` | inherits from default | Generator for strict_verify pipeline |
| `PG_EVALUATOR_MODEL` | `google/gemma-4-31b-it` | Evaluator model (must be different family) |
| `PG_MAX_COST_PER_RUN` | `5.00` | Budget cap per sweep |
| `PG_PROVENANCE_MIN_CONTENT_OVERLAP` | `2` | B-1 invariant threshold |
| `PG_LIVE_MAX_EV_TO_GEN` | `20` | Max evidence slices passed to generator |
| `PG_NLI_ENABLED` | `0` | Opt-in NLI cross-check |
| `SERPER_API_KEY` | (required for pipeline A) | Primary web search |
| `SEMANTIC_SCHOLAR_API_KEY` | (optional) | Academic search |

Additional env-vars are defined in-code across modules. A consolidated
list is deferred to `docs/runbook.md`.

---

## 9. Testing

`tests/polaris_graph/` contains **305 tests** as of 2026-04-18, all
passing. Coverage:

- Core pipeline A modules (scope gate, corpus approval, adequacy,
  contradiction detection, retrieval, tier classifier, generator,
  provenance, strict_verify, evaluator, budget guard)
- B-1 through B-5 invariants (one test file per invariant, 40+ tests
  total covering every attack vector surfaced in the 5-round Codex
  audit)
- Regression tests for prior defects (`test_regression_pg_lb_sa_02_defects.py`)

Run:

```
python -m pytest tests/polaris_graph/ -v
```

Pipeline B (UI server) and Pipeline C (frozen) are not covered by this
test suite.

---

## 10. Known gaps and non-goals

- **No end-to-end live-network test**: the sweep orchestrator depends
  on Serper + OpenRouter + sometimes Semantic Scholar. Integration
  testing against real APIs is done manually via the 8-query sweep,
  not as an automated test.
- **Pipeline A and pipeline B share some code but do not share a graph
  framework**: pipeline A is a linear async orchestrator, pipeline B
  is LangGraph-based. This is technical debt — the intent is for
  pipeline B's graph to eventually adopt the pipeline A invariants.
- **Pipeline C is frozen and partially broken**: see
  `src/orchestration/FROZEN_SINCE_2026-03-16.md`.
- **No CI/CD configured** (verified 2026-04-18 — no
  `.github/workflows/` or equivalent). Tests are run manually.

---

## 11. Change log

- **2026-04-18**: this document written from scratch after a repo
  cleanup (`archive/2026-04-18-pre-audit-cleanup/`). Supersedes the
  2026-01-31 architecture doc that described a P0-P12 pipeline that
  did not match the code.
- See git log and `outputs/codex_findings/round_*/` for the five
  hardening commits that preceded this document.
