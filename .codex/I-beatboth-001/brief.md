# Codex diff review — I-beatboth-001 (#1276): fetch-shell / boilerplate cited-span detector

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## FRONTIER-TECH MANDATE
This is a deterministic, dependency-free heuristic gate (string co-occurrence). No external library / model / runtime is introduced; nothing to date-verify. The design follows the codebase's own proven `_CHALLENGE_PAGE_COOCCURRENCE` ALL-of pattern.

## What this fixes
run7 (drb_78) P0-1: junk web-boilerplate spans passed `strict_verify` and grounded cited clinical findings — the 476-char Lancet CAPTCHA span (`ev_128`) grounded 6 top-of-report units, plus cookie banners, a Catalan 404, language-nav, citation-UI chrome, YouTube sidebars. They pass because the report prose verbatim-copies the junk span (the "self-citation hole"). This is the I-bug-775 fetch-shell class. The existing `_is_access_denial_stub`/`is_content_starved` runs at RETRIEVAL time on the full body; the per-cited-span gate (`verify_sentence_provenance`) never re-checks, so a shell in the corpus (or a shell reloaded UNTOUCHED on resume — resume_refetch STILL-SHELL) still grounds claims.

## This is a STRICTER gate (junk rejected) — it NEVER relaxes strict_verify / NLI / 4-role / provenance.

## The change (4 files)

1. **NEW `src/polaris_graph/retrieval/shell_detector.py`** — pure leaf module (stdlib-only, no network, no heavy deps). THE single source of shell vocabulary (LAW V). Owns:
   - `ACCESS_DENIAL_MARKERS`, `CHALLENGE_PAGE_COOCCURRENCE` (moved verbatim from `live_retriever`).
   - NEW high-precision classes: `SHELL_COOCCURRENCE` (cookie-consent / citation-UI / social — ALL-of tuples), `SHORT_BODY_SHELL_MARKERS` (HTTP 404/403, language-nav, paywall — fire only on a short body).
   - `is_access_denial_stub(content, max_chars=)` — behaviour-identical re-home of the prior `_is_access_denial_stub`.
   - `is_cited_span_shell(direct_quote)` — the new cited-span detector.
   - LAW VI knobs: `PG_CITED_SPAN_SHELL_DETECT` (default ON — tightening), `PG_SHELL_SHORT_BODY_MAX_CHARS` (default 3000).

2. **`provenance_generator.py`** — module-top import of the two leaf helpers (zero-cost, no cycle: `shell_detector` imports nothing from this package; this keeps the verifier off the 4712-line `live_retriever`). In `verify_sentence_provenance`'s per-token loop, AFTER the `span_invalid` check and BEFORE `valid_token_found=True`: if the cited token's source `direct_quote` is a shell, append `fetch_shell_cited_span:<eid>` and `continue` (fail-closed exactly like `span_out_of_bounds`). Multi-token rule = **option (a)**: a shell token leaves `failures` non-empty so the whole sentence drops — a shell can never ride on a real co-token.

3. **`live_retriever.py`** — re-point `_ACCESS_DENIAL_MARKERS` / `_CHALLENGE_PAGE_COOCCURRENCE` to the leaf module; `_is_access_denial_stub` delegates to `shell_detector.is_access_denial_stub(content, max_chars=_ACCESS_DENIAL_MAX_CHARS)` (passes its OWN `PG_ACCESS_DENIAL_MAX_CHARS` ceiling so it is byte-identical). Net -39 LOC (consolidation).

## §-1.3 OVERRIDE — why there is NO `weight_mass<=0` render DROP (please verify this reasoning)
The issue text asked to "gate render on weight_mass>0". Implemented as a DROP this would VIOLATE §-1.3 (operator-locked, WEIGHT-AND-CONSOLIDATE never FILTER-AND-CAP): `authority_score` is fetch-independent and is 0 for any unrated/unknown-tier venue, the run had the credibility judge OFF (priors-only), so a LEGIT span-verified source can carry `weight_mass=0` — the audit literally shows `[435] T1 wm=0.0`. The run7 CAPTCHA `ev_128` is itself `tier=T7, authority_score=None` (→ weight_mass 0). Dropping (or suppressing the corroboration count of) a zero-weight span-verified source is the AVOIDABLE B18 negligence pattern (excludes/under-counts legitimate sources). Instead, the render gate is delivered ENTIRELY by the verify wiring: a shell span → `is_verified=False` → `span_verdict != SUPPORTS` → absent from `select_unbound_supports_by_weight` (the "Corroborated Weighted Findings" surfacing) AND never increments `verified_support_origin_count`. The residual (a LEGIT zero-weight source still reading as "corroborated") is the inline per-claim weight-surfacing RENDER CONTRACT (P2-16, "UNCERTAIN — the render contract is the open design question"), split to a follow-up. Confirm: do you agree a `weight_mass<=0` drop is §-1.3-forbidden here, and that the verify-wiring render gate is sufficient + safe?

