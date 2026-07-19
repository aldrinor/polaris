# Phase 3A — contract/API docstrings (batch 1)

**Status:** shipped. 62 docstrings added across 21 contract/API-surface files
(graph API route, v6 API routes, v6 schema contracts, evidence contract, contracts_v3,
pin/query timeline, etc.). Pure documentation — zero behavior change, proven three ways:

1. **Docstring-stripped AST equivalence** — every changed file's AST, with all docstrings
   removed, is byte-identical to HEAD → the only delta is docstrings.
2. **`__doc__`-consumer audit** — each of the 62 symbols checked for a runtime `__doc__`
   consumer (pydantic/FastAPI schema description, argparse/click/typer help, doctest,
   `inspect.getdoc`). Result: 0 load-bearing; 0 reverted.
3. **Oracle replay byte-identical** — golden SHA `9c0a3d43…`, both controls pass.

**Codex verdict:** DOCS-SAFE (reversed its initial DOCS-REVISE once the `__doc__` audit
closed the load-bearing channel). `help()`/pydoc/`getdoc` intentionally surface the new
text — expected documentation exposure, not a runtime dependency.

This is a first batch on the highest-value (contract/API) surface; the remaining
docstring backlog toward ~530 can follow in the same gated pattern.

## Scope of "byte-identical"

The "byte-identical" claim is about **pipeline behaviour**, not the whole surface:

- **Pipeline behaviour is byte-identical and oracle-proven.** RACE, faithfulness,
  and data I/O are unchanged; the governing oracle replay matches golden SHA
  `9c0a3d43…` with both controls passing. The docstring-stripped AST equivalence
  independently confirms the only source delta is docstrings.

- **The API's OpenAPI schema GAINS documentation descriptions.** Where a changed
  symbol is a FastAPI route or a pydantic model, its docstring now surfaces as an
  OpenAPI `description` (operation description for routes, model/field description
  for schemas). Previously these descriptions were empty. This is an **intended
  improvement** (Plan V4 concern #5), not an incidental regression: the schema is
  strictly enriched with human-readable documentation and its shape (paths,
  operations, field names, types, required/optional) is unchanged.

- **No consumer depends on the prior empty descriptions.** Test collection is
  unchanged (16738/11), and no committed artifact (golden fixture, recorded
  cassette, snapshot) pins the previously-empty OpenAPI descriptions. The
  `__doc__`-consumer audit confirms 0 load-bearing runtime readers.
