
# POLARIS Autoloop V2 — V28 Launch Handover (2026-04-22)

Previous handovers:
- `state/autoloop_handover_2026-04-22_v26_launch.md` — V26 launch
- `state/autoloop_handover_2026-04-21_v25_v2_launch.md` — V25 launch

## Stop condition

BEAT-BOTH ChatGPT 5.4 Pro DR + Gemini 3.1 Pro DR on 7 dimensions,
cross-reviewed content audit (line-by-line PRISMA/AMSTAR-2/GRADE).

## V28 sweep state

- **Launcher**: `scripts/run_full_scale_v28.py`
- **Output root**: `outputs/full_scale_v28/clinical/clinical_tirzepatide_t2dm/`
- **Launch time**: 2026-04-22 14:11:32 PDT
- **PID**: 8466
- **stdout log**: `outputs/_V28_sweep_stdout.log`
- **Expected duration**: 90-150 min (V27 was 113.7 min; V28 adds
  11 variant queries + M-50 per-trial subsection LLM calls)
- **Budget cap**: $10.00

## V28 bundle (all Codex-reviewed; audits at
`outputs/codex_findings/m{44..50}_code_audit*/findings.md`)

| Item | Codex verdict | Scope |
|---|---|---|
| M-44 | pass-3 PASS | Primary-trial scorer/subset injection + same-sentence validator + one-shot regen |
| M-45 | pass-2 SIGN OFF | Refetch diagnostics with per-URL backend/method + 8-key schema |
| M-46 | READY | Selector early-exit fix — floors fire even when pool_size ≤ max_rows |
| M-47 | pass-3 in review | Evidence-linked clamp/PK validator + field-context tokens + regen |
| M-48 | pass-2 APPROVED | Per-anchor first-author variants + population-scope labels |
| M-49 | preservation_guard | 19 V28 acceptance tests (V27 floors + M-44/45/47/50 acceptance) |
| M-50 | pass-2 in review | Per-trial subsection generator for T2D-direct primaries |

## V28 target (per fix_plan_v28.md pass-2, Codex APPROVED)

**5 BEAT_BOTH + 2 BEAT_ONE + 0 LOSE_BOTH** (up from V27's 3+2+2).

Dim-by-dim projection:
- 1. Citations: BEAT_ONE → BEAT_BOTH (M-44 + M-48 variants)
- 2. Regulatory: BEAT_BOTH (preserved)
- 3. Jurisdictional: BEAT_BOTH (preserved)
- 4. Claim frames: LOSE_BOTH → BEAT_BOTH (M-44 + M-45 table + M-50)
- 5. Structural depth: LOSE_BOTH → BEAT_BOTH (M-45 + M-50)
- 6. Contradiction handling: BEAT_BOTH (preserved)
- 7. Narrative depth: LOSE_BOTH → BEAT_ONE (M-47 + M-50)

## V28 invariants verified in launch log

- M-28: 11 regulatory_anchors (M-43 cap=12)
- M-35+M-48: 22 primary-trial queries (11 anchors + 11 variants)
- scope_validator: 41 amplified queries, 23 dropped (healthy)

## Post-manifest actions (autonomous)

When V28 manifest.json lands:

1. Run M-49 preservation suite:
   ```
   POLARIS_V28_SWEEP_ROOT=outputs/full_scale_v28/clinical/clinical_tirzepatide_t2dm \
     python -m pytest -q tests/polaris_graph/test_m49_v28_preservation.py
   ```
   - If fail: halt, diagnose which V27 floor regressed (M-43 caught
     V26's NICE=0 via same pattern).
   - If pass: proceed.

2. V2 step 2a (Claude DEEP content audit) + step 2b (Codex DEEP
   content audit) in parallel. Audit at the content level per the
   user's explicit directive: "don't only compare metadata, you know
   what level of audit I asked".
   - Claude writes `outputs/audits/v28/claude_deep_content_audit.md`
   - Codex brief at `.codex/v28_deep_content_audit_brief.md`
   - Codex output at `outputs/codex_findings/v28_deep_content_audit/findings.md`
   - Both must cover: SURPASS-1..6 + SURPASS-CVOT + SURMOUNT-1..4,
     Mechanism, Regulatory, Contradictions
   - Line-by-line vs ChatGPT DR + Gemini DR (state/compare_*.txt)

3. V2 step 3 (cross-review) + step 4 (gate verdict):
   - Per-dim table with lower-verdict-controls rule
   - SHIPPABLE = 7/7 BEAT_BOTH
   - If PARTIAL: write V28 → V29 fix plan per §5, submit to Codex

## §7 halt triggers

- Wall-clock total session > 24h (cycle 1 started ~2026-04-22 12:00;
  cap 2026-04-23 12:00)
- Any REGRESSION dimension V27 → V28 without compensating BEAT_BOTH
  upgrade
- >3 Codex plan-review ping-pong passes on any item (budget exhausted
  in current cycle)

## Autoloop continues autonomously

No user check-in required unless §7 halt fires. Next scheduled
wakeup: check V28 manifest at ~15:30 (80 min in).
