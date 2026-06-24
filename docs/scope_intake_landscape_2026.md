# Scope / Intake Landscape 2025/2026 — Best Practice + Open-Source Solutions

**Status:** research deliverable, operator-requested 2026-06-24. Section "scope / intake" of the standard
pipeline-section review (`docs/standard_process_pipeline_section_review.md`), sibling to
`docs/retrieval_landscape_2026.md`, `docs/composition_landscape_2026.md`,
`docs/credibility_tier_landscape_2026.md`.
**Method:** deep research, 2025/2026 primary-source verified, then every current-stack claim grounded against
the actual POLARIS repo with file:line. Frontier-tech mandate applied (year + primary URL per candidate;
pre-2024 used only as a declared incumbent floor).
**Scope of this section:** turn the user's real input — a long/confusing prompt + heavy uploaded attachments +
a privileged Telus internal database — into a research plan handed off to query-gen. FOUR jobs:
(1) prompt understanding, (2) heavy-attachment intake as cited evidence, (3) Telus internal DB as a new
top-weight T0 cited tier, (4) plan handoff to FS-Researcher query-gen.

---

## 0. The one-paragraph answer

Three of the four jobs already have real machinery in the repo; one does not exist at all and is the headline
build. **Prompt understanding** is split and clinical-biased: a deterministic regex PICO/scope gate
(`scope.py`, `scope_gate.py`) plus a clinical ambiguity classifier (`intake.py`) that *dead-ends every
uncertain non-clinical question to out_of_scope*. The 2025/2026 move is an LLM intent-decomposition +
clarification step that runs **at intake time** (pre-run UI), feeding both the clinical PICO lane (AlpaPICO-style)
and the already-present domain-general frame (`extract_research_frame_heuristic`). **Attachment intake** has a
working local ingester (`document_ingester.py`: PyMuPDF/OCR/Whisper) and a session RAG
(`local_document_rag.py`) — but the RAG still embeds with all-MiniLM, and uploads are hardcoded to tier T2.
The 2025/2026 upgrade is a layout-aware extractor (PaddleOCR-VL-1.6 — the current #1 OmniDocBench-v1.6 crown at
96.33, Apache-2.0; Docling as the deterministic fallback) for tables/scans, and re-embedding on
the already-decided Qwen3-Embedding-8B so the attachment vector space aligns with public retrieval for fusion.
The same intake boundary must also **detect-and-redact PII/PHI and screen uploads for indirect prompt injection
before any embed/generator hop** — a privacy/trust gate, never a faithfulness relaxation.
**The Telus internal DB (T0) does not exist** — no connector, no tier, no fusion. It is the biggest gap and the
core design strand. A massive Telus internal DB is most likely **structured/relational (SQL/tabular), not just a
vector store** — so the T0 adapter must cover a structured/hybrid retrieval lane (text-to-SQL plus hybrid
SQL+vector, returning cell-level provenance), not a vector-only design that silently drops every structured fact.
The discriminating constraint: T0 is the most private data in the system and must be cited
at the heaviest weight, yet the egress router already forbids anything but `PUBLIC_SYNTHETIC` from reaching an
external generator. **T0 citation is therefore only legal under the self-hosted sovereign GLM-5.2 deployment** —
the design must state this, not work around it. **Plan handoff** is the healthiest: FS-Researcher query-gen
(`fs_researcher_query_gen.py`) is already wired (flag-gated) and is the correct handoff target — intake's job is
to hand it a distilled intent frame plus the attachment/T0 seed evidence.

The architectural rule from CLAUDE.md §-1.3 governs all four: **T0 is a WEIGHT, not a FILTER**, attachments and
internal-DB hits **consolidate** into baskets, and every privileged source still passes the **frozen
faithfulness gate** — privileged is not the same as unverified.

---

## 1. What POLARIS has today (verified in the repo, not assumed)

| Job | Current POLARIS implementation | Verified location |
|---|---|---|
| Prompt understanding — scope gate | Deterministic, rule-based protocol lock at T+0; writes `protocol.json` + SHA, no LLM (un-hallucinable by design) | `nodes/scope_gate.py:856` `run_scope_gate` |
| Prompt understanding — PICO | Regex PICO extractor, clinical-only; config-driven INN-stem + device/procedure recognizer (F13 / I-arch-011) | `nodes/scope_gate.py:580` `extract_pico_heuristic`, `:546` `_intervention_present` |
| Prompt understanding — domain-general frame | Field-agnostic entity/metric/comparator heuristic, NO clinical literal (B9 spine) | `nodes/scope_gate.py:656` `extract_research_frame_heuristic` |
| Prompt understanding — domain classify | Deterministic domain/intent classifier, optional injectable LLM refine, fails open to `general` | `nodes/scope_gate.py:776` `classify_domain_intent` |
| Prompt understanding — sub-question decomposition | LLM decomposes topic → 6-10 sub-questions + perspectives + queries; diversity gate; template fallback | `nodes/scope.py:82` `run_scope` |
| Intake — ambiguity / clarification | Clinical ambiguity axes (population/intervention/outcome); **uncertain → out_of_scope dead-end** | `api/intake.py:91` `process_intake`, `:182` |
| Attachment — local extraction | PyMuPDF + pytesseract OCR fallback, python-docx, openpyxl, python-pptx, readability, Whisper audio; all LOCAL | `document_ingester.py:85` `DocumentIngester`, `:230` `_parse_pdf` |
| Attachment — session RAG | Per-session ChromaDB collection, chunk + embed + query | `memory/local_document_rag.py:51` |
| Attachment — embedder | **all-MiniLM-L6-v2 (384-dim)** — NOT yet the decided Qwen3 | `memory/local_document_rag.py:7,106`; `src/utils/embedding_service.py:61-64` (flag `PG_EMBEDDER_MODEL=qwen3` exists, default still MiniLM) |
| Attachment — evidence bridge | Sovereignty-partition uploads, build pipeline-A evidence rows; **tier hardcoded T2** | `polaris_v6/adapters/upload_evidence.py:51`, `:95` `"tier": "T2"` |
| Sovereignty gate (load-bearing for T0) | `filter_for_external_egress` — only non-forbidden classifications may egress to external generator | `sovereignty/router.py:43`; `sovereignty/classification.py` |
| Telus internal DB (T0) | **DOES NOT EXIST** — no connector, no T0 tier, no privileged fusion | — |
| Tier weighting (where T0 must slot above) | T1–T7 + UNKNOWN deterministic classifier; `authority_score` model (Phase 0a) | `retrieval/tier_classifier.py:71` `TierLevel`, `:31-48` taxonomy |
| Plan handoff — query-gen | FS-Researcher TOC/todo-queue + 6-item self-review checklist, flag-gated, already wired | `retrieval/fs_researcher_query_gen.py:79` `plan_fs_researcher_queries` |

