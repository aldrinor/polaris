# Codex RECONCILE — I-bug-771 (#812): your MDPI-ceiling decision conflicts with a PRIOR Codex decision

You decided (#812, C+D): "mdpi.com and 10.3390 must NOT classify as T1/T2. Treat
as T4 ceiling." I gave you only the afib tier table then. On implementing, I read
the classifier tests and found a DIRECT conflict with earlier Codex passes you
should reconcile (I will NOT silently override prior-Codex tuning):

## The conflict
Pass-12 + pass-15 (earlier Codex) DELIBERATELY tuned MDPI:
- `test_m12::test_full_mdpi_title_with_sr_ma_suffix_is_t2`: MDPI with a FULL
  "Systematic Review and Meta-Analysis" title → **T2** (intentional; comment:
  "classifier routes to T2 correctly"). Groups MDPI WITH Frontiers as
  legitimate-enough venues for SR/MA.
- `test_m15::test_truncated_title_with_ellipsis_demotes_to_t4`: MDPI with a
  TRUNCATED title → T4 (can't confirm SR/MA).
- MDPI is in `PEER_REVIEWED_JOURNAL_DOMAINS` + `10.3390` in
  `PEER_REVIEWED_DOI_PREFIXES`, so MDPI PRIMARY articles → T1.

## What the afib over-credit actually was
The afib MDPI source (`mdpi.com/2077-0383/14/22/8079`) got **T1** — i.e. it went
through the PRIMARY path, not the SR/MA path. So the demonstrated over-credit is
**MDPI-primary → T1**, NOT MDPI-SR/MA → T2.

## Reconcile (decide one)
- **A. Hard T4 ceiling** (your #812 as written): MDPI never T1/T2. Requires
  UPDATING `test_m12` (MDPI SR/MA → T4 now) — overriding pass-12. Defensible if
  you judge MDPI SR/MA not T2-worthy (AMSTAR-2: MDPI SR quality is variable).
- **B. Discriminator**: MDPI PRIMARY → T4 (fixes the afib over-credit), but MDPI
  genuine SR/MA (full title) → T2 retained (preserves pass-12). Net: MDPI cannot
  be a T1 primary, can still be a T2 review. Keeps both decisions coherent.
- **C. Something else.**

Which? This determines whether I update `test_m12` (option A) or add a
primary-only MDPI demotion (option B). Note: the clinical adequacy gate needs
T1>=3, T2>=2 — option B keeps MDPI SR/MA counting toward T2; option A removes it
entirely. Decide on clinical-safety + precision grounds, not adequacy-pass
convenience.

Also confirm the non-conflicting parts stand: jacc.org -> PEER_REVIEWED_JOURNAL_
DOMAINS (flagship journal); escardio.org/guidelines + NICE + ACC/AHA /guidelines/
paths -> T2 guideline-authority (excluding /tools//dosing/ society-tool paths
which stay T3); ahajournals 297-char stay T7 (don't launder).

Return a decision, not a menu.
