# Claude architect audit — I-bug-771 (#812) tier_classifier fix

## What was broken (root cause, confirmed against the afib live_corpus_dump)
The dominant #763-benchmark abort was `abort_corpus_inadequate` (3/6 vectors).
The content-based `tier_classifier` mis-tiered authoritative cardiology sources,
so the clinical T1≥3 / T2≥2 minimums could not be met:

| afib source | should be | classifier gave | why |
|---|---|---|---|
| jacc.org/doi/... | T1/T2 | T4 | jacc.org not in PEER_REVIEWED_JOURNAL_DOMAINS (only acc.org); `_has_peer_reviewed_doi_prefix` only matches `doi.org/` URLs, not `jacc.org/doi/...` → R9 unverified-host demote |
| escardio.org/guidelines/... | T2 | T4 | escardio.org in no set → R9_openalex_unverified_host_demoted_to_t4 |
| ahajournals.org (297 chars) | T7 | T7 | Rule 1 stub — CORRECT; do not launder |
| mdpi.com/... (primary) | not T1 | T1 | mdpi.com in PEER_REVIEWED_JOURNAL_DOMAINS + 10.3390 in DOI prefixes → over-credit |

## Decision provenance (Codex = decision-maker, per CHARTER §1)
- `.codex/I-bug-771/decision_verdict.txt`: Codex decided **C+D** (authoritative
  floor + content fix + low-quality-OA ceiling + no-stub-laundering).
- `.codex/I-bug-771/mdpi_reconcile_verdict.txt`: I surfaced that Codex's "MDPI →
  T4 ceiling" conflicted with the prior pass-12 deliberate tuning (MDPI SR/MA →
  T2, `test_m12`). Codex reconciled to **B (discriminator)**: MDPI PRIMARY → T4,
  MDPI genuine SR/MA → T2 retained.

## Implementation (line-by-line self-audit)
1. **jacc.org/onlinejacc.org → PEER_REVIEWED_JOURNAL_DOMAINS.** Surgical set add.
   JACC is a flagship Elsevier (10.1016) cardiology journal. Verified: jacc
   primary → T1; jacc SR/MA → T2.
2. **Rule 8c** (fires after Rule 1 stub, before R8b/R9/R10 — placement is
   load-bearing): on `GUIDELINE_AUTHORITY_DOMAINS` {escardio, ahajournals, jacc,
   onlinejacc, acc, nice}:
   - society tool/dosing/practice-support path → **T3** (fixes a pre-existing
     hole where an acc.org dosing PDF with OpenAlex article metadata reached T1
     via R9).
   - guideline path OR `_title_signals_clinical_guideline` → **T2** ("guideline
     authority", not primary).
   - else → fall through to the normal journal path.
   Stub guardrail is STRUCTURAL: Rule 1 returns T7 before Rule 8c, so a 297-char
   fetch is never laundered up (asserted for AHA + ESC stubs).
3. **`_title_signals_clinical_guideline`** (the brittle part, hardened across
   5 Codex iters): exclusions FIRST (GDMT/adherence/concordant/implementation +
   START-anchored study-framings like "Validation of …") → then statement-type
   markers (consensus/scientific/position statement, practice bulletin) → then a
   year-anchored regex `\b(19|20)\d{2}\b.{0,80}\bguidelines?\s+(?:for|on|update|
   focused update)\b`. Issued guidelines are year-dated society documents saying
   "guideline for/on"; commentary/validation studies are rejected.
4. **MDPI primary → T4** in R9 + R10 via exact-DOI-prefix `_is_low_quality_oa`;
   SR/MA branch fires first so MDPI SR/MA still → T2.

## §-1.1 verification posture (clinical-safety)
- This is claim-by-claim against the EXACT domain/path each afib source
  retrieved — not metadata/pattern checks.
- The DANGEROUS direction (false-PROMOTE a non-guideline to T2 → pollute the
  evidence base / inflate adequacy) is comprehensively guarded: exclusions +
  START-anchored study-framings + year-anchor + statement markers + dropped bare
  "guideline" substrings. Every Codex-cited false-promote case has a green test.
- The residual direction is false-DEMOTE (a rare guideline TITLE form tiered T4
  instead of T2) — under-counts secondary evidence, never fabricates. Captured as
  follow-up #813 (P3).

## Evidence
- 255 classifier tests green (229 regression: m7/m10/m11/m12/m13/m15/m16/m17/m18/
  m37 + denylist + openalex_authority; 26 new #812 invariants). 154 downstream
  consumer tests green. Smoke-verified on the actual afib source URLs.
- Codex diff review: 5 iters, each a real guideline-TITLE-form finding, all
  resolved; force-APPROVE at the 5-cap per §8.3.1 (iter-5 P1 resolved, not
  banked, per §-1.2 step-6). Trajectory in
  `state/polaris_restart/iteration_trajectory.md`.

## Verdict
Code-correctness: APPROVE (Codex force-approved at cap; dangerous direction
guarded + tested). **Remaining gate (LAW II empirical):** end-to-end re-run of
the 3 corpus_inadequate vectors must confirm they reach T1≥3 / T1+T2≥5 and ship
(no abort_corpus_inadequate), with 2 controls (tirzepatide + a policy/dd vector)
showing no precision regression. Runs after the #763 sweep frees resources (§8.4).
NOT merged by Claude — queued for operator (clinical-safety core-pipeline).
