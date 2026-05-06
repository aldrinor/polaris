# POLARIS DR Auto-Loop — Current Handover (2026-04-21 resume)

Previous handover snapshots (for history, do not resume from these):
- `state/autoloop_handover_2026-04-20_TOPTIER.md` — V17 TOP-TIER-DR-ACHIEVED (single-dim pass)
- `state/autoloop_handover_2026-04-20_current.md` — V20 in-flight, M-30
- `state/restart_instructions.md` — 2026-04-19 pass-16 approval (pre-BEAT-BOTH mandate)

## Stop condition

BEAT-BOTH ChatGPT DR + Gemini 3.1 Pro DR head-to-head on 7 dimensions
(citations, regulatory, jurisdiction, claim-frames, structure,
contradictions, narrative depth). Tirzepatide/T2D query.
Competitor PDFs: `state/compare_chatgpt_dr.txt` /
`state/compare_gemini_dr.txt`.

## Latest result: V23 post-M-34, DR pass 11 = PARTIAL

### V23 sweep (commit `9674405`, post-M-34 re-gate)
- `outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/`
- status=`success`, release_allowed=`true`, gate_class=`pass`
- 5 sections (Efficacy, Comparative, Safety, Regulatory, Dose Response)
- 35 sentences verified / 35 dropped
- 1455 prose words, 70 limitations words
- 31 bibliography entries, corpus=360 sources
- Tier mix: T1=16.4%, T2=12.2%, T3=13.6%, T4=34.7%, T7=18.3%
- Evaluator: 12/13 rule checks pass; PT13 advisory only
- Qwen critical axes: clean; reasons=[`advisory_pt13_unhedged_superlatives`]

### Codex DR output audit pass 11 verdict

`outputs/codex_findings/dr_output_pass_11/findings.md` — **PARTIAL**.

**Correction to earlier in-session summary**: the prior commit message
and autoloop wake summary reported "Regulatory BEAT_BOTH; 5 dims
LOSE_BOTH." The actual findings are:

| Dimension             | Verdict   | Basis |
|----------------------|-----------|-------|
| Citations            | LOSE_BOTH | V23 omits core SURPASS-1..6 primary papers in favor of post-hocs/NMAs; ChatGPT anchors on SURPASS primaries; Gemini has 42 cites covering SURPASS-1..6 + Health Canada |
| Regulatory           | BEAT_ONE  | Beats ChatGPT (denser FDA/EMA/NICE spec); loses Gemini (Gemini adds Health Canada monograph, KwikPen, counterfeit) |
| Jurisdictional       | BEAT_ONE  | Beats ChatGPT (named authorities); loses Gemini (Gemini attributes to Health Canada separately) |
| Claim frames         | LOSE_BOTH | V23 omits per-trial N/baseline/comparator/endpoint in same frame; competitors provide trial tables/narrative |
| Structural depth     | LOSE_BOTH | V23 prose-only; ChatGPT has trial table + forest chart + sections; Gemini has deep narrative subsections |
| Contradiction handling | **BEAT_BOTH** | V23 is the only output that exposes contradiction handling (13 numeric disagreements enumerated) |
| Narrative depth      | LOSE_BOTH | V23 concise; competitors have mechanism/pharmacology narrative |

Net: **1 BEAT_BOTH / 2 BEAT_ONE / 4 LOSE_BOTH** — more competitive than
the earlier mis-summary suggested, but still PARTIAL not BEAT_BOTH.

## Fix chain recap (M-25 through M-34)

All shipped and Codex-audited READY except two utility scripts:

| ID   | Fix | Commit | Codex audit |
|------|-----|--------|-------------|
| M-25a | Trial-name match in strict_verify | `59b8f4a` | READY |
| M-25b | Outline `>=5` when corpus supports | `5df838f` | READY |
| M-25e | PT08 contradiction enumeration | `451f382` | READY |
| M-27  | Multi-source citation | `16ee8c7` | READY |
| M-28  | Regulatory-anchor retrieval | `8c54cd5` (pass 3) | READY |
| M-29  | Jurisdictional-precision prompt | `2ebe63a` | READY |
| M-30  | PT11 abbreviation boundary (5 passes) | `82b2625` | READY |
| M-31  | Outline JSON decode resilience | `e511b39` | READY |
| M-32  | Primary-study claim-frame prompt | `1d4c4b4` | READY (pass 10 = V21 PARTIAL) |
| M-33  | `section_max_tokens` 1200→2400 (two passes) | `23b00c9` | READY |
| M-34  | PT11 lookahead-window 200→1000 | `bf78396` | READY |

Utility scripts committed without a Codex code review (user flagged this):
- `408137f` — `scripts/run_full_scale_v23.py` launcher wrapper
- `9674405` — `scripts/regate_v23.py` post-hoc evaluator re-runner

