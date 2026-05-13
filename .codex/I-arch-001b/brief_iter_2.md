HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001b iter 2 — M55 locator + actor boundary injection

## P1 from iter 1 → resolutions (code-verified)

### P1-v30-synth-entities-need-m55-locators

You wrote:
> "compile_frame requires at least one doi/pmid/url_pattern/anchor. As written it emits none, so compile_frame rejects every synthesized contract."

**Code-verified**: `src/polaris_graph/nodes/frame_compiler.py:276-289` (`_compile_binding`) raises `FrameCompilerError` when no identifier resolves. Locator priority: DOI → PMID → url_pattern → anchor.

**Resolution**: every synthesized entity MUST carry at least one locator. Mechanical derivation:

```python
# For each frame in template.frame_manifest:
entity = {
    "id": f"{frame_id}_entity",
    "type": _type_for_template(template_id),  # "policy" | "drug" | "regulation" | "frame"
    "required_fields": _required_fields_for_template(template_id),
    "min_fields_for_completion": 1,
    "rendering_slot": f"{frame_id}_slot",
    # NEW (iter-2 fix) — at least one M55 locator, always emitted:
    "anchor": f"{template_id}:{frame_id}:{query_slug[:40]}",
    # Optional pass-throughs if present in template metadata:
    "doi": frame.get("doi"),
    "pmid": frame.get("pmid"),
    "url_pattern": frame.get("url_pattern"),
}
```

Anchor format `<template_id>:<frame_id>:<query_slug_prefix>` is deterministic, unique per (template, frame, query), and routes to curator-actionable gaps (no real resolution; the compiler accepts the anchor as a placeholder per `_compile_binding` line 282). This unblocks compile_frame for synthesized contracts AND keeps the door open for templates to override with real `doi`/`pmid`/`url_pattern` when those are known at synthesis time.

### P1-actor-boundary-injection-not-currently-consumed

You wrote:
> "run_one_query loads _template internally from load_scope_template(q['domain']) and does not read a q-provided template/contract override."

**Code-verified**:
- `scripts/run_honest_sweep_r3.py:1381` `_template = load_scope_template(q["domain"])`
- `scripts/run_honest_sweep_r3.py:1936` `_cf = compile_frame(q["question"], _template, q["slug"])`
- `scripts/run_honest_sweep_r3.py:2785` `v30_result = run_v30_post_generation(..., scope_template=_template, ...)`

**Resolution**: add `q.get("v30_contract_patch")` consumption in pipeline-A. Right after `_template` is loaded, merge the patch into `_template["per_query_report_contract"]`:

```python
# scripts/run_honest_sweep_r3.py (insert after line 1382)
_v30_patch = q.get("v30_contract_patch") if q.get("v6_mode") else None
if _v30_patch and isinstance(_template, dict):
    _template.setdefault("per_query_report_contract", {}).update(_v30_patch)
```

`_v30_patch` shape: `{<query_slug>: <synthesized contract dict>}` — exactly what `build_v30_contract(...)` returns wrapped under the top-level key.

actors.py wiring update (additive to I-arch-001a):
```python
# src/polaris_v6/queue/actors.py — in enqueue_research_run, after slug derivation
from src.polaris_graph.v30_contract_synthesizer import build_v30_contract
from src.polaris_graph.nodes.scope_gate import load_scope_template

try:
    _tmpl = load_scope_template(domain)
    if _tmpl is not None:
        q["v30_contract_patch"] = build_v30_contract(_tmpl, slug, question)
except Exception:
    pass  # synthesizer failure must not block the run; pipeline-A handles missing contract via legacy path
```

Non-v6 sweep calls don't set `v30_contract_patch` → pipeline-A behaves byte-identically to today.

## P2 from iter 1 → resolutions

### P2.1 — compile_frame smoke test (not just round-trip load_report_contract_for_slug)

Test `tests/polaris_graph/test_v30_contract_synthesizer.py::test_synthesized_contract_compiles`:

```python
def test_synthesized_contract_compiles(template_id):
    """Every synthesized contract must compile via compile_frame, not just load."""
    template = load_scope_template_json(template_id)  # config/v6_templates/...
    contract_patch = build_v30_contract(template, "test_slug_001", "test question")
    template.setdefault("per_query_report_contract", {}).update(contract_patch)

    from polaris_graph.nodes.frame_compiler import compile_frame
    cf = compile_frame("test question", template, "test_slug_001")
    assert cf is not None
    assert len(cf.evidence_bindings) >= 1  # at least one frame compiled successfully
```

