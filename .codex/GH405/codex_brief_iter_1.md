Review brief for GH#405 I-tpl-009 — corpus-threshold calibration for emerging-policy domains.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Context

GH#405 closes the Carney delivery blocker: Q1 (AI sovereignty), Q2 (Canada-US), Q3 (workforce), Q4 (housing) all aborted with `abort_corpus_inadequate` in the full BEAT-BOTH sweep. Only Q5 (pharmacare) produced a report. The §-1.2 diagnosis (already Codex-approved at iter1 CONFIRMED_WITH_CAVEATS in `.codex/GH405/codex_q1_q4_abort_diagnosis_iter_1.txt`) established root cause:

- `_DEFAULT_DOMAIN_THRESHOLDS` (`src/polaris_graph/nodes/corpus_adequacy_gate.py:70-99`) has entries for clinical / policy / tech / due_diligence only.
- ai_sovereignty / canada_us / workforce scope templates exist (GH#196/197/198) but lack adequacy entries — fall through to clinical-shaped `AdequacyThresholds()` defaults (min_t1=2, min_t1+t2=3) which are structurally impossible for emerging-policy (no peer-reviewed primary trials on these topics).
- Q4 (housing/policy) hits the existing `policy` entry but its min_t1=1 still aborts on T1=0.

Codex iter-1 diagnosis additional findings (must address):
1. Scope templates have `expected_tier_distribution` only — no corpus_adequacy override block reaches the gate. Verify this.
2. `min_t3_plus_t4_plus_t6` floor needs AdequacyThresholds + assess_corpus_adequacy + tests + manifest serialization extension.
3. Q3 workforce had T3=0 (T4=7, UNKNOWN=1). Even `min_t1+t2+t3≥1` would fail.

# Files I have ALSO checked and they're clean

- `src/polaris_graph/retrieval2/corpus_adequacy_gate.py` — separate slice-002 file with `ClinicalTemplate` dataclass; uses different schema (`min_t1/t2/t3`). Not on the sweep code path. Sweep uses `src/polaris_graph/nodes/corpus_adequacy_gate.py` (per `scripts/run_honest_sweep_r3.py:96,1486-1491` import + call). retrieval2 is the API path; nodes is the sweep path. Keep retrieval2 unchanged in this PR.
- `src/polaris_graph/api/retrieval_route.py:152` — references "corpus_adequacy_gate" as a pipeline_stage label string; no behavior change needed.
- `src/polaris_graph/audit_ir/regression_alerts.py:243-256` — reads adequacy.decision (proceed | expand | abort); no API break if we don't change those return values.
- `src/polaris_graph/evaluator/evaluator_gate.py:105` — consumes adequacy report; doesn't depend on threshold values.
- `src/polaris_graph/generator2/section_blueprint.py:175` — consumes adequacy verdict shape; not blocked by adding new finding.
- `tests/polaris_graph/test_corpus_adequacy_r6_gap1.py` — existing tests for nodes/ gate. Must remain green.
- `tests/polaris_graph/retrieval2/test_corpus_adequacy_gate.py` — tests for separate retrieval2 gate. Not affected.
- `scripts/run_honest_sweep_r3.py:1486-1504` — sweep call site. Passes `domain=q["domain"]` directly. The Q1-Q4 manifests confirm domain strings = "ai_sovereignty", "canada_us", "workforce", "policy".
- `config/scope_templates/{ai_sovereignty,canada_us,workforce,policy}.yaml` — checked for `corpus_adequacy:` block. Grep for `min_t1|min_total_sources|corpus_adequacy|thresholds:` returned EMPTY. Confirms Codex finding #1: scope templates carry no adequacy override.

# Proposed fix scope (Phase 1 — this PR)

## 1. Schema extension: `AdequacyThresholds`

Add one new field:

```python
@dataclass
class AdequacyThresholds:
    # ... existing fields unchanged ...
    min_t3_plus_t4_plus_t6: int = 0   # NEW: emerging-policy quality floor
```

Backwards-compatible: default 0 = no constraint, existing behavior preserved.

## 2. New domain entries in `_DEFAULT_DOMAIN_THRESHOLDS`

```python
"ai_sovereignty": AdequacyThresholds(
    min_total_sources=8,
    min_t1_count=0,                 # no peer-reviewed clinical trials exist
    min_t1_plus_t2=0,
    min_t1_plus_t2_plus_t3=0,
    min_t3_plus_t4_plus_t6=4,       # gov + think-tank + advocacy density
    min_evidence_rows=5,
    max_t5_plus_t6_fraction=0.80,
    max_t7_fraction=0.40,
),
"canada_us": AdequacyThresholds(
    min_total_sources=8,
    min_t1_count=0,
    min_t1_plus_t2=0,
    min_t1_plus_t2_plus_t3=0,
    min_t3_plus_t4_plus_t6=4,
    min_evidence_rows=5,
    max_t5_plus_t6_fraction=0.80,
    max_t7_fraction=0.40,
),
"workforce": AdequacyThresholds(
    min_total_sources=6,             # workforce evidence is thinner
    min_t1_count=0,
    min_t1_plus_t2=0,
    min_t1_plus_t2_plus_t3=0,
    min_t3_plus_t4_plus_t6=4,
    min_evidence_rows=5,
    max_t5_plus_t6_fraction=0.85,    # more tolerance for think-tank/advocacy
    max_t7_fraction=0.40,
),
```

Relax existing `policy` for emerging-policy:

```python
"policy": AdequacyThresholds(
    min_total_sources=8,
    min_t1_count=0,                  # WAS 1; emerging policy lacks T1
    min_t1_plus_t2=0,                # WAS 2
    min_t1_plus_t2_plus_t3=2,        # WAS 5; relax — gov sources are bonus not floor
    min_t3_plus_t4_plus_t6=5,        # NEW: real quality signal for policy
    min_evidence_rows=5,
    max_t5_plus_t6_fraction=0.60,
    max_t7_fraction=0.40,
),
```

## 3. Threshold check in `assess_corpus_adequacy`

Add one line after the existing checks (~line 186):

```python
t4 = tier_counts.get("T4", 0)
_record("t3_plus_t4_plus_t6", t3 + t4 + t6,
        thr.min_t3_plus_t4_plus_t6, "min")
```

`_record` already handles severity classification (ok / warn / critical).

## 4. Protocol passthrough

Extend `_get_thresholds` to read `min_t3_plus_t4_plus_t6` from protocol's corpus_adequacy block:

```python
return AdequacyThresholds(
    # ... existing fields ...
    min_t3_plus_t4_plus_t6=int(ca.get("min_t3_plus_t4_plus_t6",
                                       base.min_t3_plus_t4_plus_t6)),
)
```

## 5. Manifest serialization

No changes needed — `asdict(thr)` already serializes all dataclass fields, and `AdequacyFinding` already has the structure to carry the new finding.

## 6. Tests

Add to `tests/polaris_graph/test_corpus_adequacy_r6_gap1.py`:

```python
def test_ai_sovereignty_emerging_policy_proceeds():
    # Q1 actual: 13 sources, T3=2, T4=5, T6=3, T7=2, UNKNOWN=1
    adequacy = assess_corpus_adequacy(
        tier_counts={"T3": 2, "T4": 5, "T6": 3, "T7": 2, "UNKNOWN": 1},
        evidence_row_count=11,
        domain="ai_sovereignty",
    )
    assert adequacy.decision in ("proceed", "expand"), (
        f"expected proceed/expand, got {adequacy.decision}: {adequacy.notes}"
    )
    # Verify the new finding exists
    finding_names = {f.name for f in adequacy.findings}
    assert "t3_plus_t4_plus_t6" in finding_names

def test_canada_us_emerging_policy_proceeds():
    # Q2 actual: 20 sources, T3=1, others
    adequacy = assess_corpus_adequacy(
        tier_counts={"T3": 1, "T4": 10, "T6": 4, "T7": 4, "UNKNOWN": 1},
        evidence_row_count=19,
        domain="canada_us",
    )
    assert adequacy.decision in ("proceed", "expand")

def test_workforce_t4_only_proceeds():
    # Q3 actual: T4=7, UNKNOWN=1 (T3=0 too)
    adequacy = assess_corpus_adequacy(
        tier_counts={"T4": 7, "UNKNOWN": 1},
        evidence_row_count=7,
        domain="workforce",
    )
    assert adequacy.decision in ("proceed", "expand"), (
        f"T4-only workforce evidence should pass: {adequacy.notes}"
    )

def test_housing_policy_proceeds_after_relax():
    # Q4 actual: T3=1, T4=13, T6=2, T7=3, UNKNOWN=1
    adequacy = assess_corpus_adequacy(
        tier_counts={"T3": 1, "T4": 13, "T6": 2, "T7": 3, "UNKNOWN": 1},
        evidence_row_count=18,
        domain="policy",
    )
    assert adequacy.decision in ("proceed", "expand")

def test_clinical_still_strict():
    # Regression: clinical should still demand T1+T2
    adequacy = assess_corpus_adequacy(
        tier_counts={"T3": 5, "T4": 5},  # 10 sources but no T1/T2
        evidence_row_count=10,
        domain="clinical",
    )
    assert adequacy.decision == "abort"
```

# Out of scope (follow-up issue)

- Scope template → protocol.json corpus_adequacy passthrough wiring (Codex iter-1 caveat #1). For Phase 1, hardcoded `_DEFAULT_DOMAIN_THRESHOLDS` entries are sufficient because `domain` is passed directly from sweep questions.
- Tier-classifier improvement to recognize gov-stats agencies (StatsCan, BLS, OECD) as T3 instead of T4/UNKNOWN. Phase 1 accepts T4-only for workforce.

# Acceptance

- `_DEFAULT_DOMAIN_THRESHOLDS` has entries for ai_sovereignty / canada_us / workforce
- Relaxed `policy` entry uses min_t3_plus_t4_plus_t6 as the real quality floor
- `assess_corpus_adequacy` emits a `t3_plus_t4_plus_t6` finding
- All 5 new tests pass (4 emerging-policy proceed + 1 clinical regression)
- All existing tests pass (`pytest tests/polaris_graph/test_corpus_adequacy_r6_gap1.py tests/polaris_graph/retrieval2/test_corpus_adequacy_gate.py`)
- Smoke: rerun Q1 alone → status≠abort_corpus_inadequate
- Full sweep: Q1-Q5 all generate reports
- Reports line-by-line audited per §-1.1

# Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
