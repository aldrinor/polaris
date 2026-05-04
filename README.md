# POLARIS

High-integrity research pipeline: turns a plain-language research
question into a grounded, per-sentence-verified markdown report with
bibliography, corpus-approval gate, and a separate-family evaluator.

## v6.2 mission state (2026-05-04)

POLARIS is shipping toward a **Sep 6, 2026 tracer demo for incoming PM
Carney**, governed by `polaris-controls/PLAN.md` (admin-only, signed).
The demo target is end-to-end clinical research: scope discovery →
ambiguity detection → tiered retrieval → generator with strict-verify →
GPG-signed audit bundle → BEAT-BOTH benchmark vs ChatGPT-DR / Gemini-DR.

| Slice | Deliverable | Substrate |
|---|---|---|
| 1 | Scope discovery + ambiguity | `polaris_graph/scope/`, `/api/intake`, `/intake` page |
| 2 | Tiered retrieval (Serper + S2) | `polaris_graph/retrieval2/`, `/api/retrieval`, `/retrieval` page |
| 3 | Generator + strict-verify | `polaris_graph/generator2/`, `/api/generation`, `/generation` page |
| 4 | Audit bundle GPG-signed | `polaris_graph/audit_bundle/`, `/api/audit-bundle`, download in `/generation` |
| 5 | BEAT-BOTH benchmark + demo polish | `polaris_graph/benchmark/`, `/api/benchmark`, `/benchmark` page, `scripts/run_benchmark.py` |

Operator entry points:

- **Demo runbook:** `docs/demo_runbook.md` (env setup → boot → walkthrough)
- **Mission status:** `docs/mission_status.md` (single-page state of play)
- **Pre-demo smoke:** `PYTHONPATH=src python scripts/demo_smoke.py -v`
- **Seed benchmark UI:** `python scripts/seed_demo_benchmark.py --output outputs/demo_benchmark/clinical_n10_demo`
- **Home walkthrough:** `http://localhost:3000/` four-step click-through

## Heritage pipelines (pre-v6.2)

POLARIS also hosts three heritage pipelines from prior cycles. These
are the V30 honest-rebuild engine (305 tests, 159 commits in the 60
days before the v6.2 cutover) plus the legacy CLI. See
`architecture.md` and `docs/live_code_audit.md` for the full history.

| Pipeline | Purpose | Entry | Status |
|---|---|---|---|
| **A. Honest-rebuild** | Clean-room sweep orchestrator. Writes per-query manifests + `report.md` under `outputs/honest_sweep_*/`. Used for the 8-query validation sweep. | `python -m scripts.run_honest_sweep_r3` | Active — 159 commits in last 60 days. Hardened via 5-round Codex↔Claude audit (see `outputs/codex_findings/`). |
| **B. UI server** | FastAPI web server that the Docker default entrypoint (`serve`) launches. Hosts a single-vector research UI that uses the v1/v2/v3 LangGraph variants under `src/polaris_graph/`. | `uvicorn scripts.live_server:app` (Docker default) | Active — last updated 2026-04-17. |
| **C. Legacy CLI research** | Docker `research` subcommand → `full_cycle.py` → `src/orchestration/graph.run_research()`. | `python -m scripts.full_cycle` | **Frozen since 2026-03-16**. Also has broken imports (`scripts/final_audit.py` and `scripts/run_ragas_v3.py` no longer exist). See `src/orchestration/FROZEN_SINCE_2026-03-16.md`. |

> The prior README advertised a fictional 13-phase "P0-P12" pipeline
> that has not existed in this repo for months. That document was
> archived on 2026-04-18 and replaced with the current-state description
> in `architecture.md`.

## Quick start — pipeline A (the one we actively test)

```bash
# 1. Install
python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt

# 2. Configure — set these in .env
#    OPENROUTER_API_KEY=...     (required for generator + evaluator)
#    SERPER_API_KEY=...         (required for primary web search)
#    SEMANTIC_SCHOLAR_API_KEY=... (optional — academic search)

# 3. Run one query against the 8-query validation sweep
python -m scripts.run_honest_sweep_r3 \
    --only clinical_tirzepatide_t2dm \
    --out-root outputs/dev_smoke

# 4. Or run all 8 queries
python -m scripts.run_honest_sweep_r3

# 5. Inspect
ls outputs/dev_smoke/*/
#   manifest.json  — pipeline verdict + cost + gates
#   report.md      — verified findings OR pipeline-verdict artifact
#   corpus_approval.json, contradictions.json, etc.
```

Each run produces one of three manifest statuses:

- `success` — all gates passed, `report.md` has verified findings + bibliography
- `abort_*` — a pipeline gate refused to continue (e.g.
  `abort_corpus_approval_denied`, `abort_no_verified_sections`,
  `abort_corpus_inadequate`). No LLM tokens billed past the abort
  point. `report.md` is a pipeline-verdict artifact, not a content report.
- `error_*` — an unexpected failure

## Quick start — pipeline B (the web UI)

```bash
# Local
uvicorn scripts.live_server:app --host 0.0.0.0 --port 8000

# Or via Docker
docker compose up web
# Visit http://localhost:8000
```

