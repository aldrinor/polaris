# FX-14 (#1129) diff-gate — ITER 1 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope
P2 custody-telemetry honesty — faithfulness-SAFE (telemetry-only; generator UNCHANGED). Diff:
`.codex/I-ready-017/fx14_codex_diff.patch` (vs FX-20 verified tip `da24892c`, 3 files).

## A-vs-B DECISION — please confirm (this is the Q9 you routed at plan-gate)
- **(A)** re-derive `primary_trial_anchors` from the actual lane so the M-44/M-52/V29 block FIRES in
  planner mode. I **REJECTED A as default**: that block does M-52 pulls INTO evidence_pool + M-44
  injection INTO the outline — it MUTATES what evidence reaches the generator, i.e. faithfulness-adjacent.
- **(B) IMPLEMENTED:** telemetry-only marker. When the custody logs are empty BUT primary-trial DOI
  seeds reached generation, emit a SEPARATE `custody_lane_status.json` disambiguating
  no-activity/not-applicable/broken. ZERO generator change. **Please confirm B loses no real custody
  signal vs A, and that A's injection-in-a-dormant-lane is correctly out of scope for a telemetry fix.**

## Bug (firing-status-lie)
`v29_primary_custody.json=[]` / `m44_primary_citation_telemetry.json={injection_log:[],
validator_violations:[]}` even when primary-trial seeds reached generation, because the block gated on
`if primary_trial_anchors:` (`multi_section_generator.py:4610`) is skipped in the planner lane
(`_primary_anchors` empty). Silent empty = ambiguous = the §-1.1 firing-status-lie.

## Fix (path B, 3 files)
1. `run_honest_sweep_r3.py`: new pure `compute_custody_lane_status()` (beside `compute_run_health_gate`)
   — returns a `not_applicable_planner_lane` marker ONLY when `marker_on` AND
   `sum(query_origin=='primary_trial_doi_seed') > 0` AND both logs empty; else `None`. Call site (~4388)
   writes `custody_lane_status.json` only when the helper returns a marker. The two existing custody
   files are written UNCHANGED above it.
2. `run_gate_b.py`: `PG_CUSTODY_LANE_MARKER=1` in the slate + required-flags preflight (so an explicit
   `=0` can't survive the setdefault — your I-cap-005 P1-1 pattern).
3. Test.

## Why a SEPARATE file (not inline into v29/m44)
The m49 test asserts `m44_*.json` is a dict with `injection_log`+`validator_violations`, and the m53
test asserts `v29_*.json` is a LIST and treats any element lacking `cited_in_verified_prose` as a FAILED
anchor. A marker element inside the v29 list would be misread as a broken custody anchor. So the
type-safe, contract-preserving disambiguation is a companion `custody_lane_status.json`; both existing
files stay byte-identical.

## Evidence
- §-1.1 on the REAL held `evidence_pool.json`: raw `query_origin=='primary_trial_doi_seed'` count = **2**
  (rows 19,20); `compute_custody_lane_status(<held rows>, ... marker_on=True)` returns
  `primary_trial_doi_seed_rows == 2` — EXACT match. The held m44/v29 were empty → the marker WOULD fire.
  **Forensic correction:** the forensic said "16+"; the real artifact has 2 (the 16 predated FX-15a's
  mislabel fix). Full audit: `outputs/audits/I-ready-017/fx14_s11_audit.md`.
- Offline smoke `test_fx14_custody_lane_status_iready017.py` → 6 passed: marker on seeds+empty (counts
  only primary, not agentic/plain); None when flag OFF (byte-identical); None when no primary seeds;
  None when a custody log ran; non-dict rows ignored; held count==2.
- Regression: m49 dict + m53 list custody-contract tests pass; the 6 m49 failures are PRE-EXISTING
  V28-fixture content drift (VERIFIED identical with FX-14 stashed). FL-05 sibling 8 + Gate-B slate/CLI
  21 green.

## Faithfulness
Telemetry-only. No grounding/strict_verify/4-role/generator change. Marker DERIVED from the evidence
pool's own query_origin (cannot fabricate); only ADDS a file in the previously-silent-empty case.

## Question
Confirm path B is correct + faithfulness-safe (vs A's faithfulness-adjacent injection), the companion
file is the right type-safe disambiguation, the count matches the real artifact, and OFF is
byte-identical. Anything blocking APPROVE?