## §-1.4 behavioral proof (the effect APPEARS in the real output path, not just a unit)
`tests/polaris_graph/generator/test_fetch_shell_cited_span_ibeatboth001.py` (13 tests, all green), using the ACTUAL run7 `ev_128` CAPTCHA span (476 chars, extracted from `state/reserved_corpus_snapshots/drb_78_corpus_snapshot.json`):
- CAPTCHA-grounded claim → `verify_sentence_provenance` FAILS with `fetch_shell_cited_span:ev_128` (the self-citation hole is closed).
- Propagation: shell member → isolated `span_verdict==UNSUPPORTED` → ABSENT from `select_unbound_supports_by_weight` → `verified_support_origin_count==0` (the render gate, proven to fire — no filter).
- Multi-token: a sentence citing shell + real co-token still DROPS.
- NEGATIVES (the load-bearing test): 3 adversarial-borderline legit clinical spans STILL pass — a methods span containing "verification", a bibliography span containing "CrossRef", a nutrition span containing "cookie". No false-drop (a false-drop would itself be a §-1.3 breadth loss).
- Other shell classes (cookie banner, 404, citation-UI chrome, YouTube) detected.
- `PG_CITED_SPAN_SHELL_DETECT=0` → byte-identical legacy (the junk span verifies as before).

## Files I have ALSO checked and they're clean (adjacent-file scan)
- **Consumers of `verify_sentence_provenance`** (all funnel through the same gate → all get the fix for free): `contract_section_runner.py`, `evidence_distiller.py` (step6 verifier), `multi_section_generator.py` (atom verify, sibling re-anchor), `credibility_pass.py` `_verify_member_in_isolation` (the basket path), `clinical_generator/strict_verify.py`. None special-cases a shell; none needs a change.
- **Render paths** all read `span_verdict==SUPPORTS` / `verified_support_origin_count`: `weighted_enrichment.select_unbound_supports_by_weight` (SUPPORTS-only filter), `multi_section_generator.py:92-123` (corroboration header), `disclosure_population.py` (`verified_support_origin_count`), `both_sides.py`. All covered by the verify wiring; none touched.
- **Consumers of the re-pointed constants** `_ACCESS_DENIAL_MARKERS`/`_CHALLENGE_PAGE_COOCCURRENCE`/`_is_access_denial_stub`: only `live_retriever.py` itself (lines 2982-3018, `is_content_starved`). No other src/ or tests/ reads the private constants; tests use the public `is_content_starved`. Re-point verified byte-identical by `test_refetch_degraded_iarch011.py` + `test_resume_refetch_iarch007.py` (green).
- **Import cycle**: `live_retriever` does NOT import `provenance_generator`; `provenance_generator` does NOT import `live_retriever`; `shell_detector` imports only `os`. No cycle, no heavy import on the hot verify path.
- **Off-by-default flags untouched**: `content_quality_gate.py` (`PG_V3_CONTENT_QUALITY_GATE`) is a SEPARATE retrieval-time gate — not modified.

## Tests run (all green)
- NEW: 13/13 `test_fetch_shell_cited_span_ibeatboth001.py`.
- Regression: 79/79 across `test_provenance_generator.py`, `test_provenance.py`, `test_faith_rescue_guard.py`, `test_refetch_degraded_iarch011.py`, `test_resume_refetch_iarch007.py`, `test_a3_span_provenance_iready018.py`; 31/31 `test_weighted_enrichment_iarch007.py` + `test_credibility_pass_phase12.py`. Import sanity OK.
- Pre-existing unrelated failure: `test_provenance_generator_entailment.py` fails at COLLECTION with `ModuleNotFoundError: No module named 'polaris_graph'` (it uses a bare `from polaris_graph...` import, not `from src.polaris_graph...`) — NOT touched by this diff, fails identically on a clean tree.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Specific questions for review
1. Is the per-token loop placement correct + fail-closed (failure appended, `valid_token_found` not set, `continue`)? Any path where a shell token could still reach `valid_token_found=True`?
2. Are the new marker classes high-precision enough for **default-on**? Any phrase in `SHORT_BODY_SHELL_MARKERS` or `SHELL_COOCCURRENCE` that a legitimate clinical/biomed span could plausibly contain at <3000 chars (false-drop risk = §-1.3 breadth loss)?
3. Do you agree the `weight_mass<=0` DROP is §-1.3-forbidden and the verify-wiring render gate is the correct, sufficient implementation?
4. Is the `live_retriever` re-point genuinely byte-identical (the `max_chars=_ACCESS_DENIAL_MAX_CHARS` passthrough)?
