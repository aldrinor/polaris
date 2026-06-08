# I-cred-008 (#1157) — Phase 8: per-claim disclosure POPULATION (pure module) — BRIEF for Codex

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. Reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE'd on remaining-non-P0/P1; no iter 6.
- Surface any held-back P1 NOW. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Reviewing a DESIGN BRIEF (acceptance-criteria correctness), not a diff.

## 0. HARD CONSTRAINTS (operator-locked)

- **ADVISORY / disclosure ONLY.** Populating the 4 disclosure fields NEVER changes `is_verified` or any of `strict_verify`'s six checks — they remain the only binding faithfulness gate. The fields are side-outputs.
- **DEFAULT-OFF byte-identical:** reuse the credibility-disclosure flag (`PG_SWEEP_CREDIBILITY_DISCLOSURE`, the one the Phase-1 schema docstring names) — confirm the exact flag name with me. No production caller is added.
- **Pure**, snake_case, explicit imports, NO mutation of the input verifications (return NEW SentenceVerification copies via `dataclasses.replace`), no network, LAW VI.
- **Span verdict is SUPPORTS, not EXISTS** (operator): the label reflects that the cited span SUPPORTS the claim (verified), PARTIAL, or UNSUPPORTED — never a bare "exists".

## 1. SCOPE (confirm the split)

This issue ships the pure **POPULATION** function only: compute the 4 disclosure fields per sentence from the already-computed upstream signals. The **RENDER** (surfacing the fields in the report — the flag-gated additive edit to `provenance_generator.resolve_provenance_to_citations` / `multi_section_generator`) is the gate-touching follow-up I-cred-008b (it edits the faithfulness file's render path, so it lands with its own brief + flag). **Q1:** confirm this split.

## 2. Goal

`src/polaris_graph/generator/disclosure_population.py` (or `synthesis/`): given the post-`strict_verify` `SentenceVerification` list + the Phase-2 credibility judgments + the Phase-4 per-evidence origin assignments + (optionally) Phase-6 weight-mass, return NEW `SentenceVerification`s with the 4 inert Phase-1 fields populated: `span_verdict`, `credibility_weight`, `independent_origin_count`, `certainty_label`.

## 3. Contract + the 4 field rules (please rule on each)

```python
def populate_disclosure(
    verifications: list,          # SentenceVerification (carry .tokens[].evidence_id, .is_verified, .failure_reasons)
    credibility_by_evidence: dict, # evidence_id -> Phase-2 credibility_weight
    origin_by_evidence: dict,      # evidence_id -> Phase-4 origin_cluster_id
    *,
    weight_by_origin: dict | None = None,  # origin_cluster_id -> Phase-6 weight_mass (optional)
) -> list:                         # NEW SentenceVerifications, inputs untouched
    ...
```

Per sentence (its cited evidence = `{t.evidence_id for t in sv.tokens}`):
- **`span_verdict`** = `"SUPPORTS"` if `sv.is_verified` else `"UNSUPPORTED"`. (Q2: do you want a `"PARTIAL"` tier — e.g. some-but-not-all tokens verified — or is binary SUPPORTS/UNSUPPORTED right for a per-sentence verdict? The sentence is already all-or-nothing post strict_verify, so I lean binary.)
- **`independent_origin_count`** = number of DISTINCT `origin_cluster_id`s among the sentence's cited evidence (Phase-4). An evidence with no origin mapping counts as its own origin (uncollapsed). This is the honest "N sources → M independent origins".
- **`credibility_weight`** = (Q3) the **minimum** credibility_weight across the sentence's cited evidence (conservative — the sentence is only as credible as its weakest cited source), OR the canonical/median? I lean MIN (conservative, hardest to game). Absent judgments → `None` (unknown, not fabricated).
- **`certainty_label`** = derived deterministically from `(is_verified, independent_origin_count, credibility_weight)` via env-overridable thresholds: e.g. `high` iff verified AND ≥2 independent origins AND credibility ≥ HIGH_THRESH; `low` iff unverified OR 1 origin OR credibility < LOW_THRESH; else `moderate`. (Q4: confirm the bucketing + that it is advisory, never a gate.)

## 4. Acceptance criteria (offline, deterministic, no network)

1. Flag default-OFF helper (matches the Phase-1 disclosure flag).
2. Population NEVER changes `is_verified` / `failure_reasons` / `tokens` / `sentence` (only the 4 disclosure fields differ between input and output); inputs are not mutated (assert by identity + content).
3. `span_verdict` = SUPPORTS for a verified sentence, UNSUPPORTED for an unverified one.
4. `independent_origin_count` = distinct origin clusters among cited evidence (2 evidence in 1 origin → 1; 2 evidence in 2 origins → 2; evidence with no mapping → own origin).
5. `credibility_weight` = MIN over cited evidence (or the agreed rule); absent judgments → None.
6. `certainty_label` buckets per the agreed thresholds; env knob changes a boundary case; the label is NOT consulted by any verifier.
7. A sentence with NO tokens → all 4 fields safe defaults (span_verdict per is_verified, origin_count 0, credibility None, certainty low), no crash.
8. Purity: no faithfulness-gate import that could change behaviour; `strict_verify` is NOT re-run.

## 5. Files I have ALSO checked and they're clean (substrate scan — please VERIFY)

- `generator/provenance_generator.py:419-441` `SentenceVerification` carries `.tokens` (each a ProvenanceToken with `.evidence_id`), `.is_verified`, `.failure_reasons`, and the 4 Phase-1 disclosure fields (`span_verdict`, `credibility_weight`, `independent_origin_count`, `certainty_label`, all default-inert). Phase-1 proved these are NEVER inputs to `is_verified` / strict_verify.
- `authority/credibility_skill.py` `CredibilityJudgment{evidence_id, credibility_weight}` — Phase-2 source.
- `synthesis/independence_collapse.py` `RowOriginAssignment{evidence_id?/row_index, origin_cluster_id}` — Phase-4 source (caller passes evidence_id -> origin_cluster_id).
- `synthesis/weight_mass.py` `ClaimWeightMass` — Phase-6 (optional; not required for the per-sentence fields).
- The RENDER path `resolve_provenance_to_citations` is NOT touched here (I-cred-008b).

## 6. Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## 7. Questions

Q1 scope split (population now, render I-cred-008b)? Q2 binary SUPPORTS/UNSUPPORTED vs add PARTIAL? Q3 credibility_weight = MIN over cited evidence? Q4 certainty bucketing thresholds + advisory-only? Q5 exact flag name (`PG_SWEEP_CREDIBILITY_DISCLOSURE` or another)?
