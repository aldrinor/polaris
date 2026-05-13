HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001b iter 3 — template source fix + observability

## P1 from iter 2 → resolution

### P1-actor-synthesizes-from-wrong-template-source

You wrote:
> "load_scope_template(domain) loads config/scope_templates/{clinical,policy}.yaml which doesn't expose frame_manifest. build_v30_contract needs v6 template JSON from config/v6_templates/*.json. Use polaris_v6.templates.registry.load_template(template_id).model_dump()."

**Code-verified**: `src/polaris_v6/templates/registry.py:35` `load_template(template_id: str) -> TemplateContent` reads `config/v6_templates/{template_id}.json` and returns a Pydantic `TemplateContent` with frame_manifest exposed.

**Resolution**: actors.py uses `polaris_v6.templates.registry.load_template`, not `load_scope_template`:

```python
# src/polaris_v6/queue/actors.py
from polaris_v6.templates.registry import load_template
from src.polaris_graph.v30_contract_synthesizer import build_v30_contract

try:
    _v6_tmpl = load_template(template_id).model_dump()  # config/v6_templates/<template_id>.json
    q["v30_contract_patch"] = build_v30_contract(_v6_tmpl, slug, question)
    logger.info(
        "[actor] v30_contract_patch synthesized for run_id=%s template_id=%s slug=%s",
        run_id, template_id, slug,
    )
except FileNotFoundError as exc:
    logger.warning(
        "[actor] v6 template not found for template_id=%s; pipeline-A will run "
        "without synthesized contract patch (legacy no-contract path): %s",
        template_id, exc,
    )
except Exception as exc:  # noqa: BLE001 — synthesizer failure must not block runtime
    logger.warning(
        "[actor] v30_contract_patch synthesis FAILED for run_id=%s template_id=%s "
        "slug=%s: %s; pipeline-A will run on legacy no-contract path",
        run_id, template_id, slug, exc,
    )
```

Pipeline-A path (`run_honest_sweep_r3.py` after `_template = load_scope_template(q["domain"])`) is unchanged from iter-2 brief — it still merges `q["v30_contract_patch"]` into `_template["per_query_report_contract"]`. The patch goes into the SCOPE template (yaml-loaded) under `per_query_report_contract.{slug}`, which is the key load_report_contract_for_slug + compile_frame consume. The SOURCE of the synthesized data is v6 template JSON (with frame_manifest); the SINK is the scope template (which both `compile_frame` and `load_report_contract_for_slug` read).

This satisfies P1: synthesizer reads frame_manifest from the right place, patch goes to the right place.

**Actor-level regression test** per Codex iter-2:

```python
# tests/polaris_v6/queue/test_actors_v30_patch.py
def test_actor_attaches_v30_contract_patch(monkeypatch, tmp_path):
    """Actor calls build_v30_contract from v6 template and puts result in q."""
    captured = {}
    async def _fake_run_one_query(q, out_root):
        captured["q"] = q
        out_root.mkdir(parents=True, exist_ok=True)
        (out_root / "manifest.json").write_text(json.dumps({
            "run_id": "SWEEP_fixture", "status": "success", "cost_usd": 0.0,
        }, sort_keys=True) + "\n")
        return {"status": "success", "manifest": {...}}

    monkeypatch.setattr("scripts.run_honest_sweep_r3.run_one_query", _fake_run_one_query, raising=False)
    monkeypatch.setenv("POLARIS_V6_OUTPUT_ROOT", str(tmp_path / "v6_runs"))
    run_store.init_db(str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("POLARIS_V6_RUN_DB", str(tmp_path / "test.sqlite"))
    run_store.insert_run("test_run_uuid", "clinical", "What is GLP-1?")

    from polaris_v6.queue.actors import enqueue_research_run
    enqueue_research_run.fn("test_run_uuid", {"template": "clinical", "question": "What is GLP-1?"})

    assert "v30_contract_patch" in captured["q"]
    patch = captured["q"]["v30_contract_patch"]
    slug = captured["q"]["slug"]
    assert slug in patch
    assert patch[slug]["schema_version"] == "v30.1"
    assert len(patch[slug]["required_entities"]) >= 1
```

## P2 from iter 2 → resolutions

### P2-anchor-prefix-not-actually-unique

**Resolution**: include a short stable hash from the full slug + frame_id + template_id to guarantee uniqueness even when slug prefix collides:

```python
import hashlib

def _anchor_for(template_id: str, frame_id: str, query_slug: str) -> str:
    """Stable, unique anchor: <template>:<frame>:<slug_prefix>:<hash>.
    Collision-safe across same-prefix slugs."""
    h = hashlib.sha256(f"{template_id}|{frame_id}|{query_slug}".encode()).hexdigest()[:8]
    return f"{template_id}:{frame_id}:{query_slug[:40]}:{h}"
```

8-char hex prefix from SHA256 of (template_id, frame_id, query_slug) gives 2^32 = 4B combinations — collision-free for any realistic curator workload.

### P2-except-pass-needs-observability

**Resolution** (per iter-2 code above): bare `except Exception: pass` is REPLACED with `logger.warning(...)` that captures run_id + template_id + slug + the exception. Run continues on legacy no-contract path (graceful), but the wiring failure is now observable in logs + can be alerted on if the rate spikes.

`FileNotFoundError` is a separate, expected case (e.g., a v6 template was renamed) — logged distinctly at warning level.

## Acceptance criteria (final iter-3)

1. `build_v30_contract(v6_template, query_slug, question=None) -> dict` (input is v6 template JSON, NOT scope_template yaml)
2. Every synthesized entity carries an `anchor` (mandatory M55 locator) of form `<template_id>:<frame_id>:<query_slug_prefix>:<sha256_8>`
3. 8 golden fixtures at `tests/fixtures/v30_contracts/<template_id>.json`
4. actors.py:
   - Calls `load_template(template_id)` from `polaris_v6.templates.registry`
   - Stores synthesized contract patch in `q["v30_contract_patch"]`
   - On `FileNotFoundError` or generic exception: logs warning, continues on legacy no-contract path
5. pipeline-A: 5 LOC after `load_scope_template`: `if q.get("v6_mode") and q.get("v30_contract_patch"): _template.setdefault("per_query_report_contract", {}).update(q["v30_contract_patch"])`
6. Tests (all parameterized over 8 templates):
   - synth output == fixture JSON
   - fixture round-trips through `load_report_contract_for_slug`
   - synth compiles via `compile_frame` (non-None evidence_bindings)
   - actor-level: stubbed run_one_query captures q; asserts v30_contract_patch present + schema-valid
   - non-v6 actor mode (no v6_mode set) → no patch in q (regression for legacy CLI sweep)
7. LOC ~350

## Direct questions iter 3

1. `polaris_v6.templates.registry.load_template(template_id).model_dump()` as the v6 template source — APPROVE'd?
2. Anchor format `<template_id>:<frame_id>:<slug[:40]>:<sha256_8>` — APPROVE'd?
3. Observability path (logger.warning on FileNotFoundError + generic Exception, log run_id/template_id/slug + exc) — APPROVE'd or want fail-loud per LAW II?
4. Actor-level regression test pattern (monkeypatch run_one_query + capture q + assert v30_contract_patch shape) — APPROVE'd?
5. Anything else blocking iter-3 APPROVE?

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
