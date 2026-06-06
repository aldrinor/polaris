# FX-07 leg 1 §-1.1 audit — frame_coverage footer no longer falsely claims "all bound" (I-ready-017 #1110)

**Standard:** §-1.1 on REAL output. Input = the held drb_72 manifest's actual
`frame_coverage_report` (`outputs/audits/I-ready-017/run_artifacts/manifest.json`).

## The bug, on the real artifact (BUG-08 + BUG-09)

The real `frame_coverage_report`: `pass_count=7, total=7, gap=0, partial=0,
pipeline_fault=0` — every entry `status=pass`. But only **3 of 7** entries are
`open_access` (full text); the other **4 are abstract_only / metadata_only**:

| entity | status | provenance_class |
|---|---|---|
| acemoglu_restrepo_automation_tasks | pass | open_access |
| autor_why_still_jobs | pass | open_access |
| fourth_industrial_revolution_framing | pass | open_access |
| acemoglu_restrepo_robots_jobs | pass | **abstract_only** |
| frey_osborne_computerisation | pass | **metadata_only** |
| brynjolfsson_genai_at_work | pass | **abstract_only** |
| eloundou_gpts_are_gpts | pass | **abstract_only** |

The old `compose_methods_disclosure` emitted "Frame coverage: all 7
contract-required entities populated with **bound evidence**." That CONTRADICTS
the report body ("frey_osborne did not survive strict verification"; eloundou
non-extractable) — abstract/metadata-only is NOT full-text bound evidence.

## The fix, replayed on the SAME real frame_coverage_report (no spend)

Reconstructed the persisted `FrameCoverageReport` exactly and ran the new footer:

```
Frame coverage disclosure (V30 Report Contract):
  - Total contract-required entities: 7
  - Fully populated (full-text bound evidence): 3
  - Populated from abstract/metadata only (full text NOT retrieved): 4 (acemoglu_restrepo_robots_jobs, brynjolfsson_genai_at_work, eloundou_gpts_are_gpts, frey_osborne_computerisation)
  - Gap slots render explicit gap language in the relevant subsection; see manifest.json frame_coverage_report for per-slot detail.
```

**Audit verdict: PASS.** The footer no longer claims "all 7 bound"; it reports
the true full-text count (3) and names the 4 abstract/metadata-only entries as a
disclosed gap. "all N bound" now fires ONLY when every pass entry is
`open_access`.

## Scope (leg 1 of 4 — the rest split to FX-07b)

The plan (`fix_campaign_plan.md` FX-07, line 128) explicitly allows the
footer/provenance leg to land independently. This PR is **leg 1 (footer)**.

Legs 2-4 are split into a follow-up (**FX-07b**) because their plan line-numbers
do not match the running system and they need careful path work:
- **Leg 2 (status='generation_failed' after strict_verify):** the plan cited
  `honest_sweep_integration.py:637-648`, but that is inside
  `_synthesize_phase1_validation` — the V30 path ships **retrieval-coverage**
  semantics (explicit code comment: "this verdict does NOT claim the generator
  cited the entity… Phase 2 will add true report-coverage"). The strict_verify
  per-slot drop signal (`contract_section_runner` `slot_drop_log` /
  `error="no_sentences_verified"`) is NOT currently threaded into this compose
  path. Threading it is an architectural change → route the data-path to Codex.
- **Leg 3 (disclosure ordering, honest_sweep_integration.py:147):** depends on
  the same coverage_fraction surfacing; pairs with leg 2.
- **Leg 4 (bibliography caveats):** the plan cited
  `generator/citation_mapper.py:810`, but the module is at
  `synthesis/citation_mapper.py`; the real report's bibliography composer must
  be confirmed before editing.

## Faithfulness-invariant check
No change to provenance / strict_verify / 4-role. Leg 1 only changes the
deterministic methods-disclosure prose; manifest KEY shape unchanged.

## Offline smoke
`pytest tests/polaris_graph/test_m60_frame_manifest.py` → **27 passed** (25
pre-existing with the intentional label update + 2 new leg-1 behavior tests:
real-shape 3-full-text/4-shallow → footer not "all bound" + names the 4;
all-open_access → "all N bound").
