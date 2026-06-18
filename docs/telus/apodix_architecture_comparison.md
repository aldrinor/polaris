# Apodix vs Competitors — Architecture Internals (primary-sourced)

*Dated 2026-06-18. Built after operator flagged the prior architecture diagram as too generic ("everybody knows your mother is a woman"). Every competitor internal is from vendor docs / peer-reviewed papers (workflow wgtb9i36o, 5 agents); every Apodix internal is read line-by-line from committed code. arXiv 2508.06709 (Play Favorites) personally verified. Honesty rails: no fabricated competitor internal; Apodix maturity marked (runs-today / hardening / pilot); the differentiator is the COMBINATION, never "they don't verify."*

## The organizing thesis
In every competitor pipeline **the writer is the citer** — the generating model emits/attaches its own citation in the same pass — so there is **no point where an independent party adjudicates THIS claim against THE EXACT cited span.** Apodix inserts exactly that adjudication point.

## Competitor internals (real mechanism, named)

**OpenAI Deep Research** (o3-deep-research; internals partly undisclosed). Agentic browse loop — `web_search_call` (search/open_page/find_in_page); backend index undisclosed. Citation emitted inline by the model; API returns `annotations {url, title, start_index, end_index}` = **character offsets into the model's OWN output, not the source.** No verification component documented. No deterministic floor, no signed record. Empirical: 3.5% hallucinated URLs, 10.1% non-resolving (arXiv 2604.03173). Source: developers.openai.com Responses API docs.

**Gemini Deep Research / grounding.** Live Google Search index + `url_context` (agentic browse); **no embedding/vector DB on this path** (Vertex AI Search is the separate hybrid-vector surface). Model emits `groundingChunkIndices` inline — proven generation-time by the documented bug where indices point at an **empty** `groundingChunks` list. Serving layer only records char offsets (`startIndex`/`endIndex`). `confidenceScores` are the model's own self-report and are **empty in Gemini 2.5+**. The **Check-Grounding API** (Vertex AI) is a real per-claim support score — but a **separate opt-in API call, algorithm undisclosed, not signed/re-executable.** Source: ai.google.dev grounding docs + Google dev-forum thread.

**Perplexity Sonar Deep Research.** Hybrid BM25 + **pplx-embed (Qwen3 bi-encoder, cosine)** → cross-encoder rerank over a 200B-URL index; sub-document span extraction. Ranked spans + citation markers injected into the prompt **before** generation; LLM writes inline `[n]` as it decodes → `[n]` means "a topically-relevant passage from source n was in context," **not** "source n entails this claim." Only deterministic gate is a retrieval-quality threshold (restarts search). No claim-vs-source check, no signed record. Empirical: 37% citation hallucination (CJR Mar 2025). Source: Perplexity research/eng posts + pplx-embed HF card.

**Generic RAG-with-citation** (academic baseline). Bi-encoder cosine (DPR / Sentence-BERT) → FAISS **HNSW** top-k → optional cross-encoder rerank → top-k chunks into context → LLM emits citation markers in the same pass. Anthropic Citations API validates the cited **char-range EXISTS — explicitly not entailment** ("valid pointers" ≠ "entails the claim"). Measured: only **51.5%** of generated sentences fully supported by their citations (Liu et al. 2304.09848); up to **57%** of citations post-rationalised (Gao & Chen 2412.18004). Sources: Karpukhin (DPR, 2004.04906), Reimers (SBERT, D19-1410), Malkov (HNSW, 1603.09320), Anthropic Citations API.

## The closest verifiers (they DO verify — and the precise axis each misses)

- **Primer RAG-V** — a GENUINE independent post-hoc check: decomposes into atomic claims; a verifier LLM gets (question, answer, claim, cited source). BUT checks the claim vs the cited **source document, not the exact span**; verifier **family undocumented** (may be same as generator); no deterministic floor; no signed record. Source: primer.ai RAG-V pages.
- **Vectara HHEM** — a dedicated **NLI model** (HHEM-1.0 = DeBERTa-v3 cross-encoder; HHEM-2.1 = flan-T5-base), a real entailment check, **separate model family** from the Mockingbird generator. BUT scores the **whole (source, response) pair = response-level**; per-claim only if the caller decomposes first → a hallucinated sentence can be masked by supported ones. Neural score, no deterministic floor, no signed record. Source: HHEM model cards.
- **Contextual AI GLM + Groundedness Reward Model** — a separate post-hoc reward model that decomposes into atomic claims (per-claim). BUT the GRM is **Llama-family — same lineage as the GLM writer** (writer ≈ checker → correlated failure modes); no deterministic floor; no signed record. Source: Contextual blog + Meta Llama case study.

