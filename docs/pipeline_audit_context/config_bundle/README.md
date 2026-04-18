# Config bundle for audit

Copied verbatim from `config/` on 2026-04-18 so the audit context
includes them without chasing paths.

## Contents

- `scope_templates/` — per-domain scope protocols (4 files)
  - `clinical.yaml`, `due_diligence.yaml`, `policy.yaml`, `tech.yaml`
- `completeness_checklists/` — per-domain completeness checklists (4 files)

## What these drive

- **`scope_templates/<domain>.yaml`** feeds
  `src/polaris_graph/nodes/scope_gate.py`. It defines expected tier
  distribution (`expected_tier_distribution`), date range, forbidden
  terms, required terms, and per-domain amplification hints.
- **`completeness_checklists/<domain>.yaml`** feeds
  `src/polaris_graph/nodes/completeness_checker.py`. It defines the
  topic universe a corpus should cover for a given domain.

## Not bundled (left in `config/`)

- `config/settings/*.yaml` — 11 YAML files with tunable parameters.
  Not bundled because most are large and most parameters have env-var
  overrides documented in `.env.example`.
- `config/pipeline_templates/` — graph topologies for pipeline B
  variants.
- `config/prompts/` — a few shared prompt fragments (most prompts are
  inline in generator code; see `02_prompt_templates.md`).
- `config/searxng/` — SearXNG instance config (sovereign mode only).
- `config/vector_library.py` — legacy "175 vectors" inventory (see
  CLAUDE.md "paths that no longer exist").
- `config/sota_baselines.json` — historical baselines for tracking.
- `config/evaluation_strict.env` — evaluation env-var overrides.

## Audit questions

- Do the scope_templates tier distributions match real-world
  availability for each domain? (E.g., is T1 ≥40% achievable for
  "What are the latest techniques for quantum error correction"?)
- Does the completeness checklist for each domain cover every
  sub-topic a legitimate research answer would need to address?
- Are the scope templates in sync with the hard-coded
  `_ALLOWED_SECTIONS` set in `multi_section_generator.py`?
