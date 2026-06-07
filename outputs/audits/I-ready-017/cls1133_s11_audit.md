# §-1.1 line-by-line audit — I-ready-017 #1133 (tier_classifier statistical agencies → T3)

**Subject:** the `R2b_statistical_agency` rule (`tier_classifier.py:1325-1349`) + `STATISTICAL_AGENCY_DOMAINS`
set, classifying national/international statistical-data agencies as T3. Commit 5db270a4 (on deploy branch
origin/bot/I-ready-consolidated). Codex diff-gate APPROVE (`.codex/I-ready-017/cls1133_codex_diff_audit.txt`,
0 P0/P1; 1 cosmetic P2 — ec.europa.eu breadth, tier-harmless). Offline tests: 8/8
(`tests/polaris_graph/test_tier_classifier_stat_agency_t3_iready017.py`).

This audit verifies the fix on the **REAL $3 canary corpus** (`outputs/audits/I-ready-017/run_artifacts/
live_corpus_dump.json`) — the actual sources that triggered `abort_corpus_approval_denied` on the
2026-06-06 drb_72 live canary (#1132) — NOT synthetic fixtures, NOT a string-presence check.

---

## Claim 1 — "The exact stat-agency sources that were mis-tiered now classify T3"

Re-classified the 3 statistical-agency rows from the real canary corpus through the live (fixed)
`classify_source_tier`:

| URL (real canary row) | recorded tier (before) | re-classified (after) | rule |
|---|---|---|---|
| bls.gov/bls/congressional-reports/assessing-the-impact-of-new-tech… | **T4** | **T3** | R2b_statistical_agency |
| bls.gov/opub/mlr/2025/article/incorporating-ai-impacts-in-bls-empl… | **T4** | **T3** | R2b_statistical_agency |
| oecd.org/en/publications/2021/01/the-impact-of-artificial-intellig… | **UNKNOWN** | **T3** | R2b_statistical_agency |

**Verdict: VERIFIED.** All 3 real mis-tiered rows (2× BLS demoted to T4 by the OpenAlex narrative/preprint
paths; OECD fell through to UNKNOWN) now correctly classify T3 — the authoritative-data tier — on the exact
URLs that caused the denial. Source: the re-classification run logged above (offline, no network, no model).

## Claim 2 — "Precedence is correct: stat-agency T3 fires before the OpenAlex demotion paths and after the denylist"

- **Cited code** (`tier_classifier.py:1325-1349`): `R2b_statistical_agency` is placed adjacent to
  `R2b_gov_agency` (1314) — i.e. AFTER the R2a/R2b denylist demotions (industry/news/think-tank/market-
  research) and BEFORE R9/R10/R11 (the OpenAlex `article+journal` / preprint / repository paths that
  demoted bls.gov to T4). The `_domain_matches` parent-match also covers subhosts (www.bls.gov,
  fred.stlouisfed.org, ilostat.ilo.org).
- **Verdict: VERIFIED.** A denylisted domain can never be laundered up to T3 (denylist fires first), and a
  genuine stat-agency can no longer be demoted by OpenAlex metadata (R2b fires first, `return`s).

## Claim 3 — "Faithfulness-positive, not a corpus relaxation"

- The rule tiers stat agencies as **T3 (government/regulatory/authoritative-data)**, explicitly NOT T1
  primary-research-paper credit (`tier_classifier.py:1335-1347` reasons). It recognizes the PRIMARY required
  quantitative evidence for the generic workforce protocol (`config/scope_templates/workforce.yaml`
  `expected_tier_distribution`: T3 statistical agencies 35-65%) so a genuinely-adequate corpus is not falsely
  denied. It does NOT authorize a deviated corpus (the wrong fix would be `PG_AUTHORIZED_SWEEP_APPROVAL` on a
  mis-tiered corpus).
- **Verdict: VERIFIED.** Correct tiering strengthens the corpus-quality contract; no faithfulness gate
  (strict_verify / provenance / 4-role / two-family) is touched.

## Claim 4 — "Clinical-domain tiering is not regressed (shared classifier)"

- Offline suite `test_tier_classifier_stat_agency_t3_iready017.py` (8/8) asserts stat agencies → T3 AND a
  clinical regulatory domain still → T3 AND a generic .org keeps its prior tier. The broader classifier suite
  was unaffected by 5db270a4 (additive rule + domain set; no edit to existing rules).
- **Verdict: VERIFIED.**

---

## Summary

| Claim | Verdict |
|---|---|
| 1 — real canary stat-agency rows now T3 | VERIFIED (3/3 on real output) |
| 2 — precedence (after denylist, before OpenAlex demotion) | VERIFIED |
| 3 — faithfulness-positive, not a relaxation | VERIFIED |
| 4 — no clinical-domain regression | VERIFIED |

**#1133 is DONE** (code on deploy branch + 8/8 offline + Codex APPROVE + §-1.1 on real output).

## IMPORTANT scope reconciliation (drb_72 vs #1133)

The $3 canary (#1132) hit `abort_corpus_approval_denied` running **journal_only OFF**, so it took the GENERIC
workforce distribution (T3 statistical agencies 35-65%) and the mis-tiering bit. #1133 fixes that path.

BUT drb_72's question explicitly instructs **"only cites high-quality, English-language journal articles"**,
and `config/scope_templates/workforce.yaml:77-93` declares `source_restriction: journal_only` with the
comment that the generic T3-statistical-agency band is **the WRONG contract for drb_72** (stat-agency portals
are not journal articles). So the FAITHFUL drb_72 run is **`PG_SOURCE_RESTRICTION_JOURNAL_ONLY=1`**, under
which corpus_approval uses `journal_only_tier_distribution` (T1≥40%) + the `corpus_adequacy.journal_only`
floor (≥12 distinct journals + 4 anchor DOIs: Acemoglu-Restrepo JEP 2019 / Autor JEP 2015 / Acemoglu-Restrepo
JPE 2020 / Brynjolfsson QJE 2025), and the stat-agency tiering is moot (stat agencies are filtered out by the
citeability partition).

**Net:** #1133 is a correct, completed GENERAL fix (it un-bricks the journal_only-OFF / non-drb_72 workforce
path and prevents the mis-tier from ever silently denying an adequate generic corpus). For the **drb_72
beat-both run specifically**, the path is `journal_only ON` — so the operator GO/NO-GO step
"set `PG_SOURCE_RESTRICTION_JOURNAL_ONLY=1` for drb_72" stands and is the question-faithful config. The
cheap pre-spend canary must run **with journal_only ON** to confirm the journal_only corpus auto-approves
(12 journals + the 4 anchor DOIs present as citeable journal sources).
