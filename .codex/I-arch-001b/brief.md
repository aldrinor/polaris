HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001b — V30 contract synthesizer + 8 template golden fixtures

GH#464. Day 4-6 of I-carney-001 Posture C plan. Builds on I-arch-001a (PR #475 merged) foundation. Parallel with I-arch-001c.

## Scope (per APPROVED I-carney-001 brief_v2 iter-3)

1. New module `src/polaris_graph/v30_contract_synthesizer.py` builds a v30.1 `per_query_report_contract.{slug}` dict from a v6 template + query slug.
2. 8 golden fixtures at `tests/fixtures/v30_contracts/<template_id>.json` — one per template (ai_sovereignty, canada_us, climate, clinical, defense, housing, trade, workforce).
3. Each synthesized contract round-trips cleanly through `polaris_graph.nodes.report_contract.load_report_contract_for_slug(template, slug)`.
4. Synthesizer used by actors.py (I-arch-001a wiring): when actors.py invokes pipeline-A with `v6_mode=True`, the synthesized contract is injected into the scope template's `per_query_report_contract.{q['slug']}` BEFORE pipeline-A runs `load_report_contract_for_slug`. This is what enables ad-hoc UUID-bound runs to satisfy V30 strict AuditIR loader (the architectural seam that brief v2 iter 4 P1-v30-artifact-shape established).

Force-APPROVE residuals from I-carney-001 brief v2 iter 5 captured for this Issue:
- **Synthesizer field naming**: emit `doi` / `pmid` / `url_pattern` (NOT `doi_pattern`). Per `report_contract.py:354-359` runtime accepts these as optional entity fields.

## v30.1 schema (verified at report_contract.py:170-220 + dataclass definitions)

```python
{
    "per_query_report_contract": {
        "<query_slug>": {
            "schema_version": "v30.1",                     # _KNOWN_SCHEMA_VERSIONS frozenset
            "required_entities": [                          # list
                {
                    "id": "<unique-within-contract>",       # str, _REQUIRED_ENTITY_KEYS
                    "type": "<entity-type>",                # str
                    "required_fields": ["fld1", "fld2"],   # list[str] — domain identifier field NAMES
                    "min_fields_for_completion": 1,         # int
                    "rendering_slot": "<slot_id>",          # must match a declared slot key below
                    # Optional pass-throughs:
                    # "doi": "10.xxxx/yyyy",
                    # "pmid": 12345678,
                    # "url_pattern": r"https?://...",
                    # "anchor": "...", "journal": "...", "year": 2024,
                    # "population_scope": "...", "jurisdiction": "...", "label_name": "..."
                },
                # ... more entities
            ],
            "rendering_slots": {                            # DICT keyed by slot_id (not list)
                "<slot_id_1>": {
                    "section": "<section_name>",            # str, non-empty
                    "subsection_title": "<title>",          # str
                    "ordering": 1,                          # int
                    "required": true                        # bool, optional, default True
                },
                # ... more slots
            },
            "section_order": ["Section A", "Section B"]    # optional list[str]
        }
    }
}
```

Referential integrity: every entity's `rendering_slot` MUST match a declared slot_id (report_contract.py:435-454).

## Synthesizer design

`src/polaris_graph/v30_contract_synthesizer.py`:

```python
def build_v30_contract(
    template: dict,
    query_slug: str,
    question: str | None = None,
) -> dict:
    """Synthesize a v30.1 per_query_report_contract.{query_slug} dict
    from a v6 template's frame_manifest.

    Inputs:
      template: loaded v6 template JSON (e.g. config/v6_templates/clinical.json)
      query_slug: pipeline-A URL-safe slug (e.g. "clinical_tirzepatide_t2dm")
      question: optional research question text (for entity_id seeding)

    Output: a single-key dict {query_slug: <contract>} where <contract>
    has schema_version="v30.1", required_entities, rendering_slots (dict-keyed),
    and section_order. Round-trip clean via load_report_contract_for_slug.
    """
```

