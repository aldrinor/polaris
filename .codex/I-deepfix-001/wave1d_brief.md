HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

# Wave 1d brief — fail-loud shallow-report canaries (I-deepfix-001 #1344)

## Purpose

Guard against the **false-fired pipeline**: the winner slate is ON, the writer-path logs
look busy, yet the rendered report is still shallow/degraded. These are two DETECTORS that
FAIL LOUD (log + raise a clear canary RuntimeError → `overall_rc=1`). Per REAL_PLAN_2026.md
`coverage_fix` item 6. They are **structural detectors, never a number/target/cap** (§-1.3:
word / citation / source counts are BANNED as quality signals). A canary asserts a
STRUCTURAL condition (an *eligible-yet-zero* contradiction), not a quantity threshold to hit.

## Flag

`PG_SHALLOW_REPORT_CANARY` — opt-in, **default OFF** (LAW VI). OFF ⇒ byte-identical:
- both `assert_*` functions early-return (canary logic never runs),
- the `run_one_query` telemetry line is NOT emitted (no `run_log.txt` line, no report change),
- the post-run wrapper self-skips (`"skip:disabled"`).

## Files + functions changed

### `scripts/dr_benchmark/run_gate_b.py` (detector home — mirrors the M6 canary family at :2431)
- `_shallow_report_canary_enabled()` — reads `PG_SHALLOW_REPORT_CANARY` at CALL time (LAW VI).
- `assert_depth_synthesis_fired(log_text: str) -> None` — **canary 1**. Parses the EXISTING
  depth-synthesis telemetry line `[depth-synthesis] D8-thread: baskets_total=.. drafted=..
  kept_findings=.. (cross=.. single=..)` (produced at `run_honest_sweep_r3.py:16074`). Raises
  RuntimeError iff a line shows `drafted>=1 AND kept_findings==0` — eligible high-corroboration
  baskets were DRAFTED (the depth pre-pass only drafts baskets clearing the definitional
  `>=2 distinct-origin members` floor) yet ZERO synthesized findings survived. Self-skips on
  the flag; never touches a verdict.
- `assert_multi_origin_baskets_exist(log_text: str) -> None` — **canary 2**. Parses the new
  flag-gated line `[shallow-canary] finding_dedup_multiorigin_clusters=X multi_origin_baskets=Y`.
  Raises RuntimeError iff a line shows `X>=1 AND Y==0` — finding_dedup grouped >=1 cluster with
  >=2 DISTINCT origins yet ZERO consolidation baskets reached composition with
  `verified_support_origin_count>=2` (the finding_dedup→basket keystone silently produced no
  multi-origin baskets — the documented "787 rows → mostly-singleton baskets, Multi-source
  corroborated: 0" regression, `credibility_pass.py:51-56`).
- `_run_shallow_report_canary(log_text, status, *, smoke_scale, domain, slug) -> str` — wrapper
  mirroring `_run_m6_firing_canary`. Self-skips on flag-off / non-released status / smoke_scale;
  else runs both asserts; RuntimeError → `"FAILED"` (caller sets `overall_rc=1`).
- Post-run wiring (in the query loop, next to the M6 canary call): when the flag is on, read
  `summary["run_dir"]/run_log.txt`, call the wrapper, set `overall_rc=1` on `"FAILED"`, record
  `shallow_report_canary` in the sweep record.

### `scripts/run_honest_sweep_r3.py` (one flag-gated telemetry line — feeds canary 2)
- In `run_one_query`, immediately after the U5 synthesis-fire canary block (~:19236), a
  `PG_SHALLOW_REPORT_CANARY`-gated `_log` line emitting:
  `[shallow-canary] finding_dedup_multiorigin_clusters=<X> multi_origin_baskets=<Y>` where
  - `X` = count of `_finding_dedup_telemetry["clusters"]` with `corroboration_count >= 2`
    (`_finding_dedup_telemetry` is pre-initialized to `None` at :9676, so None-safe),
  - `Y` = `count_multi_source_baskets(multi.credibility_analysis)` (existing helper, :2000).
  Fail-open (never aborts the report). OFF ⇒ no line ⇒ byte-identical. Canary 1 needs NO new
  emission — it reads the existing D8-thread line.

## The structural-not-quantity invariant (the §-1.3 line)

Each canary fires ONLY on an *eligible-yet-zero* contradiction — a producer that was structurally
ENABLED to yield something (eligible baskets drafted / multi-origin clusters grouped) yielded
EXACTLY ZERO. There is **no magnitude threshold**:
- `drafted==0` (no eligible baskets) ⇒ never fires (§-1.3: depth is never FORCED).
- `clusters==0` (no multi-origin corroboration) ⇒ never fires (§-1.3: corroboration is never FORCED).
- `kept_findings>=1` / `multi_origin_baskets>=1` ⇒ genuinely fired ⇒ never fires.
- A large count alone (e.g. `drafted=100 kept_findings=50`) does NOT decide anything — only the
  zero-when-eligible contradiction does.
The distinct-origin basis (`corroboration_count>=2` for the cluster numerator) matches the basket
denominator (`verified_support_origin_count>=2`) so a same-host near-dup pair can never spuriously
fire canary 2.

## Faithfulness

The frozen faithfulness engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding) is
**BYTE-UNTOUCHED**. The canaries only READ post-run telemetry counts and raise for investigation;
they gate NO verdict, threshold, judge, or abort semantic. The telemetry emission is a pure read of
already-computed counts.

