# I-ret-002 — published-benchmark precondition verification (2026-06-23)

Primary-source-verified (HF cards, GitHub trees, PyPI, arXiv). No full-stop failures; 3 wiring
refinements to fold into the build.

## Confirmations (the "reuse published" plan holds)
- **BRIGHT** (xlangai/BRIGHT, arXiv 2407.12883, CC-BY-4.0): turnkey. Official `pytrec_eval` nDCG@10 via
  `run.py`; gold in example rows (`gold_ids`); MUST honor `excluded_ids` + pair `gold_ids`↔`documents` /
  `gold_ids_long`↔`long_documents`. Wire POLARIS retriever by emitting `{qid:{docid:score}}`.
- **MTEB v2** (`mteb` 2.16.1, Apache-2.0): turnkey. `mteb.get_model(id)` + `mteb.evaluate`. Embedder and
  reranker are SEPARATE flows (reranker = two-stage via `task.convert_to_reranking`).
- **PyLate** (1.6.0): ColBERT load + MaxSim API confirmed; ~150M ModernBERT models fit on ≥8 GB GPU.
- **WebMainBench** (opendatalab, Apache-2.0): the official ROUGE-N scorer EXISTS
  (`TextRougeNgramMetric.calc_rouge_n_score`, N=5 jieba) — the GATE-0 reproduce-published-numbers anchor is
  NOT circular.

## 3 refinements to apply during build integration
1. **Extraction GATE-0 / gold (IMPORTANT):** the full 7,809-row "gold" is `convert_main_content` =
   html2text auto-serialization (biased — rewards extractors that mimic html2text), NOT human markdown.
   Only **545 rows** (`groundtruth_content`) are hand-calibrated HUMAN gold. → Use the **545 human-gold
   subset** as the true-gold scoring + GATE-0 anchor; treat the 7,809 set as a secondary cross-check only.
   Add dep `rouge_score` (not in requirements; scorer imports its private internals — pin it). N=5 jieba is
   stricter than ROUGE-1/2/L — don't confuse with the exported `ROUGEMetric` (that's ROUGE-L).
2. **Reranker + embedder Qwen3 wiring (CRITICAL):** Qwen3-Embedding-8B (query-only `Instruct:…\nQuery:`
   prefix) and Qwen3-Reranker-4B/8B (yes/no token-logit scoring, not a regression head) score GARBAGE
   through a bare `SentenceTransformer(id)`/`CrossEncoder(id)`. → MUST load via `mteb.get_model(id)`
   (pre-registered wrappers handle the prefix/logit). `gte-reranker-modernbert-base` is NOT registered but
   the generic `CrossEncoder` fallback is correct for it (plain regression, no prompt).
3. **Reason-ModernColBERT license (CONFIRMS brief):** CC-BY-NC-4.0 (non-commercial, from ReasonIR data) —
   keep it a yardstick/ceiling-probe ONLY, never a sovereign deploy candidate. `GTE-ModernColBERT-v1` is
   Apache-2.0 and is the deploy candidate. The brief already frames it this way; verify the build kept the
   deploy-exclude.

## VRAM notes for the GPU VM
- Qwen3-Embedding-8B ≈ 24 GB+ (BF16); Qwen3-Reranker-4B ≈ 8 GB+; -8B ≈ 16 GB+; ColBERT ~150M ≤ 8 GB;
  MinerU-HTML 0.6B small. A single ≥48 GB GPU (A6000/A100) covers all model layers; multi-GPU for full
  concurrency. flash-attn-2 recommended not required.
