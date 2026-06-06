# FX-07 (#1110) leg-1 diff-gate — ITER 1 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope — this PR is FX-07 leg 1 (footer) ONLY

FX-07 in the plan folds 4 legs. The plan (`fix_campaign_plan.md` FX-07, line 128)
explicitly allows the footer/provenance leg to land independently. Legs 2-4 are
split to **FX-07b (#1111)** because their plan line-numbers do NOT match the
running system (verified: the cited `honest_sweep_integration.py:637-648` is the
Phase-1 retrieval-coverage synth, not a report-coverage path that carries
strict_verify drops; `citation_mapper.py` is in `synthesis/` not `generator/`).
Please review ONLY leg 1 here; do not REQUEST_CHANGES for the deferred legs.

## Bug leg 1 fixes (BUG-08/09 footer contradiction)

`compose_methods_disclosure` emitted "Frame coverage: all N contract-required
entities populated with **bound evidence**" whenever gap+partial+pipeline_fault
were all zero — even when PASS entries were `abstract_only` / `metadata_only`
(NOT full text). On the REAL held drb_72 manifest that meant "all 7 bound" while
4 of 7 entries were abstract/metadata-only and the body said frey_osborne "did
not survive strict verification". A footer contradicting the body breaks
chain-of-evidence consistency.

## Fix (diff: `.codex/I-ready-017/fx07_codex_diff.patch`, vs FX-05 tip `894ecb7c`)

In `compose_methods_disclosure`: count PASS-status entries whose
`provenance_class in {abstract_only, metadata_only}` as `shallow_entries`;
include `shallow_count` in `has_issues`; report
"Fully populated (full-text bound evidence): {pass_count - shallow_count}" and a
"Populated from abstract/metadata only (full text NOT retrieved): K (names)"
line. "all N … bound evidence" now fires ONLY when every pass entry is
`open_access`. Pure deterministic prose; manifest KEY shape unchanged.

## Evidence
- **§-1.1 audit on REAL output** (`outputs/audits/I-ready-017/fx07_s11_audit.md`):
  the held drb_72 `frame_coverage_report` replayed through the new footer →
  "Fully populated (full-text bound evidence): 3" + names the 4
  abstract/metadata-only entities; no longer "all 7 bound". PASS.
- **Offline smoke:** `pytest tests/polaris_graph/test_m60_frame_manifest.py` →
  27 passed (25 pre-existing, 2 label assertions updated to the new wording, +2
  new leg-1 behavior tests: real-shape 3-full-text/4-shallow → not "all bound" +
  names the 4; all-open_access → "all N bound").

## Faithfulness-invariant check
No change to provenance / strict_verify / 4-role. Leg 1 only changes
deterministic methods-disclosure prose (a label, not a re-classification).

## Question
Is leg 1 correct and faithfulness-safe — footer no longer claims "all bound"
when pass entries are abstract/metadata-only, "all N bound" reserved for
all-open_access, manifest shape unchanged? (Legs 2-4 are FX-07b #1111.) Anything
blocking leg 1?
