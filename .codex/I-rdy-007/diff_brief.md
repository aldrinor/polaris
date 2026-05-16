# Codex diff review — I-rdy-007 (#503): live-run artifact contract

## §0. Iteration cap directive (CLAUDE.md §8.3.1, verbatim, binding)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**This is iter 2 of 5.** iter 1 returned REQUEST_CHANGES (2 P1 + 3 P2); all five
are addressed — see §1.5.

## §1. What you are reviewing

The **diff** for Issue #503 / I-rdy-007 against its APPROVED brief
(`.codex/I-rdy-007/brief.md`, verdict APPROVE iter-1 — `spec_scope_ruling:
spec-only-correct`, `schema_ruling: pin-existing-ok`).

Diff: `.codex/I-rdy-007/codex_diff.patch` — canonical `origin/polaris...HEAD`,
**1 file, ~327 lines**, commits `5124a3e7` + `0b0e8eb7`. The single file is the new
`docs/live_run_artifact_contract.md`. No code.

## §1.5. Changes since iter 1 (REQUEST_CHANGES → all 5 findings addressed)

- **P1-001 (contradiction projection under-specified).** §4 now carries a full
  `ContradictionCluster → ContradictionRecord` mapping as **adapter decision 4**:
  `contradiction_id ← f"contradiction_{cluster_id}"`; `section_id` derived by
  locating the first `verified_report` section citing `claims[0].evidence_id`
  (fallback `"unsectioned"`); `claim_a/_b` ← `claims[0/1]` rendered text
  (`context_snippet` or composed); `evidence_a/_b` ← the claims' `evidence_id`s;
  `resolution` ← mapped from `recommended_action`+`severity` (default `unresolved`);
  and explicit `>2-claims-per-cluster` handling left to I-rdy-008 to decide+test.
- **P1-002 (evidence_pool cardinality ambiguous).** §4 now **pins** it (not an open
  decision): one `SourceSpan` per **distinct `evidence_id`**, with an *envelope*
  span (`min` start / `max` end over all citing tokens); no duplicate `evidence_id`
  entries; per-sentence spans live in each sentence's `provenance_tokens`, not the
  pool. Rationale cited (consumers key by `evidence_id`).
- **P2-001 / factual inaccuracy (`evidence_pool.json` not read by `load_audit_ir`).**
  §3 is now split: §3a lists exactly what `load_audit_ir()` reads (5 required + 4
  optional); §3b states `evidence_pool.json` is read **directly by the adapter**,
  not by `load_audit_ir()`.
- **P2-002 / factual inaccuracy (status literals).** §2 now lists
  `lifecycle_status` incl. `cancelled` and `pipeline_status` incl. `partial_*`,
  with an explicit "match by prefix, not an enumerated list" note.
- **P2-003 (model-provenance optionality).** §4 **adapter decision 1** now specifies
  the model-identity fallback chain: `AuditIR.model_provenance` → `manifest.json`
  `models` block → fail-loud (422); never silently `family_segregation_passed=True`.
  §6 gains the matching 422 row.

The "two adapter decisions" framing from iter 1 is now **four** (model identity +
local/global split + frame-coverage aggregation + contradiction projection).

## §2. What the brief authorized

A **specification deliverable**: a contract document mapping a completed run's
artifacts to what the 7 rich consumer surfaces consume. No endpoint code — the
executable adapter + endpoint rewiring is I-rdy-008 (#504). "Schema'd" satisfied by
pinning the existing `EvidenceContract` / `RunStatusResponse` / `AuditIR` schemas
(your brief ruling).

## §3. Review focus — verify, do not re-discover

1. **Are the iter-1 findings genuinely closed?** Each §1.5 item — is the fix
   complete and correct against the repo?
2. **Factual accuracy.** §2 status values vs `src/polaris_v6/schemas/run_status.py`;
   §3a vs `load_audit_ir()`; §4 field map vs `evidence_contract.py` + `loader.py`
   dataclasses; §6 vs `bundle.py:89-152`.
3. **Contract completeness.** Is the §4 field map + the four named adapter decisions
   now complete enough for I-rdy-008 to implement without guesswork? Any *remaining*
   genuine ambiguity not named?
4. **Scope discipline.** Spec-only — no code, no premature wiring that belongs to #504.

## §4. Deliberate calls flagged for your ruling

- **No new schema file** — per your brief `pin-existing-ok` ruling.
- **~327-line diff** — one markdown document, **zero code**. The 200-LOC cap is a
  code cap; a spec document is not code (you confirmed this iter-1).
- **Four adapter decisions left open** (§4) — intentional: they are executable-adapter
  design choices owned by #504, not contract-spec decisions.

## §5. Output schema (CLAUDE.md §8.3.9 — bind to this)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
factual_inaccuracies: [...]
convergence_call: continue | accept_remaining
verdict_reasoning: <text>
```
Loose prose without the schema → resubmit.
