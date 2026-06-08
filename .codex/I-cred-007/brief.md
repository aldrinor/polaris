# I-cred-007 (#1156) — Phase 7: NEUTRAL both-sides disclosure composer (pure module) — BRIEF for Codex

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Reserve P0/P1 for real execution risks; classify the rest P3/P2/cosmetic.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE'd on remaining-non-P0/P1; no iter 6.
- Surface any held-back P1 NOW. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Reviewing a DESIGN BRIEF (acceptance-criteria correctness), not a diff.

## 0. HARD CONSTRAINTS (operator-locked — not relaxable)

- **Neutral framing (operator Decision 2):** show each side as a LEGITIMATE position with its evidence weight — NOT as "warning/fringe/misinformation". The user judges; POLARIS discloses weight honestly. No judgemental labels.
- **Always-visible forewarning** (the N=887 finding): the both-sides disclosure is rendered, not hidden behind an expand affordance (rendering venue is the report artifact; UI affordance is downstream).
- **Advisory / disclosure ONLY.** A SEPARATE disclosure block appended AFTER verified prose (like `limitations_text`). NEVER edits verified sentences, NEVER runs inside `strict_verify`, NEVER touches the 4-role D8 release gate. strict_verify's six checks stay the only binding faithfulness gate.
- **Default-OFF byte-identical:** `PG_SWEEP_BOTHSIDES_DISCLOSURE` (no production caller; pure library).
- **Pure**, snake_case, explicit imports, no mutation of inputs, no network, no faithfulness-file import, LAW VI.
- **Weight = the Phase-6 origin-cluster weight-mass**, never headcount. Both sides get their honest weight + independent-origin count + cited evidence_ids.

## 1. Goal

`src/polaris_graph/synthesis/both_sides.py`: given the Phase-5 contradiction edges + the Phase-6 weight-mass + the atomic claims, compose a NEUTRAL both-sides disclosure block per CONTESTED claim (a claim cluster pair joined by a `ContradictionEdge`), showing each side's weight-mass, its independent-origin count, and its cited `evidence_id`s — in neutral language. This is Layer 6 of the redesign (operator Decision 2, plan §9.3).

## 2. Contract

```python
PG_SWEEP_BOTHSIDES_DISCLOSURE  # flag; bothsides_disclosure_enabled() + _OFF_VALUES frozenset (match siblings)

@dataclass
class SidePosition:
    claim_cluster_id: str
    subject: str
    predicate: str
    weight_mass: float            # from Phase-6 ClaimWeightMass
    independent_origin_count: int
    evidence_ids: tuple           # the cited evidence for this side (for one-click span access)

@dataclass
class BothSidesBlock:
    subject: str                  # the contested topic ("on <subject>, sources diverge")
    sides: list                   # 2+ SidePosition, ordered by weight_mass DESC (highest-weight first, NOT "correct" first)
    source: str                   # which detector raised the contradiction (numeric/qualitative/semantic)
    severity: str

def compose_both_sides(
    contradiction_edges: list,    # Phase-5 ContradictionEdge (subject, predicate, claim_cluster_ids, evidence_ids, severity)
    weight_mass: list,            # Phase-6 ClaimWeightMass list (claim_cluster_id -> weight_mass, independent_origin_count)
    claims: list,                 # Phase-5 AtomicClaim list (claim_cluster_id -> subject/predicate/evidence_ids)
) -> list[BothSidesBlock]:
    ...

def render_both_sides(blocks: list[BothSidesBlock]) -> str:
    """Neutral markdown disclosure section. Empty string if no blocks (default-OFF byte-identity)."""
    ...
```

**Mapping:** for each `ContradictionEdge`, its two `claim_cluster_ids` are the two sides; join each to its `ClaimWeightMass` (weight_mass + independent_origin_count) and to its `AtomicClaim`s (subject/predicate/evidence_ids). Order sides by weight_mass DESC (disclose which side has more evidence weight — NOT which is "true"). Render neutrally: e.g. "On <subject>, the evidence diverges: one set of sources reports <A> (evidence weight W_a across N_a independent origins); another reports <B> (weight W_b across N_b origins). Cited spans: [...]. Weigh both."

