# V28 Gate Verdict (step 4, autoloop V2)

## Summary

**Overall verdict: NOT SHIPPABLE — CONTINUE with V29.**

V28 adjudicated scoreboard: **3 BEAT_BOTH + 0 BEAT_ONE + 4 LOSE_BOTH**.

V28 target per approved plan was 5 BB + 2 BO + 0 LB. Actual result: target missed on both BEAT_BOTH count (3 vs 5 target) AND LOSE_BOTH count (4 vs 0 target). Net dimensional health REGRESSED vs V27 on ≥BEAT_ONE count (5 → 3).

## Per-dimension cross-reviewed outcome

| Dim | V27 | V28 | Rationale |
|---|:-:|:-:|---|
| 1. Citations | BEAT_ONE | **LOSE_BOTH** ↓ | SURPASS-2 T4 post-hoc; SURPASS-4/CVOT primaries absent |
| 2. Regulatory | BEAT_ONE | **BEAT_BOTH** ↑ | Only report with FDA+EMA+NICE+HC |
| 3. Jurisdictional | BEAT_ONE | **BEAT_BOTH** ↑ | Jurisdiction-specific content preserved |
| 4. Claim frames | LOSE_BOTH | LOSE_BOTH | SURPASS-2 primary ETDs missing; table malformed |
| 5. Structural depth | LOSE_BOTH | LOSE_BOTH | Trial table 2 weak rows; subsections off-target trials |
| 6. Contradiction handling | BEAT_BOTH | BEAT_BOTH | 14-item enumeration preserved |
| 7. Narrative depth | BEAT_ONE | **LOSE_BOTH** ↓ | Mechanism 866w but review-grade not primary-extracted |

## Two explanations for the shortfall

### 1. The real gap is retrieval-to-selection, not code

All V28 code modules (M-44/45/46/47/48/50) were Codex-verified and produced correct artifacts:
- M-42b trial table rendered (structure: passed; content: thin because most primary direct_quotes were <100 char)
- M-50 rendered 3 subsections (structure: passed; target-trial hit rate: 0/4 because SURPASS-2/4/CVOT/SURMOUNT-2 were not in the eligible candidate set)
- M-47 validator ran and regen fired (structure: passed; content: clamp paper findings not mined)
- M-48 emitted 22 primary-trial queries (retrieval layer: passed)
- M-44 injection fired 0 times (nothing to inject — primaries absent from evidence pool for target trials)

The upstream gap is **primary papers landing in live_corpus but not flowing through to the generator's evidence subset**. V28 live_corpus contains SURPASS-4 Del Prato and SURPASS-CVOT records (verified by Codex via `live_corpus_dump.json:2478, 1741, 3163, 3185`), but the selector dropped them.

### 2. V27 → V28 was NOT a pure upgrade

Dimension 1 (Citations) and 7 (Narrative depth) regressed from BEAT_ONE to LOSE_BOTH. Dimensions 2 and 3 upgraded. Net: 2 downgrades, 2 upgrades — no net improvement in dimension count.

The upgrades came from V28 completing things V27 was close on (Regulatory → BEAT_BOTH via M-48 labels + expanded HC Product Monograph citation). The downgrades came from V28 structurally replacing V27 prose-depth with new artifacts (trial table, per-trial subsections) that are individually thinner than what they replaced.

## §7 autoloop halt triggers

Multiple triggers fire:

1. **§7 trigger #7**: REGRESSION dimension V27 → V28 without compensating BEAT_BOTH upgrade on the same axis.
   - Dim 1 regressed BO → LB. No new BB on dim 1.
   - Dim 7 regressed BO → LB. No new BB on dim 7.
   - FIRES.

2. **§7 trigger #10**: Net dimensional health regressed cycle-over-cycle.
   - V27 ≥BEAT_ONE count: 5. V28: 3. FIRES.

3. **§7 trigger #11**: 4 Codex code-audit ping-pong passes on M-50 + M-47 (plan-level budget consumed) — within cap, not firing.

## Decision

Per V2 protocol, halt autonomous loop and surface to user for V29 direction.

## V29 scope needed (outline for user review)

The root cause is at a single layer: **selector-to-generator flow for primary papers**. Candidates:

### Candidate A: Reinforce M-42e at selection stage

Force selector to select every M-42e-tagged primary row that matches a configured anchor, regardless of tier-proportional quotas. If SURPASS-4 Del Prato primary is in live_corpus, it MUST appear in `selected_rows`. Current selector respects tier balance, which is why Lancet primaries in T1 can be outranked by better-scored T2 meta-analyses in a tier-proportional budget.

### Candidate B: Named-trial section-subset injection (at generator)

Current M-44 injects `is_primary_trial`-tagged rows into sections IF they're in `evidence_pool`. Extend to: if a named trial is present in ANY section's evidence_pool AND the anchor's primary is in live_corpus but NOT in evidence_pool, PULL THE PRIMARY from live_corpus and inject it directly into the section's ev_ids.

### Candidate C: Primary-evidence preservation quota

Reserve N slots (N=11 for tirzepatide) in the selector output specifically for anchor-matched primary rows, before any other tier allocation. Guarantees pivotal coverage at cost of evidence diversity.

### Candidate D: Trial-summary table remediation

The Trial Summary table cells are factually wrong (SURPASS-5 baseline shown as 7.0% — actual baseline HbA1c was 8.31%). Either extract from direct_quote more carefully or drop the table rather than ship corrupted values.

### Candidate E: M-47 evidence-linked regen should drop section on 2nd fail

Current: M-47 regen once; if still fails, ship section with incomplete flag. Change: if regen fails AND clamp evidence is in subset, drop the Mechanism section content and emit a skeleton with explicit "primary clamp data not extracted; see [ev_X]" pointer. Honesty over padded prose.

## User decision point

Ship V28 as-is (3 BB + 0 BO + 4 LB — **worse overall dimension health than V27**) — NOT RECOMMENDED, or launch V29 targeting selector/generator flow fix.

My recommendation: **launch V29 with Candidate A (selector-level reinforcement) + Candidate B (named-trial injection) as the V29 bundle**. These two items together directly address the "primary in live_corpus but not in report" root cause. Skip Candidates C/D/E for V29 — they're symptom-level.

Budget check: V25→V28 ran 4 cycles in ~18h of this session. V29 would be cycle 5. §7 trigger #2 (24h wall-clock cap) is at ~30h total — V29 is within budget.

**User input required**: go V29 with Candidates A+B? Or halt and ship V28 + accept the dimensional regression? Or different scope?
