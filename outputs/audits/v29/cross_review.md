# V29 Cross-review (step 3, autoloop V2)

**Audit date**: 2026-04-23
**Rule**: per-disagreement table, lower verdict controls unless disproven.
**Sources**:
- Claude: `outputs/audits/v29/claude_deep_content_audit.md`
- Codex: `outputs/codex_findings/v29_deep_content_audit/findings.md`

## Per-topic agreement table

| Topic | Claude | Codex | Agreement |
|---|:-:|:-:|:-:|
| A. SURPASS-2 | ChatGPT | ChatGPT | ✓ |
| B. SURPASS-CVOT | Gemini ≈ ChatGPT > V29 | ChatGPT | soft (Claude BEAT_ONE improvement; Codex rejects) |
| C. SURPASS-4 | ChatGPT | ChatGPT | ✓ |
| D. Mechanism | V29 ≈ Gemini | Gemini | **disagree** |
| E. Regulatory | V29 | V29 | ✓ |
| F. Contradictions | Tie (ChatGPT/V29) | Tie (ChatGPT/V29) | ✓ |

5 of 6 topics converge on winner. D disagreement: Claude saw
V29's Mechanism word-count lift (+60%) as competitive with Gemini;
Codex noted V29's Mechanism is review-derived PK content, not
clamp-primary extraction (no 63% M-value, no biphasic insulin
secretion, no receptor-affinity asymmetry). Per user's standing
content-not-metadata directive, Codex's quality-based read wins.

## Per-dimension agreement table

| Dim | Claude | Codex | Lower | Adjudicated |
|---|:-:|:-:|:-:|:-:|
| 1. Citations | BEAT_ONE | LOSE_BOTH | LB | Claude based on biblio count (47 entries); Codex on pivotal-primary coverage (Frías, Del Prato, Nicholls, Jastreboff, Garvey all absent). **Codex wins**: V29 biblio has 5/11 named trials but NONE have their primary publication. Metadata-level count ≠ content-level primary custody. **LOSE_BOTH.** |
| 2. Regulatory | BEAT_BOTH | BEAT_BOTH | — | Agreed. |
| 3. Jurisdictional | BEAT_BOTH | BEAT_BOTH | — | Agreed. |
| 4. Claim frames | LOSE_BOTH | LOSE_BOTH | — | Agreed. |
| 5. Structural depth | LOSE_BOTH | LOSE_BOTH | — | Agreed. **Codex notes V29 REGRESSED from V28 within this dim** (V28 had partial trial table + 3 subsections; V29 has ZERO artifacts). Intra-dim content loss despite same BB/BO/LB tier. |
| 6. Contradictions | BEAT_BOTH | BEAT_BOTH | — | Agreed. |
| 7. Narrative depth | BEAT_ONE | LOSE_BOTH | LB | Claude based on Mechanism word-count lift (+60%); Codex on content quality (generic PK review, not clamp-primary data). **Codex wins**: 1388-word Mechanism section is STYLISTICALLY denser but CONTENT-wise still review-grade, not primary-clamp-extracted. Misses M-value 63% + biphasic insulin from Thomas paper. **LOSE_BOTH.** |

## Adjudicated V29 scoreboard

**3 BEAT_BOTH + 0 BEAT_ONE + 4 LOSE_BOTH**

## Comparison across cycles

| Cycle | BB | BO | LB | ≥BO count |
|---|---:|---:|---:|---:|
| V25 | 1 | 4 | 2 | 5 |
| V27 | 1 | 4 | 2 | 5 |
| V28 | 3 | 0 | 4 | 3 |
| **V29** | **3** | **0** | **4** | **3** |

V29 has **identical cross-reviewed scoreboard to V28**. Two cycles
of Strategy β cycle 1 work (M-42e/M-42b/M-42c/M-42d/M-48/M-50 in V28;
M-51/M-52/M-53 in V29) produced the same dimensional outcome.

## §7 halt triggers

1. **§7 trigger #9 "repeated-root-cause (2 cycles same failure)"**:
   FIRES. V28 and V29 both landed 3 BB + 0 BO + 4 LB. Strategy β
   cycle 1's narrow custody approach is insufficient alone; V30
   two-stage generator architecture is required.

2. **§7 trigger #7 "regression dimension without compensating
   BEAT_BOTH"**: does NOT fire at the dimension-tier level
   (no dim downgraded BB→BO or BO→LB). But intra-dim content
   regression on Dim 5 (Structural depth): V28 had partial trial
   table + 3 subsections; V29 has zero. Within-dim content loss.

3. **§7 trigger #10 "net ≥BEAT_ONE count regressed"**: does NOT
   fire (3 vs 3).

## Root cause (V29 custody telemetry is precise on this)

Per `v29_primary_custody.json`:

**Defect A — Retrieval non-determinism (7/11 anchors)**:
SURPASS-2/3/6/CVOT + SURMOUNT-1/2/3/4 primary publications did not
land in live_corpus. V28 had Del Prato (SURPASS-4) + Nicholls
(SURPASS-CVOT) in corpus but V29 did not. M-48 variant queries
fire but Serper/S2 results vary cycle-to-cycle for paywalled
primary publications. Needs deterministic retrieval strategy
(CrossRef direct DOI lookup for configured anchors).

**Defect B — Forced-citation contract (3/11 anchors)**:
SURPASS-1/4/5 M-51 inserted + M-44 injected → ev_145/402/189 in
section ev_ids → LLM did not cite → ev_ids never reached
bibliography. Current M-44 validator requires trial-name mention in
prose before it can enforce same-sentence primary citation. LLM
simply doesn't name the trials, so validator is empty (0
violations despite 3 silent failures). Needs prompt-level hard
contract: "when configured primary ev_id is in section subset,
section MUST contain a sentence naming the trial AND citing that
ev_id".

## Gate verdict

See `outputs/audits/v29/gate_verdict.md`.

## Recommendation

**HALT autoloop; surface to user.** Strategy β cycle 1 exhausted
without lifting any dimensional tier. V30 scope must address both
Defect A (retrieval determinism) and Defect B (forced-citation
contract). User decides whether to proceed with V30 or change
strategy.
