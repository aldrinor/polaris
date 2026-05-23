# I-bug-771 (#812) implementation spec — tier_classifier fix per Codex C+D

Derived from a full read of `src/polaris_graph/retrieval/tier_classifier.py`
(1637 lines, 16+ Codex-pass history) + the afib live_corpus_dump tier evidence.
This converts Codex's C+D decision into exact, line-level changes.

## Why each afib source got its tier (confirmed against the cascade)
- **MDPI → T1:** `mdpi.com` ∈ `PEER_REVIEWED_JOURNAL_DOMAINS` (L478) + `10.3390` ∈
  `PEER_REVIEWED_DOI_PREFIXES` (L513). Rule 9/10 → T1 presumed-primary.
- **ESC (escardio.org) → T4:** `escardio.org` in NO set. With OpenAlex
  article+journal → Rule 9 → domain not in allowlist →
  `R9_openalex_unverified_host_demoted_to_t4` (L1450-1469).
- **JACC (jacc.org) → T4:** `jacc.org` NOT in `PEER_REVIEWED_JOURNAL_DOMAINS`
  (only `acc.org` is). `_has_peer_reviewed_doi_prefix` only matches `doi.org/`
  URLs, not `jacc.org/doi/10.1016/...` → falls to T4 demotion.
- **AHA → T7:** Rule 1 stub (L979), fetched body ~297 chars < 1000. **Correct —
  do NOT floor (Codex: never launder content-starved stubs).** The AHA full-text
  not being fetched is a RETRIEVAL/fetch concern (separate follow-up), not a
  classification bug.

## Stub-laundering guardrail = already structural
Rule 1 (stub, L979) returns T7 BEFORE any peer-reviewed/guideline rule. So every
floor/overlay below — placed after Rule 1 — physically cannot promote a stub.
Tests must still assert this (a 297-char `ahajournals.org` page stays T7).

## Changes (surgical; placement is load-bearing)

### D — MDPI / low-quality-OA ceiling
1. Remove `"mdpi.com"` from `PEER_REVIEWED_JOURNAL_DOMAINS` (L478).
2. Remove `"10.3390",  # MDPI` from `PEER_REVIEWED_DOI_PREFIXES` (L513).
3. Add `LOW_QUALITY_OA_DOMAINS = frozenset({"mdpi.com"})` (+ `10.3390` DOI check).
4. New cascade rule **after Rule 8b, before Rule 9** (so it caps the
   peer-reviewed path but lets genuine news/regulatory/social rules win first):
   `if _domain_matches(domain, LOW_QUALITY_OA) or doi-prefix 10.3390: tier=T4`
   (ceiling; reason = "low-quality OA, T4 ceiling per safety review").
   NOTE: this removes afib's lone (fake) T1 — the JACC+ESC+PMC gains below must
   more than compensate. The re-run confirms.

### C — authoritative journal + guideline recognition
5. Add `"jacc.org"` to `PEER_REVIEWED_JOURNAL_DOMAINS` (flagship cardiology
   journal; Elsevier 10.1016). Also consider `circ`/`jaha` AHA journal hosts if
   distinct from `ahajournals.org` (already present).
6. New `GUIDELINE_AUTHORITY` recognition: domains+paths
   `escardio.org/guidelines`, `nice.org.uk`, AHA/ACC `/guidelines/` paths.
   Map to **T2** (high-authority secondary — counts toward template T2≥2),
   reason = "recognized guideline-issuing body (guideline authority, NOT
   primary study)". Place AFTER Rule 1 stub. **Must NOT override** the existing
   `acc.org` society-tool demotion (L1569: `/tools/`,`/dosing/`,`/practice-
   support/` → T3) — discriminate by requiring a `/guidelines/`-family path and
   EXCLUDING the `_society_tool_markers`. (Codex: acc.org tools/dosing PDFs never
   T1/T2.)

## Codex's required test invariants (add to tests/polaris_graph/)
- `ahajournals.org` primary article w/ usable content → T1/T2; 297-char → T7.
- `jacc.org` / JACC DOI → T1/T2 by article type.
- `escardio.org/guidelines/...` → guideline-authority high tier (T2), not T4.
- PMC/PubMed primary + SR/MA → T1/T2 by content.
- `mdpi.com` and `doi.org/10.3390/...` → NOT T1/T2 (T4 ceiling).
- `acc.org/.../Tools-and-Practice-Support/...DOAC-Dosing...pdf` → NOT T1/T2 (T3).
- social/vendor/news/predatory/unknown-OpenAlex hosts stay low.

## Verification (Codex bar — NEVER skip/fake)
1. Full `tests/polaris_graph/` suite GREEN (the regression guard — classifier
   has 16-pass tests; "0 releases" cycles in history prove over-tightening risk).
2. New invariant tests GREEN.
3. Re-run the 3 blocked vectors: `clinical_afib_anticoagulation`,
   `tech_long_context_transformer`, `tech_rag_architectures_2024` → no
   `abort_corpus_inadequate`; clinical reaches T1≥3 and T1+T2≥5; MDPI never in
   T1/T2.
4. Controls: `clinical_tirzepatide_t2dm` + one policy/dd vector → no precision
   regression (didn't start over-crediting).

## Regression-risk note
This file has a documented history of tier changes driving the whole pipeline to
0 releases (see L1525-1556 BUG-M-14/M-15 reverts). The full test suite + the
3-vector + 2-control re-run are MANDATORY before merge. Codex diff review is the
gate. This is clinical-safety core — careful, not fast.
