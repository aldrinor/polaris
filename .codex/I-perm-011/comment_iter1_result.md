## iter-1 result: STARVATION FIX WORKED (544 vs 53) — exposed an outline-truncation downstream

The per-subquery relevance-floor fix (a030b024) **worked on the source side**: drb_76 re-run selected
**evidence_selected=544 of 599** rows to the generator vs run-1's **53 of 597**. The on-topic T1 papers
the whole-question floor was dropping now survive. Source starvation FIXED (10x).

**New downstream error (the win surfaced it):** `status=error_unexpected` —
`ReasoningFirstTruncationError` at the OUTLINE call (`_call_outline`, multi_section_generator.py:1032).
deepseek-v4-pro hit `finish_reason=length` (64100-char candidate, 16384 out / 16384 reasoning tokens)
when fed the now-larger 544-row pool; the fail-loud guard (I-bug-089/FX-01) correctly REFUSED to promote
the truncated scratchpad as verified prose. **Faithfulness protected; no report produced.**

**iter-2:** the outline planning call is flooded by the larger pool. Fix = feed the OUTLINE a bounded
evidence digest and/or raise its max_tokens (per-section generation is NOT the problem — it already caps
at PG_MAX_EV_PER_SECTION=40; only the outline sees the full pool). Diagnose+fix flag-safe, Codex-gated,
redeploy, re-run drb_76. Faithfulness gates never relaxed.