## Pipeline A architecture at a glance

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
provenance_generator.strict_verify   ──► drop sentences whose
    │                                    [#ev:id:start-end] span
    │                                    doesn't contain the numeric
    │                                    claim AND ≥2 content-word
    │                                    overlap. If zero verified →
    │                                    abort_no_verified_sections.
    ▼
live_qwen_judge (Qwen3-8B, DIFFERENT FAMILY from generator)
    │
    ▼
external_evaluator.run_external_evaluation
    │
    ▼
report.md + manifest.json
```

## Hardness invariants (round-tested)

Five invariants were stress-tested through a 5-round Codex↔Claude
audit (2026-04-18). All closed. See `outputs/codex_findings/round_*/`
for full findings + responses.

- **B-1 semantic grounding**: non-numeric claims require ≥2 content-word
  overlap between sentence and cited span.
- **B-2 corpus-approval enforcement**: rubber-stamp note on a corpus
  with material tier deviation aborts before the first generator token.
- **B-3 zero-verified abort**: if every generated section fails
  strict_verify, `report.md` is a pipeline-verdict artifact, not an
  empty-findings report masquerading as success.
- **B-4 budget cap**: `PG_MAX_COST_PER_RUN` holds even when OpenRouter
  omits `usage.cost` in its response (token-based imputation; negative
  tokens clamped to zero).
- **B-5 delimiter sanitization**: evidence content containing
  `<<<evidence:...>>>` / `<<<end_evidence>>>` literals, including via
  NFKC/NFKD Unicode evasions, zero-width/invisible codepoints, bidi
  overrides, and Cyrillic/Greek homoglyphs, cannot forge a false
  evidence boundary and inject directives.

## Repo layout

```
POLARIS/
├── architecture.md          — current-state architecture (rewritten 2026-04-18)
├── CLAUDE.md                — operational directives (non-negotiable)
├── ground_rules.md          — engineering ground rules
├── README.md                — this file
│
├── src/
│   ├── polaris_graph/       — pipelines A + B (active, 159 commits in last 60 days)
│   │   ├── nodes/           — scope_gate, corpus_approval_gate, ...
│   │   ├── retrieval/       — live_retriever, tier_classifier, ...
│   │   ├── generator/       — multi_section, live_deepseek, provenance
│   │   ├── evaluator/       — external_evaluator, live_qwen_judge
│   │   ├── llm/             — openrouter_client (with two-family check)
│   │   ├── graph.py, graph_v2.py, graph_v3.py  — LangGraph variants (pipeline B)
│   │   ├── memory/          — campaign/cross-vector stores (pipeline B)
│   │   └── ...
│   ├── orchestration/       — pipeline C (FROZEN 2026-03-16, see folder's README)
│   ├── auth/                — auth middleware for pipeline B UI
│   ├── tools/               — active tool clients
│   ├── audit/               — automated deep audit
│   ├── config/              — config loaders
│   ├── agents/              — agent-style helpers
│   └── ...                  — see docs/file_directory.md
│
├── scripts/
│   ├── run_honest_sweep_r3.py   — pipeline A entry (active)
│   ├── run_r6_validation.py     — 4-query revalidation
│   ├── live_server.py           — pipeline B FastAPI (active)
│   ├── full_cycle.py            — pipeline C (frozen)
│   ├── audit_live_code.py       — static import-closure audit
│   ├── codex_loop_parse.py      — Codex verdict parser
│   └── ...                      — see docs/file_directory.md
│
├── tests/polaris_graph/     — 305 tests, all passing against pipeline A
│
├── config/settings/         — active YAML configuration
├── data/                    — reproducible benchmarks (gitignored)
├── outputs/                 — runtime artifacts (gitignored), except
│                              outputs/codex_findings/ (audit record)
├── logs/                    — runtime logs (gitignored)
├── state/                   — pipeline state files (gitignored)
│
├── docs/
│   ├── file_directory.md    — inventory of active code
│   ├── todo_list.md         — prioritized backlog
│   ├── live_code_audit.md   — static import-closure analysis
│   └── runbook.md           — how to run each pipeline end-to-end
│
├── .codex/                  — Codex↔Claude audit loop infrastructure
│   └── LOOP_PROTOCOL.md
│
└── archive/                 — historical snapshots (gitignored, 36GB+)
    └── 2026-04-18-pre-audit-cleanup/   — this cleanup's artifacts
```

## Running the test suite

```bash
python -m pytest tests/polaris_graph/ -v
# Expected: 305 passed
```

## Observability

- `logs/pg_cost_ledger.jsonl` — per-call cost tracking (JSONL)
- `logs/session_log.md` — append-only operational log
- `logs/bug_log.md` — defects and blockers register

## Further reading

- `architecture.md` — detailed architecture (current state only)
- `docs/runbook.md` — how to run each pipeline end-to-end
- `docs/live_code_audit.md` — which files are reachable from which entry points
- `outputs/codex_findings/round_{1..5}/` — 5-round Codex↔Claude audit record
- `CLAUDE.md` — operational directives (non-negotiable)
- `ground_rules.md` — engineering ground rules

## License

Proprietary. All rights reserved.
