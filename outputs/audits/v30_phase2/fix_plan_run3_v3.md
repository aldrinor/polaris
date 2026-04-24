# V30 Phase-2 run-3 fix plan v3 (post-Codex pass-2)

Revision of `fix_plan_run3_v2.md` addressing Codex pass-2 review
at `outputs/codex_findings/v30_m66_plan_review/pass2_findings.md`
(verdict: CONDITIONAL-blockers — 1 new blocker + 1 medium).

## Pass-2 resolution

**RESOLVED** (3): Blocker 1 (M-66a split), Medium 1 (M-66b
split), Medium 3 (RetrievalAttempt fix landed + 39/39 green),
Nit (M-66c ordering).

**PARTIAL** (2): Blocker 2 acceptance false-pass (Trial Summary
real-content filter still prose), Medium 2 projection honesty
(Structure still over-projected).

**NEW Blocker** (pass-2): ship rule is internally inconsistent —
"zero LB" vs "1 LB still meets ship" said in the same plan.

**NEW Medium** (pass-2): M-66b test seam wrong — should mock
`_fetch_url_pattern` / AccessBypass result, not httpx.

## Resolution in v3

### NEW Blocker — ship rule clarification

**Decision**: adopt the STRICT gate.

- **BEAT-BOTH ship** = `≥5/7 dimensions BB or BO` **AND**
  **zero dimensions LB**. This is the canonical victory rule
  from `memory/autoloop_beat_tier1_mandate.md`.
- If run-3 lands `2 BB + 4 BO + 1 LB` (honest projection scenario),
  that is **NOT BEAT-BOTH**. It is a **Phase-2 checkpoint** worth
  committing + continuing, but not shipping to users.
- The lenient "ship with 1 LB" phrasing was an unintended
  artifact of the narrative-depth honesty admission. Deleted.

New labels:
- **`BEAT_BOTH_SHIP`** — the victory gate; strict zero LB.
- **`PHASE2_CHECKPOINT`** — a commit-worthy milestone short of
  ship; e.g., run-3 with 1 LB on narrative depth. Triggers
  M-67 (narrative-depth synthesis work) before next ship attempt.

### NEW Medium — test seam

**Decision**: mock at the right seam.

- `_fetch_url_pattern(url)` is the new helper. Tests mock THIS
  function's return value (or, if cleaner, mock AccessBypass
  directly), NOT httpx.MockTransport.
- `TestOrchestratorRegulatoryUrlFetch` stubs
  `_fetch_url_pattern` with a deterministic return `(content,
  final_url)` and asserts M-56 routes to it correctly.
- `TestOrchestratorOaFullTextFetch` same pattern for the
  Unpaywall-oa_pdf_url path.
- httpx.MockTransport is still used for the CrossRef / Unpaywall
  / PubMed branches (existing tests unaffected).

### Partial: Trial Summary "real content" filter

Upgrade from prose to concrete negative regression.

New negative test: `test_trial_summary_rejects_truncated_comparator_fragments`
in `tests/polaris_graph/test_m42_trial_summary_table.py`:
```python
bad_rows = [
    {"trial": "SURPASS-4", "n": 3045, "comparator":
     "insulin glargine in adults with type", "endpoint": "—",
     "result": "at week 18"},
]
# Should be rejected because comparator is a truncated fragment
# AND endpoint is placeholder AND result is missing a number.
```

The validator in `multi_section_generator._build_trial_summary`:
- Reject rows where `comparator` matches `.*\sin adults with type\b`
  (truncated NEJM/Lancet population boilerplate)
- Reject rows where `endpoint in {"—", "", None}`
- Reject rows where `result` contains no numeric match
  (`\d`) OR is just `"at week N"` with no effect size
- Emit telemetry: `trial_summary_rows_rejected` count

Run-3 acceptance: trial summary must have **≥6 rows after this
validator filters**, not ≥6 rows nominally. Matching test:
`test_run3_trial_summary_has_6_clean_rows`.

### Partial: Structure probabilistic BO, not pre-booked

Updated projection table — Structure is `PROBABLE BO`, not
`BO`:

| Dimension        | Run-2 | Run-3 target       |
|------------------|-------|--------------------|
| Citations        | BO    | **BB**             |
| Regulatory       | LB    | **BO**             |
| Jurisdiction     | LB    | **BO**             |
| Claim-frames     | BO    | **BB**             |
| Structure        | LB    | **PROBABLE BO** (data-driven — table/timeline fix lands, but new bugs possible) |
| Contradictions   | BB    | **BB**             |
| Narrative depth  | LB    | **LB** (explicit; M-67 scope) |

**Ship rule applied to this projection**: 2 BB + 4 BO + 1 LB =
**Phase-2 checkpoint**, NOT BEAT-BOTH ship. Post-run-3, M-67
addresses narrative depth to convert LB → BO, then run-4 for
BEAT-BOTH ship attempt.

## M-66 bundle — v3 (identical structure to v2)

Legs unchanged: M-66c, M-66b-R, M-66b-T, M-66a-T. Test seam
corrected (mock `_fetch_url_pattern`, not httpx for AccessBypass
path). Acceptance criteria unchanged.

## Implementation order

1. **M-66c** (yaml Thomas clamp) — 15 min
2. **M-66b-R** (regulatory url_pattern fetch + tests) — 60 min
3. **M-66b-T** (OA PDF full-text fetch + tests) — 60 min
4. **M-66a-T** (telemetry) — 30 min
5. **Trial Summary validator + negative regression test** — 30 min
6. **Acceptance assertions** (completeness downgrade, 4-of-6
   regulatory pass) — 30 min
7. **Launch V30 Phase-2 run-3** — 2h
8. **Re-audit (autoloop V2)** — 10 min
9. **If LB ≥ 1: commit as `PHASE2_CHECKPOINT`, escalate to M-67.**
   **If zero LB: BEAT_BOTH_SHIP, close V30 Phase-2 cycle.**

**Total: ~5 hours to checkpoint.**

## Ship criteria (canonical, one source of truth)

| Label               | Gate                                                                |
|---------------------|---------------------------------------------------------------------|
| `BEAT_BOTH_SHIP`    | ≥5/7 dimensions BB or BO **AND** **zero LB dimensions**             |
| `PHASE2_CHECKPOINT` | ≥4/7 dimensions ≥BO **AND** ≤1 LB **AND** zero regressions vs run-2 |
| `REGRESSION`        | any run-3 dimension strictly worse than run-2                       |

Expected outcome for run-3 (honest): `PHASE2_CHECKPOINT` — not
ship but commit-worthy. BEAT_BOTH_SHIP deferred to run-4 post-M-67.

## Codex pass-3 review ask

Before implementation, Codex verifies:
1. Ship-rule internal consistency (only one gate definition now)
2. M-66b test seam is AccessBypass-level, not httpx
3. Trial Summary negative regression is concrete enough
4. Structure PROBABLE BO label is honest
5. `PHASE2_CHECKPOINT` vs `BEAT_BOTH_SHIP` distinction is
   operationally unambiguous (no misread scenarios)
