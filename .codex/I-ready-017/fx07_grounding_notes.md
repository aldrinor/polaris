# FX-07 (#1110) grounding notes — frame_coverage 4-leg coupled fix

Depends on FX-01 (done). Non-rerun-gating. Base = current HEAD of bot/I-ready-017-faithfulness (FX-05 verified, 894ecb7c).

## Leg 1 — Footer (frame_manifest.py `compose_methods_disclosure`, lines 310-367)
- The "all N contract-required entities populated with bound evidence" line fires when
  `has_issues` is False (`frame_gap_count or partial_count or pipeline_fault_count` all zero).
- BUG: a slot can be `status=PASS` (→ pass_count) while its row `provenance_class` is
  metadata_only/abstract_only (NOT full text) OR strict_verify dropped its slot. Those count as
  pass → footer falsely says "all bound".
- FIX: in `compose_methods_disclosure`, count `coverage.entries` whose
  `provenance_class in {abstract_only, metadata_only}` (and, after leg 2, whose strict_verify
  kept==0). If any such → do NOT emit "all N bound"; emit the verified-and-bound count + name the
  abstract/metadata-only entities as disclosed gaps. `SlotCoverageEntry.provenance_class` is a
  string on each entry (set at frame_manifest.py:258).
- NEED: confirm `ProvenanceClass` enum string values for abstract_only / metadata_only / open_access
  (grep `class ProvenanceClass`).

## Leg 2 — Status after strict_verify (frame_manifest.py:236-249 compose_frame_coverage + honest_sweep_integration.py:637-648)
- Today status comes from validation verdict + provenance_class only (PASS / gap / partial).
- `contract_section_runner.py:854-944` ALREADY computes a per-slot generation/strict_verify result
  map. Thread it into `compose_frame_coverage`: a slot with `generated=False` OR
  `strict_verify_kept==0` → `status='generation_failed'`, `is_pipeline_fault=True` (engineer bug,
  not curator-routed). Fixes the silent pass on theory_task_framework (hard-failed 16384/16384
  narrative call) AND the all-pass count.
- NEED: read contract_section_runner.py:854-944 (the result-map shape) + how
  honest_sweep_integration calls compose_frame_coverage (637-648) to thread the new arg.

## Leg 3 — Disclosure ordering (honest_sweep_integration.py:147)
- PREPEND the Gate-B report-level `coverage_fraction` (e.g. 0.286 = 2/7) + NAME the absent required
  sources ABOVE the Phase-1 over-optimistic line, so the FIRST coverage number a reader meets is the
  Gate-B figure.
- NEED: read honest_sweep_integration.py around 140-160.

## Leg 4 — Bibliography caveats (citation_mapper.py:810+)
- Append `' (abstract only)'` / `' (metadata only — full text not retrieved)'` to bibliography
  entries from `evidence['provenance_class']`. Tier (authority) and provenance_class (fetch depth)
  stay orthogonal — a label, NOT a re-classification. Byte-unchanged for open_access.
- NEED: read citation_mapper.py around 800-860.

## Tests (test_m60_frame_manifest.py) + §-1.1
- Unit: metadata_only entry + strict_verify-dropped slot → footer NOT "all N bound" + names gaps;
  hard-failed slot → status=generation_failed; consistency invariant (no entity "pass/bound" in
  footer AND "did not survive" in body); bibliography caveat for abstract/metadata, byte-unchanged
  for open_access.
- §-1.1: fresh report.md+manifest.json claim-reconciliation per frame_coverage entry (a-e in #1110).
- Keep manifest KEY shape stable (only prose + status values change).

## Resume: author leg 1 + leg 4 (independent) first, then leg 2 + leg 3 (need the strict_verify map). One Codex gate when all 4 legs done.

## PROGRESS (2026-06-06)
- LEG 1 (footer) — DONE in frame_manifest.py compose_methods_disclosure: shallow_entries =
  PASS-status entries with provenance_class in {abstract_only, metadata_only}; included in
  has_issues; footer reports "Fully populated (full-text bound evidence): N" + a
  "Populated from abstract/metadata only (full text NOT retrieved): K (names)" line; "all N bound"
  only when zero shallow + zero gap/partial/fault. Existing test_m60 label assertions updated
  (lines 435/754). 25 test_m60 tests pass.
- TODO before gate (one gate for whole FX-07):
  - leg-1 behavior test: build FrameCoverageReport with a PASS+abstract_only entry → assert footer
    NOT "all bound" + names the entity + fully_bound count excludes it. (need SlotCoverageEntry ctor;
    see frame_manifest.py:251-292 for fields; ValidationVerdict.PASS.value for status.)
  - leg 2 (status after strict_verify): contract_section_runner.py:854-944 result map →
    compose_frame_coverage (frame_manifest.py:236-249) + honest_sweep_integration.py:637-648 threading;
    generated=False OR strict_verify_kept==0 → status='generation_failed', is_pipeline_fault=True.
  - leg 3 (disclosure ordering): honest_sweep_integration.py:147 prepend Gate-B coverage_fraction.
  - leg 4 (bibliography caveats): citation_mapper.py:810+ append abstract/metadata caveats.
  - §-1.1 audit on real report.md+manifest.json; then ONE Codex gate.
- WIP commit for leg 1 below.
