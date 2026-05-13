# Claude architect audit — I-arch-001b

**Canonical PR diff SHA256:** `4f5668f2bb27d04108553b87147fd9c7349559b8a3915a1a4a942d885b9976e0`

## Acceptance criteria

| Criterion | Status | Evidence |
|---|---|---|
| `build_v30_contract(v6_template, query_slug, question)` returns `{slug: <contract>}` | ✓ | `v30_contract_synthesizer.py:95-159` |
| schema_version="v30.1" | ✓ | line 153 + test_fixture_round_trips |
| `required_entities` shape per `_REQUIRED_ENTITY_KEYS` | ✓ | line 142-152 + 35-test parametrize |
| `rendering_slots` DICT keyed by slot_id with `_REQUIRED_SLOT_KEYS` | ✓ | line 130-141 |
| Every entity has concrete http(s) `url_pattern` (M-56 fetchable, NOT regex) | ✓ | `_concrete_url_for_entity` lines 64-82; verified by `test_synthesized_bindings_have_fetchable_url` |
| Stable `anchor` `<template_id>:<frame_id>:<slug[:40]>:<sha256_8>` | ✓ | `_anchor_for` lines 53-62; collision-safety test |
| 8 golden fixtures | ✓ | `tests/fixtures/v30_contracts/<8>.json` |
| actors.py invokes `polaris_v6.templates.registry.load_template` | ✓ | `actors.py:99` |
| actors.py logs warning on FileNotFoundError + generic Exception | ✓ | `actors.py:111-122` (exc_info=True on generic) |
| pipeline-A merges `q["v30_contract_patch"]` into scope template | ✓ | `run_honest_sweep_r3.py:1390-1396` |
| Non-v6 sweep (no `v6_mode`) → noop, byte-identical | ✓ | guard at line 1390; legacy CLI unchanged |
| Tests: 35 new, all pass | ✓ | 35/35 in 2.15s |
| Regression check: 1988 total | ✓ | 1988 pass + 1 pre-existing isolation failure |

## Codex review trail

| Iter | Verdict | Findings closed |
|---|---|---|
| 1 | REQUEST_CHANGES | P1-v30-synth-entities-need-m55-locators + P1-actor-synthesizes-from-wrong-template-source |
| 2 | REQUEST_CHANGES | P1-actor-synthesizes-from-wrong-template-source (real fix via load_template(template_id).model_dump()) |
| 3 | REQUEST_CHANGES | P1-synth-contract-can-still-pass-with-anchor-only-unfetchable-entities |
| 4 | REQUEST_CHANGES | P1-url_pattern-regex-is-not-M56-fetchable + P2-www-stripping-breaks-www150-hosts |
| 5 | **APPROVE** | zero P0/P1, 3 P2 nudges (frame-specific URL derivation, empty-T1 fail-loud, EvidenceBinding accessor) |

P2 nudges from iter 5 accepted as follow-up quality work (not blockers per Codex `convergence_call: accept_remaining`):
- Concrete T1 URL rotation often fetches landing pages — future iteration: question-aware URL derivation
- Empty-T1 fallback uses unrelated URL — future iteration: fail-loud
- EvidenceBinding accessor: implemented via `cf.contract.entities_by_id()[binding.entity_id]` in test_synthesized_bindings_have_fetchable_url

## Locator analysis (P1.4 verification)

The url_pattern emitted for each entity rotates through `template["source_tiers"]["T1"]`. For `clinical` template with T1 = `[fda.gov, cdc.gov, ema.europa.eu, www.cochrane.org, www.canada.ca/health-canada]`, entity[0]→fda.gov, entity[1]→cdc.gov, …, entity[5%5=0]→fda.gov. M-56's `_fetch_url_pattern()` receives these as literal http(s) URLs and dispatches to AccessBypass → real fetch.

Anchor (`clinical:efficacy:clinical_fixture:abc12345`) remains as secondary stable id; not used as M-56 retrieval locator.

## Smoke

- 35 new tests pass (8 parametrized × 4 + 3 single)
- Full suite: 1988 passed
- Pre-existing `test_demo_smoke.py::test_main_returns_0_when_app_healthy` fails in full-suite ordering only (pollution from earlier test); passes in isolation pre AND post my changes

## Out of scope (per APPROVED brief; routed to downstream)

- frame-specific URL derivation (Codex iter-5 P2 #1) — follow-up quality work
- empty-T1 fail-loud (Codex iter-5 P2 #2) — future template iteration
- I-arch-001c scope_domain expansion (templates housing/trade/defense/climate map to "policy" at actor boundary today)

## Verdict

SHIP. Brief APPROVE iter 5; 35 tests pass; 1988 total pass; LOC: 1218 inserted across 12 files
(synthesizer 164 + actors 37 + pipeline-A 8 + 8 fixtures × ~109 + tests 135). Above brief budget
~350 because 8 fixtures × ~109 LOC = ~870 LOC. The fixtures are pure data, not source code,
and exist solely so synthesizer drift is caught at PR review time.