## Tests — `tests/polaris_graph/test_shallow_report_canary_wave1d.py` (offline, no model/GPU)

Telemetry is stubbed as log strings:
1. **OFF byte-identical**: flag unset ⇒ both asserts return None on a would-fire log; wrapper
   returns `"skip:disabled"`.
2. **ON canary 1 fires**: `drafted>=1 kept_findings==0` ⇒ RuntimeError (depth dark).
3. **ON canary 2 fires**: `multiorigin_clusters>=1 multi_origin_baskets==0` ⇒ RuntimeError.
4. **ON healthy**: `drafted>=1 kept_findings>=1` and `clusters>=1 baskets>=1` ⇒ no raise.
5. **Structural-not-quantity**: `drafted==0 kept==0` and `clusters==0 baskets==0` ⇒ no raise
   (conditional absence); large counts with no contradiction ⇒ no raise.
6. Wrapper: skip on non-released status / smoke_scale; `"FAILED"` on firing log; `"ok"` on healthy.
7. Smoke-import both modules.

## Files I have ALSO checked and they're clean

- `run_honest_sweep_r3.py:16011-16085` — depth-synthesis D8-thread producer; confirmed the
  `drafted`/`kept_findings` fields on the line and that `_log` tees to `run_dir/run_log.txt`.
- `run_honest_sweep_r3.py:9676,14373,17460` — `_finding_dedup_telemetry` lifecycle: init `None`,
  set inside `if _use_finding_dedup`, later read for `manifest["finding_dedup"]`. Cluster dict
  shape `{finding_key, corroboration_count, member_hosts}` confirmed (:14387).
- `run_honest_sweep_r3.py:2000-2028` — `count_multi_source_baskets` / U5 `synthesis_did_not_fire`:
  canary 2 is UPSTREAM of U5 (finding_dedup→basket keystone) and does NOT duplicate U5
  (baskets-exist-but-no-multicited-sentences).
- `run_gate_b.py:2419-2562` — the M6 canary family (`assert_cross_source_synthesis_fired`,
  `_run_m6_firing_canary`) whose shape is mirrored; `_BREADTH_CANARY_RELEASED_STATUSES` reused.
- `run_gate_b.py:4053-4056,4554` — `summary["run_dir"]` is the released-run dir (breadth canary
  reads report.md/manifest.json from it); `run_log.txt` lives there.
- `run_gate_b.py:5127-5190` — the post-run canary call site pattern (M6 + breadth) mirrored.
- Slate: `PG_SHALLOW_REPORT_CANARY` is NOT added to `_PAID_PATH_WINNER_FLAGS` or the gate-B
  full-capability slate (Wave-1d slate additions are a SEPARATE unit) ⇒ stays default-OFF ⇒ the
  SLATE-PURITY allowlist is untouched.
