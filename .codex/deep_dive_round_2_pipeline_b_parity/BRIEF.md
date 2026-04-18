# Deep-dive round 2 — Pipeline B parity (BUG-B-102)

You are the independent reviewer for a focused deep-dive on the
active-production parity defect surfaced in the full-audit scoping pass.

**Target**: `BUG-B-102 — Pipeline B (UI production) has zero hardening`
(full finding: `outputs/codex_findings/full_audit_pass_1/findings.md` §11).

## The defect, restated

The Docker default entrypoint (`uvicorn scripts.live_server:app`) is
the production-facing pipeline every UI user hits. It dispatches to
one of three LangGraph variants under `src/polaris_graph/`:

- `graph.py` — v1
- `graph_v2.py` — v2 (CRAG)
- `graph_v3.py` — v3 (ReAct agent)

A repo-wide search for `strict_verify | sanitize_evidence_text |
corpus_approval | abort_no_verified_sections | abort_corpus_approval_denied`
across these files returns ZERO matches. The entire pipeline-A hardening
(5 rounds of Codex audit, 85+ tests, 5 blockers closed) is absent here.

Meanwhile pipeline A (`scripts/run_honest_sweep_r3.py`) HAS all of
these. So the UI ships users an un-hardened report while the batch
sweep ships a hardened one. This is the highest-severity gap on the
full-audit risk register.

## Your mandate (pass 1: scope mapping)

Produce the fix SPECIFICATION. Specifically:

### 1. Inventory of pipeline-A invariants to replicate

For each invariant below, identify:
- The pipeline-A source file implementing it
- The invariant's behavioral contract (what it blocks / allows)
- The test that pins it

Invariants to map:
1. `strict_verify` (provenance token grounding)
2. `sanitize_evidence_text` (delimiter breakout defense + Unicode hardening)
3. `corpus_approval_gate` (material deviation + rubber-stamp note)
4. `corpus_adequacy_gate` (tier distribution thresholds)
5. `filter_verified_sections` + `build_no_verified_sections_abort_body` (zero-verified abort)
6. Budget guard (`check_run_budget`, `_impute_cost_from_tokens`)
7. Two-family evaluator (`check_family_segregation`)
8. Unified `manifest.status` (just fixed in R1 via BUG-B-101)
9. Content-word overlap (`MIN_CONTENT_WORD_OVERLAP`)
10. Delimiter-breakout Unicode evasion defense (NFKD + Mn-strip + confusable map)

### 2. Inventory of pipeline B entry points

Trace `scripts/live_server.py`:
- Every HTTP endpoint that triggers a research run
- Every dispatch to `graph.py`, `graph_v2.py`, `graph_v3.py`
- The state flow for each (synchronous / async / SSE streaming)
- The output artifact path each variant writes to

### 3. Per-variant gap analysis

For each of the 3 graph variants, map which invariants are:
- **Present** (already implemented somewhere in the variant)
- **Missing** (absent entirely — full back-port needed)
- **Partially present** (similar but diverged behavior — reconciliation needed)

### 4. Recommend a strategy — pick ONE

Three candidate strategies; pick one and justify:

**Strategy A: Back-port into every variant**. Patch graph.py,
graph_v2.py, graph_v3.py with the same invariant coverage. Pro: no
routing changes, minimal user-visible risk. Con: 3x the work, 3x
the surface for drift; the three variants will keep diverging.

**Strategy B: Consolidate on a single graph variant**. Deprecate
v1/v2, route all UI traffic through v3 (or whichever is most
aligned with pipeline A). Pro: single source of truth going
forward. Con: requires feature-parity analysis; may regress UI
features that depend on v1 or v2 specifics.

**Strategy C: Wrap pipeline A in a "graph_v4" shim**. Make
`scripts/live_server.py` dispatch new research requests into a
thin wrapper that calls the pipeline-A flow (`run_one_query`-style)
and adapts the output shape to what the UI expects. Pro: UI gets
the full hardening. Con: output shape mismatch — pipeline A writes
manifests + reports, UI wants SSE streaming events for real-time
display.

### 5. Test specification

Identify tests that would catch re-regression. Each graph variant
(or the consolidated variant) needs integration tests that assert:
- `manifest.status` exists and is in the unified taxonomy
- A fabrication attack (citing a span that doesn't contain the
  claim's numeric or content words) is rejected
- A delimiter-breakout payload is redacted
- The budget guard holds
- A rubber-stamp corpus approval is refused

Plan for at least 6-10 integration tests per variant.

## Output

Write to `outputs/codex_findings/deep_dive_round_2/findings.md` with
this frontmatter:

```yaml
---
target_bug: B-102
scope: pipeline B UI parity with pipeline A hardening
verdict: scoped | needs_more_info
strategy_chosen: A | B | C
pipeline_a_invariants_identified: <int>
pipeline_b_entry_points: <int>
tests_required: <int>
rationale: |
  <2-4 sentences explaining the strategy choice>
---
```

Followed by sections 1-5 above.

## Context

- `outputs/codex_findings/full_audit_pass_1/findings.md` — original B-102
- `outputs/codex_findings/deep_dive_round_1/findings.md` — R1 pattern
- Source code at HEAD (commit `c764ddb` or later)
- `scripts/live_server.py` (214KB — the UI server)
- `src/polaris_graph/graph.py`, `graph_v2.py`, `graph_v3.py` — 3 variants
- `src/polaris_graph/nodes/`, `generator/`, `retrieval/`,
  `evaluator/`, `llm/` — pipeline A invariant implementations
- `tests/polaris_graph/test_b{1..5}_*.py` — pipeline A tests
- `tests/polaris_graph/test_manifest_contract.py` — just-landed R1 tests

## Anti-circle-jerk rules

1. Read code at HEAD, not this brief's summaries.
2. If you can construct a UI-path attack that bypasses pipeline-A
   invariants, flag it as a reproducer, not just speculation.
3. `success` as a strategy choice requires JUSTIFICATION — don't pick
   strategy C just because it sounds clean; weigh the SSE-streaming /
   output-shape cost honestly.

## What NOT to do

- Do NOT write code. This pass produces the SPEC.
- Do NOT audit UI JavaScript — focus on Python-level parity.
- Do NOT re-litigate B-1..B-5. Those are closed for pipeline A.
  The question here is ONLY "how to get pipeline B to the same bar."

## Authentication

OAuth. No API-key burn.

## Expected duration

10-20 minutes. Pipeline B has significant code surface (`live_server.py`
is 214KB); a thorough scoping pass will take longer than R1's.

---

Start:

```
git log --oneline c764ddb | head -5
grep -n "build_and_run\|dispatch\|@app.post\|@app.get" scripts/live_server.py | head -30
```

Then trace each dispatch into the graph variants and map the invariant
gap per variant.