**Three corrections to naive assumptions, grounded in the repo:**

1. **The scope gate is deliberately LLM-free.** `scope_gate.py` writes an immutable, hash-stamped `protocol.json`
   so the pre-registered scope cannot be hallucinated or silently drifted. Any LLM intent-decomposition we add
   must sit *in front of* this gate as advisory enrichment, never replace the deterministic protocol lock.
2. **PICO is clinical-only and the pipeline is now domain-general (B9).** The decomposition design must cover the
   general frame path *and* the clinical PICO lane — not bolt PICO onto every domain.
3. **The attachment path already enforces sovereignty.** `upload_evidence.py` only lets `PUBLIC_SYNTHETIC`
   uploads become external-generator evidence. This is the exact mechanism the T0 design must plug into — there
   is no need (and it would be a bug) to invent a parallel egress policy.

---

## 2. The discriminating constraint: the sovereignty / egress paradox (read before the T0 design)

This is the hinge of the whole section, not a footnote.

- **T0 is the most private data in the system.** A Telus internal database is `CLIENT` / `PRIVATE` /
  `CAN_REAL`-class content, never `PUBLIC_SYNTHETIC`.
- **The egress router forbids it from reaching an external generator.** `is_external_leak_forbidden` blocks every
  classification except the public-synthetic safe set (`router.py:58`; `upload_evidence.py:29`
  `EGRESS_SAFE_CLASSIFICATION = "PUBLIC_SYNTHETIC"`). The generator is an OpenRouter call on the public benchmark
  path. So **citing Telus T0 through the OpenRouter generator is a sovereignty violation** — it would leak
  privileged data off Canadian-sovereign infra.
