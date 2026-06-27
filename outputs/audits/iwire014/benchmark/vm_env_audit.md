# I-wire-014 — VM Environment Audit + Install Report

VM: ssh2.vast.ai:37450 (root) — 2x NVIDIA RTX 3090 Ti (24564 MiB each), torch 2.12.1+cu130, CUDA available, 2 GPUs.
Conda python/pip: /opt/conda/bin/python, /opt/conda/bin/pip (Python 3.11).
Repo: /root/polaris (PYTHONPATH=/root/polaris). Run artifacts: /root/polaris/outputs/iwire014_replay3/.

## Target-library status (the 10 requested)

| lib (requested name) | status before | version | action |
|---|---|---|---|
| trafilatura | INSTALLED | 2.1.0 | none |
| resiliparse | INSTALLED | 1.0.8 | none |
| jusText (justext) | INSTALLED | 3.0.2 | none |
| justext | INSTALLED | 3.0.2 | none (same package as jusText) |
| datasketch | INSTALLED | 1.10.0 | none |
| simhash | MISSING | -> 2.1.2 | pip installed |
| scikit-learn (sklearn) | INSTALLED | 1.9.0 | none |
| sentence-transformers | INSTALLED | 5.3.0 | none |
| rapidfuzz | MISSING | -> 3.14.5 | pip installed |
| numpy | INSTALLED | 2.4.6 | none |

Note: `jusText` and `justext` are the same PyPI package (`justext` 3.0.2) — both resolve to the one install.

## Installed this session (open-weight / self-hostable, small CPU libs, one at a time)

- `rapidfuzz==3.14.5` — `/opt/conda/bin/pip install rapidfuzz`. Verified `import rapidfuzz` OK.
- `simhash==2.1.2` — `/opt/conda/bin/pip install simhash`. Verified `import simhash` OK.

Both are small, pure/CPU-friendly, open-source. No GPU work, no large model downloads.

## Open-weight embedder + NLI model availability (cached on VM)

HF cache `~/.cache/huggingface` is 128 GB and richly populated. Key models for an
extraction/dedup + faithfulness benchmark are present AND complete (config + full weights):

EMBEDDER (locked winner per memory = Qwen3-Embedding-8B):
- `Qwen/Qwen3-Embedding-8B` — 19 GB, complete (config.json, model.safetensors.index.json,
  model-0000{1..4}-of-00004.safetensors, tokenizer). The pipeline's locked embedder. CACHED.
- `sentence-transformers/all-MiniLM-L6-v2` — 88 MB, complete (legacy/baseline embedder). CACHED.
- Also cached: granite-embedding-english-r2, gte-modernbert-base, jina-embeddings-v5-text-small,
  llama-embed-nemotron-8b, QZhou-Embedding, potion-base-8M, MedTE.

NLI / faithfulness / entailment models:
- `cross-encoder/nli-deberta-v3-base` — 715 MB, complete. VERIFIED loads OFFLINE
  (HF_HUB_OFFLINE=1) with labels {0: contradiction, 1: entailment, 2: neutral}.
  This is the repo's contradiction-detection NLI (verifier.py:1570). READY.
- `lytang/MiniCheck-Flan-T5-Large` — 5.9 GB, complete (the repo's primary NLI weights,
  nli_verifier.py). Weights CACHED.
- `KRLabsOrg/lettucedect-large-modernbert-en-v1` (1.5 GB) + base variant — complete.
  `import lettucedetect` OK. CACHED + importable.
- Also cached: vectara/hallucination_evaluation_model, yaxili96/FactCG-DeBERTa-v3-Large,
  MiniCheck-Flan-T5-Large (the I-faith-001 candidate set).

Rerankers (bonus, all cached): Qwen3-Reranker-{0.6B,4B,8B}, bge-reranker-v2-m3,
gte-reranker-modernbert-base, ERank-4B, jina-reranker-v3, mxbai-rerank-base-v2,
nvidia llama-nemotron-rerank, zerank-1-small, zerank-2.

## Gap (NOT auto-installed — flagged)

- `minicheck` library: the repo's `nli_verifier.py` does `from minicheck.minicheck import MiniCheck`
  and the error message says `pip install minicheck`, BUT it is NOT on PyPI
  (`ERROR: No matching distribution found for minicheck`). It installs only from git
  (`pip install git+https://github.com/Liyan06/MiniCheck.git`), which is a git-source install
  pulling heavier deps — outside the "small CPU pip-install" scope and not done autonomously.
  The MiniCheck-Flan-T5-Large *weights* are cached, so the runtime wrapper is the only missing piece.
  IMPACT: the MiniCheck NLI leg specifically is not loadable until `minicheck` is git-installed.
  WORKAROUND already available: `cross-encoder/nli-deberta-v3-base` (verified offline-loadable via
  transformers) and `lettucedetect` (importable, weights cached) both provide a working NLI/entailment
  path without `minicheck`.

## Benchmark-readiness verdict

READY for a CPU-side extraction + dedup benchmark and an embedder/NLI faithfulness benchmark:
- All extraction libs (trafilatura, resiliparse, justext) present.
- All dedup libs present after install (datasketch, simhash, rapidfuzz, scikit-learn, numpy).
- sentence-transformers present; Qwen3-Embedding-8B embedder weights cached + complete; GPUs available.
- A working NLI model (nli-deberta-v3-base) verified offline-loadable; lettucedetect importable;
  MiniCheck weights cached (wrapper lib pending git-install if MiniCheck specifically is required).

One caveat to note before any NLI run that specifically needs MiniCheck: git-install `minicheck`
first, OR point the NLI leg at the already-loadable deberta/lettucedetect path.
