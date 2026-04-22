You are Codex DR output audit pass 14, running as step 2b of the
autoloop V2 protocol. V27 audit. Claude is writing its parallel
audit to outputs/audits/v27/claude_audit.md.

## Stop criterion (unchanged)

BEAT-BOTH ChatGPT DR + Gemini 3.1 Pro DR on 7 dimensions:
1. Citations (breadth + primacy)
2. Regulatory (coverage + jurisdictional spread)
3. Jurisdictional (non-US regulator depth)
4. Claim frames (N/dose/comparator/endpoint/timepoint/effect in-sentence)
5. Structural depth (tables/timelines/sub-cases)
6. Contradiction handling (detection + adjudication)
7. Narrative depth (mechanism, dose-response, population subgroups)

## V27 setup context

V27 = V25 + M-42 bundle (all Codex-approved) + M-43 (regulatory
anchor cap 10→12 to restore NICE after V26 caught NICE=0 regression
via preservation suite).

V26 outcome: manifest landed; preservation caught NICE=0; halt +
root-cause fix → M-43 → V27 relaunch.

V27 sweep: 253 min (4h13), cost $0.0055, manifest.status=partial_qwen_advisory,
release_allowed=false (qwen_citation_tightness_needs_revision +
qwen_multi_axis_needs_revision + pt13 advisory).

## V27 headline metrics

| Metric | V23 | V24 | V25 | V26 | V27 |
|---|---:|---:|---:|---:|---:|
| sections | 5 | 5 | 6 | 6 | 7 |
| total report words | 2503 | 2666 | 2921 | 3527 | 3441 |
| bibliography size | 31 | 35 | 40 | 48 | 47 |
| corpus size | 360 | 409 | 414 | 408 | 422 |
| FDA entries | 6 | 0 | 7 | 7 | **5** |
| EMA entries | 4 | 0 | 3 | 3 | 3 |
| NICE entries | 3 | 0 | 4 | **0** | 3 |
| HC entries | 0 | 0 | 1 | 3 | **2** |
| Contradictions | — | — | 15 | 15 | 13 |
| SURPASS mentions | — | — | 6 | — | 10 |
| Trial Summary table | MISSING | THIN | SUPPRESSED | ? | **SUPPRESSED** (M-42b thin quotes) |
| release_allowed | true | true | true | false | **false** |

### Preservation suite results (10/12 pass)

- ✓ biblio >= 40, T2 >= 3, EMA >= 3, HC >= 2 (M-42d target hit),
  contradictions >= 10, underframed rate check (skipped — no
  Mechanism heading match)
- ✗ FDA = 5 (V25=7, below baseline by 2)
- ✗ NICE = 3 (V25=4, below baseline by 1)

### Selector short-circuit note (important for root-cause analysis)

V27 evidence_selection strategy = `tier_balanced_v1_all`
(short-circuit fired because pool_size=385 <= max_rows=600).
This means M-42c, M-42d, M-42e selector floors did NOT run at
retrieval-time — they require pool > max_rows to activate. In
V27 they were dormant. Only M-42a (prompt rule) and M-42b
(trial table builder, which suppressed due to thin quotes) were
active in the generator path.

M-42e / M-42c / M-42d code is proven correct by unit tests but
did not influence V27's actual biblio composition. This is a
finding: the M-42 selector floors won't fire unless max_rows is
tightened to below pool size. Either the code is "correct but
inactive" or max_rows should be lower by design.

## Competitor baselines

Read once; do not re-load per dim:
- `state/compare_chatgpt_dr.txt` — ChatGPT 5.4 Pro DR on same query
- `state/compare_gemini_dr.txt` — Gemini 3.1 Pro DR on same query

## What to verify dimension-by-dimension

For each dim: V27 vs ChatGPT and V27 vs Gemini → BEAT_BOTH /
BEAT_ONE / LOSE_BOTH, with concrete POLARIS-line + competitor-
line + source URL as evidence. Use the V25 pass-13 brief template.

1. **Citations**: biblio 47 vs ChatGPT 21 vs Gemini 43. Primary-
   trial coverage: SURPASS-1 (Rosenstock 2021), SURPASS-2 (Frías
   NEJM 2021), SURPASS-3 (Ludvik 2021), SURMOUNT-1 (Jastreboff
   NEJM 2022), SURPASS-4, -5, -6 — cited as first-class or as
   post-hoc/meta?

2. **Regulatory**: 5 FDA + 3 EMA + 3 NICE + 2 HC = 13 regulatory
   entries. V25 had 15. Numeric density in Regulatory section:
   V27 Regulatory = 547 words (vs V25 ~400).

3. **Jurisdictional**: non-US coverage. V27 has EMA + NICE + HC
   all present (V26 had NICE=0). HC gained 2 entries (M-42d
   target hit). Does V27 cite jurisdiction-specific content (not
   just boilerplate approval statement)?

4. **Claim frames**: N/dose/comparator/endpoint/timepoint/effect
   in same sentence. M-41c deterministic post-check still active
   in V27 generator. Trial mentions should be framed.

5. **Structural depth**: V27 has 7 content sections (Efficacy,
   Safety, Comparative, Mechanism, Dose Response, Regulatory,
   Limitations). M-42b Trial Summary table SUPPRESSED (primary-
   trial direct_quotes too thin — strict contract honored).
   Timeline MISSING. Dose-response section present.

6. **Contradiction handling**: 13 contradictions disclosed (V25=15).
   V27 "Contradiction disclosures" section narrates adjudication.

7. **Narrative depth**: Mechanism=184 words, Dose Response=323
   words. How does this compare to competitors?

## Verdict format

Use V25 pass-13 pattern. Be concrete; cite specific report lines
with citation numbers. Write to outputs/codex_findings/dr_output_pass_14_v27/findings.md
(under 2000 words).
