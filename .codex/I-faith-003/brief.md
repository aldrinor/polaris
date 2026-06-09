HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Brief review — I-faith-003 (#1174): redactor leaks UNSUPPORTED S3 (observe-only) claims into the shipped report

You are reviewing the ACCEPTANCE CRITERIA + fix direction (not a diff yet). APPROVE iff the plan correctly and completely closes the leak without a faithfulness regression or over-redaction.

## Context (from the beat-both run-5 dual §-1.1 audit + bug forensic, BB5-F01)
The 5-question benchmark run produced reports that were §-1.1 line-by-line audited. Confirmed IN RENDERED OUTPUT (not inferred): claims the binding 4-role (D8) verifier marked **UNSUPPORTED** ship as asserted, cited prose whenever their severity is **S3 ("observe-only")**. Across all 5 Qs: 39 UNSUPPORTED final verdicts, 13 redacted, **26 leaked**; per-Q leaked drb_72=6, drb_75=5, drb_76=3, drb_78=9, drb_90=3. Example (drb_76 Safety, zero redaction tombstone): "current evidence advises against routine probiotic use in patients with central venous catheters, immunosuppression, or critical illness.[4]" — an UNSUPPORTED clinical-safety instruction shipped as fact. Clinical = §-1.1 lethal-class.

## Root cause (code-confirmed)
`src/polaris_graph/roles/report_redactor.py::reconcile_report_against_verdicts` (lines 147–223). The redaction loop at **line 186**:
```
severity = str(meta.get("severity", ""))
if not _is_material_non_verified(verdict, severity, material_severities):
    continue   # VERIFIED survives; S3 observe-only ships disclosure-only (scope guard)
```
`material_severities` defaults to `("S0","S1","S2")` (DEFAULT_MATERIAL_SEVERITIES). So an UNSUPPORTED claim rated S3 is SKIPPED by the redactor and ships. S3 is assigned by `native_gate_b_inputs.py::_DEFAULT_OBSERVE_ONLY_SEVERITY` to any claim that covers **no pre-registered contract entity** (line 55, 482). So "covers no required entity" silently became "never redacted, even when UNSUPPORTED."

The conflation: S3 correctly means "does NOT gate/latch the RELEASE" (a non-required observation should not block release). That latch semantics live in `release_policy.py` (material_severities, line 48–173) and are CORRECT. But the same severity guard was wrongly extended to the **redaction** path, which must be severity-INDEPENDENT: a claim the verifier says is UNSUPPORTED must not ship as asserted fact regardless of whether it is a required entity.

## Proposed fix direction
1. **Decouple redaction from severity.** In `reconcile_report_against_verdicts`, the redaction decision becomes: redact iff the verdict is non-VERIFIED (UNSUPPORTED / FABRICATED / UNREACHABLE), **regardless of severity**. Keep recording `severity` on each `RedactedClaim` for the manifest. Do NOT use `material_severities` to EXEMPT a non-VERIFIED claim from redaction. (Severity / `material_severities` remains valid for the RELEASE LATCH in release_policy.py — out of scope here; do not change release-latch gating.)
2. **Fail-closed preserved exactly as today:** a non-VERIFIED verdict with no audit_map row still raises ReportRedactionError (line 178–182); present-but-unlocatable still raises (line 213–219); empty claim_text still raises (line 195–198). VERIFIED still never redacts (line 177 comment + the non-verified guard).
3. **No marker-strip regression:** the existing span-based byte-preserving `_redact_sentence` (Codex iter-1 P1 from #1171) is unchanged — VERIFIED neighbors keep their `[N]` citation markers byte-for-byte.
4. **Manifest auditability:** persist per-claim {severity, verdict, claim_id→sentence} for redacted AND already-absent claims so the reconciliation is line-by-line auditable (`already_absent` is already collected at line 220; surface it + severities to the manifest via the run_honest_sweep_r3 caller).
5. **By-design guards (DO NOT regress):** do not re-enable analyst synthesis or any unverified-prose surface (BB5-D01). Do not weaken any release-gate latch. Do not change `_DEFAULT_OBSERVE_ONLY_SEVERITY` (S3-as-default is correct for the LATCH; only the redaction path must stop honoring it as an exemption).

## Acceptance criteria
- AC1: every non-VERIFIED 4-role verdict present in `report.md` is redacted (refused-in-place with the visible gap language), regardless of severity (S0/S1/S2/**S3**).
- AC2: fail-closed unchanged: missing audit row / unlocatable-but-present / empty claim_text on a non-VERIFIED claim → ReportRedactionError.
- AC3: VERIFIED claims never redacted; their `[N]` markers preserved byte-for-byte; no over-redaction of verified content (S3-VERIFIED still ships).
- AC4: regression test on the REAL drb_76 fixture (`tests/fixtures/drb90_redaction/` pattern — add a drb_76 fixture if needed): an UNSUPPORTED S3 safety sentence is redacted (tombstone present); a VERIFIED neighbor keeps its citation marker.
- AC5: existing `tests/roles/test_report_redactor_iready017.py` stays green (S0/S1/S2 behavior unchanged).
- AC6: manifest persists per-claim severity+verdict+absent list (auditability).

## Files I have ALSO checked and they're clean (scan results)
- `src/polaris_graph/roles/report_redactor.py` — the only redaction decision site is line 186; `_is_material_non_verified` (the severity guard) and `_redact_sentence` (byte-preserving) are the relevant helpers; lines 24/49/50/161/187 are comments documenting the S3-never-redacted guard (must be updated to match the new behavior).
- `src/polaris_graph/roles/release_policy.py` — material_severities used for the RELEASE LATCH only (lines 48, 70, 153, 173). Out of scope; not changed.
- `src/polaris_graph/roles/native_gate_b_inputs.py` — `_DEFAULT_OBSERVE_ONLY_SEVERITY=S3` (line 55) for claims covering no required entity; `validate` FAILS CLOSED and never defaults to S3 (line 240–251). Not changed (S3-as-default for the latch is correct).
- `scripts/run_honest_sweep_r3.py` — the redactor caller (PG_REDACT_HELD_UNSUPPORTED=1 default-ON); manifest persistence of redaction records lives here.
- Branch context: redactor lives only on `bot/I-ready-017-faithfulness` (the beat-both deploy/run branch; report_redactor.py NOT on polaris/main; no open PR). This fix extends that branch.

## Questions for you (Codex)
- Q1: Is "redact ALL non-VERIFIED regardless of severity" correct, or should UNREACHABLE be treated differently from UNSUPPORTED/FABRICATED (e.g., UNREACHABLE = couldn't verify, not wrong)? My default: redact all non-VERIFIED (fail-safe — an unverified claim must not ship as asserted fact). Confirm or correct.
- Q2: Any over-redaction risk you see — a legitimate class of S3 claim that SHOULD ship despite a non-VERIFIED verdict? (Honest gap-disclosures are separate tombstones, not claims with verdicts, so they are unaffected — confirm.)

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
