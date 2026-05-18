# Claude architect audit — I-beat-001 (#400) finalization

**Issue:** GH #400 (I-beat-001) — the BEAT-BOTH proof. This PR **finalizes** it:
consolidates the completed §-1.1 audit into the definitive
`BEAT_BOTH_SUMMARY.md`, supersedes the stale v3, and closes #400 on the
honest result.
**Branch:** `bot/I-beat-001` off `polaris` HEAD `df7022b1`.
**Commit 1:** `d0bf1689` — 1 file, `outputs/audits/I-beat-001/BEAT_BOTH_SUMMARY.md` (+152/-91).
**Brief:** `.codex/I-beat-001/brief.md` — Codex APPROVE iter 1 (0 P0/P1, 4 P2 — all folded in).

## 1. Operator-chosen path

#400 was offered three completion paths. The operator was shown that #400 is
2/5+ done (in fact all 6 reports produced + audited post-I-tpl-009), that a
heavy rerun is unnecessary and would not change the corpus-gate behaviour, and
asked which path yields the highest-quality output. The operator's effective
choice: **finalize the honest result, no rerun**. This PR is that finalization
— a pure documentation consolidation, no generation run, ~no cost.

## 2. What shipped

`outputs/audits/I-beat-001/BEAT_BOTH_SUMMARY.md` rewritten as the definitive
final summary. It consolidates `cross_review_v12.md` (the 55-claim Claude+Codex
§-1.1 cross-review) + the tirzepatide/pharmacare full mechanical audits. v1/v2/v3
remain on disk as dated historical iterations.

## 3. Per-finding verification (the 4 Codex brief P2s, all folded in)

- **VERIFIED — P2-1 (bound headline numbers to the audited sample):** §3 and §4
  explicitly state every rate "within the 55-claim audited sample"; §5 spells
  out that the competitor un-audited remainder is unmeasured. No unbounded
  "POLARIS beats X" claim.
- **VERIFIED — P2-2 (Q1-Q4 wording):** §2 + §3 say Q1-Q4 *produced reports* and
  the cross-review *sampled* deep claims (Q1:3, Q2:3, Q3:2, Q4:2); only
  tirzepatide + Q5 have the full mechanical 208-sentence audit. Coverage is
  stated as 55/~85 (65%). No implication of full per-sentence Q1-Q4 audits.
- **VERIFIED — P2-3 (GRADE scoping):** §1 "Audit frameworks by domain" scopes
  GRADE / Cochrane RoB 2 to the clinical (tirzepatide) claims; policy claims
  are described under evidence-tier + source-appropriateness review.
- **VERIFIED — P2-4 (#422 de-dup):** I checked GH#422 — it is CLOSED and is
  exactly the Q5-C4 PBO/Bill-C-64 framing bug. §6 references #422 (closed) for
  Q5-C4 and the newly-filed **#586 (I-bug-117)** for Q3-C1. No duplicate filed.

## 4. §-1.1 compliance

The summary is the **consolidation of a completed claim-by-claim audit**, not a
banned metadata/pattern comparison. §1 states the methodology so every count is
readable as a claim-level aggregate (each of the 55 claims carries a Claude
verdict + an independent Codex verdict against the cited source span — that
work is in `cross_review_v1..v12.md`). The BEAT-BOTH conclusion (§4) rests on
per-claim faithfulness verdicts, not on any "fewer contradictions / more
sources, therefore better" framing. The honesty-bounds section (§5) bounds
every claim.

## 5. Follow-up issues filed

- **#586 (I-bug-117)** — POLARIS Q3-C1 source attribution (exposure decimals
  cited to Goldman Sachs 2023, match PWBM 2025). Newly filed.
- **#422 (I-gen-001)** — POLARIS Q5-C4 PBO-vs-Bill-C-64 framing. Pre-existing,
  already CLOSED; referenced, not re-filed.

## 6. Scope + diff shape

The deliverable lives under `outputs/audits/I-beat-001/`, which the
`codex-required` CI gate excludes from the canonical diff. The canonical diff
is therefore just the `state/polaris_restart/iteration_trajectory.md` append.
This is expected — `BEAT_BOTH_SUMMARY.md` is an issue audit artifact and
correctly lives in the audit dir. No production code / test / config touched —
zero runtime risk. The Codex diff review brief points directly at the
`BEAT_BOTH_SUMMARY.md` content.

## 7. Verdict

#400 finalized honestly: the BEAT-BOTH proof rests on a completed 55-claim
§-1.1 cross-review across 6 reports / 5 Carney priorities + clinical, 0
fabrications, with explicit honesty bounds. Faithful to the iter-1 APPROVE'd
brief. Ready for Codex diff review.
