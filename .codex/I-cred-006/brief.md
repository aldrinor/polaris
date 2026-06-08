# I-cred-006 (#1155) — Phase 6: origin-cluster weight-mass aggregator (pure module) — BRIEF for Codex

HARD ITERATION CAP: 5 per document. This is iter 2 of 5. (See §7 ITER-1 RESOLUTIONS — they supersede §3 Q2 / §4 AC2.)
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; classify the rest P3/P2/cosmetic.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE'd on remaining-non-P0/P1; no iter 6.
- Surface any held-back P1 NOW. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Reviewing a DESIGN BRIEF (acceptance-criteria correctness), not a diff.

## 0. HARD CONSTRAINTS (operator-locked — not relaxable)

- **Advisory only.** Weight-mass is a DISCLOSED side-output. The 4-role D8 release policy (`roles/release_policy.py` `apply_d8_release_policy`, `roles/sweep_integration.py` `run_four_role_evaluation`) remains the SINGLE BINDING release gate; `strict_verify`'s six checks remain the only binding faithfulness gate. P6 does NOT touch either.
- **Default-OFF byte-identical:** `PG_SWEEP_WEIGHT_MASS` (no production caller; pure library).
- **Pure**, snake_case, explicit imports, no row mutation, no network, no faithfulness-file import, LAW VI (env-overridable thresholds).
- **Copies contribute ZERO** to the mass (the vax-defense). Mass uninflatable by copies (origin-cluster invariant per #1161).

## 1. SCOPE (please confirm the split)

This issue ships ONLY the **pure weight-mass aggregator module** `src/polaris_graph/synthesis/weight_mass.py`. The three GATE-TOUCHING parts the plan groups under "Phase 6" are DEFERRED to a wiring follow-up (matching your P2 note "wire before independence-aware downstream wiring"), because they modify faithfulness-adjacent gates and should land with their own brief + flag:
- (a) REMOVING the journal count-floor (`nodes/journal_only_filter.py:531` `DEFAULT_MIN_DISTINCT_JOURNALS=12`, `assess_journal_only_adequacy`),
- (b) wiring weight-mass INTO `nodes/corpus_adequacy_gate.py` (`assess_corpus_adequacy`),
- (c) the per-claim clinical source-type veto (kept DISTINCT from the corpus clinical adequacy floor per your #1161 ruling).

**Question Q1:** confirm this scope split (pure aggregator now; gate-wiring + journal-floor removal + clinical veto as I-cred-006b with its own flag), OR tell me to fold (a)/(b)/(c) into this issue.

## 2. Goal

`weight_mass.py`: given the evidence rows (carrying `origin_cluster_id` from P4), the atomic claims (P5, `claim_cluster_id` + `evidence_id`), and the credibility judgments (P2, per `evidence_id`), compute per claim cluster a **weight-mass** = Σ over INDEPENDENT origin clusters of `cluster_mass`, where `cluster_mass = authority_score(canonical_origin) × credibility_weight(canonical_origin)` and every derivative copy contributes ZERO. Plan §148 is the executable spec.

## 3. Contract

```python
PG_SWEEP_WEIGHT_MASS  # flag; weight_mass_enabled() + _OFF_VALUES frozenset (match supersession/claim_graph/credibility_skill)

@dataclass
class OriginContribution:
    origin_cluster_id: str
    canonical_evidence_id: str
    authority_score: float          # of the canonical origin
    credibility_weight: float       # P2 weight of the canonical origin (1.0 if no judgment present)
    cluster_mass: float             # = authority_score * credibility_weight
    copy_count: int                 # derivative copies attributed to this origin (disclosure: "N copies -> 1 origin")

@dataclass
class ClaimWeightMass:
    claim_cluster_id: str
    weight_mass: float              # Σ cluster_mass over independent origins in this claim cluster
    independent_origin_count: int
    contributions: list[OriginContribution]

def aggregate_weight_mass(
    claims: list,                   # P5 AtomicClaim list (claim_cluster_id + evidence_id)
    rows: list[dict],               # evidence rows carrying origin_cluster_id + authority_score
    judgments: list,                # P2 CredibilityJudgment list (evidence_id -> credibility_weight)
    *,
    independence: Optional[...] = None,  # P4 result (canonical per origin_cluster_id); see Q2
) -> list[ClaimWeightMass]:
    ...
```

**Aggregation rule:** group supporting rows by `(claim_cluster_id, origin_cluster_id)`; for each origin cluster pick the CANONICAL row (P4's canonical for that `origin_cluster_id`); `cluster_mass = authority_score(canonical) × credibility_weight(canonical)`; copies (same `origin_cluster_id`, non-canonical) contribute ZERO but increment `copy_count`. `weight_mass(claim) = Σ cluster_mass` once per origin cluster. NO row-level term, NO averaging, NO max-over-copies.

**Question Q2:** the canonical-origin designation lives in P4's `RowOriginAssignment` (`is_canonical_origin` / `canonical_index`), not on the row dict. Should P6 (i) take the P4 `IndependenceCollapseResult` as an input and read canonical from it, or (ii) require the rows to already carry an `is_canonical_origin` bool + `origin_cluster_id` (caller merges P4 onto rows first)? I lean (ii) — keeps P6 a pure dict-in function and matches how P4 emits per-row assignments — but want your call.

**Question Q3:** when a canonical origin has NO P2 judgment (credibility skill OFF / not run), use `credibility_weight = 1.0` (mass = pure authority) — confirm that is the right neutral, vs dropping the origin.

## 4. Acceptance criteria (offline, deterministic, no network)

1. Flag default-OFF (`weight_mass_enabled()` false unset; on-values flip it) — matches siblings.
2. Single origin cluster of N rows (1 canonical + N-1 copies) → `weight_mass == authority(canonical) × credibility_weight(canonical)`, `independent_origin_count == 1`, `copy_count == N-1`. **Adding more copies of ANY authority does NOT change weight_mass** (the vax invariant — direct test).
3. Two INDEPENDENT origin clusters supporting one claim cluster → weight_mass = sum of the two cluster masses; each counted once.
4. A copy whose own `authority_score` / `credibility_weight` is HIGHER than its canonical contributes ZERO (mass uses the CANONICAL only).
5. Canonical with no P2 judgment → `credibility_weight = 1.0` (mass = authority).
6. Distinct claim clusters aggregate independently (no cross-claim bleed).
7. Missing `authority_score` on a canonical → treated as 0.0 (no crash), surfaced in the contribution (fail-soft on a disclosure signal, never a NaN mass).
8. Purity: no row mutation; no faithfulness import; deterministic ordering of contributions.

## 5. Files I have ALSO checked and they're clean (substrate scan — please VERIFY)

- `synthesis/independence_collapse.py` — P4 emits `RowOriginAssignment{row_index, origin_cluster_id, canonical_index, is_canonical_origin, is_derivative_copy}` + `OriginCluster`. Canonical per origin_cluster is stable (#1161: dated=earliest-date; undated=lowest-authority, no inflation).
- `synthesis/claim_graph.py` — P5 `AtomicClaim{evidence_id, claim_cluster_id, ...}`; join key `evidence_id`.
- `authority/credibility_skill.py` — P2 `CredibilityJudgment{evidence_id, credibility_weight, ...}`; advisory, default-OFF.
- `nodes/corpus_adequacy_gate.py:167-273` `assess_corpus_adequacy` (tier-count thresholds — NOT touched by this pure module; the wiring follow-up handles it).
- `nodes/journal_only_filter.py:531,543` the journal count-floor (`DEFAULT_MIN_DISTINCT_JOURNALS=12`, `assess_journal_only_adequacy`) — NOT touched here; removal is the wiring follow-up.
- `roles/release_policy.py` / `roles/sweep_integration.py` — the binding D8 gate; P6 is advisory, does NOT touch it.
- Join key `evidence_id` is the stable per-evidence id all three phases share (`schemas.py`).

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