Mechanical transform: each frame in `template["frame_manifest"]` →
- 1 rendering_slot with slot_id = `<frame_id>_slot`, section = template-derived section name, subsection_title from frame_name
- 1 required_entity with id = `<frame_id>_entity`, type = template's primary entity type (drug/policy/jurisdiction/...), required_fields = template-derived domain identifier names (clinical: [`rxcui`,`drugbank_id`,`icd_10`]; policy: [`bill_id`,`jurisdiction`,`year`]; etc.), min_fields_for_completion = 1, rendering_slot pointing to the slot above

`section_order` is derived from frame_manifest order or omitted (`load_report_contract_for_slug` tolerates None per dataclass definition).

## Files I have ALSO checked and they're clean (§-1.2 #2)

- `src/polaris_graph/nodes/report_contract.py:170-220` — `_REQUIRED_ENTITY_KEYS = {"id", "type", "required_fields", "min_fields_for_completion", "rendering_slot"}` + `_REQUIRED_SLOT_KEYS = {"section", "subsection_title", "ordering"}`
- `src/polaris_graph/nodes/report_contract.py:354-359` — runtime accepts optional `doi`, `pmid`, `url_pattern` on entities
- `src/polaris_graph/nodes/report_contract.py:381-454` — rendering_slots dict-keyed; entity.rendering_slot must match a declared slot_id
- `src/polaris_graph/nodes/report_contract.py:86-153` — `RequiredEntity`, `RenderingSlot`, `ReportContract` dataclasses (frozen)
- 8 templates at `config/v6_templates/*.json` all share the schema: `template_id`, `template_name`, `frame_manifest` (list of `{frame_id, frame_name}`), `primary_domains`, `source_tiers`, etc.
- I-arch-001a's `actors.py` does NOT yet inject the synthesized contract into the scope template; that wiring is in scope of this Issue.

## Acceptance criteria

1. `build_v30_contract(template, query_slug, question=None) -> dict` emits a schema-valid v30.1 contract dict
2. 8 golden fixtures at `tests/fixtures/v30_contracts/<template_id>.json` — each loads cleanly via `load_report_contract_for_slug(template, slug)` round-trip
3. Wire actors.py: before invoking pipeline-A, inject `{query_slug: <contract>}` into the resolved scope template's `per_query_report_contract` dict (or via q-dict if pipeline-A reads from q first)
4. Tests in `tests/polaris_graph/test_v30_contract_synthesizer.py`:
   - 8 parameterized test cases (one per template) verifying schema-valid output
   - Round-trip: synth → `load_report_contract_for_slug` returns `ReportContract` with same slug + schema_version
   - Referential integrity: every entity's `rendering_slot` matches a declared slot
   - Optional doi/pmid/url_pattern field-naming smoke (per residual fix)
5. LOC budget: 250 (synthesizer ~80 + 8 fixtures × ~30 lines avg = 240 + tests ~50). Likely overshoots; confirm acceptable.

## Direct questions iter 1

1. Mechanical-transform approach (1 frame → 1 slot + 1 entity) — APPROVE'd, or want frame-→-multi-entity (e.g., a frame about "policy comparison" producing one entity per jurisdiction)?
2. Per-domain `required_fields` defaults (clinical: rxcui/drugbank_id/icd_10; policy: bill_id/jurisdiction/year) — APPROVE'd as v1 defaults? Codex-review per template fixture happens in Issue review.
3. Synthesizer wiring point: inject into scope template's `per_query_report_contract` dict at actor boundary (BEFORE pipeline-A's `load_report_contract_for_slug` call) — APPROVE'd?
4. Round-trip test pattern (synth → load_report_contract_for_slug → assert dataclass attributes) — APPROVE'd?
5. LOC 250 overshoot acceptable (probable ~350 for synthesizer + 8 fixtures + tests)?
6. Anything else blocking iter-1 APPROVE?

## Resource discipline

Pre-task: 0 codex/python/node processes. Will check after each Codex iter and kill orphans per §8.4. No pipeline-A real runs during this Issue — synthesizer is pure pyhton + JSON I/O.

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