## 3. Neutral-language guardrail (tested)

`render_both_sides` MUST NOT emit any judgemental framing label. A test asserts the rendered text contains NONE of: `fringe`, `misinformation`, `debunked`, `conspiracy`, `warning`, `unreliable`, `false claim`, `discredited` (case-insensitive). Approved vocabulary: "sources diverge / disagree", "reported values range", "evidence weight", "independent origins". (The generator codebase is already clean of these labels — keep it so.)

## 4. Acceptance criteria (offline, deterministic, no network)

1. Flag default-OFF (`bothsides_disclosure_enabled()` false unset; on-values flip it) — matches siblings.
2. A single ContradictionEdge between cluster A (weight 0.9, 3 origins) and B (weight 0.2, 1 origin) → one BothSidesBlock with 2 sides ORDERED by weight DESC (A first), each carrying its weight_mass + independent_origin_count + evidence_ids.
3. `render_both_sides` is byte-empty for `[]` blocks (default-OFF byte-identity precondition).
4. Neutral-language guardrail: the rendered text contains NONE of the banned labels (§3) and DOES carry both sides' weights + a "weigh both / the evidence diverges" neutral frame.
5. A claim cluster with NO contradiction edge produces NO block (only CONTESTED claims get a both-sides block).
6. Both sides are shown even when one side's weight is far lower — the low-weight side is NOT dropped or hidden (operator Decision 2: show both as legitimate); only ORDERED by weight.
7. A ContradictionEdge whose claim_cluster_id is missing from the weight_mass input → that side's weight defaults to 0.0 with origin_count 0 (fail-soft disclosure, never a crash, never a fabricated weight).
8. Purity: inputs not mutated; deterministic block + side ordering; no faithfulness import.

## 5. Files I have ALSO checked and they're clean (substrate scan — please VERIFY)

- `generator/multi_section_generator.py:4381` `generate_multi_section_report` → `MultiSectionResult` (280); `limitations_text` (≈289) is the precedent for a standalone disclosure section appended AFTER verified prose. P7 outputs a string the caller appends the SAME way; P7 itself does NOT edit `generate_multi_section_report` (the wiring is the caller's job / a later step).
- `generator/provenance_generator.py:1889` `resolve_provenance_to_citations` renders verified prose + bibliography — P7 does NOT touch it.
- `synthesis/claim_graph.py:151-167` `ContradictionEdge{source, subject, predicate, evidence_ids, claim_cluster_ids, severity}`; `AtomicClaim{evidence_id, subject, predicate, claim_cluster_id}`.
- `synthesis/weight_mass.py:71-79` `ClaimWeightMass{claim_cluster_id, weight_mass, independent_origin_count, contributions}`.
- `generator/contradiction_hedging.py` — existing section-local hedging is PROMPT-only (an LLM reminder), NOT a final disclosure artifact; P7 is the structured both-sides disclosure, orthogonal.
- Generator code is CLEAN of judgemental labels (no fringe/misinformation/warning framing) — P7 keeps it neutral.
- `provenance_generator.py:438-441` SentenceVerification disclosure fields are Phase-8's job (per-claim confidence); P7 (contested-claim both-sides) is orthogonal but shares the default-OFF inert-plumbing pattern.

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

## 7. Questions for you

1. Side ordering by weight_mass DESC — right for honest disclosure (shows which side has more evidence weight without calling it "true")? Or alphabetical/stable to avoid implying ranking?
2. Should `compose_both_sides` emit a block for EVERY severity, or only `severity >= review`/a threshold? I lean every edge (recall-first; the caller/UI can filter), but want your call.
3. Confirm P7 ships as the pure composer ONLY; wiring the block into `generate_multi_section_report` + the UI affordance is a separate step (I-cred-007b), keeping this faithfulness-safe and default-OFF.
