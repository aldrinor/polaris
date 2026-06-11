## Source-starvation fix — traced from the first live instrumented run (drb_76, 2026-06-11)

The funnel-first run (#1204) released a faithful-but-THIN report (status `released_with_disclosed_gaps`;
always-release + confidence labels + gap disclosures all worked; no fabrication). It was thin because
the generator saw only **53 evidence rows out of 2,689 discovered**. The new telemetry traced exactly
where the sources die — and it is NOT the off-topic filter (ran=0 this run) nor the 1500 cap (never bound):

**Loss 1 — rerank/fetch-cap cull: 2,689 → 740 (drop 1,949 = `drop_reasons.rerank_not_selected`).**
`_rerank_and_reserve` (live_retriever.py) hard-slices `candidates[:fetch_cap + n_seed_injected]`. This is
the single biggest drop. Need: is the cap (~740) too low, or is this legitimate relevance ranking?

**Loss 2 — extraction/lane collapse: 524 fetched → ~58 evidence rows reaching the generator.**
`evidence_selection`: evidence_total=53, dropped_count=0; `finding_dedup`: raw_row_count=58,
collapsed_row_count=0. So selection + dedup cut NOTHING — the pool was already ~58 before them. But the
NEW `extraction_yield.finding_rows = 498` (the main retrieval's return-time count) does NOT match the
final 58. **Hypothesis: a downstream retrieval lane (agentic/deepener, live_retriever reassigns
`retrieval.evidence_rows` at the expansion/deepener/agentic seams) is CLOBBERING the main lane's ~498
extracted evidence rows down to ~58.** If true, that is a major bug — the pipeline finds the evidence
then throws most of it away before generation. (Also: my Task-2a `extraction_finding_rows` telemetry is
misleading — captures 498, not the final pool — fix it to report the real final extraction count.)

## Plan (execute via Claude Codex Workflow, data-driven, NOT a hand-guess)
1. DIAGNOSE (read-only): trace `evidence_rows` from the main `run_live_retrieval` return (498) through
   the expansion/deepener/agentic reassignment to the final 53–58. Is evidence being clobbered/over-pruned,
   or is 498→58 a legitimate distinct-finding reduction? Confirm the rerank cull mechanism + whether 740
   is an over-aggressive cap. Use the saved run artifacts (outputs/audits/I-perm-010/run_drb76_jun11/) + code.
2. FIX the binding over-aggressive throttle/bug, flag-gated + tested + behavior-safe; fix the
   extraction_yield telemetry to report the true final extraction count.
3. Codex diff-gate. Redeploy to VM, re-run drb_76, confirm more evidence reaches the generator + the
   report fattens (still faithful), THEN the full 5-question beat-both.

Faithfulness gates (strict_verify / 4-role / D8) are NEVER relaxed. Links: funnel #1204, cap #1070,
selection #1197, extraction #1201.
