HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex DIFF review — I-perm-009 (#1203): behavioral replay/proof harness (Wave 0) — ITER 1 of 5

You are the ONLY gate. Review the DIFF at `.codex/I-perm-009/codex_diff.patch` (5 new files, 478 LOC, **test-only — zero production code touched**, test-bulk LOC exemption per the I-transport-001 precedent).

## What this is
The I-perm-009 proof ledger for the permanent-fix program: an OFFLINE, deterministic replay of the real D8 release decision + the §-1.1 zero-fabrication invariant over the SAVED real run `outputs/audits/beatboth8/drb_76/` (no network, no spend, no model calls). It proves each upcoming fix on real saved data BEFORE any paid re-run. This is the Wave-0 SKELETON (per blueprint §4); the full `build_native_gate_b_inputs` production replay lands with I-perm-002.

## CLAIMS LEDGER (every claim → file:line → live/staged → evidence)
1. **The replay reuses production code (zero drift), not a re-implementation.** `d8_replay_harness.py:31-46` imports the real `load_required_entities`, `validate_entity_severity`, `load_d8_policy_config`, `apply_d8_release_policy`, `CoverageLedger`, `D8ClaimRow`. VERIFY: no policy logic is copied; the harness only reconstructs INPUTS and calls the real policy.
2. **BASELINE-LOCK is faithful — reproduces the saved run bit-for-bit.** `test_drb76_baseline.py:48-79`. Evidence (ran locally): reconstructed `held_reasons == {d8_unsupported_residual_below_coverage, d8_s0_must_cover_missing:contraindications, d8_pending_rewrite}` == saved; coverage `0.40` == saved `four_role_evaluation.coverage_fraction`; needs_rewrite `10` == saved. VERIFY: the asserts compare against BOTH a hard-coded baseline AND `saved_run.saved_*` (the live manifest), so a stale hard-code cannot hide drift.
3. **§-1.1 zero-fabrication invariant is a CONTENT check, not string-presence.** `cited_span_audit.py:54-79` extracts every numeric from each claim_text (after stripping provenance tokens + numbered markers) and asserts it appears verbatim in that claim's `cited_span_text`. Evidence: 0 findings on drb_76 → mechanically re-confirms `DRB76_FORENSIC.md` "zero fabrications". VERIFY: this is numeric-grounding-in-cited-span (a faithfulness check), NOT a banned keyword-presence gate. Is the numeric regex + NFKC/thousands-separator normalization (`_normalize`, `cited_span_audit.py:48-66`) sound, or could it MISS a fabricated numeric (false-negative) or FLAG a legitimately-reformatted one (false-positive)?
4. **The I-perm-002 fix LOGIC is proven on real data (simulation).** `d8_replay_harness.py:97-145` `corpus_satisfaction=True` credits a required element + its S0 category whenever ANY VERIFIED claim cites that element's evidence_id. `test_drb76_baseline.py:96-112`: on drb_76 this credits `contraindications` from the VERIFIED Safety claims 03-001/03-002/03-005 (evidence_id `probiotic_immunocompromised_contraindication`), clears the false hold, raises coverage 0.40→0.60, and the test ASSERTS the other two holds REMAIN (does not spuriously release — those are I-perm-003/006/007 territory). VERIFY: is the simulation HONESTLY LABELLED as a sim (not claimed as the production fix)? Is crediting via `evidence_ids ∩ required_element_ids` a sound proxy for the I-perm-002 corpus-satisfaction rule, or does it over-credit (e.g. could a VERIFIED claim citing a required element's evidence_id WITHOUT genuinely supporting that S0 category falsely credit it — the cross-document safety guard R6 concern)?
5. **The proof-ledger xfail entry is honest.** `test_drb76_baseline.py:115-135` `test_iperm002_production_flip` is `xfail(strict=True)` with a reason linking #1196. VERIFY: is this a legitimate ledger marker (currently fails because the frozen production binding still holds contraindications), and is the docstring honest that it must be RE-POINTED at the production replay when I-perm-002 lands (it will not auto-flip from a code change alone, since the saved audit_map is frozen)? Flag if this xfail is misleading about what flips it.
6. **No hard-coding (LAW VI).** `saved_run_loader.py:30-37` run dir + template path default to the committed beatboth8 evidence but are env-overridable (`PG_REPLAY_RUN_DIR`, `PG_REPLAY_TEMPLATE_PATH`). Thresholds come from `load_d8_policy_config()` (the production YAML), not magic numbers.
7. **Fail-loud (LAW II).** `saved_run_loader.py:96-128` raises FileNotFoundError/KeyError on any missing artifact; never silently defaults.

## Evidence pack (ran locally, this session)
- `python -m pytest tests/polaris_graph/replay/ -v` → **6 passed, 1 xfailed in 3.43s** (the xfail is claim #5's ledger entry).
- Probe reproduction (`.codex/I-perm-009/probe_d8_replay.py`): `BASELINE-LOCK FAITHFUL: True`, required_element_ids=5, required_s0_categories=['contraindications'], covered=2 → 0.400.

## Acceptance criteria (verify the diff meets these)
- A1: replay reuses production policy (no copied logic). [claim 1]
- A2: BASELINE-LOCK reproduces saved held_reasons/coverage/needs_rewrite exactly. [claim 2]
- A3: §-1.1 zero-fabrication is a sound content check (no false-neg that lets a fabrication pass). [claim 3]
- A4: I-perm-002 sim is honestly labelled + logically sound; does not over-credit safety. [claim 4]
- A5: xfail ledger entry is honest about its flip condition. [claim 5]
- A6: LAW VI (no hard-coding) + LAW II (fail-loud) hold. [claims 6,7]
- A7: zero production code touched (additive test-only); the harness cannot alter any pipeline behavior.

## Red-team focus
Run the Codex red-team checklist (`.codex/codex_red_team_checklist.md`). The HIGHEST-stakes question: **does the §-1.1 numeric invariant (claim 3) have a false-negative path that would let a real fabrication ship undetected?** (e.g., a fabricated number that happens to be a substring of the span; a number the regex doesn't capture like "1.5-fold" or "p<0.001"; a unit-reformatted value). This is the clinical-safety load-bearing check — be adversarial.

## Output schema (REQUIRED — last `verdict:` line is parsed by CI)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
