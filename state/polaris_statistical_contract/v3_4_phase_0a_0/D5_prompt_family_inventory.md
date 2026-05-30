# D5 — Prompt-Family Inventory: Methodology + Schema (draft for Codex review)

**Deliverable**: Phase 0a.0 / D5 — the prompt-family enumeration METHODOLOGY + family-ID scheme + `state/prompt_families.json` schema.
**Status**: LOCKED (Codex APPROVE 2026-05-27 after 2 rounds; pending operator sign-off).
**Parent**: contract v3.3 §3.4 criterion 4 (prompt-family match); depends on D1a.
**Plan**: `PHASE_0a_0_PLAN.md` (D5 runtime-reachability, prompt-constructor-level — Codex plan round-1 P1-3 / round-2 / round-3).
**Codex review**: `.codex/I-safety-001b/codex_d5_review.txt`.
**Version**: 1 (draft)

**Why this exists**: §3.4 criterion 4 fires when two claims share a generator OR verifier prompt family (a real correlation source — same prompt skeleton → correlated outputs). 0a.-1.C `construction_manifest` carries `generator_prompt_family_id` + `verifier_prompt_family_id`; the relation-builder fail-closes on null. D5 locks WHAT a prompt family is, the deterministic family-definition rule, the runtime-reachability enumeration methodology, and the `prompt_families.json` schema. Like D4-seed/D6-content, the FULL enumeration content is a gated authoring step (§6); D5 locks the methodology + schema.

---

## §1. What a prompt family is (locked)

A **prompt family** = a deterministic equivalence class of prompt-CONSTRUCTORS whose outputs are correlated because they share the same prompt skeleton. Two claims share a prompt family iff they were produced (generator) or verified (verifier) by prompt-constructors in the same family. It is a §3.4 criterion-4 correlation source — distinct from same-report (criterion 1), evidence overlap (criterion 2), same-template (criterion 3), microtopic (criterion 5).

## §2. Deterministic family definition (Codex round-2 P2-3 + round-1 #1/#2)

A prompt family is defined DETERMINISTICALLY from the prompt SKELETON, NOT from an output-similarity test and NOT from the call site. The family IDENTITY is:

`family_key = (role, system_template_id, user_template_id, model_conditioned_branch, retry_path)`

- `role` ∈ {gen, ver} — part of identity (§3 dual-role rule).
- `system_template_id` / `user_template_id`: the SKELETON identity (canonical-skeleton hash per §2.1, with data spans as placeholders — NOT filled values).
- `model_conditioned_branch`: which model-conditioned variant fired (each branch is part of the key).
- `retry_path`: initial vs retry/repair prompt (retry differs → different family).

