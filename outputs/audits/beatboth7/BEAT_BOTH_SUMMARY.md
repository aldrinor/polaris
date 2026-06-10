# beatboth7 §-1.1 line-by-line audit — Novita run (2026-06-10)

**Method:** claim-by-claim vs the actually-cited evidence span (VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE). Claude audits had the full `evidence_pool.json` (RELIABLE basis); Codex audits on the completion batch used a lean brief that lacked the spans (see caveat). Metadata/count/pattern/sample/**traceability** banned.

## Per-question verdict (Claude full-evidence = authoritative)

| Q | Faithful (0 fab) | Beat Gemini | Beat ChatGPT | Auditors agree |
|---|---|---|---|---|
| drb_72 ai_labor | YES | YES (Goldman $13T-vs-~$7T, WEF misdated 2024-vs-2020, 146,932 fabricated refs) | NO (ChatGPT careful + far more complete) | yes (Codex re-run agrees) |
| drb_75 metal_ions_cvd | YES | NO | NO (only ~4 narrow slices; both competitors cover full picture inc IV-iron HFrEF/AFFIRM-AHF) | yes |
| drb_76 gut_microbiota_crc | YES (40 claims) | YES (A.muciniphila/CXCL8 reversal, H2S-carcinogen, RS2 overstatement) | NO (completeness; 6+ slots failed verify) | yes (true dual) |
| drb_78 parkinsons_dbs | YES | YES | **NO** (Codex said beat-both but that is a TRACEABILITY ARTIFACT — rejected; still held coverage 0.6, 52 dropped, thin vs ChatGPT) | Codex-only beat rejected |
| drb_90 adas_liability | YES (despite status=error_unexpected fetch err) | YES | NO | yes |

## Overall
- **POLARIS faithful: 0 fabrications across ALL 5** — span-verified, genuine. The core differentiator holds.
- **Beats Gemini: 4/5** (all but drb_75, where POLARIS is too thin to win even vs Gemini's fabrications).
- **Beats ChatGPT: 0/5** — gpt_5_5_pro is careful (no fabrication) AND more complete; POLARIS's reports are redaction-thin (held, low coverage).
- **BEAT-BOTH: 0/5.** Not there yet. The gap is COMPLETENESS, not faithfulness.

## Honest caveats (process integrity)
1. **drb_78 Codex "beat both" REJECTED:** Codex credited POLARIS for "claim-level citation bindings" + penalized competitors for "broader claims without per-claim spans" — that rewards traceability (banned) and inverts completeness. Not a real win.
2. **Codex completion briefs were lean (lacked evidence spans)** → Codex couldn't verify claim-by-claim, defaulted to traceability. The Claude audits (full evidence) are the reliable basis. FIX: future Codex audit briefs must include the actual evidence spans. Re-audit with proper briefs after the Zyte re-run.

## Next
Zyte fetch-coverage re-run (validated 6/6 on real failing clinical URLs) → close the completeness gap WITHOUT fabricating (required-entity retrieve+verify, the held slots get their evidence) → re-audit (proper briefs) → loop until genuine beat-both.
