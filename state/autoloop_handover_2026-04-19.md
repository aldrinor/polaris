# POLARIS DR Auto-Loop — Handover State (2026-04-19)

## Current cycle state

**Iteration 2** of Codex-gated full-scale auto-loop.

- V4 sweep completed (2026-04-19 ~11:15)
  - Commit: `10bb23f` (M-17g classifier gate)
  - Output: `outputs/full_scale_v4/clinical/clinical_tirzepatide_t2dm/`
  - 1083 words, 34 verified sentences, 5 sections, 24 unique citations
  - T1=6.77%, T2=12.58%, T7=33.55%
  - cost=$0.004 (cap $10)
  - status=success, release_allowed=true

- DR output audit pass 1 verdict: MATERIAL-GAPS-FIX-AND-RESWEEP
  - Below GPT-5.4 DR / Gemini 3.1 Pro DR
  - 5 required fixes, split into classifier (1-2) and generator (3-5)
  - findings: `outputs/codex_findings/dr_output_pass_1/findings.md`

- M-18 classifier fixes applied (commits 8039f8c + 17c16c1):
  - M-18a: Add "as compared with" primary marker; split narrative
    markers into STRONG/WEAK; add PEER_REVIEWED_DOI_PREFIXES
  - M-18b: Move social platform check before R1 stub
  - M-18c: Add narrative-framing STRONG markers (beyond/update on/
    role of randomized trials)

- Codex pass 10 verdict: CONDITIONAL, classifier_promotable=true
  - findings: `outputs/codex_findings/full_scale_pass_10/findings.md`

- **V5 re-sweep IN FLIGHT** (task `bl5atkybf`)
  - Commit: `17c16c1`
  - Same max-capacity knobs
  - Output will be at `outputs/full_scale_v5/`

### Iteration 6 update (V6-V10, 2026-04-19 PM)

V5-V9 completed. Each was MATERIAL-GAPS per DR audits pass 2-6.

V10 LAUNCHED at commit `6c015ea` via `scripts/run_full_scale_v10.py`:
- M-23 access-bypass fixes (Unpaywall + strip-before-paywall +
  quality-scored winner + HTTP-error stub detection + paywall
  regex tightening) committed at `6c999e8` and `ff68b86`.
- M-24 outline/section prompt changes (allow overlap, raise
  sentence+citation targets) committed at `6c999e8`.
- Reproducible launcher: `scripts/run_full_scale_v10.py`
  exports all capacity knobs explicitly.
- DR audit brief: `.codex/dr_output_audit_pass_4_v10_brief.md`
  requires live-DOI fetch for 25+ citations, verbatim comparison.
- Output will be at `outputs/full_scale_v10/`.
- Suite: 654 passed at `ff68b86`.

## Next actions after V5 completes

1. Verify V5 manifest (success status, tier distribution improved)
2. Dispatch Codex DR output audit pass 2
   - Brief: `state/codex_dr_audit_brief.txt` (update commit SHA + v5 paths)
   - Target: `outputs/codex_findings/dr_output_pass_2/findings.md`
3. If TOP-TIER-DR-ACHIEVED → STOP loop (terminal).
4. If MATERIAL-GAPS → next classifier/generator iteration:
   - Fixes 3-5 from DR pass 1 were generator-side (causal-strength
     distinctions, remove out-of-scope T1D, adjudicate contradictions)
   - Evaluate against DR pass 2's specific feedback

## Convergence bounds

The user rule: no cycle cap, but "not pattern finding, not cherry
picking" — Codex must audit line-by-line.

If pass 2 also MATERIAL-GAPS with novel content gaps (not variants of
pass 1 gaps), consider:
- Strengthening scope protocol / completeness checklist for clinical
  queries to require SURPASS-1/2/3/4/5 + SURMOUNT-2 + guidelines +
  regulatory label as mandatory sources
- Generator prompt improvements for causal-strength framing
- Max_rows reduction to force T7 exclusion from citation pool

Do NOT continue re-sweeping without making at least one substantive
change between passes. The $10/query cost is bounded but the bigger
cost is time-to-ship.

## Key files

- `docs/todo_list.md` — prioritized backlog, ACTIVE section at top
- `state/codex_dr_audit_brief.txt` — DR audit brief template
- `state/full_scale_auto_loop_procedure.md` — loop procedure spec
- `outputs/codex_findings/full_scale_pass_3` through `pass_10/` —
  Codex code audit trail
- `outputs/codex_findings/dr_output_pass_1/` — DR content audit #1
- `outputs/full_scale_v4/` — v4 output artifacts
- `outputs/full_scale_v5/` — v5 output artifacts (in flight)

## Tests added during this cycle

- `tests/polaris_graph/test_m17_body_article_type.py` (67 tests)
  covering body-inspection detector + M-17f/g title-diagnostic gate
- `tests/polaris_graph/test_m18_dr_audit_fixes.py` (13 tests)
  covering NEJM DOI prefix, social platform early short-circuit,
  narrative-framing STRONG markers

## Suite health

634 passed in polaris_graph/ as of commit 17c16c1.

## Timeline

- 08:45 V3 aborted (T7=70%)
- 09:50 V4 launched at max capacity
- 11:15 V4 completed (success, 310 sources, 1083 words)
- 11:30 DR audit pass 1 dispatched
- 11:40 M-18 applied (commits 8039f8c)
- 11:45 Codex pass 10 dispatched
- 11:50 M-18c applied (commit 17c16c1)
- ~11:45 V5 launched
- V5 completion: ~12:45-13:15 estimated
