# I-rdy-005 (#501) — adjacent-file scan

Grep for every consumer of a template-id set or the string ids
`housing/climate/defense/trade`.

## Files that MUST change (carry the wrong 4 ids)
- `config/v6_templates/{climate,defense,housing,trade}.json` — 4 stale TemplateContent JSON; `/templates` endpoint serves them via `registry.py` glob.
- `src/polaris_v6/schemas/run_request.py:9` — `TemplateId = Literal[...]` includes `trade/housing/defense/climate`; this is the POST /runs validator.
- `src/polaris_v6/queue/actors.py:51-61` — `TEMPLATE_TO_SCOPE_DOMAIN` maps `climate/defense/housing/trade → "policy"`; comment block says authoring the real per-domain YAMLs is "Phase 2" — stale, the YAMLs already exist.
- `src/polaris_graph/v30_contract_synthesizer.py:22-44` — `_TYPE_FOR_TEMPLATE` + `_REQUIRED_FIELDS_FOR_TEMPLATE` both keyed on the wrong 4.
- `web/lib/api.ts:56-63` — `TemplateId` TS union.
- `web/app/page.tsx:22` — hardcoded landing `templates` array (clinical/housing/climate/ai_sovereignty/canada_us/defense/trade/workforce).
- `web/app/dashboard/page.tsx:31` — `FALLBACK_TEMPLATES` (offline fallback for the `listTemplates()` fetch).

## Files I have ALSO checked and they are CLEAN (no change needed)
- `src/polaris_graph/nodes/scope_gate.py:69-73` — `SUPPORTED_DOMAINS` is **already exactly the canonical 8** (`clinical, policy, tech, due_diligence, custom, ai_sovereignty, canada_us, workforce`). The scope gate is the part already correct; everything else must converge to it.
- `config/scope_templates/*.yaml` — already the canonical 8 (8 files, exact id set). This IS the source of truth per #501.
- `src/polaris_v6/templates/registry.py` — glob-driven (`config/v6_templates/*.json` → `list_template_ids()`); reads whatever JSON files exist, so fixing the dir contents fixes the endpoint with zero code change.
- `src/polaris_v6/api/templates.py` — `/templates` + `/templates/{id}`; pure pass-through of `registry.py`; no id literals.
- `src/polaris_v6/api/scope.py:9,15` — imports `TemplateId` from `run_request`; inherits the fix, no own literal.
- `web/lib/api.ts:243 listTemplates()` + `web/app/dashboard/page.tsx:88` — dashboard already fetches `/templates` live; only its offline `FALLBACK_TEMPLATES` is stale.
- `src/agents/analyst_agent.py:1461` — `"trade"` is a free-text keyword in an industry-term list, NOT a template id. Clean.

## Net: 7 files to change + 1 new test. `scope_gate` + `scope_templates/` are the fixed point everything converges to.
