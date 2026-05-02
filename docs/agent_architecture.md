# POLARIS v6.2 — Agent Architecture & Verifier Pattern Adoption

**Last updated:** 2026-05-01
**Owning task:** Phase 0 Task 0.2
**Plan reference:** `docs/carney_delivery_plan_v6_2.md`

This document fixes the architecture pattern POLARIS will adopt for the agent + verifier loop, performs the license scan that gates whether external code can be reused, and locks the implementation plan that extends existing POLARIS substrate (no fork).

---

## 1. Decision (TL;DR)

- **Adopt pattern, NOT code**: Local Verifier + Global Verifier loop (architecture only)
- **No fork**: do not vendor MiroThinker or any third-party verifier into POLARIS
- **Extend existing substrate**: build native verifier on top of POLARIS strict_verify provenance check (`src/polaris_graph/agents/verifier.py`, `src/polaris_graph/agents/nli_verifier.py`, `src/polaris_graph/synthesis/verifier_v2.py`)
- **License scan**: Apache 2.0 patterns (MiroThinker, Toolformer, Self-RAG) are reference-only; CC-BY-NC training data is forbidden

**Rationale:** POLARIS already has 9 verifier-adjacent modules in production substrate. Forking a third-party verifier creates a maintenance burden + license-attribution surface area for what is fundamentally a 200-300 LOC architectural pattern. Reference the literature, build native.

---

## 2. The pattern (what we are adopting)

### 2.1 Two-stage verifier loop

```
generator output (with provenance tokens)
        ↓
[Local Verifier]   per-sentence
- evidence-id in pool                ──── strict_verify (already exists)
- span bounds valid
- decimals in sentence appear in span
- ≥2 content-word overlap
        ↓
        ├── PASS → mark verified
        └── FAIL → drop sentence + log
        ↓
[Global Verifier]  per-section + cross-section
- frame coverage check               ──── frame_manifest (already exists)
- contradiction detection            ──── audit_ir (already exists)
- two-family disagreement signal     ──── openrouter_client family-segregation
- numeric consistency cross-claims   ──── NEW (M-INT-3 substrate)
- citation density ≥40% of section   ──── strict_verify section gate
        ↓
        ├── PASS → ship section
        └── FAIL → one regeneration attempt → re-run Local + Global
        ↓
        └── still FAIL → abort_no_verified_sections
```

### 2.2 Why two stages

- Local Verifier is **cheap and deterministic** (string match + numeric match + token overlap). Catches fabricated cites, hallucinated numbers, off-topic prose.
- Global Verifier is **section-and-corpus-aware**. Catches frame imbalance, contradiction, sycophantic agreement with leading prompts, two-family bias.
- A single-stage verifier conflates these and over-rejects (kills good sentences) or under-rejects (lets a coherent-but-wrong-frame report ship).

### 2.3 What POLARIS already has

| Pattern component | Existing module | Status |
|---|---|---|
| Per-sentence provenance token | `src/polaris_graph/generator/provenance_generator.py` | LIVE |
| Strict verify (Local Verifier core) | `src/polaris_graph/synthesis/verifier_v2.py` | LIVE |
| NLI-based verification (deeper Local) | `src/polaris_graph/agents/nli_verifier.py` | LIVE (flan-t5-large 512-token, 96× speedup via context extraction per memory lesson 6) |
| Generator-side verifier hook | `src/polaris_graph/agents/verifier.py` | LIVE |
| Two-family segregation (Global guard) | `src/polaris_graph/llm/openrouter_client.py` | LIVE (raises RuntimeError if violated) |
| Frame coverage check | `src/polaris_graph/generator/frame_manifest.py` | LIVE |
| Contradiction detection | `src/polaris_graph/audit_ir/` (47 modules) | LIVE |
| Retrieval-side verify context | `src/polaris_graph/retrieval/verify_context.py` + `verify_schemas.py` | LIVE |
| Section-level abort gate | strict_verify pipeline status `abort_no_verified_sections` | LIVE |

**Conclusion:** ~80% of the pattern exists. Build is wiring + Global Verifier numeric-consistency module + UX surfacing of verifier verdicts in Inspector view.

### 2.4 What is NEW build (M-INT-3)

1. **Numeric consistency cross-claim verifier**: takes all numbers from a section, groups by entity (e.g., "Canadian housing starts 2025"), flags disagreement >5% across cited sources. ~300 LOC, new module `src/polaris_graph/agents/global_numeric_verifier.py`.
2. **Verifier verdict streaming to UI**: SSE event `verifier_verdict` per sentence + per section, consumed by F4 (live audit run) + F5 (Inspector view).
3. **Verifier audit trail in bundle**: every verified sentence carries `{verifier_local_pass: bool, verifier_global_pass: bool, drop_reason: str|null}` in F15 bundle JSON.

---

## 3. License scan

### 3.1 Patterns referenced (no code adoption)

