# POLARIS pass 10 — 8-query sweep content re-audit after M-7/M-8

You are re-auditing the 8-query sweep output after the pass-9
BLOCKED-ON-ISSUE verdict was remediated.

## What changed since pass 9

Commits:
- `5fe0212`…`039db05`…`e552a05` — pass 9 context & loop spec
- **`<latest>`** — M-7 tier domain overrides + M-8 degenerate-sentence
  guard + regression tests (455 pass total).

Specifically:
- New `SOCIAL_PLATFORM_DOMAINS` set demotes Facebook/Reddit/AOL/
  Twitter/X/Yahoo/MSN/HuffPost/etc. to T6 regardless of OpenAlex
  metadata (rule R2b_social_platform).
- New `MARKET_RESEARCH_DOMAINS` set demotes DelveInsight/Statista/
  MatrixBCG/PortersFiveForce/PharmaVoice/McKinsey/Gartner/etc. to
  T5 (rule R2b_market_research).
- `LEGAL_COMMENTARY_DOMAINS` extended: Knobbe + 10 other IP/pharma
  law-firm domains now T6.
- `NEWS_BLOG_DOMAINS` extended: cen.acs.org (C&EN trade news) now T6.
- `resolve_provenance_to_citations()` now drops degenerate sentences
  (<3 content words or <15 chars after provenance stripping) and
  reorders citation-number assignment so pruned sentences don't
  leave dangling bibliography entries.

## Cycle-2 sweep results

| slug | status | release | T1% | T6% | fetched | words |
|---|---|---|---|---|---|---|
| clinical_afib_anticoagulation | success | True | 40 | 0 | 16 | 753 |
| clinical_tirzepatide_t2dm | partial_qwen_advisory | False | 25 | 0 | 15 | 507 |
| policy_fda_ai_devices | partial_qwen_advisory | False | 16 | 10 | 14 | 631 |
| policy_medicare_drug_price | partial_qwen_advisory | False | 34 | 0 | 14 | 721 |
| tech_rag_architectures_2024 | abort_corpus_inadequate | None | 5 | 20 | 19 | 0 |
| tech_long_context_transformer | abort_corpus_inadequate | None | 0 | 10 | 20 | 0 |
| dd_novo_nordisk_obesity_position | abort_corpus_inadequate | None | 5 | 30 | 18 | 0 |
| dd_lilly_tirzepatide_manufacturing | abort_corpus_inadequate | None | 0 | 43 | 13 | 0 |

1 released / 3 partial (qwen-blocked) / 4 aborts. Total cost: $0.0046.

Compared to cycle 1 (pass 9):
- Cycle 1: 4 released, 3 partial, 1 abort — but several released
  reports had Facebook/Reddit/AOL/MatrixBCG/etc. labeled T1.
- Cycle 2: 1 released, 3 partial, 4 aborts — honest tier labels
  now expose that those queries didn't actually have sufficient
  primary-research corpus to pass adequacy.

## Your mandate

### 1. Tier-label honesty check

Open `outputs/sweep_r3_final/<domain>/<slug>/live_corpus_dump.json`
for each query. For each:

- Grep for `"tier": "T1"` entries. Are all T1-classified domains
  actually peer-reviewed primary research? (PMC, NEJM, JAMA,
  Lancet, Frontiers, MDPI, BMC, etc. = yes. Facebook, Reddit,
  AOL, Knobbe, DelveInsight, etc. = NO.)
- Any remaining domain that looks like it shouldn't be T1?
  Name it, file path, URL, why.

For the 1 released report (clinical_afib_anticoagulation):
- Open `report.md`; cross-check 3+ citations against ground-truth
  bibliography URLs. Any hallucinations?
- Does the limitations section's tier accounting match the actual
  distribution? (T1=40%, T7=35%, T4=25%.)

### 2. Abort legitimacy check

4 queries aborted with corpus_inadequate (was 1 in cycle 1).
Open `corpus_adequacy.json` + `run_log.txt` for each aborted
query. Are the aborts legitimate refusals given the honest tier
signal, or are the adequacy thresholds mis-tuned for these topics?

Consider: the abort is pipeline A saying "I don't have enough
primary research to answer this question". That is the
honest-by-construction discipline working. But if a topic
legitimately has few T1 sources (e.g., policy topics, emerging
tech), the threshold might need to be domain-aware.

### 3. Partial-release qwen-advisory check

3 queries shipped as `partial_qwen_advisory` (release blocked).
Open each `qwen_judge_output.json`:

- Are qwen's complaints substantive (real defects in the report)
  or stochastic noise (qwen flagged something minor)?

### 4. Were M-7 and M-8 substantive?

- M-7: did the tier classifier changes actually fire on the
  sweep URLs? Grep `live_corpus_dump.json` across all 8 queries
  for Facebook/Reddit/AOL — they should ALL be T6 now.
- M-8: the degenerate-fragment guard — did it activate? Open
  the released report and the 3 partial reports; look for
  ".[N]" or "word.[N]" patterns like cycle 1 had. If they're
  gone, the guard is working.

### 5. Final verdict

One of:
- **APPROVED-FOR-FULL-SCALE-RUN**: tier labels honest, aborts
  legitimate, partials have real qwen concerns, no hallucinations,
  M-7+M-8 working as intended.
- **BLOCKED-ON-ISSUE**: one or more of the above failed.
  Specifically identify what's still broken.
- **CONDITIONAL**: approve with specific targeted change (e.g.,
  domain-aware adequacy thresholds before declaring full-scale ready).

### READY BAR

- Zero tier-label hallucinations in any released or partial report
- Aborts must be legitimate (not thresholds mis-tuned)
- No degenerate citation fragments in released prose
- 0 fabricated citations (pass 9 already saw 0; pass 10 must also
  see 0)

## Output

Write to `outputs/codex_findings/full_audit_pass_10/findings.md`
with frontmatter:

```yaml
---
verdict: APPROVED-FOR-FULL-SCALE-RUN | BLOCKED-ON-ISSUE | CONDITIONAL
pass: 10
cycle: 2
m7_tier_fix_working: true | false
m8_fragment_guard_working: true | false
tier_label_hallucinations: <int>
citation_hallucinations: <int>
aborts_legitimate: true | false | mixed
rationale: |
  <3-5 sentences>
---
```

Followed by per-section findings.

## Auth + duration

OAuth chatgpt. 30-45 minutes.

---

Start:

```
cat outputs/codex_findings/full_audit_pass_10/sweep_index.md
git log --oneline 3e4dd03..HEAD | head
```

Then walk sections 1-5.
