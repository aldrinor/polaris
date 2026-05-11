Diagnose why POLARIS Q1-Q4 aborted with `abort_corpus_inadequate`. Output YAML verdict.

# Evidence

## Q1 ai_sovereignty manifest (abort_corpus_inadequate)
- Domain detected: `ai_sovereignty`
- Total sources fetched: 13 (above min_total_sources=8 — fetch was OK)
- Tier counts: T3=2, T4=5 (plus others; T1=0, T2=0)
- Thresholds applied: `min_t1_count=2, min_t1_plus_t2=3, min_t1_plus_t2_plus_t3=3`
- Failed thresholds: t1_count (0<2, critical), t1_plus_t2 (0<3, critical)
- Status: `abort_corpus_inadequate`

## Q2 canada_us manifest
- Domain: `canada_us`
- Total sources: 20 (above min 8)
- Tier counts: T1=0, T2=0, T3=1
- Thresholds: same as Q1 (min_t1=2, min_t1+t2=3, min_t1+t2+t3=3)
- Failed: t1_count, t1_plus_t2, t1_plus_t2_plus_t3 (all critical)

## Q3 workforce manifest
- Domain: `workforce`
- Tier counts: T4=7, UNKNOWN=1 (T1=0, T2=0, T3=0)
- Thresholds: same as Q1 (min_t1=2)
- Failed: t1_count, t1_plus_t2, t1_plus_t2_plus_t3

## Q4 housing/policy manifest
- Domain: `policy`
- Tier counts: T3=1, T4=13, T6=2, T7=3 (T1=0, T2=0)
- Thresholds: `min_t1_count=1, min_t1_plus_t2=2, min_t1_plus_t2_plus_t3=5`
- Failed: t1_count, t1_plus_t2, t1_plus_t2_plus_t3 (all critical)

## Source code: `src/polaris_graph/nodes/corpus_adequacy_gate.py:32-99`

```python
@dataclass
class AdequacyThresholds:
    min_total_sources: int = 8
    min_t1_count: int = 2            # at least 2 peer-reviewed primary
    min_t1_plus_t2: int = 3
    min_t1_plus_t2_plus_t3: int = 3
    min_evidence_rows: int = 5
    max_t5_plus_t6_fraction: float = 0.70
    max_t7_fraction: float = 0.50
    abort_if_below_fraction: float = 0.5

_DEFAULT_DOMAIN_THRESHOLDS: dict[str, AdequacyThresholds] = {
    "clinical": AdequacyThresholds(
        min_total_sources=10, min_t1_count=3, min_t1_plus_t2=5,
        min_t1_plus_t2_plus_t3=6, ...),
    "policy": AdequacyThresholds(
        min_total_sources=8, min_t1_count=1, min_t1_plus_t2=2,
        min_t1_plus_t2_plus_t3=5, ...),
    "tech": AdequacyThresholds(...),
    "due_diligence": AdequacyThresholds(...),
}
```

**ONLY 4 domains have entries: clinical, policy, tech, due_diligence.**

`ai_sovereignty`, `canada_us`, `workforce` are NOT in `_DEFAULT_DOMAIN_THRESHOLDS` — they fall through to the bare `AdequacyThresholds()` defaults (min_t1=2, min_t1+t2=3, etc., which are CLINICAL-shaped).

This matches the manifest thresholds exactly:
- Q1/Q2/Q3 (ai_sovereignty/canada_us/workforce) — min_t1=2 (default fallthrough)
- Q4 (policy) — min_t1=1 (the `policy` entry)

## Cross-reference: scope templates exist for these domains
- `config/scope_templates/ai_sovereignty.yaml` ✓
- `config/scope_templates/canada_us.yaml` ✓
- `config/scope_templates/workforce.yaml` ✓

GitHub issues GH#196 (I-tpl-006), GH#197 (I-tpl-007), GH#198 (I-tpl-008) added these scope templates as completed work — but `_DEFAULT_DOMAIN_THRESHOLDS` was NOT updated.

## Domain reality check

For "AI sovereignty Canada compute 2026", "CUSMA review 2026", "GenAI white-collar workforce 2026":
- T1 = peer-reviewed primary studies → **structurally absent** (these are emerging policy topics, not biomedical research)
- T2 = systematic reviews → **structurally absent**
- T3 = regulatory/government → 1-2 sources typical
- T4 = narrative reviews / think-tank reports → bulk of evidence
- T6 = industry / advocacy → significant
- T7 = news / preprints → significant

Requiring T1>=1 or T1+T2>=2 for these domains is structurally impossible regardless of how good retrieval is.

# Hypothesis to verify

**Root cause:** new scope templates added in GH#196/197/198 created `ai_sovereignty`, `canada_us`, `workforce` domains but did NOT add corresponding entries in `_DEFAULT_DOMAIN_THRESHOLDS`. They fall through to clinical-shaped defaults that demand T1>=2, which is structurally impossible for emerging-policy topics. Q4 separately needs `policy` thresholds relaxed for emerging-policy contexts (housing 2026) that don't have T1 evidence.

**Proposed fix scope (GH#405 I-tpl-009 already exists for this):**
1. Add `_DEFAULT_DOMAIN_THRESHOLDS` entries for ai_sovereignty / canada_us / workforce with min_t1=0, min_t1+t2=0, min_t1+t2+t3=1 (gov/regulatory floor), and stronger T3+T4+T6 cumulative floors
2. Optionally split `policy` into `policy_established` (current settings) vs `policy_emerging` (looser T1 demand) — Q4 housing should route to emerging
3. Add a `min_t3_plus_t4_plus_t6` floor as the actual quality signal for emerging-policy (think-tank + regulatory + advocacy density)

# Question for Codex

Audit this diagnosis. Output YAML verdict.

```yaml
diagnosis_id: GH405-Q1-Q4-ABORT-ROOT-CAUSE
root_cause_confirmed: yes | partial | no
root_cause_summary: "one sentence"
fix_scope_correct: yes | partial | no
additional_findings: []
verdict: CONFIRMED | CONFIRMED_WITH_CAVEATS | DISPUTED
reason: "one sentence"
```
