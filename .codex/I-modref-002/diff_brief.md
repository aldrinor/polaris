# Codex DIFF review — I-modref-002 / GH #528: align stale model default in config/settings/models.yaml

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. What you are reviewing

A **DIFF review** — verify the implemented diff is correct against the Codex-APPROVE'd brief (`.codex/I-modref-002/brief.md`, brief APPROVE iter 1).

Canonical diff: `.codex/I-modref-002/codex_diff.patch` (1 file, +20 / -0; the last line is a `# canonical-diff-sha256:` trailer, not part of the diff). Read it and `config/settings/models.yaml` on disk (branch `bot/I-modref-002-models-yaml-doc`). Claude's architect review: `outputs/audits/I-modref-002/claude_audit.md`.

## 1. The change

`config/settings/models.yaml` gains 20 comment-only lines (0 key/value changes):
- A SCOPE header block: the file configures the legacy Gemini agent stack only (consumers: `src/config/core.py` `load_models()`, `src/llm/gemini_client.py`, `src/utils/atomic_decomposer.py` `GeminiClient` fallback, `config/settings/extraction.yaml`); it is intentionally distinct from pipeline A, whose V4 Pro generator + Gemma evaluator are configured in `src/polaris_graph/llm/openrouter_client.py` + env.
- A 2-line note on the `llm:` block pointing to the header.

This implements #528 acceptance criterion 1's OR-clause path 2 ("documented as intentionally distinct"). Reconciling the Gemini values to V4 Pro/Gemma would break `gemini_client.py` and violate criterion 2.

## 2. Verify

1. The diff is genuinely comment-only — no YAML key or value changed. (A re-parse confirmed every `llm`/`embedding`/`cross_encoder`/`nli`/`minicheck`/`chunking` value byte-identical.)
2. The SCOPE documentation is factually accurate: pipeline A (`src/polaris_graph/`) + `scripts/` do not import `src.config.core` / `src.llm.gemini_client`; the consumer list is complete (incl. `atomic_decomposer.py`, the brief-iter-1 P2).
3. Criterion 2 ("any consumer of models.yaml verified unaffected") holds — comment-only ⇒ unaffected by construction.
4. The chosen path (document, not reconcile) is correct given reconcile breaks `gemini_client.py`.

## 3. Files I have ALSO checked and they're clean

- `src/config/core.py` — `load_models()` parses YAML structurally; YAML comments do not alter parsed values.
- `src/llm/gemini_client.py`, `src/utils/atomic_decomposer.py`, `config/settings/extraction.yaml` — consume models settings; no key/value changed.
- `src/polaris_graph/**`, `scripts/**` — not consumers of models.yaml.

## 4. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
