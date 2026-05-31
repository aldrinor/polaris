# Codex gate — full-power POLARIS architecture (beat-frontier): grounded, honest, buildable?

ADVERSARIAL §-1.1 auditor. A workflow produced the full-power end-to-end architecture doc at
docs/full_power_polaris_architecture_2026_05_31.md (READ IT FULLY). It is the design to beat Gemini 3.1 Pro DR +
ChatGPT 5.5 Pro DR, cross-checked against the stored competitor outputs. Sub-agents may have leaked the forbidden
advisor tool — re-verify yourself. This doc will be COMMITTED to docs/ on APPROVE, so gate it hard. Output YAML FIRST. iter 1.

```yaml
verdict: APPROVE | REQUEST_CHANGES
fabricated_competitor_citations: [...]   # spot-check: do the cited spans actually exist in the compare_*.md/.txt files?
wrong_shipped_line_refs: [...]           # are the code line refs (query_decomposer.py:33-36, :2266, domain_backends.py:452, role_pipeline.py, etc.) real?
overstated_beats: [...]                  # any BEAT that is really parity, or a counter that wouldn't actually work?
safety_holes: [...]                      # esp. the guarded citation-repair (Stage 8) + fail-closed Sentinel polarity
buildability_concerns: [...]             # is the ordered build list (§4) realistic + correctly sequenced?
honest_framing_ok: <true|false>          # is "4 BEAT / 5 parity / 2 deliberate-behind" honest, NOT "beat on all"?
the_one_correction: "<or none>"
honest_one_line: "<for the operator>"
```

## What to verify (the doc has 10 stages + frontier counter-map + per-parameter map + build list)
1. COMPETITOR CITATIONS — spot-check 4-5 of the frontier-counter-map rows against the actual files:
   - ChatGPT stacked footnotes 33-41 on one paragraph (compare_chatgpt_dr.txt:1067-1075)
   - ChatGPT opaque token turn31view0 (compare_chatgpt_q1.md:11)
   - Gemini 4,932-word q1 with zero citations (compare_gemini_q1.md)
   - Gemini whole-PDF superscript on "63%...M-value" (compare_gemini_dr.txt:57)
   - ChatGPT figure-read decimals 6.43/6.13/6.11 (compare_chatgpt_dr.txt:614-616)
   - ChatGPT fabrication-suspect "SURPASS-SWITCH reported in 2026" (compare_chatgpt_dr.txt:1089-1091)
   Are these REAL spans or invented? (A fabricated competitor-citation in a doc whose whole point is faithfulness
   would be fatal.)
2. SHIPPED LINE REFS — are query_decomposer.py:33-36/108-148 (string-split, no LLM/MeSH/PICO), run_honest_sweep_r3.py:
   1885-1891 (R6 4-query cap) + :2266 (MAX_EV_TO_GEN 20), domain_backends.py:452 (ctgov skipped) + :7, live_retriever.py:
   1573-1591 (fetch-cap truncation), evidence_selector.py:976, role_pipeline.py default-off real?
3. BEAT/PARITY HONESTY — are the 4 BEATs (faithfulness, auditability, contradiction, refusal) genuinely structural
   wins given frontier has NO claim→span binding, or is any overstated? Is "prose readability PARITY (real risk)"
   appropriately honest about the largest match-risk? Is length/memory correctly deliberate-behind?
4. SAFETY — Stage 8 guarded citation-repair (candidate-generator only, re-judge short span, fail-closed) + Sentinel
   UNGROUNDED=fail-closed-cannot-upgrade: is this the SAFE form, or any residual hole?
5. BUILDABILITY — is §4's ordered build list (cap-removal first, default-on 4-role gate, map-reduce, clinical
   backends) correctly sequenced + realistic on the OpenRouter open-weight lineup at ~$2.63/run?

## Your ruling
APPROVE iff: competitor citations real, shipped line-refs accurate, beats not overstated, citation-repair safe,
build list sound, framing honest (not "beat on all"). REQUEST_CHANGES with the specific fix otherwise. The single
most important correction. Honest one-liner for the operator.
