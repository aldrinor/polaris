REVIEW DISCIPLINE (read first): FOCUSED DIFF REVIEW of
`.codex/I-meta-005-phase-5/codex_diff.patch` against the APPROVED brief
`.codex/I-meta-005-phase-5/brief.md` (iter 2) + build_spec. Do NOT run a repo-wide
audit. Open at most the 5 changed files + the brief. 642 insertions, pure-CPU.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## What this diff is
Phase 5 (#989): dedup-by-finding + relevance-floor corpus, gated behind
`PG_USE_FINDING_DEDUP` (default OFF, byte-identical). ON-mode replaces the
`PG_LIVE_MAX_EV_TO_GEN=20` cap with a relevance floor (keep every row ≥ floor,
ranked relevance × authority) and, AFTER the Phase-3 gate, collapses rehashes of
the same numeric finding to one representative + `corroboration_count`
(independent registrable-domains; Knowledge-Based Trust, gap D).

## Files (5)
- `src/polaris_graph/synthesis/finding_dedup.py` (NEW, pure): `dedup_by_finding`
  reusing `contradiction_detector.extract_numeric_claims` (finding key) +
  `authority/corroboration.{registrable_domain,count_independent_hosts}` (hosts
  parsed from URLs). CONSERVATIVE-SINGLETON merge rule (brief §2.4).
- `src/polaris_graph/retrieval/evidence_selector.py`: `relevance_floor` mode +
  `selection_relevance` sidecar + `parse_relevance_floor` (fail-loud).
- `scripts/run_honest_sweep_r3.py`: flags + pinned order
  (floor-select → inject → gate(pre-dedup) → terminal decision → dedup → generator)
  + `manifest["finding_dedup"]`.
- `tests/.../test_finding_dedup_phase5.py`: 15 cases P5-1..P5-11.

## CRITICAL safety property to verify — NO unique-claim loss (clinical-lethal)
Two findings merge ONLY when subject is KNOWN (not the `"unknown"` fallback) +
predicate + value(rounded)+unit + EVERY extracted qualifier (dose, arm,
endpoint_phrase) equal (absent==absent ok, absent-vs-present differs). Unknown
subject → per-CLAIM singleton. A multi-finding row is retained if it is the rep of
ANY of its findings. VERIFY: (a) a same-value/different-endpoint pair stays
separate; (b) unknown-subject rows never merge; (c) a row carrying a unique finding
is never dropped; (d) `dedup_by_finding` never mutates its input (returns shallow
copies) so the Phase-3 gate's corpus is never shrunk.

## Constraints to confirm (brief §0, §2)
1. OFF byte-identity: `relevance_floor=None` → legacy max_rows path, NO new row key;
   flag default OFF → no dedup, manifest key absent.
2. Corroboration reuses corroboration.py with HOSTS (urlparse), no host/TLD literals;
   same registrable-domain (incl www. / different paths) → 1.
3. Order: dedup runs AFTER the gate (gate sees full pre-dedup set), applies to
   full-plan AND partial pruned pool.
4. `PG_RELEVANCE_FLOOR` fail-loud on invalid/out-of-range; primary trial anchors
   floor-EXEMPT (a relevant primary RCT is never dropped on a low lexical score).
5. Money: pure CPU, zero spend. snake_case; no unittest.mock in src/.

## DOCUMENTED SCOPE (Codex ruling A 2026-06-01 — already decided, do NOT relitigate)
`extract_numeric_claims` is clinical-tuned (≤1 claim/row; [] for non-clinical
numerics). So dedup + corroboration are EFFECTIVE for clinical, INERT-but-SAFE for
non-clinical (safe singletons; no false merge; no corroboration). Field-agnostic
extractor deferred to follow-up #1002. P5-8 pins the SAFE non-clinical behaviour.

## Open items I flagged (rule on these)
1. ON-mode generator pool can be larger than 20 (floor + dedup + PG_MAX_COST_PER_RUN
   bound it). Acceptable per the plan's "no arbitrary cap"?
2. P5-10 ordering covered by purity test + structural placement, not a full-sweep
   integration test (would need live retrieval). Acceptable?
3. OFF stamps NO `selection_relevance` key (stricter than the brief's both-mode
   suggestion, for true OFF byte-identity). Acceptable?

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
