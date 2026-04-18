---
verdict: READY
blocker_count: 0
medium_count: 0
rationale: |
  The round-4 Unicode hardening is present and coherent at `src/polaris_graph/generator/provenance_generator.py:215-230`: `_build_normalized_view()` uses `unicodedata.normalize("NFKD", ch)` and drops `Cf`, `Mn`, and `Mc`, and my direct repros for both `<<<\u0115nd_evidence>>>` and `<<<e\u0306nd_evidence>>>` now redact. The earlier invariants remain closed in code: `MIN_CONTENT_WORD_OVERLAP` still defaults to 2 at `src/polaris_graph/generator/provenance_generator.py:520-522`, corpus approval still aborts cleanly on `if not approved:` at `scripts/run_honest_sweep_r3.py:557-605`, zero-verified output still emits a pipeline-verdict artifact via `filter_verified_sections()` / `build_no_verified_sections_abort_body()` at `scripts/run_honest_sweep_r3.py:90-116,676-705`, and cost imputation still backstops missing `usage.cost` at `src/polaris_graph/llm/openrouter_client.py:111-143,1320-1356`.
  Round-5 probes did not surface a new silent-failure input: `resolve_provenance_to_citations()` keeps a shared bibliography map at `src/polaris_graph/generator/provenance_generator.py:796-810`, `family_from_model()` recognizes both `deepseek-ai/...` and `deepseek/...` as the same family at `src/polaris_graph/llm/openrouter_client.py:239-257`, preprint URLs remain intentionally T4 by domain rule at `src/polaris_graph/retrieval/tier_classifier.py:328-332,700-706`, and the abort artifact writer was byte-identical across separate Python processes. I also stress-ran `verify_sentence_provenance()` in a thread pool without observing shared-state corruption, and the normalized-view index projection stayed correct on NFKD expansion cases including Hangul syllables and compatibility decompositions.
---

## Result

No new blockers or medium findings in `c2570b2`.

## Probes run

- Confirmed the requested round-4 reproducers redact:
  - `sanitize_evidence_text("<<<\u0115nd_evidence>>>")`
  - `sanitize_evidence_text("<<<e\u0306nd_evidence>>>")`
- Checked NFKD/index behavior on Hangul syllables, stacked combining marks, CJK compatibility forms, and ZWJ emoji clusters.
- Stress-ran `verify_sentence_provenance()` in a `ThreadPoolExecutor` across 2000 calls; all results were stable and there is no mutable module-level verifier cache.
- Verified citation numbering stays shared across sections: the same `ev_001` resolves to `[1]` in both sentences, not `[1]` and `[2]`.
- Verified abort-artifact determinism across separate Python processes by comparing SHA-256 hashes.
- Probed classifier/model-family edge cases:
  - `family_from_model("deepseek-ai/DeepSeek-V3.2-Exp") == "deepseek"`
  - `family_from_model("deepseek/deepseek-v3.2-exp") == "deepseek"`
  - bioRxiv URL remains T4 from the preprint-domain rule, which is consistent with URL-only classification.

## Audit notes

- `MIN_CONTENT_WORD_OVERLAP` is resolved once at module import; I did not find a call-time env-var read path.
- `_CONFUSABLE_ASCII_MAP` and `_INVISIBLE_CHARS_RE` contain some entries/ranges not individually exercised by tests, but I did not find a resulting false-negative or mutation path in the current delimiter-matching architecture.
