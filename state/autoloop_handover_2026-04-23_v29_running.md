
# POLARIS Autoloop V2 — V29 Running Handover (2026-04-23 07:26 UTC)

Previous handover: `state/autoloop_handover_2026-04-22_v29_entry.md`.

## Stop condition (unchanged)

BEAT-BOTH ChatGPT 5.4 Pro DR + Gemini 3.1 Pro DR on 7 dimensions,
cross-reviewed content audit.

## V29 sweep state

- **Launch**: 2026-04-23 07:25:53 PDT, PID 753
- **stdout log**: `outputs/_V29_sweep_stdout.log`
- **Out-root**: `outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/`
- **Expected duration**: ~2-3h (V27 was 113 min, V28 was 2h51m)
- **Budget cap**: $10.00

## V29 bundle (all Codex-verified READY before launch)

| Item | Codex verdict | Commit |
|---|---|---|
| M-51 selector primary custody | CONDITIONAL-no-blockers (fixture hardened in pass-2) | `0143deb` + `7c081dc` |
| M-52 generator live_corpus pull | READY / CONDITIONAL-no-blockers | `0ac24cb` |
| M-53 per-anchor custody telemetry | READY / CONDITIONAL-no-blockers | `332265b` |
| M-49 V29 custody assertion extension | included (bundled with M-53) | `332265b` |
| V29 launcher | import-ok | `f02f80c` |

Codex M-52+M-53 audit verdict: "No V29 launch-blocking defects...
Claude can proceed to V29 sweep launch."

## V29 invariants verified in launch log

- 11 regulatory_anchors queries (M-28)
- 22 primary-trial queries (M-35 + M-48: 11 anchors × 2 variants)
- scope_validator: 41 kept / 23 dropped

## Post-manifest automation (will run without user input)

On `V29_MANIFEST_LANDED` event from Monitor `b2oaumm97`:

1. Read `v29_primary_custody.json` — the FIRST diagnostic. If any
   anchor has `cited_in_verified_prose=false`, the 9-field entry
   identifies exactly which custody step broke (retrieval /
   selector / generator / quote / prose).

2. Run M-49 preservation suite extended with V29 custody assertion:
   ```
   POLARIS_V28_SWEEP_ROOT=outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm \
     PYTHONPATH=src python -m pytest -q tests/polaris_graph/test_m49_v28_preservation.py
   ```
   (Path name still V28-prefixed because suite file was written
   pre-V29-naming; V28-era tests run + V29 custody assertion now
   included.)

3. If `test_all_anchors_cited_in_verified_prose` FAILS: halt V29
   gate verdict; analyze which step broke per anchor. Emit
   PushNotification to user with specific failing anchors + step.

4. If preservation passes: launch parallel Claude + Codex deep
   content audits per V2 step 2a/2b.
   - Codex brief pre-staged at
     `.codex/v29_deep_content_audit_brief.md`
   - Codex launches via
     `codex exec --full-auto "$(cat ...)" > ... &`
   - Claude writes `outputs/audits/v29/claude_deep_content_audit.md`
     while Codex runs (parallel work)

5. Cross-review per V2 step 3 (per-dim table, lower-verdict-controls
   rule). Write `outputs/audits/v29/cross_review.md`.

6. Gate verdict per V2 step 4. Write
   `outputs/audits/v29/gate_verdict.md`:
   - SHIPPABLE (7/7 BB): PushNotification, STOP.
   - PARTIAL with improvement: analyze against Strategy β roadmap;
     if expected outcome (4-5 BB, 0-1 LB): write V30 fix plan
     (two-stage generator). If unexpected regression: §7 halt.
   - REGRESSION from V28: §7 trigger #7 fires; PushNotification.

## §7 halt triggers still active

- #7 REGRESSION without compensating BEAT_BOTH
- #10 Net ≥BEAT_ONE count regressed
- #11 Plan review ping-pong >3 (budget intact)

## Files the autoloop consults on wake

- `CLAUDE.md` + `~/.claude/CLAUDE.md`
- `docs/todo_list.md` — ACTIVE V29-V32 roadmap
- `state/restart_instructions.md`
- `state/autoloop_handover_2026-04-23_v29_running.md` (this file)
- `outputs/audits/v28/strategic_cross_review.md` — V29-V32 plan
- `state/compare_chatgpt_dr.txt`, `state/compare_gemini_dr.txt`
- `logs/session_log.md`, `logs/bug_log.md`

## V29 projected outcome

Per strategic cross-review: **4-5 BB + 2-3 BO + 0-1 LB**.

Dim-by-dim projection:
- 1. Citations: LOSE_BOTH → **BEAT_ONE** (M-51/52 land primaries)
- 2. Regulatory: BEAT_BOTH preserved
- 3. Jurisdictional: BEAT_BOTH preserved
- 4. Claim frames: LOSE_BOTH → **BEAT_ONE** (primary ETDs citable)
- 5. Structural depth: LOSE_BOTH → **BEAT_ONE** (M-50 subsections
  now for target trials)
- 6. Contradictions: BEAT_BOTH preserved
- 7. Narrative depth: LOSE_BOTH likely stays (V31 scope)

If projection holds, Strategy β cycle 1 succeeded and V30 is next
(two-stage generator).

## User instruction context

User's standing directive (2026-04-23): "follow tightly on the
next run", "execute". V29 implementation + Codex audits +
sweep launch all executed autonomously per this directive. No
user check-in required unless §7 fires or SHIPPABLE.
