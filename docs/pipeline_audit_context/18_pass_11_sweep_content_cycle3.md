# POLARIS pass 11 — 8-query sweep content audit (cycle 3, post-M-10)

Third content audit of the 8-query sweep. Pass 9 and pass 10 both
returned BLOCKED-ON-ISSUE on T1 tier misclassification. M-7 covered
social/market-research/law-firm/trade-news. M-10 adds:

- Clinical reference products (UpToDate, DynaMed, ClinicalKey)
  → T4
- Policy think-tanks (KFF, Commonwealth Fund, Brookings, Rand, NBER,
  AccessibleMeds, PhRMA, BIO, AMA) → T4
- Government agencies (cms.gov, hhs.gov, va.gov, ihs.gov, samhsa.gov,
  hrsa.gov) → T3
- Business/general news (fastcompany.com, forbes.com, businessinsider,
  fortune, beckers, modern healthcare) → T6
- Web guides (chitika.com, pcmag, techradar, cnet, g2) → T6
- R9 title-based demotion: "guideline", "guiding principles",
  "explainer", "policy brief", "key facts", "fact sheet", "issue
  brief", "primer on", "what is", "how does" markers now route to
  T4 instead of T1 even on legitimate journal hosts (e.g.,
  PMC-hosted "2025 Guidelines for DOACs")

Tests: 479 pass (+24 M-10 tests). Commit: latest HEAD.

## Cycle-3 results

| slug | status | release | T1% | T3% | T4% | T6% | words |
|---|---|---|---|---|---|---|---|
| clinical_afib_anticoagulation | partial_thin_corpus | True | 15 | 5 | 45 | 0 | 535 |
| clinical_tirzepatide_t2dm | partial_thin_corpus | True | 20 | 5 | 20 | 0 | 634 |
| policy_medicare_drug_price | success | True | 20 | 15 | 25 | 0 | 581 |
| policy_fda_ai_devices | abort_corpus_inadequate | None | 3 | 33 | 18 | 7 | 0 |
| dd_novo_nordisk_obesity_position | abort_corpus_inadequate | None | 0 | 0 | 5 | 35 | 0 |
| dd_lilly_tirzepatide_manufacturing | abort_corpus_inadequate | None | 6 | 6 | 18 | 37 | 0 |
| tech_rag_architectures_2024 | abort_corpus_inadequate | None | 0 | 0 | 70 | 25 | 0 |
| tech_long_context_transformer | abort_corpus_inadequate | None | 5 | 0 | 75 | 10 | 0 |

3 released (1 success + 2 partial_thin_corpus) / 5 honest refusals.
Total cost: $0.0041.

## Your mandate (third content re-audit)

### 1. Verify M-10 eliminates the 13 pass-10 hallucinations

Pass 10 named 11+ specific T1-hallucinated domains. Grep the
cycle-3 `live_corpus_dump.json` files for each:

- uptodate.com, downstate.edu, ihs.gov (should be T4/T3, not T1)
- fastcompany.com (should be T6)
- kff.org, accessiblemeds.org, cms.gov, commonwealthfund.org
  (should be T4/T3)
- ai.jmir.org guiding-principles, PMC guideline titles (should be
  T4 via title-based demotion)
- chitika.com (should be T6)

If any still show as T1, that's a regression. Name the URL, the
dump file, and why it leaked through.

### 2. Cross-check the 3 released reports

- `outputs/sweep_r3_final/clinical/clinical_afib_anticoagulation/report.md`
- `outputs/sweep_r3_final/clinical/clinical_tirzepatide_t2dm/report.md`
- `outputs/sweep_r3_final/policy/policy_medicare_drug_price/report.md`

For each:
- Cross-check ≥3 citations against bibliography URLs for accuracy
- Verify tier counts in the limitations section match the actual
  distribution (no more inflated T1 due to mislabeling)
- Check for malformed citation fragments (M-8 should have prevented)
- Check section labels align with their content (M-9 was deferred —
  call out if this is a real issue in the released reports)

### 3. Verify the 5 aborts are legitimate

Each abort's `corpus_adequacy.json`: are threshold failures real,
given the honest tier mix? The pass-10 Codex accepted aborts as
legitimate when tier mix was genuinely thin. Same standard.

### 4. `partial_thin_corpus` release disposition

Two clinical queries now ship with `partial_thin_corpus,
release=True` instead of the cycle-2 `partial_qwen_advisory,
release=False`. That's a release-path shift:

- Is `partial_thin_corpus` a legitimate ship status, or a regression
  (release=True when it should be False)?
- Check the report's limitations section — does it flag thin-corpus
  clearly enough for a downstream consumer?

### 5. Final verdict

- **APPROVED-FOR-FULL-SCALE-RUN**: zero T1 hallucinations, 0
  citation hallucinations, aborts legitimate, released reports
  clean, partial_thin_corpus disposition is honest.
- **BLOCKED-ON-ISSUE**: any of the above failed.
- **CONDITIONAL**: specific targeted improvement.

### Ready bar

Same as before. Zero tier hallucinations. Zero citation
hallucinations. Honest refusals. No malformed fragments.

## Output

`outputs/codex_findings/full_audit_pass_11/findings.md` with
frontmatter:

```yaml
---
verdict: APPROVED-FOR-FULL-SCALE-RUN | BLOCKED-ON-ISSUE | CONDITIONAL
pass: 11
cycle: 3
m10_fix_working: true | false
tier_label_hallucinations: <int>
citation_hallucinations: <int>
aborts_legitimate: true | false | mixed
partial_thin_corpus_honest: true | false
rationale: |
  <3-5 sentences>
---
```

## Duration

30-45 min. OAuth chatgpt.

---

Start:
```
cat outputs/codex_findings/full_audit_pass_11/sweep_index.md
git log --oneline -5
```
