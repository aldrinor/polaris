# V29 Gate Verdict (step 4, autoloop V2)

## Summary

**Overall verdict: NOT SHIPPABLE — HALT autoloop, surface to user.**

V29 adjudicated scoreboard: **3 BEAT_BOTH + 0 BEAT_ONE + 4 LOSE_BOTH**
(identical to V28). Two cycles of Strategy β cycle 1 work produced
the same dimensional outcome. §7 trigger #9 FIRES.

## Per-dimension outcome (cross-reviewed)

| Dim | V27 | V28 | V29 | Delta V28→V29 |
|---|:-:|:-:|:-:|:-:|
| 1. Citations | BO | LB | LB | = |
| 2. Regulatory | BO | BB | BB | = |
| 3. Jurisdictional | BO | BB | BB | = |
| 4. Claim frames | LB | LB | LB | = |
| 5. Structural depth | LB | LB | LB* | *intra-dim regression* |
| 6. Contradictions | BB | BB | BB | = |
| 7. Narrative depth | BO | LB | LB | = |

*V29 within Dim 5 LOST all V28 structural artifacts (M-42b trial table
0 rows, M-50 subsections total_subsections=0, Trial Program Timeline
absent). V28 had partial versions of all three. Same BB/BO/LB tier
(both LOSE_BOTH vs ChatGPT's full-frame trial table + Gemini's
per-trial subsections), but intra-dim content regression.

## §7 halt triggers

1. **#9 repeated-root-cause (2 cycles same failure)**: FIRES. V28
   and V29 both landed 3 BB + 0 BO + 4 LB cross-reviewed.
2. **#7 dimension regression without compensating BEAT_BOTH**:
   does NOT fire at tier level (no dim downgraded tier).
   Intra-dim content regression on Dim 5 (Structural depth) noted
   but not trigger-firing.
3. **#10 net ≥BEAT_ONE count regressed**: does NOT fire (3 vs 3).

## V29 intervention outcome audit

Strategy β cycle 1 (V29) added M-51/M-52/M-53 to fix V28's
primary-custody failure. Custody telemetry tells us exactly what
happened:

**M-51/M-52 PARTIALLY worked**:
- M-51 fired once (SURPASS-4 inserted into selected_rows)
- M-42e pre-existing floor caught SURPASS-1
- M-44 injection fired for SURPASS-1/4/5 across 4 sections each
- Only 4/11 anchors passed through selector+generator custody

**M-51/M-52 did NOT rescue the anchors V28 lost**:
- SURPASS-CVOT + SURMOUNT-2 + SURPASS-2 primaries NOT in V29
  live_corpus (7/11 anchors) — retrieval variance, not custody
- V29 retrieval surfaced DIFFERENT primaries than V28 (SURPASS-1
  primary new in V29; Del Prato and Nicholls absent from V29 but
  were in V28)

**M-51/M-52/M-44 failed at the LLM prose step** for the 4 anchors
that DID make it through (SURPASS-1/4/5):
- Injected ev_ids (ev_145/402/189) never cited in verified prose
- Never made it to final bibliography
- M-44 validator empty because LLM didn't name trials

**Two distinct V30 scope items** surfaced:
- **Defect A**: retrieval determinism — anchor primaries must land
  in live_corpus every cycle, not cycle-to-cycle variance
- **Defect B**: forced-citation contract — when M-44 injects
  primary ev_id, generator must be forced to cite it, not just
  "hinted at"

## What V29 DID improve (not tier-level, but worth noting)

- Mechanism section lifted 866→1388 words (+60%)
- FDA entries lifted 4→8
- Contradictions enumeration 14→15
- SURPASS-CVOT mentioned for first time (noninferiority correct,
  though HR/CI absent)
- SURMOUNT-2 mentioned for first time

These are intra-dim improvements not reflected in the BB/BO/LB
tier scoring because competitors are stronger on the absolute axis.

## Strategy β roadmap update

Original projection (strategic cross-review):
- V29: 4-5 BB + 2-3 BO + 0-1 LB
- V30: 5-6 BB + 1-2 BO + 0 LB
- V31: 7/7 BB

V29 actual: 3 BB + 0 BO + 4 LB. Projection missed by 2 dims on BB
and 4 on LB.

**Revised V30 scope required**:
Original V30 was "two-stage generator" (primary skeleton + enrichment).
V29 custody telemetry refines this:
- V30a: retrieval determinism (CrossRef direct-DOI lookup for
  configured anchors; bypass Serper/S2 variance for known primaries)
- V30b: forced-citation contract at generator prompt level
  (configured-primary must be cited by name in prose, enforced by
  validator that fires on INJECTION not on trial-name mention)

These two items together are larger than the originally-projected
V30. Estimate: +2 additional days engineering beyond V30 original
estimate.

## Recommendation

HALT autoloop. User decides:

**Option 1 (recommended)**: V30 = revised scope per V29 custody
diagnostic — V30a retrieval determinism (CrossRef DOI anchor lookup)
+ V30b forced-citation contract (prompt hard rule + validator on
injection). ~5-7 days engineering. Likely lifts Dims 1, 4, 5 to
BEAT_ONE-or-better. Then V31 mechanism closure as originally planned.

**Option 2**: Accept V28/V29 dimensional ceiling (3 BB + 0 BO + 4 LB)
and pivot effort to other value axes — e.g. document POLARIS's
regulatory + contradiction transparency strengths as a COMPLEMENTARY
tool to ChatGPT/Gemini DR, not a replacement on clinical-trial
narrative. Ship V29 honestly as a rigorous-transparency reference.

**Option 3**: Investigate whether the tirzepatide-T2D query is
structurally unreachable for POLARIS architecture due to retrieval/
paywall constraints. Test on a different clinical question (or a
non-clinical template) to see if the primary-custody gap generalizes
(Codex's V32 calibration idea brought forward).

## User input required

§7 trigger #9 fired. Autoloop HALTED. Surfaced to user via
PushNotification.
