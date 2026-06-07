# §-1.1 audit — FX-07b leg-2 (#1111) ROOT-CAUSE fix: frame_coverage substantive-prose honesty

**Standard:** §-1.1 line-by-line on the REAL held drb_72 generation artifacts
(`outputs/audits/I-ready-017/run_artifacts/`: `manifest.json` frame_coverage_report
+ `report.md` body + `verification_details.json` per-sentence ground truth). The held
run PREDATES the fix (Jun 5; telemetry/override commits Jun 6), so per the run's actual
per-entity ground truth (extracted by the 4-agent root-cause workflow + re-read here),
this audit maps each of the 7 frame_coverage entries to the TELEMETRY the fix computes
and the DECISION the override makes, and confirms it flips exactly the false-pass entries
to the HONEST owner-routed status (and nothing genuinely-covered).

The behaviour is additionally locked by focused unit tests built from these real shapes
(`tests/polaris_graph/test_m60_frame_manifest.py::TestFx07bLeg2PipelineFaultOverride`,
11 tests, all green).

## The discriminator (Codex-ratified root-cause design)
Per-(slot,entity), TOKEN-INDEPENDENT signals from `contract_section_runner`:
- `sentences_drafted_substantive` = count of `status=="extracted"` payload fields (real
  drafted prose), counted BEFORE `_rewrite_draft_with_spans` can strip an unspannable marker.
- `sentences_kept_substantive` = kept sentences EXCLUDING `_GAP_DISCLOSURE_MARKER`
  ("not extractable from available primary content") placeholders, attributed by primary token.
- `has_usable_quote` = `len(direct_quote.strip()) >= _MIN_VERIFIABLE_SPAN_CHARS` (50).

Override (non-gap, verdict==pass, not FRAME_GAP_UNRECOVERABLE):
`sentences_kept_substantive == 0` →
- `has_usable_quote AND sentences_drafted_substantive > 0` → **generation_failed** (pipeline fault, engineer-owned, human_completion_eligible=False)
- else → **curator_gap_no_substantive_content** (curator supplies licensed full-text, human_completion_eligible=True, is_pipeline_fault=False)

## Entry-by-entry on the REAL held manifest (claim-by-claim)

| entity_id (slot) | held manifest | report.md body (verbatim sense) | verification_details ground truth | telemetry the fix computes | fix decision | honest? |
|---|---|---|---|---|---|---|
| **frey_osborne_computerisation** (empirical_exposure) | status=**pass**, is_pipeline_fault=false, failure_reason=null, human_completion_eligible=false | report.md:38 "Contract-bound content for frey_osborne_computerisation **did not survive strict verification** … curator-actionable gap." | metadata_only, `direct_quote=""`; 5 not_extractable field-sentences in Empirical_Displacement.dropped, all `tokens:[]`, `failure_reasons:['no_provenance_token']`; 0× `ev:frey` anywhere | drafted_substantive=0, kept_substantive=0, has_usable_quote=False | **curator_gap_no_substantive_content** (is_pipeline_fault=False, human_completion_eligible=True) | ✅ was a LETHAL false pass → now an honest curator gap; correctly NOT a pipeline fault (no licensed full-text; curator-fixable) |
| **eloundou_gpts_are_gpts** (Class B) | status=pass | body entirely "X: not extractable from available primary content" | kept=5, every kept sentence a placeholder bearing a valid `[#ev:eloundou…]` token (non-empty quote) | drafted_substantive=0 (no extracted fields), kept_substantive=0 (all kept are placeholders, excluded), has_usable_quote=True | **curator_gap_no_substantive_content** | ✅ was a false pass (kept!=0 technicality) → honest curator gap; NOT a pipeline fault because nothing substantive was drafted |
| **fourth_industrial_revolution_framing** | status=pass | body all "not extractable" disclosures | kept placeholders only (open_access page yielded no extractable fields) | drafted_substantive=0, kept_substantive=0 | **curator_gap_no_substantive_content** | ✅ honest curator gap (no substantive verified prose) |
| **acemoglu_restrepo_automation_tasks** | status=pass | real extracted field prose ([1]) | kept=10 substantive | kept_substantive>0 | **pass (unchanged)** | ✅ genuine (partial) pass — has verified substantive prose |
| **acemoglu_restrepo_robots_jobs** | status=pass | real extracted prose ([4]) | kept=12 substantive | kept_substantive>0 | **pass (unchanged)** | ✅ genuine pass |
| **brynjolfsson_genai_at_work** | status=pass | real extracted prose ([6]) | kept=14 substantive | kept_substantive>0 | **pass (unchanged)** | ✅ genuine pass |
| **autor_why_still_jobs** | status=pass | extracted prose ([2]) | kept=157 (non-placeholder) | kept_substantive>0 | **pass (unchanged)** | ✅ for THIS fix (coverage-status honesty). NOTE: auditor 2 flagged autor's kept sentences include raw CoT scratchpad — a SEPARATE faithfulness bug tracked under drb_72 campaign #1100, OUT OF SCOPE for #1111 (which fixes the coverage-status, not CoT-leak). |

## Result
- **3 false passes flipped** to honest status: frey_osborne (Class A, metadata_only/empty-quote — the lethal manifest-vs-body contradiction), eloundou + fourth_industrial (Class B, placeholder-kept). All → `curator_gap_no_substantive_content`, is_pipeline_fault=False, human_completion_eligible=True (correctly routed to curator, NOT engineers).
- **4 genuine passes unchanged** (kept_substantive>0): acemoglu×2, brynjolfsson, autor.
- **Zero false flips**: no genuine-pass-with-substantive-prose reclassified; no extraction/retrieval gap (verdict!=pass) or FRAME_GAP_UNRECOVERABLE row touched (triple-guarded); missing telemetry → byte-identical.

## Fail-closed boundaries (unit-verified on real shapes)
- verdict!=pass (FAIL_MIN_FIELDS) zero substantive → STAYS partial (extraction gap).
- FRAME_GAP_UNRECOVERABLE → STAYS gap.
- pass with substantive kept>0 → unaffected.
- None/missing telemetry → non-overriding (byte-identical).
- usable-quote + substantive-drafted + zero-substantive-kept → generation_failed (engineer); no-usable-quote OR placeholder-only → curator_gap (curator). Owner routing is the §-1.1-critical distinction (mis-routing a curator gap to engineers would be a different dishonesty).

## Faithfulness
No change to strict_verify / provenance tokens / 4-role / two-family. Additive + default-None
(byte-identical when telemetry absent). Converts a misreported coverage "pass" with zero
substantive verified prose into the honest owner-routed status; never reclassifies a genuine
pass, extraction gap, or retrieval gap.
