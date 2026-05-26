# Codex — Step 3a diff review (V4 Pro atom catalog prompt injection)

## §8.3.1 cap directive (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. No drip-feeding.
- "Don't pick bone from egg" — reserve P0/P1 for execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE per §8.3.1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Context

You APPROVE_DESIGN'd refusal/gap rendering (iter 4). You explicitly said
`approval_to_proceed_to_step_3: YES`. This commit is Step 3a — the
PROMPT side of the hybrid approach. Step 3b (POST-HOC side wired into
the multi_section_generator output pipeline) is deferred to a follow-up
because the existing pipeline (strict_verify → sentence_repair →
resolve_provenance_to_citations → SectionResult) is complex and requires
careful coordination with the atom validator.

## What this commit adds (~50 lines)

Inside `_call_section` in `multi_section_generator.py`, AFTER the
existing allow-list block:

```python
try:
    from src.polaris_graph.generator.claim_atom_extractor import (
        build_atom_catalog, filter_atoms_for_section,
        format_atom_catalog_for_prompt,
    )
    _atom_catalog = build_atom_catalog(evidence_subset)
    _section_atoms = filter_atoms_for_section(_atom_catalog, section.title)
    if _section_atoms:
        atom_block = format_atom_catalog_for_prompt(_section_atoms)
        atom_instruction = (
            "\n\nATOM-CITATION CONTRACT (post-hoc enforced):\n"
            "For factual quantitative claims (effect size, comparator, "
            "safety incidence, dose-response), cite the atom_NNN ID "
            "from the ATOM CATALOG above — NOT the raw [ev_XXX] marker. "
            ... [full instruction including worked example] ...
        )
        system = system + "\n\n" + atom_block + atom_instruction
        logger.info(...)
except Exception as _atom_exc:
    # Fail-soft per atom-first design
    logger.warning(...)
```

## Design notes

### Gated to ALL models, not just reasoning-first

The atom-citation contract is a generation directive, not a reasoning-
specific quirk. Both V4 Pro (reasoning-first) and any non-reasoning
generator benefits from the structured citation contract.

### Fail-soft on extraction errors

If `build_atom_catalog` raises (regex failure, malformed evidence,
etc.), we log + fall through. Existing HARD CONTRACT + allow-list
constraints remain in effect. This preserves the existing safety floor
even if atom extraction is broken.

### Section-relevance filter

Atoms are filtered to `primary_section == section.title` via
`filter_atoms_for_section`. Per refusal-validator iter-3's single-best-
placement enforcement, atoms only appear in their primary section.

### Instruction wording

The instruction tells V4 Pro:
1. Cite atom_NNN for factual claims
2. [ev_XXX] is for narrative transitions only
3. OMIT claims with no supporting atom (refusal-validator will replace
   bare-claim sentences anyway — better to write fewer cited claims
   than to have refusals replace prose)
4. Worked example showing the cited form

Per your APPROVE_DESIGN trigger schema: V4 Pro is gently informed
about the post-hoc consequence (refusal replacement) without strict
banishing of [ev_XXX] for narrative.

## Step 3b plan (NOT in this commit)

The post-hoc validator (`validate_section()`) will be called in the
caller pipeline AFTER strict_verify produces `kept_sentences` and
AFTER resolve_provenance_to_citations renders the final cited text.
The atom validator then:
1. Splits the rendered text into sentences (decimal-aware split)
2. For each sentence, applies the STRICT layer:
   - missing atom_NNN for factual claim → replace with refusal
   - invalid atom_NNN → replace with refusal
   - [ev_XXX] for factual claim → replace with refusal
3. For each sentence, applies the SOFT layer (log only, keep sentence)
4. Aggregates GapRecords across sections
5. `write_gaps_sidecar()` emits gaps.json next to report.md

This requires new fields on SectionResult + a top-level orchestrator
hook for the sidecar writer + possibly a new flag to enable/disable
the post-hoc enforcement (until V4 Pro proves it can emit atom_NNN
reliably, we may want to ship with logging-only mode first).

## Questions for your review

### Q1: Is the fail-soft policy right?

Currently: atom extraction error → log + skip atom block. The existing
[ev_XXX] verification path continues to enforce the safety floor.

Alternative: atom extraction error → raise + abort section generation
(strict mode). Less recoverable but more visible to operators.

### Q2: Is the gating to ALL models correct?

Or should this be gated to `_REASONING_FIRST_MODELS` only (like the
allow-list block above)? Argument for ALL: atom citation is universal.
Argument for reasoning-first only: prompt-token cost — atom catalog
adds 1-2K tokens per call.

### Q3: Should I land Step 3b in this same PR?

Step 3b touches the SectionResult dataclass, the orchestrator that
calls _call_section, and adds gaps.json to the output artifacts.
That's a much larger diff. Alternatively, Step 3b can be a separate
PR (smaller scope per PR, easier to revert if real-run finds issues).

### Q4: Should we ship Step 3b in "logging-only" mode initially?

Until we have real-run evidence that V4 Pro reliably emits atom_NNN,
the post-hoc validator could run in "logged_only" mode for ALL gap
classes (not just SOFT). Operators see the refusal-WOULD-replace
records in gaps.json but the report.md preserves V4 Pro's original
prose. Once we trust V4 Pro's compliance, flip the flag to STRICT.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES

prompt_injection_correctness: YES | NO

fail_soft_policy_appropriate: YES | NO
  if_no: |
    (recommended policy)

gating_to_all_models_correct: YES | NO

step_3b_scope_recommendation: SAME_PR | SEPARATE_PR
  reasoning: |

step_3b_logging_only_initial: YES | NO
  reasoning: |

instruction_wording_no_issues: YES | NO
  if_no: |
    (specific wording problem)

novel_p0: [...]
novel_p1: [...]
p2: [...]
p3: [...]

approval_to_proceed_to_step_3b: YES | NO
convergence_call: continue | accept_remaining
```

EMIT YAML ONLY. Diff at `.codex/I-gen-005-refusal/codex_step3a_diff.patch`.