The re-gate script mutates manifest/summary on disk and determined V23's
release_allowed flip from false→true. Audit gap is material.

## Trajectory

| Sweep | Pass | Verdict | Release | Notes |
|------:|-----:|---------|:-------:|:------|
| V17   | 8    | TOP-TIER (single-dim) | yes | Single-query pass 8 threshold (pre-BEAT-BOTH mandate) |
| V18   | 9    | MATERIAL-GAPS | yes | M-28 regulatory landed |
| V19   | (no DR pass) | | no | PT11 `vs.` false-fail; outline decode 3× fail |
| V20   | — | — | — | M-30 stack; outcome not separately audited before V21 |
| V21   | 10   | PARTIAL | yes | M-31 landed; citations BEAT_ONE, regulatory BEAT_BOTH, narrative LOSE_BOTH |
| V22   | (skipped, advisor) | | — | M-32 claim-frame prompt — metrics within ±3% of V21; section_max_tokens cap hit |
| V23   | 11   | **PARTIAL** | yes | M-33 ceiling + M-34 PT11 widen; 1 BEAT_BOTH / 2 BEAT_ONE / 4 LOSE_BOTH |

## Codex pass-11 gap list → V24 candidate fixes

Ordered by leverage (Codex priority order + advisor tie-break):

1. **M-35 (HIGH, retrieval)**: anchor-query SURPASS-1..6 / SURPASS-CVOT
   / SURMOUNT-2/4 primary papers. Analogous to M-28's regulatory-
   anchor pattern in `scripts/run_honest_sweep_r3.py`. Closes the
   LOSE_BOTH on Citations + most of Claim frames (ChatGPT/Gemini
   both anchor there).
2. **M-36 (MEDIUM, generator+schema)**: trial-summary table +
   benefit-risk/NNT table. New post-synthesis stage; outline allows
   table slot. Closes the LOSE_BOTH on Structural depth.
3. **M-37 (MEDIUM, retrieval+prompt)**: Health Canada anchor queries +
   jurisdictional-precision prompt rule update. Lifts Regulatory and
   Jurisdictional from BEAT_ONE → BEAT_BOTH.
4. **M-38 (MEDIUM, prompt)**: trial-framed claims — for each named
   trial, include N / baseline / comparator / dose / endpoint /
   timepoint in same clause. Closes remaining Claim-frames gap.
5. **M-39 (MEDIUM, generator)**: contradiction adjudication, not just
   enumeration. Already BEAT_BOTH — consolidate and avoid regression.
6. **M-40 (LOW, prompt)**: mechanism/pharmacology narrative expansion.
   Closes Narrative depth.

Batching guidance per user's memory rule (`full_scale_dr_auto_loop`):
ONE fix at a time, unit tests first, Codex audit green before full-
scale sweep, Codex DR output audit before declaring.

## Outstanding protocol-compliance items

1. Retroactive Codex audit of `scripts/run_full_scale_v23.py`
   (launcher — low blast radius, cosmetic).
2. Retroactive Codex audit of `scripts/regate_v23.py` (higher blast
   radius — rewrites manifest.json/sweep_summary.json on existing
   sweep artifacts; release_allowed flipped false→true as a result).

User has been notified; awaiting direction on whether to submit now or
fold into V24 sprint.

## Immediate next actions (awaiting user direction)

1. Option A — retroactive audit first: submit `regate_v23.py` to Codex,
   then submit `run_full_scale_v23.py` to Codex.
2. Option B — push forward to V24: start with M-35 (SURPASS primary
   anchors) which is the highest-leverage single fix per pass 11.
3. Option C — batch: M-35 + M-37 (retrieval-side pivots together) in
   one V24, since both add anchor queries.

## Test suite health

All M-28..M-34 tests green. Full polaris_graph suite was 747/747 at
V20 baseline; M-31+M-32+M-33 added ~20 tests; M-34 added 4. Exact
count not re-verified at resume. Re-run before starting next work:
`python -m pytest -q tests/polaris_graph/`.

## Key artifacts

- V23 report: `outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/report.md`
- V23 manifest: same dir, `manifest.json` (post-M-34 re-gate state)
- V23 pre-regate backup: `outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/.regate_backup_*/`
- Codex pass-11 verdict: `outputs/codex_findings/dr_output_pass_11/findings.md`
- Competitor PDFs: `state/compare_chatgpt_dr.txt`, `state/compare_gemini_dr.txt`
- Memory lesson saved: `memory/autoloop_full_scale_launcher_pattern.md` (never run `run_honest_sweep_r3.py` direct for BEAT-BOTH autoloop; always use a V{N} wrapper)
