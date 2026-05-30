RULE NOW — emit the YAML verdict block FIRST. VERIFY each gap by READING the cited code (§-1.1 line-by-line, not a rubber-stamp). Do NOT trust the summary — check the code. NO SPEND.

HARD ITERATION CAP: 5. Iter 1 of 5. Front-load all findings. Reserve REFUTED for gaps the code contradicts.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
gap_verdicts:
  S0_no_query_decomposition: CONFIRMED | PARTIAL | REFUTED
  S1_no_fetch_time_rerank: CONFIRMED | PARTIAL | REFUTED
  S1_analyst_synthesis_unverified_unsanitized: CONFIRMED | PARTIAL | REFUTED
  S1_no_table_extraction: CONFIRMED | PARTIAL | REFUTED
build_order_correct: yes | no   # is "fetch-cap → query-decomposition(S0) → clinical backend → deepener → conflict → rest" right?
p0_corrections: [...]
notes: [...]
```

# Codex verification — top-tier gap hunt (#950, concern 7). VERIFY the load-bearing NEW gaps that a Claude Codex Workflow found beyond concerns 1-6. These drive the pre-Q1 build, so confirm or refute precisely by reading the code.

## Gaps to verify (read the files)
1. **S0 — no query decomposition on the live path.** The 5 golden benchmark questions are 40-70-word multi-clause paragraphs. Four (drb_75/76/78/90) ship WITHOUT a hand-authored `amplified` list, so the only content-bearing queries are the full paragraph (and `{paragraph} site:{anchor}`). VERIFY: `scripts/run_honest_sweep_r3.py:~1638` builds `_amplified_effective = list(q.get('amplified', [])) + _reg_queries + _trial_queries`; the no-amplified stubs at `~648-704`; `regulatory_expander.py:~133` prepends the WHOLE paragraph before `site:`; and the PICO decomposer at `src/polaris_graph/clinical_retrieval/query_planner.py:~167` (`plan_queries`) EXISTS but is NOT called from `run_live_retrieval`. Confirm a long multi-clause golden Q is fired essentially as ONE keyword query with no decomposition.
2. **S1 — no fetch-time relevance rerank.** Candidates are truncated by INSERTION ORDER, not relevance. VERIFY: `src/polaris_graph/retrieval/live_retriever.py:~1324` `candidates = candidates[:fetch_cap + _n_seed_injected]`; the prefetch embedding off-topic filter is DISABLED on the sweep (`live_retriever.py:~1173` default `enable_prefetch_filter=False`, and `run_honest_sweep_r3.py:~1664` passes `False`); downstream `evidence_selector.py:~37-40` ranks only by tier + lexical Jaccard over the already-truncated survivors. So early queries saturate the cap and later sub-queries' best hits are truncated pre-fetch.
3. **S1 — analyst-synthesis ships unverified AND un-sanitized.** The Analyst Synthesis layer (~70% of the shipped report) builds raw `<<<evidence:ev_X>>>` blocks with NO `sanitize_evidence_text` call and only `[#ev:...]`/`[N]` syntactic scrubs — no entailment check, no qualitative-negation screen. VERIFY: `src/polaris_graph/generator/analyst_synthesis.py:~285-301` (raw evidence blocks; grep `sanitize` in that file → zero) and `~252-266`/`~184-249` (only the two scrubs); appended to report at `run_honest_sweep_r3.py:~2637-2644`. Confirm the verified multi_section path DOES call `sanitize_evidence_text`/`wrap_evidence_for_prompt` but analyst_synthesis does NOT (Invariant §9.1.7 delimiter-sanitization bypass + the qualitative-negation fabrication class can ship).
4. **S1 — no table/figure structured-results extraction.** Result-table clinical numbers are invisible to provenance. VERIFY: `live_retriever.py:~1098-1156` `_build_provenance_quote` keeps only first 1500 chars + 500-char windows around bare decimals (`-?\d+\.\d+`); `~686-700` `_strip_html` flattens tables; integer-only / no-decimal-% cells aren't captured → strict_verify can only verify numbers surviving as loose decimals in running text.

## Also rule on
- Is the build order correct: fetch-cap retune → **query-decomposition (S0, promoted)** → clinical backend (Europe PMC) → deepener-behind-flag → qualitative conflict → citation-leak → trial-name recall → exec-summary → retrieval-trace → claim-reuse? Is anything mis-prioritized?
- Any gap materially wrong that would misdirect the build?

APPROVE iff the load-bearing gaps are CONFIRMED (or PARTIAL with the core true) and the build order is sound. REQUEST_CHANGES with `p0_corrections` if a gap is REFUTED in a way that changes the work.
