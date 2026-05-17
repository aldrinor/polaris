# Codex BRIEF review — I-modref-002 / GH #528: align stale model default in config/settings/models.yaml

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. What you are reviewing

A **BRIEF review** — verify the acceptance criteria + approach are correct and complete BEFORE the diff is written.

## 1. The issue (GH #528 / I-modref-002)

Carved from I-rdy-006 (#502) per the Codex-ratified pipeline-A scope boundary. `config/settings/models.yaml` carries a stale Gemini / model-default entry outside pipeline-A's runtime path.

**Acceptance criteria (verbatim):**
- models.yaml model entries reconciled to current operator-locked state (DeepSeek V4 Pro generator / Gemma 4 31B evaluator) **OR documented as intentionally distinct**.
- Any consumer of models.yaml verified unaffected.
- Codex brief + diff APPROVE.

## 2. Feasibility findings (grounded — read before approving)

- `config/settings/models.yaml` (last touched at the 2026-03-16 initial commit, never since) carries an `llm:` block: `provider: gemini`, tiers `simple: gemini-2.5-flash` / `important: gemini-3-pro-preview`, default `model: gemini-2.5-flash`, `fallback_model: gemini-2.5-pro`. Plus `embedding` / `cross_encoder` / `nli` / `minicheck` / `chunking` blocks (local HF models — not LLM-vendor models).
- **Consumers** (grep `models\.yaml|settings/models`): `src/config/core.py` (`load_models()` → Pydantic `Models`), `src/llm/gemini_client.py`, `config/settings/extraction.yaml`.
- **Pipeline A (`src/polaris_graph/`) and `scripts/` import NEITHER `src.config.core` NOR `src.llm.gemini_client`** — grep `from src\.config\.core|from src\.llm\.gemini_client` across `src/polaris_graph` + `scripts` returns zero. models.yaml's `llm:` block is consumed only by the legacy Gemini agent stack, exactly as the issue states ("outside pipeline-A's runtime path").
- Pipeline A's generator (DeepSeek V4 Pro) + evaluator are configured in `src/polaris_graph/llm/openrouter_client.py` (module constants + env), NOT via models.yaml.

## 3. Proposed approach — DOCUMENT as intentionally distinct (acceptance OR-clause #1, path 2)

Reconciling the `llm:` block to DeepSeek V4 Pro / Gemma would **break** its only consumer `src/llm/gemini_client.py` (a Gemini-specific client) — that violates acceptance criterion 2 ("any consumer verified unaffected"). The non-breaking, correct resolution is the acceptance criteria's explicit second option: **document the Gemini `llm:` block as intentionally distinct.**

**Diff (documentation-only, zero behavior change):**
- Prepend a clarifying header block to `config/settings/models.yaml` stating: the `llm:` block configures the **legacy Gemini agent stack** (`src/llm/gemini_client.py`, `src/agents/`, `src/config/core.py::load_models()`); it is **intentionally distinct** from POLARIS pipeline A (the honest-rebuild sweep), whose generator (DeepSeek V4 Pro) + evaluator (Gemma 4 31B) are configured in `src/polaris_graph/llm/openrouter_client.py` + env, NOT this file. Editing the Gemini entries here does NOT change pipeline-A behavior.
- Add a one-line in-section note on the `llm:` block pointing to that header.
- No YAML keys/values changed → `load_models()` / `gemini_client.py` byte-unaffected.

## 4. Acceptance criteria for this brief (verify correct + complete)

1. Approach correctly chooses "document as intentionally distinct" (acceptance OR-clause) over "reconcile" — because reconcile breaks `gemini_client.py` (criterion 2).
2. The documentation accurately states which code consumes models.yaml and which does not (pipeline A does not).
3. Diff is comment-only → consumers provably unaffected (criterion 2 satisfied by construction).
4. Codex diff review APPROVE.

## 5. Files I have ALSO checked and they're clean

- `src/config/core.py` — `load_models()` parses the YAML structurally; adding YAML comments does not change parsed values. Unaffected.
- `src/llm/gemini_client.py` — consumes the `llm:` block; comment-only edit leaves every key/value identical. Unaffected.
- `config/settings/extraction.yaml` — references models settings; no key/value change. Unaffected.
- `src/polaris_graph/**`, `scripts/**` — do not import `src.config.core` / `src.llm.gemini_client`; pipeline A is not a consumer.

## 6. Required output schema (§8.3.9)

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
