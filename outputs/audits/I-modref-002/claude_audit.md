# Claude architect review — I-modref-002 (#528): models.yaml legacy-stack documentation

Reviewer: Claude (architect pass, pre-Codex-diff-review)
Branch: `bot/I-modref-002-models-yaml-doc` @ `a38e2435`
Canonical diff: `.codex/I-modref-002/codex_diff.patch` — 1 file, +20 / -0.

## 1. What this delivers

#528 acceptance criterion 1 is an OR: reconcile `config/settings/models.yaml`
to V4 Pro/Gemma, **or** document it as intentionally distinct. Reconciling
would break the file's only LLM consumer `src/llm/gemini_client.py` (a
Gemini-specific client) — violating criterion 2 ("consumers unaffected").
This takes the documentation path.

## 2. The change

`config/settings/models.yaml` — 20 added comment lines, **0 key/value changes**:
- A SCOPE header block naming the consumers — `src/config/core.py`
  (`load_models()`), `src/llm/gemini_client.py`,
  `src/utils/atomic_decomposer.py` (`GeminiClient` fallback),
  `config/settings/extraction.yaml` — and stating that no code under
  `src/polaris_graph/` or `scripts/` imports them; pipeline A's V4 Pro
  generator + Gemma evaluator are configured in
  `src/polaris_graph/llm/openrouter_client.py` + env, not this file.
- A 2-line note on the `llm:` block pointing to the header.

## 3. Invariants held

- **Comment-only.** A YAML re-parse confirmed every
  `llm` / `embedding` / `cross_encoder` / `nli` / `minicheck` / `chunking`
  value is byte-identical to pre-change → `load_models()` and every
  consumer are provably unaffected (#528 criterion 2 satisfied by
  construction).
- No behavior change anywhere; no code touched.

## 4. Feasibility grounding (per CLAUDE.md §-1.2)

Grep evidence: `src/polaris_graph/**` + `scripts/**` import neither
`src.config.core` nor `src.llm.gemini_client` → models.yaml is genuinely
off pipeline-A's runtime path, exactly as #528 states. `models.yaml` was
last modified at the 2026-03-16 initial commit (legacy).

## 5. Residual risks

- None. A pure documentation edit; the only risk surface is YAML validity,
  verified by re-parse + key spot-checks.

Verdict: ready for Codex diff review.
