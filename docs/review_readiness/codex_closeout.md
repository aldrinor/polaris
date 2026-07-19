# Closeout — dangling imports + lethal_retrieve (codex CLOSEOUT-SAFE)

Closes two codex-identified readiness blockers:
1. **2 dangling retired-script imports resolved** — `scripts/_retired_2026_06_14/pg_compose_production_scale.py`
   and `pg_geval_openai.py` (which imported a moved module via a nonexistent leading-underscore path)
   are **deleted** (601 lines); they were already-dead quarantine scripts with zero live importers.
2. **`lethal_retrieve` → `high_recall_retrieve`** (marketing adjective removed, per codex Q3/DOMAIN-REVIEW)
   in `src/polaris_graph/wiki/mesh/retrieve/retrieval.py`, with a **same-object backward-compat alias**
   (`lethal_retrieve = high_recall_retrieve`; `lethal_retrieve is high_recall_retrieve` == True). The
   active importers (`tests/integration/test_mesh_e2e.py`, `tests/unit/test_mesh_lethal_retrieve.py`,
   `retrieve/__init__.py`) still resolve via the alias — no test edits, no behavior change.

**Verification:** collection 16738/11 (unchanged; the 11 are pre-existing missing-module errors),
oracle replay byte-identical (golden 9c0a3d43). The only observable delta is the callable's `__name__`
(now `high_recall_retrieve`) — no runtime code path changes. Codex verdict: **CLOSEOUT-SAFE**.