| Reference | License | Use | Adoption |
|---|---|---|---|
| MiroThinker (Tencent) | Apache 2.0 | Architecture pattern: dual verifier loop | Reference only — pattern reimplemented native |
| Toolformer (Meta, 2023) | Apache 2.0 | Tool-call provenance tokens | POLARIS pattern predates; no new adoption |
| Self-RAG (Asai 2023) | Apache 2.0 | Reflection tokens | POLARIS provenance tokens are functionally equivalent; no adoption |
| WebGPT (OpenAI) | Closed | Citation-grounded generation | Reference only |
| Perplexity (citation hover-card UX) | Closed | Live citation overlay UX | UX pattern only; F6 implementation native |

### 3.2 Forbidden inputs

- **CC-BY-NC training data**: any verifier model fine-tuned on CC-BY-NC corpora is excluded (commercial-restriction risk for Carney delivery)
- **GPL-licensed code**: no copyleft contamination of POLARIS Apache-style licensing posture
- **Closed-license model weights**: GPT-4-class weights are call-only via OpenRouter / DeepSeek API, not vendored

### 3.3 POLARIS verifier model selection (Phase 0 Task 0.8 verifies, this task locks intent)

- **Local Verifier**: deterministic Python (no LLM call). Cost: $0/sentence.
- **Local Verifier deeper check (NLI)**: `flan-t5-large` (Apache 2.0, public). Cost: $0/sentence (local CPU/GPU).
- **Global Verifier**: Gemma 4 31B Dense (Apache 2.0, Google) running on sovereign cluster (Phase 4). Two-family-segregated from generator (DeepSeek V4 family).
- **Sycophancy stress-test grader (Layer-1 CI)**: Gemma 4 31B + paired-prompt methodology (ELEPHANT/SycEval).

**Cross-check vs CLAUDE.md §9.1 invariant 1**: Two-family evaluator. DeepSeek V4 (DeepSeek lineage) generator + Gemma 4 (Google lineage) global verifier passes `openrouter_client.check_family_segregation`.

---

## 4. Implementation plan (extends, not replaces)

### 4.1 Phase 1 (M-INT-3 substrate)

- [ ] Wire existing `verifier_v2.py` Local Verifier into v6 graph (graph_v4 → graph_v5 wrapper that produces `verifier_local_*` SSE events)
- [ ] Build `global_numeric_verifier.py` (NEW, ~300 LOC)
- [ ] Wire `frame_manifest.py` + `audit_ir/` contradiction modules into Global Verifier pass
- [ ] Add verifier audit trail to F15 bundle schema (Evidence Contract Gate, M-INT-1)

### 4.2 Phase 2A (UI surfacing)

- [ ] F4 live audit run UI consumes SSE `verifier_verdict` events
- [ ] F5 Inspector view shows per-sentence verifier verdict (PASS / DROPPED + reason)
- [ ] Drop-reason taxonomy: `evidence_id_not_in_pool`, `span_oob`, `numeric_mismatch`, `content_word_overlap_lt_2`, `numeric_consistency_violation`, `frame_imbalance`, `contradiction_unresolved`

### 4.3 Phase 3 (benchmark)

- [ ] Verifier verdict ratio (verified-sentences / total-generated-sentences) is a benchmark dimension
- [ ] Compare POLARIS verifier-pass rate vs ChatGPT 5.5 Pro DR + Gemini 3.1 Pro DR (sentence-level audit by paid Layer-3 evaluator)

### 4.4 Phase 4 (sovereign)

- [ ] Migrate Gemma 4 31B Global Verifier to OVH Canada BHS sovereign cluster
- [ ] Re-verify family segregation invariant on sovereign topology
- [ ] Re-run benchmark on sovereign infra

---

## 5. Acceptance criteria for Task 0.2

Per `docs/task_acceptance_matrix.yaml` task_0_2:

- [x] Architecture pattern documented (dual-verifier loop)
- [x] License scan complete — Apache 2.0 patterns referenced, no fork; no CC-BY-NC inputs; no GPL contamination
- [x] Existing POLARIS substrate mapped to pattern components
- [x] NEW build identified (Global Numeric Verifier ~300 LOC, M-INT-3 milestone)
- [x] Two-family segregation invariant cross-checked (DeepSeek V4 generator + Gemma 4 31B verifier passes `check_family_segregation`)
- [x] Implementation plan sequenced across Phase 1 → 2A → 3 → 4
- [x] Verifier audit trail design integrated into F15 bundle schema commitment

**Codex review brief:** `.codex/task_0_2_review_brief.md` (next step — write before triangle-loop self-audit)

**Triangle loop next:**
1. Claude self-audit at `outputs/audits/task_0_2/claude_audit.md`
2. Codex independent audit at `outputs/audits/task_0_2/codex_audit.md`
3. Cross-review at `outputs/audits/task_0_2/cross_review.md`
4. Both GREEN → merge + advance Task 0.3