**`callable_qualname` is NOT in the identity (Codex round-1 #1 — false-negative risk)**: two call sites with the SAME skeleton are the SAME family (putting qualname in the identity would split genuinely-same families → deflate P/DEFF, the dangerous direction for a safety bound). `callable_qualname` is recorded as PROVENANCE in the family's `constructors[]` list (§5), and is a tie-breaker ONLY if two same-skeleton constructors have materially different assembly/input semantics (a documented exception, not the default).

Two constructors with byte-equal `family_key` are the same family. **Similarity testing is AUDIT-ONLY** (Codex round-2 P2-3): an output-similarity probe MAY verify same-family→correlated / cross-family→not, but does NOT define the family. A similarity surprise triggers review, not redefinition.

### §2.1 Skeleton canonicalization (Codex round-1 #2 — instrument before fill)

`system_template_id`/`user_template_id` are computed by CONSTRUCTOR INSTRUMENTATION that emits a canonical skeleton BEFORE fill — NOT by reverse-hashing the final emitted prompt (unreliable for the repo's f-strings / concatenation / conditional + helper-rendered blocks, e.g. `multi_section_generator` appending model-allow-lists / atom-catalogs / contradiction-hedging / retry-contracts). Canonicalization rule:
- Fixed literal text stays in the skeleton.
- Runtime DATA values become typed placeholders (`<evidence>`, `<claim>`, `<source_list>`, ...).
- An OPTIONAL literal block present vs absent produces a DIFFERENT skeleton hash (the structure differs).
- Dynamic block renderers expose their OWN skeleton IDs (composed into the parent skeleton).
- Canonical serialization + hash algorithm are FIXED (locked, §5).
- A hash collision or an unknown/unregistered skeleton is FAIL-CLOSED (halt, not silent).

## §3. Family-ID scheme (locked)

`prompt_family_id` = `"<role>.<stable_hash>"` where:
- `role` ∈ {`gen`, `ver`} (generator vs verifier — part of the family_key identity, §2).
- `stable_hash` = a stable hash of the `family_key` tuple (§2), fixed length + canonical JSON serialization (§5), collision fail-closed.

`generator_prompt_family_id` (gen.*) + `verifier_prompt_family_id` (ver.*) are the two construction_manifest fields. Criterion 4 (0a.-1.C §2.1): two claims related iff `generator_prompt_family_id` match OR `verifier_prompt_family_id` match.

**Dual-role constructors (Codex round-1 #3)**: a constructor whose SAME skeleton is used in BOTH the generation and verification paths does NOT collapse across roles — it produces TWO role-scoped records, `gen.<hash>` and `ver.<hash>` (role is in the identity §2). Cross-role does not match under criterion 4 (which matches gen-family OR ver-family separately).

## §4. Runtime-reachability enumeration methodology (Codex round-2 P1-3 — NOT directory-based)

The inventory is built by RUNTIME REACHABILITY, not a directory scan (prompts live across `src/agents/` (12+ files: analyst/verifier/synthesizer/planner/critic/...), `src/polaris_graph/generator/` (8+), `src/polaris_graph/evaluator/`, and possibly `src/polaris_v6` / `config/prompts`):

1. **Reachable under the FROZEN gold-set configuration (Codex round-1 #4)**: reachability is defined under the frozen production config used for gold-set generation+verification — entry points, env vars, model slugs, provider-fallback policy, feature flags, router config, retry settings, enabled gen/verifier stages. The call graph is too dynamic for static enumeration ALONE (router decisions, retries, model branches, fallback LLMs, data-dependent blocks). Static tracing SEEDS the inventory; **instrumented dry-run coverage is the ENFORCEMENT surface**.
2. **Enumerate every REACHABLE prompt-constructor**: each distinct `family_key` (§2) reachable under the frozen config is a family. A constructor not reachable can't produce a gold-set claim.
3. **Per-constructor enumeration**: a single file may host MANY constructors (e.g. `multi_section_generator.py` — outline / section / trial-table / limitations / per-trial-subsection / retry / model-conditioned). Enumeration is per-CONSTRUCTOR (per-skeleton), not per-file.
4. **Call-boundary instrumentation + completeness fail-closed (Codex round-1 #5)**: the invariant "every emitted prompt resolves to an enumerated family else halt" is enforced AT THE LLM CALL BOUNDARY, not by reverse-mapping prompt text. The central call wrapper (e.g. `OpenRouterClient.generate`) receives/derives `{role, family_key, prompt_family_id, system_template_id, user_template_id, retry_path, model_conditioned_branch, callable_qualname}`, validates against the active `prompt_families.json`, and writes the `prompt_family_id` into the prompt trace + construction_manifest. An emitted prompt that does not resolve to an active family is fail-closed (halt).

## §5. `prompt_families.json` schema (locked)

```
{
  inventory_version: str, inventory_hash: str,   # NOT ontology_* (Codex round-1 #8)
  hash_algorithm: str,                           # fixed (e.g. "sha256"); stable_hash = first 16 hex of canonical-JSON family_key hash
  families: [
    { prompt_family_id: str,            # §3 "<role>.<hash>"
      role: enum[gen, ver],             # in the identity (§2)
      family_key: { role, system_template_id, user_template_id,
        model_conditioned_branch, retry_path },   # identity (NO callable_qualname)
      constructors: [                   # PROVENANCE (Codex round-1 #1) — call sites sharing this skeleton
        { callable_qualname, reachable_from: [entry_point] } ],
      status: enum[active, deprecated],
      added_at, added_by, supersedes?, replaced_by? }
  ]
}
```

- `inventory_version`/`inventory_hash` (NOT `ontology_*` — that vocabulary is D4's). `hash_algorithm` + canonical-JSON serialization of `family_key` are fixed; `stable_hash` length fixed; a hash COLLISION (two distinct family_keys → same stable_hash) is fail-closed.
- `constructors[]` is the provenance list: multiple call sites with the same skeleton share ONE family (§2 — qualname is provenance, not identity).
- Custody artifact (0a.-1.E §1). Append/deprecate governance mirrors D4: pre-structural recorded append; **post-structural §P4 Category-3 — which REQUIRES recomputing affected construction_manifests, pairwise relations, degree stats, and DEFF, retaining old AND new hashes** (Codex round-1 #7, mirroring D4's L3-change specificity); post-outcome Category-4. A constructor change (new skeleton/branch/retry/role) = new family (deprecate-not-mutate).

## §6. D5-inventory gate (like D4-seed / D6-content)

The FULL `prompt_families.json` enumeration is a HARD GATE. Two enforcement points (Codex round-1 #6 — the gate wording is split to resolve the dry-run/pilot contradiction):

1. **Pre-pilot instrumented dress-rehearsal**: a dress-rehearsal run under the frozen gold-set config (§4) must resolve EVERY emitted prompt to an active family; the enumeration is then hash-pinned. This precedes construction-manifest acceptance, D8 allocation, and the relation-builder dry-run.
2. **Actual pilot/gold-set run**: ALSO enforces the same call-boundary fail-closed check (§4.4). A prompt emitted during the real run that resolves to no active family HALTS and INVALIDATES that run until the family is amended under the correct §P4 exposure window (pre-structural append vs Category-3/4).

Until the enumeration is hash-pinned, `generator_prompt_family_id`/`verifier_prompt_family_id` are unresolved and the relation-builder fail-closes (0a.-1.C §2.3). D5 locks the METHODOLOGY + schema; the enumeration content is gated.

## §7. Definition of done (D5)

Locked: prompt-family definition (deterministic family_key, NOT similarity), role-typed family-ID scheme, runtime-reachability enumeration methodology (trace-from-entry-points, per-constructor, completeness fail-closed — NOT directory scan), `prompt_families.json` schema, append/deprecate governance (D4-mirrored §P4 windows), similarity-as-audit-only, the D5-inventory hard gate. Codex §-1.1 APPROVE. Operator sign-off. NOTE: the full enumeration CONTENT is gated (§6), not in this lock.

## §8. Dependencies + forward notes

- Needs D1a — DONE. (Enumeration reaches across the actual prompt-construction call graph; not domain-specific.)
- `generator_prompt_family_id` + `verifier_prompt_family_id` consumed by relation-builder criterion 4 (0a.-1.C §2.1) + construction_manifest (0a.-1.C §1.1).
- `prompt_families.json` + append-log are custody artifacts (0a.-1.E §1).
- D5-inventory gate (§6) precedes construction-acceptance / D8 / dry-run / pilot.
- Similarity-audit probe (optional, §2) is observability; the deterministic key is binding.
