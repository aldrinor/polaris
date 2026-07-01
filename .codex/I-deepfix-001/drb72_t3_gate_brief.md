# Codex diff gate — drb_72 T3-targeting + weighted-gate proceed-on-skew

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## What to review

Review the unified diff at `.codex/I-deepfix-001/drb72_t3_gate.patch` (in this repo, `C:/POLARIS`). It contains the COMPLETE real change — 5 files:

1. `src/polaris_graph/retrieval/domain_backends.py` (BUILD 1 retrieval reach)
2. `src/polaris_graph/retrieval/credibility_llm_tiering.py` (BUILD 1 tier correction)
3. `scripts/run_honest_sweep_r3.py` (BUILD 2 weighted-gate proceed-on-skew)
4. `tests/polaris_graph/blockers/test_g2_runsweep_blockers.py` (BUILD 2 tests)
5. `tests/polaris_graph/test_workforce_t3_targeting.py` (BUILD 1 tests, new file)

You may read the surrounding source in `C:/POLARIS` read-only to verify context (e.g. `tier_classifier.STATISTICAL_AGENCY_DOMAINS`, `_domain_matches`, `has_usable_corpus`, `site_scoped_serper`, `disclosure_to_dict`, the `_TIER_SCHEME` text, and the pre-existing `_corpus_skew_blocks_ready` call site).

## Context — what problem this fixes (drb_72)

drb_72 is a workforce/labour-market benchmark question. The paid run reached only **T3=4** (four statistical-agency sources) and aborted with `abort_corpus_approval_denied` on a material tier-count skew. Two root causes:
- (a) RETRIEVAL REACH: `run_domain_backends` has no `workforce` branch, so the workforce domain fired ZERO statistical-agency `site:` queries; the drb_72 amplified set is journal-publisher-only. BLS / OECD / ILO / StatCan / Eurostat were under-reached.
- (b) CLASSIFICATION OVERRIDE: the run used the W5 LLM-tiering winner. Its T3 scheme text names only clinical government/regulatory bodies (FDA/EMA/WHO/CDC), NOT statistical/data agencies, so the GLM can DOWN-tier a genuine OECD/ILO page below the deterministic rules-floor's correct T3. On LLM success the LLM tier overrides the floor, suppressing the agency.
- BUILD 2: on the benchmark strict path, even with the weighted-corpus gate ON, a material tier skew RE-IMPOSED a hard tier-COUNT refusal (`abort_corpus_approval_denied`). A hard tier-COUNT refusal is itself the §-1.3 filter-by-number anti-pattern.

## Architecture DNA that governs the verdict (§-1.3)

The pipeline is WEIGHT-AND-CONSOLIDATE, not FILTER-AND-CAP. WEIGHT don't filter; CONSOLIDATE don't drop; basket faithfulness. The ONLY hard gate is the faithfulness engine (strict_verify / NLI entailment / 4-role D8 / provenance / span-grounding). Everything else is a WEIGHT or a CONSOLIDATION — never a DROP / CAP / THIN / TARGET. A change that ADDS reach or RAISES a weight is §-1.3-consistent; a hard-coded target number, a drop, a cap, or a hidden skew is a violation.

## Build reports (author's claims — VERIFY, do not trust)

```json
[
 {
  "build": "BUILD 1 — workforce T3 targeting",
  "flag": "PG_WORKFORCE_T3_TARGETING (default OFF)",
  "claim": "(i) RETRIEVAL REACH: a 'workforce' branch in run_domain_backends runs a new statistical_agency_serper backend — a (site:bls.gov OR site:oecd.org OR site:ilo.org OR site:statcan.gc.ca OR site:ec.europa.eu OR ...) OR-clause over the SAME Serper budget via the shared site_scoped_serper seam (fail-open, path-B telemetry, no new HTTP literal). ADDS agency-authoritative sources; never drops/caps/thins/filters; hard-codes NO target number. (ii) TIER CORRECTION: _floor_known_statistical_agency keeps the deterministic rules-floor tier when a source host is a KNOWN statistical-agency domain (same STATISTICAL_AGENCY_DOMAINS authority list) AND the LLM tier is LOWER credibility than the floor. Raise-to-floor WEIGHT only: never drops a source, never lowers a legitimately-higher LLM tier (T1/T2 stay), never gates release. Wired into both the batch gather-then-sort tail and the single-source classify_source_tier_llm path. OFF => byte-identical.",
  "faithfulness_neutral": true,
  "s13_consistent": true
 },
 {
  "build": "BUILD 2 — weighted-gate proceed-on-skew",
  "flag": "PG_WEIGHTED_GATE_PROCEED_ON_SKEW (default OFF)",
  "claim": "_corpus_skew_blocks_ready takes three keyword-only params (weighted_gate_on, proceed_on_skew, corpus_nonempty), all defaulting False so a positional call is byte-identical. When the kill-switch is ON AND the weighted gate is ON AND the corpus-ZERO floor passes (has_usable_corpus non-empty), a MATERIAL tier skew DISCLOSES-and-PROCEEDS (returns False) via the credibility-weighted path; a genuinely EMPTY corpus still blocks (returns True). MUST-DISCLOSE: _weighted_corpus_proceed_on_skew_disclosure builds a discrete proceed_on_skew decision record (gate, action, reason, had_material_deviation, tier_counts, tier_fractions, total_sources) injected into the credibility-disclosure dict (rides every manifest exit path + corpus_credibility_disclosure.json), plus the approval note and a run log line both disclose the relaxation. None when not fired => byte-identical OFF. This is the pre-generation CORPUS gate only; strict_verify / NLI / 4-role D8 / provenance are untouched.",
  "faithfulness_neutral": true,
  "s13_consistent": true
 }
]
```

