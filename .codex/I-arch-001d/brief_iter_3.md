HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001d iter 3 — section_status cascade + final corrections

## P1-001-continuing — Recompute section_status, not just sentence rates

**Code-verified**: `SectionStatus = Literal["verified", "regenerated", "dropped"]` (`verified_report.py:29`). Success validation (`verified_report.py:467-487`) only counts sections with `section_status != "dropped"`. Marking sentences as failed but leaving `section_status="verified"` would pass success-validation with a fully-redacted section.

**Resolution**: after sovereignty cascade, set `section_status="dropped"` for any section with zero remaining `verifier_pass=True` sentences:

```python
for section_idx, section in enumerate(sections):
    kept = []
    for sent in section.verified_sentences:
        sent_tokens = _parse_provenance_tokens(sent.provenance_tokens)  # see P2 note below
        evidence_ids_used = {t.evidence_id for t in sent_tokens}
        all_cleared = evidence_ids_used.issubset(cleared_evidence_ids)
        if all_cleared:
            kept.append(sent)
        else:
            kept.append(sent.model_copy(update={
                "verifier_pass": False,
                "drop_reason": "invalid_token",  # closest legal — references a redacted source
            }))
    pass_count = sum(1 for s in kept if s.verifier_pass)
    # P1-001-continuing: recompute section_status — drop the section when
    # NOTHING passes; otherwise preserve "verified" / "regenerated".
    new_status = "dropped" if pass_count == 0 else section.section_status
    sections[section_idx] = section.model_copy(update={
        "verified_sentences": kept,
        "section_verify_pass_rate": pass_count / max(len(kept), 1),
        "section_status": new_status,
    })

# Recompute overall_verify_pass_rate over non-dropped sections only
non_dropped = [s for s in sections if s.section_status != "dropped"]
if not non_dropped:
    raise SovereigntyFilterEmptiedReportError(
        "every section dropped after sovereignty cascade; bundle cannot be assembled"
    )
overall = sum(s.section_verify_pass_rate for s in non_dropped) / len(non_dropped)
```

This guarantees: if even ONE non-dropped section survives → `pipeline_verdict="success"` is valid + at least one section has real verified content. If ALL sections are dropped → bridge raises explicit error → endpoint returns 422.

## P2 from iter 2 → resolutions

### P2 (Q3) — DropReason full Literal list

**Code-verified**: full DropReason Literal at `verified_report.py:57-64`:
```python
DropReason = Literal[
    "invalid_token",       # token doesn't reference a known source_id
    "span_out_of_range",   # span_start > span_end or > len(full_text)
    "numeric_mismatch",
    "overlap_too_low",
    "no_provenance_token",
    "entailment_failed",
]
```

Updated normalization map (preserves the 2 missed Literals):

```python
_DROP_REASON_MAP = {
    "invalid_token": "invalid_token",
    "span_out_of_range": "span_out_of_range",
    "numeric_mismatch": "numeric_mismatch",
    "number_not_in_any_cited_span": "numeric_mismatch",
    "overlap_too_low": "overlap_too_low",
    "low_content_overlap": "overlap_too_low",
    "no_provenance_token": "no_provenance_token",
    "missing_provenance": "no_provenance_token",
    "entailment_failed": "entailment_failed",
}
def _normalize_drop_reason(raw: str | None) -> str | None:
    if raw is None:
        return None
    base = raw.split(":")[0].strip().lower()
    # Default to "invalid_token" (audit-grade conservatism): when classification
    # is unknown, we say the token reference itself can't be trusted.
    return _DROP_REASON_MAP.get(base, "invalid_token")
```

Sovereignty cascade uses `"invalid_token"` (per the rationale: a redacted source is one whose token reference cannot be trusted), aligned with the default.

### P2 (note) — provenance_tokens is `list[str]`, not typed

**Code-verified**: slice-chain `VerifiedSentence.provenance_tokens: list[str]` (`verified_report.py:81-84`). Each token is the raw string `[#ev:<evidence_id>:<start>-<end>]`. Need a parser to extract evidence_id:

```python
import re

_PROV_TOKEN_RE = re.compile(r"\[#ev:([^:]+):(\d+)-(\d+)\]")

def _evidence_ids_in_tokens(provenance_tokens: list[str]) -> set[str]:
    ids: set[str] = set()
    for tok in provenance_tokens:
        m = _PROV_TOKEN_RE.search(tok)
        if m:
            ids.add(m.group(1))
    return ids
```

Bridge constructs slice-chain `VerifiedSentence` from AuditIR `ReportSentence` (which DOES have typed `tokens: tuple[EvidenceSpanToken, ...]`) by serializing the tokens back to strings:

```python
def _tokens_to_provenance_strings(tokens: tuple[EvidenceSpanToken, ...]) -> list[str]:
    return [f"[#ev:{t.evidence_id}:{t.start}-{t.end}]" for t in tokens]
```

### P3 cosmetic — HTTPException detail wrapping

**Acknowledged**: FastAPI wraps `HTTPException(detail=X)` as `{"detail": X}` in response body. Test assertions use `body["detail"]["error"] == "..."` not `body["error"]`. Test scaffolding adjusted accordingly.

## Acceptance criteria (final iter-3)

1. `build_slice_chain` (per iter-2) + section_status cascade:
   - Sentences citing excluded sources → verifier_pass=False, drop_reason="invalid_token"
   - Section with zero passing sentences → section_status="dropped"
   - Zero non-dropped sections → SovereigntyFilterEmptiedReportError
2. provenance_tokens regex parser for evidence_id extraction (slice-chain VerifiedSentence uses string tokens, not typed)
3. AuditIR → slice-chain token serialization: typed EvidenceSpanToken → `[#ev:id:start-end]` string
4. DropReason normalization map includes invalid_token + span_out_of_range
5. SourceTier normalization (T4+/UNKNOWN → T3 + raw_tier provenance)
6. GET endpoint with Depends(get_sign_fn); 404 for missing/not-completed; 422 for aborted/sovereignty-emptied; 200 with signed tar.gz when bundleable
7. Tests covering all above + endpoint detail-shape assertions (`body["detail"]["error"]`)
8. LOC budget ~370 (bridge ~220 + endpoint ~50 + tests ~150)

## Direct questions iter 3

1. section_status="dropped" when section's `pass_count == 0` post-cascade — APPROVE'd?
2. SovereigntyFilterEmptiedReportError when ALL sections dropped → 422 — APPROVE'd?
3. provenance_tokens regex `\[#ev:([^:]+):(\d+)-(\d+)\]` — APPROVE'd, or want a stricter shape (e.g., evidence_id must be UUID-format)?
4. AuditIR `tuple[EvidenceSpanToken, ...]` → string token serialization — APPROVE'd?
5. DropReason fallback `"invalid_token"` (instead of `"no_provenance_token"`) — APPROVE'd as the audit-grade conservative default?
6. Anything else blocking iter-3 APPROVE?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```
