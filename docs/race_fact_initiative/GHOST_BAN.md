# GHOST_BAN — standing guard against overfit / faithfulness-ghost / post-generation-fix

Prepended to EVERY Sol/Fable brief. Run by Opus as a mechanical audit on EVERY verdict, spec, and code diff BEFORE
acceptance. Origin: the Wave-1 build (Sol-solo gates v1–v4) drifted into the banned apparatus over five rounds; the
operator caught it and ordered a rollback (MASTER_ACTION_PLAN §12). This guard exists so it never recurs.

## THE THREE BANNED FAMILIES (any design that does these is REJECTED)

### 1. OVERFIT
- task/domain literals in runtime code/prompts/config: task-72 domain nouns (labor / AI / 4IR / industry / journal
  names), benchmark task IDs, venue whitelists, sector lists, domain-vocabulary lookup tables.
- magic counts / hardcoded numbers that force a score / breadth / paragraph / source / section / table / citation
  target.
- adjective or version flag names (max / full / rich / smart / deep / enhanced / better; "wave1"; version numbers).
- a fix that only passes on task-72. Every fix must pass its deterministic TEST on held-out tasks 91 / 100 / 73.

### 2. FAITHFULNESS GHOST
- entailment / NLI machinery of ANY kind (model, predicate, or "does the prose entail X" runtime check).
- runtime admission gate: "licensed-inference admission", "premise-relation license", "operator-license
  predicate", "canary that rejects a sentence before/after the producer".
- re-implementing, importing, modifying, weakening, or wrapping the faithfulness engine
  (`provenance_generator.py`, `clinical_generator/strict_verify.py`).
- any second verification / acceptance layer on top of the EXISTING per-sentence verifier.
- typed carriers whose fields include premise IDs, admitted tokens, marker bindings, or reasoning operators.

### 3. POST-GENERATION FIX
- editing / rewriting / dropping / re-ranking / suppressing any sentence or the report AFTER generation.
- "exact emitted==admitted binding audit", "non-scoreable-on-mismatch", "release_allowed=False" on content grounds,
  "fail-closed" content states, per-route acceptance checks woven into the generation call path.
- post-assembly content insertion (summary-table-compose style).
- SOLE EXCEPTION: layout-only whitespace/heading normalization that PROVABLY preserves content (ordered
  non-whitespace token stream + citation markers byte-identical before/after; no word/number/marker/sentence
  change), with its token-identity test attached.

## THE POSITIVE RULE (what a lever MAY be)
- a PRE-GENERATION change to prompt text / outline-or-plan text / plan-merge role selection / retrieval scope that
  executes BEFORE the producer LLM call it shapes, and reaches the ACTIVE writer.
- rely on the EXISTING faithfulness engine, untouched. Verifier-strip is lawful: if it drops the new sentence, the
  responses are better upstream evidence ownership OR drop the lever — never rescue / re-insert / relax.
- deterministic checks are TESTS that decide whether a lever SHIPS (scripts under `tests/` or standalone lints run
  on emitted artifacts) — nothing in the generation call path reads their result.
- a shared PRE-GENERATION plan structure is allowed ONLY if it (a) exists solely before generation, (b) renders
  into prompt/plan text then has no runtime reader, (c) carries no admission/binding/entailment fields, (d) is
  never compared against emitted text. If it pulls toward per-sentence identity / premises / admitted candidates →
  use the per-lever prompt change instead, or DROP THE LEVER.
- **DROP-LEVER DEFAULT:** if a gap cannot be fixed by a clean pre-generation change verified by the existing
  engine, DROP it and record it dropped. Never invent machinery to rescue a lever.

## MECHANICAL AUDIT (Opus runs this on every verdict / spec / diff; reviewer runs it on every wave diff)
```
grep -inE 'admission|canary|entail|nli|licens|binding|premise|operator[_ -]?licen|non[_ -]?scoreable|scoreab|suppress|fail[_ -]?closed|admitted|emitted[_ =]|reasoning operator|analyticalcontract' <target>
```
Every hit must be a REJECTION / naming-to-exclude / a reference to this ban — NEVER a proposal. Any proposing hit
inside `src/` or `scripts/run_honest_sweep_r3.py` / `scripts/dr_benchmark/` = REJECTED.
PLUS five structural checks (reject on any one failure):
- (a) no new code path compares emitted text against a stored "admitted/planned" text;
- (b) no new predicate consulted between any producer call and final render that can drop or replace content
  (layout normalizer excepted, with its token-identity test attached);
- (c) no new import of either frozen faithfulness module;
- (d) every new deterministic check lives under `tests/` or a standalone lint; nothing in the generation call path
  reads its result;
- (e) no new dataclass/type whose fields include premise IDs, admitted tokens, marker bindings, or reasoning
  operators.

## PROCESS GUARD
- TWO-MODEL always: every design AND every build diff is gated by BOTH Fable and Sol. NEVER a single-model gate.
  (The drift happened under solo-Sol; Fable authored "no entailment machinery" and is the counterweight.)
- Opus holds the ban over Sol's correctness-maximizing: if Sol proposes an admission/entailment/binding/post-gen
  apparatus "for correctness", Opus REJECTS it and applies the clean form or drops the lever — never gate-obeys.
