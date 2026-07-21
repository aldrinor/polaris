---
name: batch1-evidence-substrate-result
description: "Batch 1 (Levers B/E/F) shipped+scored: RACE flat within noise, FACT more citations at a measurement-confounded lower rate"
metadata:
  node_type: memory
  type: project
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

**2026-07-21: Round-2 Batch 1 (evidence substrate = Levers B source-eligibility + re-anchor, E fetch salvage, F canonicalize) — dual-approved, committed 3d89179 on branch fix/race-batch1-evidence-substrate, PUSHED to github (aldrinor/deep-cove-research).** 5-round Sol(gpt-5.6-sol max)+K3(kimi-k3) gate; both APPROVE. General, config-gated, all flags default OFF, faith-ghost-clean.

**Levers verified as REAL treatment (not just flags set):** B eligibility 18 fires, E salvage 26 fires, F canonicalize 112 members folded (b1 bib: 0 unfolded same-work dupes vs baseline's 13 — e.g. baseline had one World Bank PDF as [5][6][7]). B re-anchor = 0 swaps: legit conservative zero (upstream eligibility already demotes secondary sources at selection, so compose baskets are primary-leaning; nothing to re-point). NOTE: re-anchor + F don't LOG unless they act — a grep "fire count" of 0 is a logging artifact, verify via OUTPUT (bib fold, swaps).

**Scores (run_raw_a_b1.sh = run_raw_a.sh + 4 flags → outputs/b1_run vs baseline outputs/step1_run):**
- RACE 3x each: b1 mean 0.4646 vs baseline 0.4605 — FLAT within judge noise (~±0.01). Per-dim: Comprehensiveness +0.015, Instruction-Following +0.008, Insight -0.006, Readability -0.003. Expected: B/E/F is the citation-quality batch, not the readability/structure batch (that's Batch 2 = A1).
- FACT: b1 = 45 judged citations / 31 supported / rate 0.689; baseline = 17 / 16 / 0.941. valid_rate EXCLUDES 'unknown' (scrape-fails) from denominator (stat.py:27).

**THE FACT RATE DROP IS LARGELY A MEASUREMENT ARTIFACT (investigated, not assumed):** the baseline report cites the SAME marginal domains at similar/higher counts (rtsa.eu 1/1, webapps.ilo.org 2/3, equitablegrowth 1/2, treasury 1/1, aeaweb 4/2) but FACT's extractor only pulled 17 of the baseline's 93 markers -> most never judged. b1 is more extractable (45 of 104) so its marginal citations got exposed. A fair same-depth compare would put both ~0.7. b1's REAL gains: +15 supported citations (16->31), +24 cited domains (56->80). Only 2 genuinely-new weak sources; only 1 concerning = japksu.com (predatory) — Lever B eligibility KEEPS ineligible at weight 0.3 (keep-not-delete, Rank12 generalization), so a predatory source can still be cited under the "high-quality English-language journal articles" constraint. Candidate tuning: demote predatory/low-quality genre harder (not a bug; a weight/genre policy call). See [[race-maxing-audit]], [[race-champion-config]].

**FACT scorer caveat (reusable):** score_report_race.py needs OPENROUTER_API_KEY exported (BLOCKs without it, silent-empty). RACE result at third_party/deep_research_bench/results/race/<name>/race_result.txt ("Overall Score:"). FACT via scratchpad/score_report_fact.sh <report> <name> 72; per-citation verdicts in results/fact/<name>/validated.jsonl -> citations_deduped[url]['validate_res'][*]['result'] (supported/unsupported/unknown). The pipeline's outline step can flake with deepseek-v4-pro ReasoningFirstTruncationError (I-bug-089/FX-01) at the outline leg — re-run clears it.
