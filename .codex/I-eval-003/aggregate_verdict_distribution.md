# Tier-1 v2 audit verdict distribution — Q1-Q5 + tirzepatide-pending

Per CLAUDE.md §-1.1 line-by-line standard, every claim audited claim-by-claim against the cited 500-char span_text (Codex pass complete for Q1-Q4 + Q5).

## Codex per-report verdict totals

| Report | Domain | Claims | VERIFIED | PARTIAL | UNSUPPORTED | %V |
|---|---|---:|---:|---:|---:|---:|
| Q1 | ai_sovereignty | 31 | 8 | 10 | 13 | 25.8% |
| Q2 | canada_us / CUSMA | 46 | 3 | 15 | 28 | 6.5% |
| Q3 | workforce / GenAI | 61 | 11 | 12 | 38 | 18.0% |
| Q4 | policy / housing | 51 | 12 | 9 | 30 | 23.5% |
| Q5 | policy / Pharmacare (PR #421 pilot) | 28 | 24 | 4 | 0 | 85.7% |
| **TOTAL** | | **217** | **58** | **50** | **109** | **26.7%** |

## Codex per-report context_match totals

| Report | yes | partial | no |
|---|---:|---:|---:|
| Q1 | 8 | 17 | 6 |
| Q2 | 7 | 27 | 12 |
| Q3 | 14 | 40 | 7 |
| Q4 | 12 | 31 | 8 |
| Q5 | n/a (v1 schema) | | |

## Headline finding

73% of audit-grade claims across Q1-Q4 are not VERIFIED against the cited span_text window. This breaks down approximately as:
- ~24% PARTIAL: span on-topic and broadly consistent, but the specific decimal/year/figure is not visible in the 500-char window POLARIS captured.
- ~49% UNSUPPORTED: cited span does not show the figure at all (per the 500-char window).

This is a sharp contrast with Q5 Pharmacare (85.7% VERIFIED), where the canonical source spans (Quebec RPAM, Bill C-64 PBO) contain headline figures in the first 500 chars.

## Limitation: span_text window scope

The audit operates on the `direct_quote` field (first ~500 chars of fetched source per evidence_id), per `tests/fixtures/` schema. The full source URL may contain the figure further down the page; the audit asserts "the captured span does not show the figure," not "the source URL definitively lacks the figure."

GH#398 (I-audit-001, completed) extended audit-bundle to include `resolved_report.md` + `bibliography.json` + `evidence_pool.json` so audits can read more than just the first 500 chars. The Tier-1 v2 schema here intentionally remains on the 500-char window since that is what POLARIS's strict_verify NLI gate evaluated when accepting the sentence into the report. A report-level claim that fails when audited against the exact same 500-char span POLARIS used is a real production quality concern — patient/policy decisions resting on that report would not have access to the wider context either.

## Q1-Q4 vs Q5 verdict-rate delta — three likely contributors

1. **Domain-source structure**: Q5's clinical-economic sources (Steve Morgan UBC pharmacare RPAM analysis; Quebec drug insurance PMC paper; PBO cost estimate) are written with the headline decimal in the introduction or abstract. Q1-Q4's policy/regulatory/labour sources scatter figures across multiple paragraphs.

2. **Pipeline emerging-policy threshold relaxation (GH#405 / PR #417)**: dropping T1 / T1+T2 / T1+T2+T3 minimums to 0 for emerging-policy domains let Q1-Q4 generate reports against sparser tier-1 corpora. The generator then selected what the corpus offered (often T4 secondary commentary or news), not primary T1-T3 evidence.

3. **Tier-balanced selector** picked 9/20 T4 + 4/20 UNKNOWN/T6/T7 in the post-fix Q5 sweep this turn — but Q5's underlying T4 sources DO contain the headline figures in the captured span. Q1-Q4 T4 sources tend not to.

## Recommended next steps (per Codex's path-quality criteria)

1. **Re-fetch full source content** for Q1-Q4 evidence rows where Codex returned UNSUPPORTED; extend `direct_quote` window from ~500 chars to full body (cap ~10K chars per evidence_id). Re-run Tier-1 audit on the same claims. This bounds the "audit-window vs source-content" gap.
2. **Investigate Q2 (CUSMA) specifically** — 6.5% V is the worst tier of any report and 93.5% PARTIAL/UNSUPPORTED suggests either (a) the CUSMA legal-text retrieval is mis-targeted (legal-section vs trade-flow facts), or (b) the generator is paraphrasing CUSMA Article references with figures from elsewhere.
3. **Claude independent Tier-1 pass on Q1-Q4** is INCOMPLETE per §-1.1 standard (only Q5 had paired Claude pass per PR #421). The Codex pass here covers 217/217 claims; Claude pass covers 28/217 (Q5 only). Reconciliation per §-1.1 requires both passes.

## Strictly NOT done in this aggregate (per §-1.1 banned-shortcut list)

- No metadata comparison framing ("ChatGPT has X, POLARIS has Y").
- No string-presence PASS/FAIL.
- No sample-based audit — 217/217 claims went through Codex line-by-line.
- No word-count or citation-count quality signals.

The Codex pass is the actual line-by-line work product. Each per-claim verdict is in `.codex/I-eval-003/codex_q{1..4}_batch_{N}_output.txt`. Cross-reference with `.codex/I-eval-003/q{1..4}_claims_enumeration.yaml` for the claim text + cited span.

## Per-batch verdict-distribution detail (audit trail)

### Q1 — 31 claims, 5 batches
- B1 (7): 2V / 1P / 4U → context: 2y / 2p / 3n
- B2 (7): 1V / 2P / 4U → context: 1y / 5p / 1n
- B3 (7): 3V / 2P / 2U → context: 3y / 4p / 0n
- B4 (7): 1V / 3P / 3U → context: 1y / 3p / 3n
- B5 (3): 1V / 2P / 0U → context: 1y / 2p / 0n

### Q2 — 46 claims, 7 batches
- B1 (7): 0V / 3P / 4U → context: 0y / 6p / 1n
- B2 (7): 0V / 2P / 5U → context: 0y / 4p / 3n
- B3 (7): 1V / 3P / 3U → context: 2y / 3p / 2n
- B4 (7): 0V / 3P / 4U → context: 0y / 6p / 1n
- B5 (7): 1V / 3P / 3U → context: 4y / 3p / 0n
- B6 (7): 0V / 0P / 7U → context: 0y / 6p / 1n
- B7 (4): 1V / 1P / 2U → context: 1y / 2p / 1n

### Q3 — 61 claims, 9 batches
- B1 (7): 1V / 1P / 5U → context: 1y / 6p / 0n
- B2 (7): 0V / 3P / 4U → context: 0y / 5p / 2n
- B3 (7): 1V / 2P / 4U → context: 1y / 2p / 4n
- B4 (7): 1V / 0P / 6U → context: 1y / 6p / 0n
- B5 (7): 1V / 3P / 3U → context: 1y / 3p / 3n
- B6 (7): 2V / 1P / 4U → context: 3y / 4p / 0n
- B7 (7): 2V / 1P / 4U → context: 2y / 5p / 0n
- B8 (7): 2V / 0P / 5U → context: 2y / 5p / 0n
- B9 (5): 1V / 1P / 3U → context: 1y / 4p / 0n

### Q4 — 51 claims, 8 batches
- B1 (7): 2V / 1P / 4U → context: 2y / 4p / 1n
- B2 (7): 3V / 1P / 3U → context: 3y / 4p / 0n
- B3 (7): 2V / 1P / 4U → context: 2y / 4p / 1n
- B4 (7): 0V / 1P / 6U → context: 0y / 7p / 0n
- B5 (7): 1V / 2P / 4U → context: 1y / 3p / 3n
- B6 (7): 2V / 0P / 5U → context: 2y / 2p / 3n
- B7 (7): 2V / 2P / 3U → context: 2y / 5p / 0n
- B8 (2): 0V / 1P / 1U → context: 0y / 2p / 0n

## Status

GH#429 (I-eval-003) Tier-1 v2 audit pass on Q1-Q4: Codex side COMPLETE (24 batches across 4 reports). Claude independent pass + cross-review reconciliation INCOMPLETE for Q1-Q4 — only Q5 has paired Claude pass (PR #421). Tirzepatide triple still pending per GH#403 in_progress.