- **Therefore T0 citation is only legal under the self-hosted sovereign GLM-5.2 deployment** (the Carney sovereign
  pipeline, on-prem, no external egress). On the public OpenRouter benchmark path, T0 must be *withheld from the
  generator payload* and can at most contribute non-egressing signal (e.g., a count that "N internal sources
  corroborate" without shipping their text).
- **Load-bearing assumption (must be confirmed with the operator before build):** the Telus deployment is on-prem
  / self-hosted with the sovereign GLM-5.2 backbone. If Telus runs POLARIS against an external generator, T0 is
  **uncitable** by construction and the entire strand collapses to "internal-DB-as-retrieval-signal-only." This
  assumption is the gate on the whole job-(3) design.

Design consequence: T0 is wired as a **deployment-conditional** tier. In the sovereign deployment it is a full
citable T0 evidence row at heaviest weight; on any external-generator path it is egress-blocked exactly like a
non-`PUBLIC_SYNTHETIC` upload today.

---

## 3. The four jobs — axis, candidates, and design

### Job 1 — Prompt understanding (DESIGN STRAND: concrete design below)

**Axis:** intent-extraction correctness — does a long/confusing/multi-part prompt yield the right research
question(s), in/out scope, domain, must-cover points, and output shape, **without** over-refusing legitimate
research and **without** mid-run pauses.

**Current floor + its gap.** Two disconnected mechanisms: (a) the deterministic regex scope gate
(`scope_gate.py`) is robust but shallow — it cannot decompose a confusing multi-part prompt into distinct
questions; (b) `intake.py` only understands *clinical* ambiguity and **gives up on everything else** — an
uncertain non-clinical prompt is coerced to `out_of_scope` (`intake.py:182-198`). A confusing economics or
policy prompt therefore gets no clarification and no decomposition; it either passes through shallowly or is
wrongly rejected.

**2025/2026 candidates:**

| Candidate | Year / primary source | License | Why / fit |
|---|---|---|---|
| RQ-RAG (refine-query decomposition) | 2024, arXiv 2404.00610 | OSS (code on GitHub) | Decomposes multi-hop/ambiguous queries into latent sub-questions — the pattern, not the model; portable as a prompt scaffold on GLM-5.2 |
| Intent-based query rewriting | 2025, VLDB-W DATAI25 (arXiv 2511.20419) | paper (method) | Frames rewriting around *user intent* not surface tokens — the right primitive for "confusing prompt → actual question" |
| AlpaPICO | 2024, arXiv 2409.09704 | OSS (LoRA, Llama/Alpaca) | In-context PICO-frame extraction from clinical text; **clinical lane only**. Incumbent floor (2024) — declared, not frontier |
| 680k-PICO GenAI extraction | 2024, Pharm Med (PMC11473607) | paper (GPT-4o, closed) | Evidence that LLM PICO extraction is production-viable; method is portable, the model is not (sovereignty) |
| Clarification-question generation (asking-not-guessing) | 2025, conversational-intervention line (arXiv 2503.16789) | paper (method) | Best practice = ask 2-3 targeted clarifiers when scope is under-specified; matches the repo's own `deep-research` skill pre-flight. **Incumbent floor — superseded as frontier by IntentRL (below)** |
| IntentRL — proactive user-intent agents for deep research | **2026, arXiv 2602.03468** | **method/pattern only — no confirmed public repo+license (LAW II: not recommended as a deployable candidate, used as a design pattern)** | The 2026 frontier framing of Job 1: *proactively clarify latent/evolving user intent before launching the long-horizon run*, instead of passively executing the first instruction. Exactly the "confusing prompt → ask, don't guess, at intake time" pattern. Imported as a PROMPT/loop pattern on GLM-5.2, **never** as the RL training pipeline (sovereignty + the unverified-OSS bar). Re-check for a public release before any build |

**Proposed design (concrete):**

1. **Add an intake-time intent-decomposition step, advisory, in front of the deterministic gate.** A single
   GLM-5.2 call (sovereign backbone; injectable `llm` seam already exists at
   `classify_domain_intent(..., llm=...)`, `scope_gate.py:782`) takes the raw prompt and returns a structured
   `IntentFrame`: `{questions[], in_scope[], out_of_scope[], domain, must_cover[], output_shape,
   clarification_needed[]}`. This **does not** replace `run_scope_gate` — its output flows in as
   `user_overrides` + advisory notes, so `protocol.json` stays deterministic and hash-stamped (clinical
   byte-identity preserved; the frame is routing context, never serialized into the protocol — same contract as
   the existing `DomainIntent`, `scope_gate.py:729`).
2. **Branch the decomposition by domain.** Clinical → the PICO lane (AlpaPICO-style frame on GLM-5.2, falling
   back to the existing regex `extract_pico_heuristic`). Non-clinical → the existing field-agnostic
   `extract_research_frame_heuristic` (`scope_gate.py:656`), now seeded/refined by the LLM frame. This honours
   B9 domain-generality and never forces PICO on a non-clinical prompt.
3. **Move clarification to intake time, not mid-run.** When `clarification_needed` is non-empty, surface 2-3
   targeted questions in the **pre-run UI** (the `/intake` page already auto-detects domain and source-set).
   This respects the autonomous-run directive (no mid-run pause — `feedback_no_midcampaign_checkpoint_stops`):
   clarification happens *before* the run is launched, never during it. Replace the
   `uncertain → out_of_scope` dead-end (`intake.py:182`) with `uncertain → clarify` for in-domain prompts;
   keep refusal only for genuine harm-intent / true out-of-scope.
4. **Fail open, never fabricate.** LLM error / garbage → the deterministic heuristic frame (the existing
   fail-open contract, `scope_gate.py:837`). A confusing prompt degrades to "run the literal question with a
   flagged needs_user_review," never to a hallucinated rewrite.

5. **Detect-and-redact PII/PHI at intake, before any chunk/embed/generator hop (unknown-unknown the prior draft never asked).** The whole §2 hinge is privacy, yet intake currently does no PII/PHI screen on inbound prompts or uploads. For a clinical + Telus-private pipeline this is a hard gap: a pasted prompt or an uploaded chart can carry patient identifiers straight into the session RAG and (on the public path) into the OpenRouter generator payload. Add a deterministic redaction pass at the intake boundary using **Microsoft Presidio** (2026, GitHub `microsoft/presidio`, MIT, self-hostable; v2.2.362 Mar-2026 ships a `MedicalNERRecognizer` + GLiNER/Stanza engines for clinical entities). General-text NER drops sharply on clinical notes (GLiNER F1 0.81→0.41), so on the clinical lane prefer a clinical-tuned recognizer (Presidio MedicalNER, or a clinical de-id model — John Snow Labs Healthcare-NLP reports 96% PHI-F1 but is not OSS, named only to set the bar). Redaction maps identifiers to placeholders **before** embed/generator; the verbatim-span faithfulness contract is preserved on the *redacted* span (the placeholder is byte-stable). This is a privacy gate, never a faithfulness relaxation.

**Faithfulness path:** none of this touches the faithfulness engine — it only shapes *which questions get asked* and *which identifiers are masked before egress*.
The deterministic protocol lock + SHA remain the source of truth for scope.

**Provisional pick / design to beat:** GLM-5.2 single-call `IntentFrame` decomposition + domain-branched
PICO/general frame + intake-time clarification, advisory-in-front-of-deterministic-gate. The bake-off
(I-cred-001 sibling series) scores it on intent-extraction correctness vs the current regex-only gate on a
gold-set of confusing multi-part prompts (§4).

### Job 2 — Heavy-attachment intake as cited evidence (lighter survey + targeted upgrades)

**Axis:** attachment coverage — how much of a large/long/scanned upload corpus becomes faithful, cited,
faithfulness-gated evidence.

**Current floor + gaps.** `document_ingester.py` is solid for born-digital text (PyMuPDF, docx, xlsx, pptx,
Whisper) with an OCR fallback. Two gaps: (a) **tables and complex-layout scans** — PyMuPDF `get_text` + flat
pytesseract loses table structure and multi-column order; (b) the session RAG embeds with **all-MiniLM**
(`local_document_rag.py:7,106`), a different vector space from the public retrieval path, which breaks fusion;
and (c) uploads are **hardcoded to tier T2** (`upload_evidence.py:95`) regardless of what they are.

**2025/2026 candidates:**

| Candidate | Year / primary source | License | Why / fit |
|---|---|---|---|
| Docling (IBM/DS4SD) | 2024-2026, GitHub `docling-project/docling` | MIT, self-hostable | Layout-aware: DocLayNet layout + TableFormer table-structure; emits structured JSON/Markdown. Best fit for our verbatim-span faithfulness rule (deterministic, keeps spans). Still the deterministic default; **no longer the accuracy frontier** — the VLM parsers below now top OmniDocBench |
| **PaddleOCR-VL-1.6** (NEW frontier crown — #1 OmniDocBench v1.6) | **2026, arXiv 2606.03264 (2026-06-02); HF `PaddlePaddle/PaddleOCR-VL-1.6`** | **HF model-card license field = `apache-2.0` (verified at source), self-hostable, vLLM-supported** | ~0.9-1.0B compact VLM; **new #1 on OmniDocBench v1.6, overall 96.33** — raises its predecessor's 94.93 via region-aware data optimization + progressive RL post-training. Tops MinerU2.5-Pro (95.75) at ~1/1.3 the size. The current frontier table/formula/scan extractor AND the sovereign-light default in one — both jobs that the 1.5 + MinerU2.5-Pro split used to cover |
| MinerU2.5-Pro (prior #1, now demoted) | 2026, arXiv 2604.04771; HF `opendatalab/MinerU2.5-Pro-2604-1.2B` | HF model-card license field = `apache-2.0` (verified at source — AGPL concern RESOLVED), self-hostable | 1.2B decoupled VLM; OmniDocBench v1.6 overall **95.75** — was the crown last pass, now superseded by PaddleOCR-VL-1.6 (96.33). The AGPL blocker the earlier draft flagged is gone (released weights carry apache-2.0; the repo-code MinerU Open Source License is the separate wrapper — confirm the LICENSE you actually link against at build). Strong table/formula extractor; kept as the larger-model alternate |
| PaddleOCR-VL-1.5 (incumbent floor, superseded by 1.6) | 2025-2026, HF `PaddlePaddle/PaddleOCR-VL-1.5` | Apache-2.0, self-hostable | 0.9B, OmniDocBench v1.6 = 94.93; directly superseded by PaddleOCR-VL-1.6 (same family, 96.33). Named only as the version the 1.6 release builds on |
| dots.ocr / DeepSeek-OCR-2 (NEW — open alternates) | 2025-2026, HF `rednote-hilab/dots.ocr`, `deepseek-ai/DeepSeek-OCR-2` | MIT (dots.ocr) / Apache-2.0 (DeepSeek-OCR-2), self-hostable | 3B VLM parsers, OmniDocBench v1.6 ≈90.8 / 90.3. Multilingual layout parsing; viable if MinerU/PaddleOCR licenses ever conflict |
| OmniDocBench (v1.6, 2026/04) | 2025-2026, CVPR 2025 + maintained leaderboard; GitHub `opendatalab/OmniDocBench` | OSS (eval harness) | The benchmark to pick the extractor against — 1651 pages, 10 doc types. **v1.6 is the current leaderboard** (the prior draft cited the static CVPR-2025 v1.x); pick against v1.6, re-check for a newer release at build |
| Qwen3-Embedding-8B | 2025, HF `Qwen/Qwen3-Embedding-8B` | Apache-2.0, self-hostable | The **already-decided** embedder (I-arch-009 #1266). Re-embed attachments on it to align with public retrieval |
| LlamaParse | 2024, closed SaaS | **non-sovereign** | Strong parser but cloud-only → BANNED for the sovereign path; named only to reject |

**Proposed upgrades (surgical, not a rewrite of the ingester):**
1. Add a **layout-aware extraction lane** (PaddleOCR-VL-1.6 as the frontier extractor for table/scan-heavy docs —
   Apache-2.0, #1 OmniDocBench v1.6 @96.33; Docling as the deterministic fallback; MinerU2.5-Pro as the larger
   alternate) behind the existing `DocumentIngester.PARSERS` dispatch — keep PyMuPDF for clean born-digital text.
   Faithfulness rule (per `retrieval_landscape_2026.md` §3): deterministic extractors that keep **verbatim
   spans**; never let an LLM rewrite a span the verifier later checks.
2. **Re-embed the session RAG on Qwen3-Embedding-8B** (flip `PG_EMBEDDER_MODEL=qwen3`; the seam exists at
   `embedding_service.py:61`). This is the alignment prerequisite for fusing attachment hits with public
   retrieval.
3. **Tier attachments by what they are, not a constant.** Replace the hardcoded `"tier": "T2"`
   (`upload_evidence.py:95`) with a light classification: a user-uploaded peer-reviewed PDF → its real tier; a
   user's own working doc → an "uploaded/user-provided" weight. Still consolidates into baskets; still passes
   the faithfulness gate.
4. **Summarize/index when many/long.** For a large upload corpus, the session RAG already chunks + retrieves
   top-k per sub-question — keep that as the selection mechanism; add a per-document map-reduce summary as a
   navigation index (not as evidence; evidence stays verbatim-span).
5. **Screen uploads for indirect prompt injection (unknown-unknown the prior draft never asked).** Invariant
   §9.1.7 sanitizes *web* evidence against delimiter literals, but an uploaded PDF/docx is an equally hostile
   channel: a 2025/2026 attack class hides instructions in white-on-white text, HTML comments, or off-canvas
   layers that a parser extracts but a human never sees (arXiv 2601.10923 "Hidden-in-Plain-Text" RAG indirect-
   injection benchmark; the broader RAG-security taxonomy arXiv 2604.08304). The same NFKD/invisible-char/
   homoglyph neutralizer that §9.1.7 already runs MUST also run on extracted upload spans, plus an instruction-
   pattern flag (imperative / role-play / "ignore previous" framing) that tags the span for extra scrutiny rather
   than executing it. Treat every uploaded document as untrusted data, never as instructions — uploads carry the
   user's authority over *content*, never over the *pipeline*.

**Faithfulness path:** unchanged — uploaded evidence rows flow through the same `strict_verify` / provenance /
NLI / 4-role engine as web evidence (`upload_evidence.py` already shapes them to the V30-P2 contract). The
injection screen and the PII redaction (Job 1) are upstream of, and independent from, the faithfulness gate.

### Job 3 — Telus internal DB as T0 top-weight cited evidence (DESIGN STRAND: concrete design below)

**Axis:** privileged-source integration — connect, query, weight, fuse, and cite a massive private DB at the
heaviest weight, while staying sovereign and passing the faithfulness gate.

**Current floor:** nothing. No connector, no T0 tier, no fusion. This is a from-scratch build, governed by §2's
egress paradox and the §-1.3 weight-not-filter DNA.

**2025/2026 candidates:**

| Candidate | Year / primary source | License | Why / fit |
|---|---|---|---|
| pgvector + HNSW (on PostgreSQL) | 2024-2026, GitHub `pgvector/pgvector` | PostgreSQL license, self-host | Simplest sovereign private vector store; co-locates with relational metadata; the EU-sovereign-RAG reference stack |
| Weaviate | 2025-2026, GitHub `weaviate/weaviate` | BSD-3, self-host | AI-native, **built-in hybrid (BM25 + vector)** in one engine, SOC2/HIPAA — strong if hybrid-in-engine is wanted |
| Milvus | 2025-2026, GitHub `milvus-io/milvus` | Apache-2.0, self-host | Scales to enterprise/"massive DB"; deploy on-prem/hybrid |
| Weighted Reciprocal Rank Fusion (WRRF) | 2025-2026, arXiv (CCNC 2026 WRRF paper) | method | **The source-priority fusion rule** — fuse private + public ranked lists with a trust weight per source; broader source diversity than plain RRF |
| HF-RAG (hierarchical fusion) | 2025, arXiv 2509.02837 | method | Two-stage: within-source RRF, then z-score-standardized cross-source merge — the clean pattern for "fuse T0 list with public list" |
| **Permission-aware / ACL-filtered retrieval (unknown-unknown — the prior draft treats T0 as one monolithic egress-binary)** | **2026, arXiv 2604.08304 (RAG security taxonomy); Milvus/Weaviate metadata-filter docs (primary)** | method + OSS engine feature | A real internal DB is **not** one blob with a single egress bit: it has per-document ACLs, tenant/department scope, classification labels. The 2026 enterprise pattern is to sync source-system ACLs into vector metadata and **filter inside the ANN search** (e.g. `tenant_id == "telus" && array_contains(allowed_roles, role)`) at retrieval time — pre/post-filter, ABAC over chunks. POLARIS must carry a per-T0-row ACL/classification and filter to the requesting principal **before** the row enters a basket, not just at the generator egress |
| **Structured / text-to-SQL retrieval (unknown-unknown — the prior draft assumes T0 is a vector store only)** | **2026, arXiv 2602.21480 ("Text-to-Big SQL", Spider 2.0 lineage)** | method (benchmark CC BY 4.0) | A massive Telus internal DB is most likely **relational/tabular**, not a pile of documents. A vector store only covers unstructured text; structured facts (a metrics table, a claims ledger) need a text-to-SQL / structured-query lane that returns **cell-level provenance** (table+row+column) as the citable span. This is a second T0 retrieval modality the design must name, not fold into "private vector store" |
| **MCP (Model Context Protocol) as the connector standard (is-anything-newer-than-bespoke?)** | **open standard, Anthropic Nov-2024 → Linux Foundation "Agentic AI Foundation" Dec-2025; MCP Toolbox for Databases (OSS, self-hostable on-prem; AlloyDB/Postgres/MySQL/SQL-Server)** | open standard, self-hostable | The 2025/2026 answer to "connect an internal source" is an MCP server, not a one-off adapter. Self-hostable on Telus infra (the index never egresses). Use MCP as the connector **interface** for the T0 retriever (and the structured-SQL lane); keep the sovereign retriever logic behind it. Began 2024 but the open-governance + self-hosted DB-connector maturity is 2025/2026 — declared incumbent-standard floor |
| Cohere North / Glean / Vectara | 2025-2026, commercial | **non-sovereign / closed** | Turnkey enterprise RAG; named only to reject for the sovereign clinical pipeline (and Cohere is a Telus-adjacent vendor) |
| Exa / Tavily | — | **BANNED** | Telus competitors' AI-search tools — never recommend (mandate) |

**Proposed design (concrete):**

1. **Connector = a sovereign private retriever adapter**, parallel to the existing discovery adapters
   (`discovery/source_adapter_registry.py`). It queries a self-hosted private vector store (pgvector default;
   Weaviate if hybrid-in-engine is preferred) embedded with **the same Qwen3-Embedding-8B** as public retrieval —
   one embedder both sides so the vector spaces align for fusion. The connector lives entirely inside Telus
   sovereign infra; it never egresses the private index.
   - **Two T0 modalities, not one (unknown-unknown the prior draft missed).** A massive internal DB is rarely
     just unstructured text. Wire a **vector lane** (above) AND a **structured / text-to-SQL lane** (per
     arXiv 2602.21480 "Text-to-Big SQL") for relational/tabular T0, returning **cell-level provenance**
     (table+row+column) as the citable span so the faithfulness gate still has a verbatim anchor. Folding a
     relational DB into "private vector store" silently drops every structured fact.
   - **Expose the connector behind MCP, not a one-off shim.** Implement the T0 retriever (both lanes) as a
     self-hosted **MCP server** on Telus infra (open standard, Linux-Foundation-governed since Dec-2025;
     MCP Toolbox for Databases is the OSS Postgres/SQL reference). The sovereign retriever logic stays behind
     the MCP interface; the index never egresses.
   - **ACL-aware retrieval BEFORE the basket, not just egress-after (unknown-unknown).** Every T0 row carries an
     ACL / classification / tenant-scope synced from the source system into vector metadata. Filter inside the
     ANN search to the requesting principal (ABAC: `tenant`, `roles`, `classification`) **before** a row enters a
     basket — the §2 egress gate alone is too coarse, because it only stops external leakage, not cross-principal
     leakage *inside* the sovereign deployment (arXiv 2604.08304 RAG-security taxonomy). Permission filtering is a
     pre-retrieval weight-of-zero for unauthorized rows, never a relaxation of the faithfulness gate.
2. **A new top tier T0** in `tier_classifier.py` above T1, with the heaviest `authority_score`. Per §-1.3, T0 is
   a **WEIGHT, not a FILTER**: it does NOT hard-suppress public corroboration. T0 + public agreement = the
   strongest basket; T0-alone = a single-source basket, flagged as such (single-source verification is the
   known blind spot, §-1.3 basket faithfulness).
3. **Privileged fusion = WRRF / HF-RAG.** Run private and public retrieval as two ranked lists; fuse with
   source-priority weighting (T0 list gets the trust weight) into one unified ranking, then consolidate
   same-claim sources into baskets. This is a *weight on the rank*, not a drop of public sources.
4. **Egress-conditional citation (the §2 hinge).** On the **sovereign GLM-5.2 deployment**, T0 rows are full
   citable evidence at heaviest weight, passing the unchanged faithfulness engine. On **any external-generator
   path**, T0 is routed through `filter_for_external_egress` exactly like a non-`PUBLIC_SYNTHETIC` upload — its
   text is withheld from the generator payload; at most a non-egressing corroboration count is surfaced. The same
   one gate (`sovereignty/router.py`) enforces both — no parallel policy.
5. **Faithfulness path:** T0 is privileged, **not** pre-verified. Every T0-cited claim still passes
   `strict_verify` / NLI / 4-role / provenance against the T0 span. Heaviest weight ≠ bypass the gate.

**Provisional pick / design to beat:** pgvector (HNSW) private store + Qwen3-Embedding-8B both sides + a new T0
tier + WRRF source-priority fusion + egress-conditional citation through the existing sovereignty router. The
bake-off scores it on whether T0 hits get cited at top weight on the sovereign path AND are correctly withheld on
the external path (a fail-loud sovereignty assertion), plus basket strength (T0+public vs T0-alone).

### Job 4 — Plan handoff to query-gen (survey — already healthy)

**Axis:** plan quality — does intake hand query-gen a frame good enough to drive wide, faithful retrieval.

**Current floor:** the strongest of the four. FS-Researcher (`fs_researcher_query_gen.py`, arXiv 2602.01566) is
already wired (flag `PG_QGEN_FS_RESEARCHER`) and won the recency-completion query-gen bake-off (I-recency-001
#1296). Its TOC/todo-queue + 6-item self-review checklist is exactly the adaptive-coverage loop that turns an
intent frame into a wide query set, and every query still flows through the unchanged `run_live_retrieval`.

**Proposed design:** intake's deliverable to FS-Researcher is the distilled `IntentFrame` from Job 1 (questions +
must-cover + domain) **plus** the attachment/T0 seed evidence digest from Jobs 2-3. FS-Researcher's checklist
("an aspect with only 1-2 weak sources?") then naturally drives queries to fill gaps the seed evidence does not
cover. No new build here — only the handoff contract (frame + seed digest → `plan_fs_researcher_queries`).

**Provisional pick / design to beat:** keep FS-Researcher; extend its input contract to accept the intent frame +
seed-evidence digest. The bake-off measures plan quality (coverage of must-cover points) with vs without the
seed-evidence digest in the handoff.

---

## 4. The axis + gold-set sketch (for the isolation bake-off)

This doc feeds the isolation bake-off series (sibling to I-cred-001). The scope/intake section is scored on a
held isolation harness with FIXED downstream (same retrieval + composition + render), varying only intake.

**Axes (one composite per job):**
- **A1 intent-extraction correctness** — on a gold-set of confusing multi-part prompts, does intake recover the
  right question(s), in/out scope, domain, must-cover, output shape. Metric: per-element match vs a human/Codex
  gold frame (NOT word counts — §-1.1 bans metadata proxies).
- **A2 attachment coverage** — fraction of a known upload corpus's facts that become correctly-cited,
  faithfulness-passing evidence (tables and scans included). **Also asserts:** PII/PHI in the upload is redacted
  before embed/generator (no identifier leaks to the public path), and a planted indirect-injection payload in an
  upload is neutralized/flagged, never executed.
- **A3 T0 privileged integration** — (sovereign path) T0 hits cited at top weight + faithfulness-passing;
  (external path) T0 correctly withheld (fail-loud sovereignty assertion); basket strength T0+public vs T0-alone.
  **Also asserts:** structured/relational T0 returns cell-level provenance, and an ACL-scoped row is NOT retrieved
  for an unauthorized principal (cross-principal-leakage assertion inside the sovereign deployment).
- **A4 plan quality** — coverage of gold must-cover points by the handed-off plan, with vs without seed digest.

**Gold-set sketch:**
- **Prompt-understanding gold (A1):** ~20 prompts across domains (clinical PICO, economics, policy, tech, plus
  deliberately confusing multi-part / contradictory / under-specified ones), each with a human/Codex gold
  `IntentFrame` (questions, in/out scope, domain, must-cover, clarification_needed). Includes the
  over-refusal trap (legitimate research that the current `uncertain → out_of_scope` wrongly rejects).
- **Attachment gold (A2):** a fixture upload corpus — born-digital PDFs, a table-heavy xlsx/PDF, a scanned image,
  a docx — with a gold list of extractable facts + their verbatim spans, to score extraction + citation.
- **T0 gold (A3):** a synthetic "private DB" fixture (clearly-labelled non-real, sovereignty-classified) with
  claims that (i) only T0 covers, (ii) T0 + public both cover. Asserts top-weight citation on the sovereign
  path and egress-block on the external path.
- **Plan-handoff gold (A4):** the A1 frames → run FS-Researcher → score must-cover coverage.

**Banned metrics (per §-1.1):** unique-source counts, citation counts, word counts, string-presence PASS/FAIL.
Scoring is per-element / per-claim against the gold frame, line-by-line.

---

## 5. OSS-vs-banned, honest

| Use | Recommended (sovereign, self-hostable) | Rejected / banned |
|---|---|---|
| Intent decomposition | GLM-5.2 (sovereign backbone) running RQ-RAG / intent-rewrite / IntentRL-pattern scaffolds; AlpaPICO LoRA for clinical | GPT-4o PICO method (model closed; sovereignty) — use the *method*, not the model. IntentRL (2602.03468) = pattern only, no confirmed OSS repo |
| PII/PHI redaction at intake | **Presidio (MIT) + MedicalNER/GLiNER for clinical** | John Snow Labs Healthcare-NLP (not OSS — named to set the bar only) |
| Upload injection screen | Reuse §9.1.7 NFKD/homoglyph neutralizer + instruction-pattern flag on extracted upload spans | trusting upload text as instructions (the indirect-injection hole) |
| Attachment extraction | **PaddleOCR-VL-1.6 (Apache-2.0, #1 OmniDocBench v1.6 @96.33, ~0.9-1.0B — the frontier crown AND sovereign-light default); Docling (MIT, deterministic default); MinerU2.5-Pro (Apache-based, 95.75 — larger alternate); dots.ocr (MIT) / DeepSeek-OCR-2 (Apache-2.0) alternates** | **LlamaParse (cloud, non-sovereign)** |
| Embedder (both sides) | **Qwen3-Embedding-8B (Apache-2.0)** — already decided I-arch-009 | all-MiniLM (current floor; misaligned vector space, replace) |
| Private vector store | pgvector (default) / Weaviate / Milvus — all self-hostable | Pinecone (managed cloud) for the sovereign path |
| Structured T0 lane | text-to-SQL over the relational DB (Text-to-Big SQL pattern, 2602.21480), cell-level provenance | treating a relational DB as if it were vector-only (drops every structured fact) |
| T0 connector interface | self-hosted MCP server (Linux-Foundation open standard; MCP Toolbox for Databases OSS) | one-off bespoke shim with no standard contract |
| T0 access control | ACL/ABAC metadata-filter inside the ANN search, per-principal, pre-basket | egress-binary only (misses cross-principal leakage inside the sovereign deployment) |
| Privileged fusion | WRRF / HF-RAG (methods) | — |
| Enterprise RAG turnkey | — | **Cohere North / Glean / Vectara (closed / non-sovereign)** |
| Search/fetch plumbing (allowed) | Serper (raw SERP), Zyte (paywall bypass) — plumbing, not AI modules | **Exa, Tavily — BANNED (Telus competitors)** |
| Query-gen handoff | FS-Researcher (already wired) | IterResearch (lost the validated-judge re-bake-off) |

---

## 6. Recency check (frontier-tech mandate)

- **Frontier (2025/2026), primary-source verified:** **PaddleOCR-VL-1.6 (2026, arXiv 2606.03264 @ 2026-06-02;
  HF `PaddlePaddle/PaddleOCR-VL-1.6`, Apache-2.0 verified at source; #1 OmniDocBench v1.6 @96.33, ~0.9-1.0B,
  vLLM-supported)**, MinerU2.5-Pro (2026, arXiv 2604.04771, 95.75, Apache-based — now the larger alternate),
  PaddleOCR-VL-1.5 (2025-2026, Apache-2.0, 0.9B @94.93 — superseded by 1.6),
  dots.ocr / DeepSeek-OCR-2 (2025-2026), OmniDocBench **v1.6 (2026/04)**, Qwen3-Embedding-8B (2025, HF),
  FS-Researcher (2026, arXiv 2602.01566 — already the repo's pick), WRRF / HF-RAG fusion (2025-2026), intent-based
  query rewriting (2025, arXiv 2511.20419), **IntentRL proactive-intent pattern (2026, arXiv 2602.03468 — pattern
  only, OSS unconfirmed)**, **Presidio PII/PHI redaction (2026, MIT)**, **Text-to-Big SQL structured retrieval
  (2026, arXiv 2602.21480)**, **RAG indirect-injection + ACL-aware-retrieval security (2026, arXiv 2601.10923 /
  2604.08304)**.
- **Crowns DEMOTED this pass:** **MinerU2.5-Pro (2604.04771, 95.75) — last pass's #1 — is superseded by
  PaddleOCR-VL-1.6 (2606.03264, 96.33), the newer and higher-scoring frontier crown; MinerU2.5-Pro stays as the
  larger-model alternate.** PaddleOCR-VL-1.5 (94.93) is now the incumbent the 1.6 release builds on. (The older
  "MinerU 2.5 (2509.22186, AGPL-3.0)" remains demoted — the AGPL blocker was already resolved by MinerU2.5-Pro's
  Apache-based license.) "OmniDocBench CVPR-2025 v1.x" → maintained **v1.6 leaderboard**. The 2025
  clarification-question candidate is now an incumbent floor under the IntentRL framing.
- **Declared incumbent floors (used only as best-available):** AlpaPICO (2024, arXiv 2409.09704) and the 680k-PICO
  GenAI study (2024, PMC11473607) remain the best published PICO-extraction references (no 2025/2026 OSS successor
  found this pass — re-check before build). RQ-RAG (2024) and IntentRL (2026, OSS-unconfirmed) are pattern
  references, not pinned dependencies. Docling is mature/maintained, kept as the deterministic default. MCP
  (open standard, 2024 origin) is a declared incumbent-standard floor — its self-hosted DB-connector + open
  governance matured in 2025/2026.
- **Rejected / logged (LAW II):** IntentRL as a *deployable* candidate (no confirmable public repo+license — kept
  as pattern only); John Snow Labs Healthcare-NLP (not OSS — bar-setting only); LlamaParse, Pinecone, Cohere
  North / Glean / Vectara (non-sovereign / closed); Exa, Tavily (BANNED — Telus competitors).
- **Is anything newer now?** Re-verify the OmniDocBench leaderboard (the PaddleOCR-VL / MinerU lines move fast —
  PaddleOCR-VL-1.6 @96.33 was the top on v1.6 as of 2026-06, a month after MinerU2.5-Pro @95.75), the
  Qwen3-Embedding line, and a possible IntentRL public release at build time. The
  fusion (WRRF/HF-RAG), MCP, and ACL-filter methods are method/standard-level and stable.

---

## 7. The honest bottom line

- **Job 1 (prompt understanding):** real gap — the clinical-biased `uncertain → out_of_scope` dead-end wrongly
  rejects legitimate non-clinical research and never decomposes a confusing prompt. Fix = intake-time LLM
  `IntentFrame` + domain-branched frame + clarification-before-run, advisory in front of the deterministic gate.
- **Job 2 (attachments):** working floor, surgical upgrades — a PaddleOCR-VL-1.6 layout lane (Apache-2.0, the #1
  OmniDocBench-v1.6 crown @96.33; Docling stays the deterministic default; MinerU2.5-Pro the larger alternate),
  re-embed on Qwen3, real per-attachment tiering instead of hardcoded
  T2, **plus an upload PII/PHI redaction (Job 1) and indirect-injection screen** before the faithfulness gate.
- **Job 3 (Telus T0):** the headline build, gated on one operator confirmation (Telus is on-prem self-hosted).
  T0 = a new top WEIGHT tier + private pgvector store on the shared embedder + **a structured/text-to-SQL lane
  with cell-level provenance** + **an MCP connector interface** + **per-principal ACL/ABAC pre-retrieval
  filtering** + WRRF fusion + egress-conditional citation through the existing sovereignty router. Privileged,
  never unverified — still passes the frozen faithfulness gate.
- **Job 4 (handoff):** healthy — keep FS-Researcher, extend its input to the intent frame + seed digest.

The §-1.3 DNA holds across all four: **weight, don't filter; consolidate into baskets; faithfulness is the only
hard gate.** T0 makes baskets stronger, never relaxes the gate.

---

## 8. Completeness note (independent critic pass — 2026-06-24)

An independent completeness + unknown-unknowns critic adversarially fresh-searched every job area for missed
2025/2026 OSS candidates, dated crowns, and questions the prior draft never asked. All additions are
primary-source verified per LAW II.

**Frontier additions (verified, recommended):**
- **OCR/parser crown refresh (Job 2):** crowned **PaddleOCR-VL-1.6** (arXiv 2606.03264 @ 2026-06-02; HF
  `PaddlePaddle/PaddleOCR-VL-1.6`, license field `apache-2.0` verified at source; **new #1 on OmniDocBench v1.6
  @96.33**, ~0.9-1.0B, vLLM-supported) — the frontier extractor AND the sovereign-light default in one. Demoted
  **MinerU2.5-Pro** (arXiv 2604.04771, 95.75, Apache-based — last pass's #1, now the larger alternate) and
  **PaddleOCR-VL-1.5** (Apache-2.0, 0.9B @94.93 — the incumbent 1.6 builds on); **dots.ocr** (MIT) /
  **DeepSeek-OCR-2** (Apache-2.0) alternates; benchmark stays **OmniDocBench v1.6 (2026/04)**.
- **Presidio PII/PHI redaction at intake (Job 1):** MIT, v2.2.362 (Mar-2026) with MedicalNER/GLiNER — closes the
  privacy gate the §2 hinge implied but never specified.
- **MCP connector standard + Text-to-Big SQL structured lane + ACL-aware retrieval (Job 3):** the T0 design now
  names a structured/relational modality with cell-level provenance (arXiv 2602.21480), an MCP server interface
  (Linux-Foundation open standard), and per-principal ACL/ABAC metadata-filtering inside the ANN search
  (arXiv 2604.08304).

**Unknown-unknowns surfaced (questions the prior draft never asked):**
1. **Does intake detect & redact PII/PHI before embed/generator?** It didn't — added as a Job 1 design point.
2. **Are uploaded documents screened for indirect prompt injection?** §9.1.7 covered web evidence only; uploads
   are an equally hostile channel (white-text/HTML-comment payloads, arXiv 2601.10923) — added to Job 2.
3. **Is the Telus internal DB structured (SQL/tabular), not just a vector store?** Almost certainly — a vector-only
   T0 design silently drops every structured fact. Added a text-to-SQL lane to Job 3.
4. **Does T0 have per-document ACLs / cross-principal isolation inside the sovereign deployment?** The egress-binary
   gate is too coarse — added ACL/ABAC pre-retrieval filtering to Job 3.
5. **Is the connector a standard (MCP) or a bespoke shim?** The frontier answer is MCP — added to Job 3.

**Demoted dated crowns:** MinerU2.5-Pro (2604.04771, 95.75) → **PaddleOCR-VL-1.6 (2606.03264, 96.33)** as the
new #1 (MinerU2.5-Pro kept as the larger alternate); PaddleOCR-VL-1.5 (94.93) → incumbent the 1.6 builds on;
MinerU 2.5 (2509.22186, AGPL) → MinerU2.5-Pro (2604.04771, Apache-based — already resolved last pass);
OmniDocBench CVPR-2025 v1.x → v1.6; the 2025 clarification-question candidate → incumbent floor under the
IntentRL (2602.03468) proactive-intent framing.

**Rejected / logged (LAW II):** IntentRL as a *deployable* candidate (no confirmable public repo+license — kept as
pattern/method only); John Snow Labs Healthcare-NLP (not OSS — bar-setting reference only); LlamaParse, Pinecone,
Cohere North / Glean / Vectara (non-sovereign / closed); Exa, Tavily (BANNED — Telus competitors). No pre-2024
entry was admitted except declared incumbent floors (AlpaPICO 2024, 680k-PICO 2024, RQ-RAG 2024, MCP-origin 2024).