Note on file selection: the workflow's original file list named `weighted_corpus_gate.py`, `live_retriever.py`, `config/scope_templates/workforce.yaml` — those are UNCHANGED (0 lines) so they are not in the patch; and it omitted `domain_backends.py` which IS the core retrieval-reach change, so it was added. The patch is the real, complete diff.

## Confirm STRICTLY

(a) **T3-targeting ADDS reach / corrects classification — NO drop/cap/thin, no hard-coded target NUMBER (§-1.3).** Verify `statistical_agency_serper` only ADDS `site:`-scoped hits to the corpus and that the workforce branch never removes/caps other candidates. Verify `_floor_known_statistical_agency` ONLY raises an under-tiered known-agency source up to the deterministic floor tier (`chosen rank > floor rank => return floor`; LOWER rank = HIGHER credibility) — it must NEVER lower a legitimately-higher LLM tier (T1/T2 must stay), never drop a source, never gate release. Confirm the agency host allowlist is the SAME deterministic authority list (`STATISTICAL_AGENCY_DOMAINS`) the floor uses, and that no fixed T3 target-count is hard-coded anywhere.

(b) **Weighted-gate change makes a material skew DISCLOSE-and-PROCEED (weight-not-filter) behind a default-OFF kill-switch, still refuses a genuinely EMPTY corpus, and DISCLOSES the skew (does not hide it).** Verify: with the kill-switch OFF the strict path still refuses a material deviation; with it ON + weighted gate ON + non-empty corpus it proceeds; an EMPTY corpus STILL blocks (`corpus_nonempty` gate). Verify the proceed-on-skew record carries the actual tier skew (had_material_deviation + tier_counts/fractions) and is attached to the disclosure dict / note / log — i.e. the skew is disclosed, never silently swallowed.

(c) **Frozen faithfulness engine untouched — the name-only diff must be EMPTY.** strict_verify / NLI / 4-role / D8 / provenance / span-grounding must NOT appear in the diff. Confirm every change is the pre-generation CORPUS gate + retrieval + tiering only. If any faithfulness-engine logic is altered => P0.

(d) **Byte-identical when both flags OFF.** Confirm `PG_WORKFORCE_T3_TARGETING` OFF => workforce branch `specs == []`, `_floor_known_statistical_agency` returns `chosen` unchanged, single-source path unchanged; and `PG_WEIGHTED_GATE_PROCEED_ON_SKEW` OFF => `_corpus_skew_blocks_ready` positional behavior unchanged (`bool(strict and has_material_deviation)`), disclosure helper returns None, note + log byte-identical. Also flag whether computing `_corpus_nonempty = has_usable_corpus(...)` unconditionally (even when the flag is OFF) is a behavior change (is `has_usable_corpus` a pure side-effect-free predicate?).

**Any faithfulness relaxation, any hidden-skew, any hard drop / cap / thin / hard-coded target number = P0.**

## Required output schema (YAML, last block)

```yaml
verdict: APPROVE | REQUEST_CHANGES
s13_consistent: true | false
faithfulness_neutral: true | false
frozen_engine_untouched: true | false
t3_targeting_adds_not_filters: true | false
weighted_gate_discloses_and_proceeds: true | false
default_safe_byte_identical_off: true | false
novel_p0: [...]
p1: [...]
concerns: [...]
```

Verdict APPROVE iff zero NOVEL P0 AND zero P1. End with a single final `verdict:` line.
