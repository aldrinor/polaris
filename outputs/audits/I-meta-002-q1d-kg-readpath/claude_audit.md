# Claude architect audit — PR10: campaign KG reuse read-path, fail-closed (#948)

**Issue:** #948 (q1c-7, operator concern #6 — semantic memory). **Branch:** `bot/I-meta-002-q1d-kg-readpath`.
**Both Codex gates APPROVE** — brief iter-2 ("fail-closed is now mechanical") + diff iter-2 (zero
P0/P1/P2). **NO SPEND** — read-only sqlite, default-OFF, no network/model.

## What this fixes

Codex-verified gap (#941): `VerifiedClaimGraphStore` was WRITE-ONLY — `query_related_claims` was never read
back into generation, and the store was opened per-question (`run_dir`), so even a read would see an empty
db. Result: ZERO citation-snowball reuse across the campaign's questions. This wires the read-path in,
campaign-scoped, and FAIL-CLOSED.

## Fail-closed is MECHANICAL (the safety core)

The earliest design injected reused claims into the analyst layer with a prompt instruction to "re-ground or
omit" — Codex (brief iter-1 P1) correctly rejected that: for clinical-safety reuse, omission must be
*structural*, not advisory. The shipped design:

- `match_prior_claims_to_current_corpus` reuses strict_verify's OWN primitives (`_content_words`,
  `_decimals`, `_min_overlap_threshold`). A prior-VERIFIED claim is KEPT only if some CURRENT evidence row
  shares ≥ the threshold content words AND contains every decimal in the claim — the same rule the verified
  chokepoint applies. Unmatched prior claims are OMITTED before they ever reach a prompt.
- A surviving claim is anchored ONLY to the CURRENT evidence id that supports it. Prior evidence ids are
  never read or injected, so a reused claim can never carry prior provenance and can only surface a fact
  that is already present-and-supported in this question's corpus (a cross-question relevance signal).

## Read-path is mechanically read-only (Codex diff iter-1 P1)

`VerifiedClaimGraphStore(read_only=True)` opens the existing db via the SQLite `file:<path>?mode=ro` URI —
no parent mkdir, no `_ensure_table` DDL, cannot create/migrate/write-lock/mutate. A missing/unreadable db
raises and `gather_reuse_context` fail-opens to []. Write mode (default) is byte-unchanged.

## Anti-poisoning + verified core untouched

`query_related_claims` returns only `reusable==1` (VERIFIED) rows — anti-poisoning intact. The verified
multi_section generator + strict_verify path is NOT threaded with reuse context; `prior_verified_context`
reaches ONLY the unverified analyst layer (already screened by PR3/PR7), as a labeled advisory block
instructing `[N]`-only current-bibliography citation. Empty input → prompt byte-identical.

## Campaign-scope + flags

`run_four_role_evaluation` / `run_four_role_seam` gain `campaign_kg_db=None` (default → per-`run_dir`,
existing callers/tests unchanged); when given, the KG persists to `out_root/verified_claim_graph_campaign.db`
shared across the sequentially-run questions. Default-OFF `PG_SWEEP_KG_REUSE` (normalized `.strip().lower()`
so FALSE/No/OFF any case stay disabled). Gather is fail-open (a KG/read error never aborts or alters a run).

## Tests (13 KG-reuse + 22 no-regression, NO SPEND)

Match-gate (supported→anchored-to-current-ev, unsupported→omitted, decimal-mismatch→omitted, low-overlap→
omitted, dedup); Codex's two mandated cases (a prior-VERIFIED claim NOT in the current corpus is OMITTED; a
supported one carries only the CURRENT ev id); anti-poisoning (UNSUPPORTED-verdict prior excluded); read-only
(missing-db read creates nothing + fail-opens; write_claim on a read_only store raises); flag case-normalize
matrix; empty advisory block. Plus 9 verified_claim_graph no-regression (read_only param additive). `py_compile`
OK on all 5 source files.

## Verdict

Reuse is mechanically fail-closed (omit-unless-current-supported, current ev ids only, no prior provenance),
read-only + fail-open, campaign-scoped with default-None back-compat, default-OFF, anti-poisoning + verified
core + strict_verify untouched, offline-tested. Both gates APPROVE. Ready to queue for operator merge.
