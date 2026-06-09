# I-beatboth-fix-000 (#1171) — Faithfulness leak design (drb_90)

Design only. No code edited. Authored by the research+design subagent.

## Cluster
FAITHFULNESS LEAK: material UNSUPPORTED claims survive into the **shipped
report.md** because the assembled artifact is never reconciled against the
authoritative 4-role D8 verdicts. The gate only flips a manifest status flag
(`four_role_held` / `release_allowed=False`); it never redacts/regenerates
report.md. Orthogonal to the drb_72 BUG-01/02/03/11 cluster (those tighten
strict_verify; none close this assemble-before-the-authoritative-gate gap).

## Frontier best practice (2025-2026)
Claim-level grounding with span-scoped NLI, fail-closed on any claim not
entailed by its CITED passage. A citation pointing at the wrong span is itself
a faithfulness failure. Safety-critical RAG must surface/abstain on
un-grounded content, never present it as verified prose. The strongest
verifier's verdict must bind the SHIPPED artifact: an unsupported claim is
redacted to a visible gap, never left in the body.
Sources: ALCE arXiv 2305.14627; Auto-GDA ICLR 2025 arXiv 2410.03461; Verified
Misguidance arXiv 2605.28565; Why Your Deep Research Agent Fails arXiv
2601.22984; Claim-Level Auditability arXiv 2602.13855; DeepFact arXiv
2603.05912; MedRAGChecker arXiv 2601.06519; The Energy to Say No openreview
MtKSNKnNzN.

## Root cause (confirmed: source + run-record)
`scripts/run_honest_sweep_r3.py`:
1. report.md is **written at L5616-5620** (`final_report = _key_findings +
   sections_concat + methods + biblio_section; (run_dir/'report.md').write_text`)
   — body = strict_verify-KEPT sentences only.
2. The authoritative 4-role D8 seam runs **AFTER**, ~L6300-6456:
   `build_native_gate_b_inputs` builds `FourRoleClaim` rows ONLY from kept
   `is_verified` sentences (`native_gate_b_inputs.py:461-466`), re-judges them
   (Mirror/Sentinel/Judge, + FX-03 cited-span window when
   `PG_GATE_B_CITED_SPAN=1`); `apply_d8_release_policy`
   (`release_policy.py:178-306`) returns `release_allowed=False` + held_reasons.
3. The runner consumes that **ONLY as metadata**: L6404
   `manifest['release_allowed']`; L6406-6415 `summary_status='four_role_held'`
   + `manifest['status']=abort_four_role_release_held`; L6422-6441 writes
   `four_role_evaluation` incl `needs_rewrite` (L6429). **Nothing redacts /
   regenerates report.md against the verdicts.** The ONLY post-gate report.md
   mutation is the V30 **additive** Methods append at L6490-6532
   (`append_disclosure_to_report`) — never redactive.

RUN-RECORD PROOF (drb_90): `held_reasons =
[d8_unsupported_residual_below_coverage, d8_pending_rewrite]`; `needs_rewrite =
[01-000, 01-001, 02-000, 04-002, 05-001, 06-000, 06-002]` (7 material
UNSUPPORTED). Those exact sentences are PHYSICALLY PRESENT in the shipped
report.md:
- 01-000 "Instrument: UN Regulation No. 157 - Automated Lane Keeping Systems
  (ALKS)" = report.md:32
- 06-002 "Violations of the NHTSA General Order can result in civil penalties
  of up to $27,874 per violation per day, with a maximum of $139,356,994..." =
  report.md:64
- 06-000 NHTSA-not-statistically-representative = report.md:64
- 05-001 = report.md:60

strict_verify passed them; the stronger 4-role seam rejected them; the report
still ships them. That is the leak.

SECONDARY (designed-but-unwired refuse-in-place): `release_policy.py` docstring
L16-26 specifies "UNSUPPORTED is RESIDUAL-gated: one rewrite/refuse-in-place
attempt". `needs_rewrite` + `rewrite_already_attempted` EXIST, but
`rewrite_already_attempted` is **hardcoded False** (`native_gate_b_inputs.py:529`)
and `needs_rewrite` has exactly ONE consumer — the manifest write at L6429
(grep-confirmed across run_honest_sweep_r3.py / run_gate_b.py /
sweep_integration.py). The presumed rewrite/refuse-in-place pass never executes.