## The six discriminating properties (the matrix)

| Property | Frontier DR | Generic RAG | Primer RAG-V | Vectara HHEM | Contextual | **Apodix** |
|---|---|---|---|---|---|---|
| Independent post-hoc check? | No (writer=citer) | No | **Yes** (verifier LLM) | **Yes** (NLI model) | **Yes** (reward model) | **Yes** (cross-family judge + gate) |
| Per-claim, not whole-response? | — | — | Per-claim | Response-level* | Per-claim | **Per-sentence** |
| Tests the EXACT cited span? | No | No (range exists only) | vs whole document | vs whole response | vs retrieved set | **the EXACT span `[#ev:src:s–e]`** |
| Deterministic floor under the judge? | No | char-range only | No (LLM) | No (neural) | No (neural) | **Yes (span-bounds + numeric-subset + ≥2 overlap)** |
| Writer ≠ checker (different family)? | No | No | Undocumented | **Yes** | No (both Llama) | **Yes — enforced at construction** (Play Favorites 2508.06709) |
| Signed, re-executable record? | No | No | No | No | No | **Pilot — GPG manifest, `gpg --verify`** |

\* HHEM scores the whole (source,response) pair; per-claim only if the caller decomposes first.

**Why the others cannot just add it:** closing even one gap is an architectural change, not a feature toggle — a SECOND different-family model, a deterministic gate fronting it, holding the EXACT cited span as a drop-condition, and a signed re-executable record. Apodix was built around that adjudication point; the rest were built to retrieve-and-generate.

## Apodix internals (read from committed code — honest maturity)

`strict_verify.py` — six ordered checks; any fail drops the sentence with a precise reason code:
- (a) ≥1 well-formed provenance token `[#ev:<source_id>:<start>-<end>]` (regex `\[#ev:([A-Za-z0-9_][A-Za-z0-9_\-]{0,99}):(\d+)-(\d+)\]`) else `no_provenance_token`
- (b) token source_id ∈ evidence pool else `invalid_token`
- (c) span bounds 0 ≤ start ≤ end ≤ len else `span_out_of_range`
- (d) every decimal in sentence ⊆ decimals in cited span else `numeric_mismatch`
- (e) ≥2 shared content words (sentence ∩ span, stopwords removed, default `PG_PROVENANCE_MIN_CONTENT_OVERLAP=2`) else `overlap_too_low`
- (f) cross-family NLI entailment: verdict NEUTRAL/CONTRADICTED → drop `entailment_failed`; `judge_error` → **FAIL CLOSED** (I-ready-002 P0). Mode default `enforce`.

`check_family_segregation()` (openrouter_client.py) — generator and checker MUST be different training lineages; raises `RuntimeError` at construction if violated; cites *Play Favorites* (arXiv 2508.06709, which measures LLM judges' family-bias). Family derived from OpenRouter publisher-slug prefix.

`release_policy.py` (D8) — verdicts VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE; FABRICATED → abort (zero-tolerance one-way latch); UNSUPPORTED/UNREACHABLE → one rewrite, then gate on coverage; refused/residual claims emitted as **visible Gaps, never silent drops**.

`gpg_signer.py` (audit_bundle, slice 004) — detached ASCII-armored GPG signature over the manifest YAML; external verifiers run `gpg --verify manifest.yaml.asc manifest.yaml`. Fail-loud per LAW II.

**Maturity boundary (per landscape §9):** checks (a–e) deterministic + D8 label/drop = run today. Check (f) cross-family entailment = enforce-by-default, fail-closed, **reliability hardening in progress** (current branch `bot/verify-entailment-speed-and-repair-loop`; tail #1267 moves judge_error→advisory). Signing = signer + conformance tests in-tree, **end-to-end live-render wiring is the pilot piece, not GA.**

## Deck mapping
Slides 13 (Competitor Anatomy) → 14 (Apodix Architecture — The Adjudication Point) → 15 (Six-Way Comparison). Replaced the generic "hop-by-hop" slide + the "standout 4-leg" slide (both skipped).
