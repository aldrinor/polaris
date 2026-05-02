M-D11 phase 1 review (commit d150a43).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Phase D M-D2 phase b GREEN-locked at v5 (5-round autoloop).
Now starting M-D11 model + version pinning.

This commit ships M-D11 PHASE 1 (capture + serialization).
PHASE 2 (replay) is deferred.

`src/polaris_graph/audit_ir/model_pin.py`:
  - ModelPin frozen dataclass
  - capture_pin(...) builder
  - SHA-256 helpers (hash_inductor_profile, hash_file)
  - pin_to_dict / pin_to_json / pin_from_dict / pin_from_json
  - pins_equivalent_for_replay(a, b)

22/22 tests covering capture, hashing, round-trip, replay
equivalence, validation-set hash integration.

## Your job

GREEN / PARTIAL / DISAGREE.

1. **Schema soundness**: ModelPin captures run_id, captured_at,
   llm_model + provider, prompt_version_hash,
   retrieval_source_versions dict, inductor_type +
   inductor_version_hash, validation_set_hash, notes. Anything
   important missing for re-run-from-pin (e.g. environment
   variables, evidence-pool snapshot pointer)?

2. **Hash strategy**: SHA-256 over UTF-8 text for prompts +
   inductor profiles, SHA-256 over file bytes for validation
   set. Adequate for content-addressable pinning, or should I
   include file path + size for paranoia?

3. **Replay equivalence semantics**: `pins_equivalent_for_replay`
   excludes run_id, captured_at, notes. Does this list cover all
   pure-metadata fields? Is there anything in the equivalence
   set that should NOT block replay (e.g. minor LLM-provider
   diff that produces the same outputs)?

4. **JSON serialization**: stable key ordering via sort_keys.
   Does the current asdict() shape produce a stable
   nesting (retrieval_source_versions dict iteration order)?
   Round-trip tests confirm; verify no edge cases I missed.

5. **Coupling**: model_pin doesn't import OpenRouter or M-16
   bundle. Caller integrates. Is that the right cut, or should
   it auto-detect?

6. **Phase 2 readiness**: is the API shape (capture_pin returns
   ModelPin; pins_equivalent checks delta) sufficient for a
   future replay module to load + configure pipelines? Anything
   I should add now to avoid breaking changes later?

## Output

`outputs/codex_findings/md11_phase1_review/findings.md`:

```markdown
# Codex review of M-D11 phase 1 (commit d150a43)

## Verdict
GREEN / PARTIAL / DISAGREE

## Findings
- [schema gap, if any]
- [hash strategy concern, if any]
- [replay equivalence concern, if any]
- [serialization edge case, if any]
- [coupling issue, if any]
- [phase-2 readiness concern, if any]

## Final word
GREEN to lock M-D11 phase 1 / PARTIAL with edits.
```

Be terse. Under 60 lines.
