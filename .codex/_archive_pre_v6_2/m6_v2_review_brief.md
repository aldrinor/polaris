M-6 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-6 v1 verdict: PARTIAL with 5 areas of concern. All integrated in v2.

## What changed in v2

1. **IR extended** — `AdequacyGate` + `CorpusApprovalGate` types added,
   loaded from `manifest.adequacy` + `corpus_approval.json`.
   `RetrievalStats.queries` tuple added (parses both list-of-strings
   and `[{query: str}]` shapes).

2. **Audit-bundle endpoint hardened**:
   - **Fail loud** (500) on any missing canonical-required file
     (report.md / manifest.json / bibliography.json / contradictions.json
     / verification_details.json).
   - Optional files extended: + `run_log.txt` + `live_corpus_dump.json`
     + `cost_ledger.jsonl`.
   - **INDEX.txt rewritten** with explicit sections:
     - RUN IDENTITY (slug, run_id, protocol_sha256, status, created_at,
       word_count, cost, contradictions, release_allowed)
     - MODEL PROVENANCE (generator family/model, evaluator family/model)
     - GATE DECISIONS (adequacy, corpus, evaluator)
     - BUNDLE FILES + DIGESTS (sha256 + size + filename per line)
   - **MANIFEST.SHA256 file** with per-file SHA-256, verifiable via
     `sha256sum -c MANIFEST.SHA256`.

3. **Terminology fixed**: button text "Download audit bundle (ZIP)",
   not PDF.

4. **Two-family invariant**:
   - Missing `model_provenance` → distinct yellow warning banner
     ("NOT RECORDED").
   - Same-family pair → red violation banner with declared
     `methods-two-family-banner-violation` CSS.

5. **Retrieval queries** section added to view (lists queries; falls
   back to "not persisted by this run" when absent).

6. **Pre-generation gates** section added (adequacy + corpus_approval
   as structured KV table).

7. **Tier band logic fixed**:
   - Nullish-safe parsing: `exp.max_fraction == null` check, so
     explicit `max_fraction=0` stays 0 (forbidden tier).
   - Residual rows for tiers in actual distribution but absent from
     `expected_tier_distribution` — labeled "unexpected (no band
     declared)".

Tests: 145 → 155 (10 new router tests including HMAC-style digest
verification, monkeypatched-registry incomplete-run smoke test).

## Your job

Quick verification. Verdict: GREEN / STILL-PARTIAL / DISAGREE.

Spot-check:
- INDEX.txt content acceptable for procurement?
- MANIFEST.SHA256 verifiable with `sha256sum -c`?
- Fail-loud actually fails (500)?
- Retrieval queries surface correctly when absent?
- Pre-generation gates rendered?
- Missing-provenance warning + violation distinct style?
- Tier-band edge cases fixed?
- Any new issues?
- M-7 ready?

## Output

Write to `outputs/codex_findings/m6_v2_review/findings.md`:

```markdown
# Codex re-review of M-6 v2

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Fix integration
- [x/no] Bundle hardening (fail-loud + INDEX + MANIFEST.SHA256)
- [x/no] Terminology fixed (ZIP not PDF)
- [x/no] Two-family banner: warning + violation states
- [x/no] Retrieval queries surfaced
- [x/no] Pre-generation gates surfaced (adequacy + corpus approval)
- [x/no] Tier band edge cases (zero max, residual rows)

## New issues
none / list

## Final word
GREEN to lock M-6 / STILL-PARTIAL with edits.
```

Be terse. Under 100 lines.