Parameterized over all 8 templates.

### P2.2 — section_order dedup / omit

Each frame's section name is derived from the `frame_id`'s natural grouping. For mechanical 1:1 transform, multiple frames may share a section (e.g., a policy template's "Overview" + "Implementation" subsections both belong to section="Background"). I'll deduplicate `section_order` per slug, OR omit it entirely when section_order would have duplicates (loader tolerates omission per dataclass — `section_order: tuple[str, ...] | None = None`).

Concrete: build section_order = sorted(set(slot.section for slot in slots)) — deduplicated, alphabetically. If a template wants explicit ordering, it overrides via the `<template_id>.json` `report_contract_override` block (Phase 2 follow-up, not in this Issue).

### P2.3 — Golden fixture test pattern

```python
def test_synthesized_contract_matches_fixture(template_id):
    """build_v30_contract output equals tests/fixtures/v30_contracts/<template>.json verbatim."""
    template = load_scope_template_json(template_id)
    synth = build_v30_contract(template, "fixture_slug", question=None)
    fixture_path = Path(__file__).parent.parent / "fixtures" / "v30_contracts" / f"{template_id}.json"
    expected = json.loads(fixture_path.read_text())
    assert synth == expected

def test_fixture_loads_via_report_contract(template_id):
    """Fixture wrapped under per_query_report_contract loads cleanly."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "v30_contracts" / f"{template_id}.json"
    contract_patch = json.loads(fixture_path.read_text())
    template = load_scope_template_json(template_id)
    template.setdefault("per_query_report_contract", {}).update(contract_patch)
    slug = next(iter(contract_patch.keys()))
    from polaris_graph.nodes.report_contract import load_report_contract_for_slug
    rc = load_report_contract_for_slug(template, slug)
    assert rc is not None
    assert rc.schema_version == "v30.1"
```

## P3 cosmetic (accepted)

- LOC 250 overshoot acceptable (~350 likely final).
- Docstring on `question` param: "Reserved for future question-aware seeding; iter-1 implementation uses frame_id as entity_id basis."

## Updated acceptance criteria

1. `build_v30_contract(template, query_slug, question=None) -> dict` emits a schema-valid v30.1 contract dict with **every entity carrying at least an `anchor` locator** (compile_frame requirement)
2. 8 golden fixtures at `tests/fixtures/v30_contracts/<template_id>.json`
3. pipeline-A patch (`run_honest_sweep_r3.py` ~5 LOC additive): consumes `q.get("v30_contract_patch")` and merges into `_template["per_query_report_contract"]` before any compile_frame/load_report_contract_for_slug call
4. actors.py update (~6 LOC additive): synthesizer invoked after slug derivation, output stored in `q["v30_contract_patch"]`; failure is graceful (pipeline-A handles missing contract via legacy path)
5. Tests:
   - build output matches golden fixture (8 parameterized cases)
   - fixture round-trips through load_report_contract_for_slug (8 cases)
   - synthesized contract compiles via compile_frame (8 cases)
   - referential integrity (every entity's rendering_slot matches a declared slot)
   - Non-v6 sweep call (no `v30_contract_patch` in q) → pipeline-A behavior byte-identical (regression check)
6. LOC budget ~350 (synthesizer ~120 + 8 fixtures ~30 each = 240 + tests ~100 + pipeline-A/actor patches ~12). Confirm acceptable.

## Direct questions iter 2

1. Mandatory `anchor` locator emission `<template_id>:<frame_id>:<query_slug_prefix>` — APPROVE'd, or want a different anchor scheme (e.g., URL-derived from template T1 source list)?
2. `q["v30_contract_patch"]` envelope + pipeline-A 5-LOC merge after `load_scope_template` — APPROVE'd?
3. Synthesizer failure swallowed in actors.py (`except Exception: pass`) — APPROVE'd, or fail-loud per LAW II?
4. `section_order = sorted(set(slot.section for slot in slots))` — APPROVE'd dedup pattern?
5. LOC ~350 — acceptable?
6. Anything else blocking iter-2 APPROVE?

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