MAPPING CAVEAT (load-bearing, `run_honest_sweep_r3.py:5660-5669` in-tree
comment): the report body is **NOT 1:1** with `kept_sentences_pre_resolve`
("sentences listed as dropped were still appearing in report.md because
downstream dedup/repair passes had accepted them"). Therefore claim->report
redaction MUST fail closed if a needs_rewrite claim is unlocatable.

## D8 coverage-gate dispute — DEFINITIVE RULING (drb_72 CORRECT; drb_90 WRONG)
The coverage gate is a LEGITIMATE fixed-denominator semantic-coverage fraction,
NOT a forbidden count. Evidence:
- `release_policy.py:120-124` `fraction() = len(required & covered_element_ids)
  / len(required)`; `:241` fires when `fraction() < coverage_threshold`
  (0.70, `d8_release_policy.yaml:27`).
- Denominator = the PRE-REGISTERED `required_entities` set loaded fail-closed
  from the scope contract (`native_gate_b_inputs.py:447-448` `load_required_
  entities -> template[per_query_report_contract][slug].required_entities`;
  `:526` `CoverageLedger(required_element_ids=...)`).
- Numerator credited ONLY by citation-supported VERIFIED final verdicts
  (`sweep_integration.py:614-615`).
- drb_72 = 2/7 = 0.286; drb_90 = 2/6 = 0.333.

Why it is NOT a §-1.1-banned count: the §-1.1 ban targets counts used as a
FAITHFULNESS/CREDIBILITY proxy and SOURCE-TYPE-count floors. This gate measures
COMPLETENESS of a fixed pre-registered semantic contract — a different axis —
and is un-gameable in the forbidden direction (dropping/refusing a claim LOWERS
the fraction because the denominator is fixed). drb_90's audit conflated
"uses a fraction" with "is a forbidden count proxy". **RULING: no change to the
coverage gate. Keep the two held_reasons surgically separate: reason 1
(coverage_shortfall) is a legitimate completeness gate; reason 2
(pending_rewrite / material unsupported in the body) is the faithfulness leak
this fix targets.**

## Fix design
### PRIMARY (close the leak, fail-closed)
- Where: new post-gate hook in `scripts/run_honest_sweep_r3.py` after the
  4-role block (~L6456) and **BEFORE** the V30 append (L6490); logic in a new
  pure helper under `src/polaris_graph/roles/`.
- What: for EVERY claim whose `final_verdict` is material-non-VERIFIED
  (UNSUPPORTED/FABRICATED/UNREACHABLE/PARTIAL at S0/S1/S2 — the set
  release_policy already routes to needs_rewrite/gaps), look up the verbatim
  `claim_text` from the M3a `audit_map` / `FourRoleClaim.claim_text` (NOT a
  re-hash) and REMOVE that exact sentence from the WHOLE report.md (body AND
  the carried-up Key Findings block at report.md:19-20), replacing with the
  existing visible gap language ("did not survive verification; curator-
  actionable gap", as already used at report.md:9/15/18/26). Write report.md
  back. Emit one `redacted_unsupported` entry per removed claim into gaps.json
  (reuse `release_policy.Gap` kind `_GAP_RESIDUAL_UNSUPPORTED`).
- **FAIL CLOSED**: if a material-non-VERIFIED claim_text cannot be located
  verbatim, do NOT ship — hard-abort with a new terminal status
  `abort_report_redaction_failed`. Redaction MUST run on the HELD path too (the
  §-1.1 forensic audit reads report.md, not the manifest).
- Flag: default-ON fail-closed (no silent downgrade per LAW II / operator
  no-cap directive). Optional kill-switch `PG_REDACT_HELD_UNSUPPORTED` for
  documented offline-test isolation ONLY; production default = ENABLED.

### SECONDARY (wire the designed refuse-in-place)
- `native_gate_b_inputs.py:529` + `sweep_integration.py` (consume
  needs_rewrite) + `run_honest_sweep_r3.py`: realize the policy docstring's
  "one rewrite/refuse-in-place attempt" AS the PRIMARY redact-to-gap step (the
  redaction IS the refuse-in-place). Do NOT bundle a generative rewrite (new
  spend / new claims). Surface in the manifest that the attempt ran. Turns the
  dead `needs_rewrite` signal into a real artifact mutation.

### D8 ruling
No code change (see ruling above).

### SCOPE GUARD
Keep the existing BUG-11 S3-disclosure decision (cluster plan L233-242): S3
observe-only off-contract claims stay disclosure-only (non-gating); only
material (S0/S1/S2) non-VERIFIED claims are redacted. Avoids a blanket recall
cut and keeps this fix orthogonal to the drb_72 cluster.

## Smoke plan (proof by evidence — named drb_90 IDs; synthetic-only insufficient)
OFFLINE:
1. Fixture from real artifacts: load
   `outputs/vm_forensic/drb_90_adas_liability/report.md` +
   `four_role_claim_audit.json`; build a `four_role_result` marking exactly
   01-000, 01-001, 02-000, 04-002, 05-001, 06-000, 06-002 UNSUPPORTED, rest
   VERIFIED.
2. Run the new reconciliation helper over (report.md, four_role_result,
   audit_map). ASSERT:
   (a) each of the 7 named claims' verbatim text is ABSENT/replaced by the gap
       marker — '$27,874 per violation' (06-002, report.md:64) and 'UN
       Regulation No. 157 - Automated Lane Keeping Systems (ALKS)' (01-000,
       report.md:32) no longer appear as asserted prose;
   (b) PRECISION not blanket recall — VERIFIED kept claims SURVIVE (the OR
       0.457/0.171 sentence report.md:60; the SAE-taxonomy kept sentence
       report.md:56);
   (c) gaps.json gains one redacted_unsupported entry per removed claim.
3. FAIL-CLOSED test: feed a needs_rewrite claim whose claim_text is NOT
   verbatim in report.md (simulate the 5660-5669 dedup/repair drift) -> ASSERT
   the helper raises / query takes `abort_report_redaction_failed` and report.md
   is NOT shipped unredacted.
4. HELD-PATH test: assert redaction runs even when `release_allowed=False`.
5. Coverage-gate regression: run `apply_d8_release_policy` over the drb_90
   d8_rows unchanged -> ASSERT held_reasons still contains
   `d8_unsupported_residual_below_coverage` at coverage 0.333 (legitimate gate
   untouched).
LIVE PROBE (small): one cheap single-question single-section micro-run that
yields >=1 strict_verify-kept sentence the 4-role seam rejects (or replay
drb_90 inputs through the seam) -> confirm the on-disk report.md contains ZERO
seam-rejected claim sentences as asserted prose, and manifest
`four_role_evaluation.needs_rewrite` is 1:1 with gaps.json redaction entries.

## Risks
1. **MAPPING/FAIL-CLOSED is the one thing that breaks the fix if missed**: body
   not 1:1 with kept_sentences_pre_resolve (5660-5669); MUST hard-abort (not
   ship) on an unlocatable material claim. Spot-checks (01-000, 06-002
   verbatim) make it "mostly" hold — but "mostly" is the §-1.1-lethal gap.
2. Over-redaction/recall cut: exact-text match on material S0/S1/S2
   non-VERIFIED only; never S3/fuzzy.
3. Key Findings carry-up (report.md:19-20) must also be scanned.
4. drb_72 FX-01/02/03 change WHICH sentences reach the seam (the "7" count is
   not stable; FX-03 cited-span shifts it); anchor to the STRUCTURAL gap (any
   material non-VERIFIED claim in the body), not exactly 7.
5. Held-vs-shipped: rebut head-on — the §-1.1 forensic audit reads report.md
   (not the manifest); a held run's report.md is what a human inspects and must
   be fail-closed consistent.
6. Ordering/blast-radius: the hook runs once per query on an assembled report
   (string ops, no network) — low blast radius; redact BEFORE the V30 append
   (L6490) so the disclosure reflects the redacted body.
7. Codex framing: present as WIRING existing release_policy refuse-in-place
   machinery (needs_rewrite / rewrite_already_attempted already exist), not a
   new gate, and keep the D8-dispute ruling (no change) surgically separate.
