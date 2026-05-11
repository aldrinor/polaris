# Codex independent line-by-line audit — POLARIS tirzepatide-T2DM

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- "Don't pick bone from egg" — reserve P0/P1 for real fabrication or
  citation-appropriateness blockers.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Your role

You are the **INDEPENDENT parallel auditor** per CLAUDE.md §-1.1. Claude has already done a partial audit (5 of ~30 body claims). You re-audit the SAME report INDEPENDENTLY — do NOT read Claude's audit doc until you have written your own verdicts. After Codex completes, Claude and Codex cross-review and reconcile.

## Report to audit

`outputs/I-beat-001_round3/clinical/clinical_tirzepatide_t2dm/report.md`

Body sections to audit (per §-1.1 scope rules):
- `### Efficacy`
- `### Safety`
- `### Comparative`
- `### Mechanism`
- `### Regulatory`
- `### Limitations` (after `## Analyst Synthesis`)

**EXCLUDE from audit scope:**
- `# Research report:` title
- `## Analyst Synthesis` (synthesis layer — separate audit lane)
- `## Methods`, `## Contradiction disclosures`, `## Bibliography`, `## V30 ...` (appended substrate)

## Audit framework

Per CLAUDE.md §-1.1 (clinical-safety-critical):

1. **Claim-by-claim** verdict against the actually-fetched cited source (NOT just title/abstract — fetch primary source if cited URL is paywalled, find an open mirror or PubMed abstract).
2. **Reasoning-step-by-reasoning-step** — verify each piece of reasoning follows from cited evidence.
3. **Citation-by-citation** appropriateness — is the citation appropriate for the claim (T1 primary trial for trial-decimal claims, T1/T2 SR for pooled estimates, T3 regulatory for label claims).
4. **Domain framework:**
   - GRADE per claim (HIGH/MODERATE/LOW/VERY LOW certainty)
   - Cochrane RoB 2 for cited RCTs (low/some concerns/high risk per domain)
   - AMSTAR-2 for cited systematic reviews (HIGH/MODERATE/LOW/CRITICAL LOW confidence)
   - ICMJE for authorship + COI flags

## Verdict rubric per claim

- **VERIFIED** — fully supported by cited span
- **PARTIAL** — partially supported, hedged, or numeric precision mismatch
- **UNSUPPORTED** — content overlap insufficient; cited span doesn't back claim
- **FABRICATED** — sentence asserts content not in any cited span (numeric mismatch, named-entity inflation, etc.)
- **UNREACHABLE** — span pointer invalid; cannot verify

## Inputs

- Report: `outputs/I-beat-001_round3/clinical/clinical_tirzepatide_t2dm/report.md`
- Bibliography: `outputs/I-beat-001_round3/clinical/clinical_tirzepatide_t2dm/bibliography.json` (10 sources, [1]-[10])
- Evidence pool (retrieved snippets): `outputs/I-beat-001_round3/clinical/clinical_tirzepatide_t2dm/evidence_pool.json` (20 entries)
- For each cited URL in bibliography, you may need to fetch the primary source (use curl or web access) for §-1.1 compliance.

## Output schema (binding)

```yaml
verdict: APPROVE | REQUEST_CHANGES
audit_summary:
  total_body_claims_identified: <int>
  verdicts:
    VERIFIED: <int>
    PARTIAL: <int>
    UNSUPPORTED: <int>
    FABRICATED: <int>
    UNREACHABLE: <int>
  fabrication_rate: <float>
  citation_appropriateness_failures: <int>
per_claim_verdicts:
  - claim_id: C1
    claim_text: "...first 150 chars..."
    cited_sources: [1]
    primary_source_verified: yes | no
    decimals_match: yes | no | n/a
    reasoning_sound: yes | partial | no
    citation_appropriate: yes | partial | no
    grade_certainty: HIGH | MODERATE | LOW | VERY_LOW
    rob_2_overall: low | some_concerns | high | n/a
    verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
    reason: "specific finding"
  - claim_id: C2
    ...
findings:
  - id: F1
    type: duplicate_citation | t4_substitution | numeric_mismatch | reasoning_gap
    description: "..."
    severity: P0 | P1 | P2 | P3
convergence_call: continue | accept_remaining
```

Audit ALL body claims (~30 expected). Do NOT sample. Per §-1.1: sample-based audits are STRICTLY BANNED.

If any claim FABRICATED → verdict = REQUEST_CHANGES with explicit identification of the fabrication.
If zero FABRICATED + zero UNREACHABLE → verdict = APPROVE.

## Why this matters (one paragraph)

This is the BEAT-BOTH proof against ChatGPT DR + Gemini DR for Carney delivery. We need an independent Codex audit to cross-check Claude's findings on POLARIS. After this, you'll audit ChatGPT DR and Gemini DR with the same framework. Cross-review combines all three Codex audits with Claude's. Disagreements escalate to user-as-spec-owner.
