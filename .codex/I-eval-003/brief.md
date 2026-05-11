Brief review for GH#429 I-eval-003 — Tier-1 v2 audit extension to Q1-Q4. Output YAML.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Scope

Extend the Q5 Tier-1 v2 pilot (PR #421 / GH#420) to Q1 ai_sovereignty, Q2 canada_us, Q3 workforce, Q4 housing. Tirzepatide triple remains under GH#403.

# Deliverables in this PR

1. `scripts/enumerate_tier1_claims.py`: deterministic parser that reads `report.md` + `bibliography.json` + `evidence_pool.json` and emits the Tier-1 v2 YAML schema used by the Q5 pilot (`q5_claims_enumeration.yaml`). Splits on sentence boundaries handling inline `[N]` citation tokens. Skips Analyst-Synthesis sections (hedged-only). Each cited [N] is mapped via bibliography to its evidence_id then to the `direct_quote` ~500-char span_text from the pool.
2. `.codex/I-eval-003/q{1..4}_claims_enumeration.yaml`: 189 audit-grade claims across the four reports.
3. `.codex/I-eval-003/codex_q{1..4}_batch_{N}_output.txt`: 24 Codex batches with Tier-1 v2 records (claim_type / materiality / citation_context_match / verdict / rationale / reviewer_confidence).
4. `.codex/I-eval-003/aggregate_verdict_distribution.md`: cross-report verdict + context-match totals, per-batch detail, and three identified limitations.

# Codex pass coverage

- Q1: 31 claims / 5 batches → 8V/10P/13U
- Q2: 46 claims / 7 batches → 3V/15P/28U
- Q3: 61 claims / 9 batches → 11V/12P/38U
- Q4: 51 claims / 8 batches → 12V/9P/30U
- Total: 189 claims, 24 Codex batches. Aggregated with Q5 (28 claims, 24V/4P/0U) gives 217 claims, 58V/50P/109U.

# Acceptance criteria

1. Enumerator script reads only the verified-findings sections of each report (truncates at Analyst Synthesis marker) — synthesis text is hedged per the report header and not audit-grade.
2. Each cited `[N]` token in a sentence is mapped to its `evidence_id` via bibliography.json and to its `direct_quote` span_text via evidence_pool.json. Sentences without [N] are filtered.
3. Codex pass per batch outputs valid Tier-1 v2 records: claim_id matches enumeration, all 6 fields filled, batch_summary present.
4. Aggregate writeup honest about what was NOT done (Claude's independent parallel pass on Q1-Q4 is pending) per §-1.1 banned-shortcut clause "no sample-based audits" — flagging incomplete coverage explicitly is the opposite of dressing it up.

# §-1.1 alignment

- Line-by-line: 217/217 claims audited claim-by-claim by Codex (per-claim verdict + rationale + reviewer_confidence).
- Industrial frameworks: applied per Codex prompt (PRISMA / regulatory schema implied by claim_type taxonomy). Not separately tagged in this iteration; that's a Tier-1 v3 schema upgrade for a follow-up Issue.
- Both Claude AND Codex: PARTIAL — Codex side covered Q1-Q4 + Q5; Claude side covered Q5 only (PR #421). Aggregate writeup flags this gap explicitly.
- Banned (metadata / pattern / sample / string-presence / aggregate-tally framings): not used.

# Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
