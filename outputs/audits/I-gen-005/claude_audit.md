# I-gen-005 Claude architect review

## Scope review

I-gen-005 began as a verifier-bug fix (V4 Pro 87% sentence drop rate in baseline smoke) and expanded into an architectural pivot to atom-first generation per operator's "atom-first per Codex's recommended_path" directive 2026-05-26.

## Architectural decisions

### Atom-first synthesis layer

V4 Pro is no longer trusted as the sole fact source. Instead:
- `claim_atom_extractor.py` extracts ClaimAtoms from evidence via pure-Python regex (Codex Option D: regex now, LLM later). 17 fields per atom including primary_section, comparator, dose-arm.
- Atom catalog is built per section + filtered to single-best-placement (Codex iter-3 primary_section enforcement).
- `format_atom_catalog_for_prompt()` renders the catalog as a compact prompt block.

### Refusal/gap rendering as safety floor

`atom_refusal_validator.py` enforces post-hoc:
- STRICT layer: missing/invalid atom_NNN citation for factual claim → REPLACE sentence with refusal disclosure template (Codex APPROVE_DESIGN wording).
- SOFT layer: value mismatch → log only (preserves V4 Pro paraphrase latitude).
- gaps.json sidecar emitted per Codex schema.

### Additive citation contract

Atom_NNN is ADDITIVE to existing [ev_XXX] (Codex Step 3a iter-1 P1 fix). Sentences must carry BOTH:
- [ev_XXX] satisfies existing strict_verify pipeline (safety floor unchanged).
- atom_NNN satisfies future post-hoc atom validator (Step 3b).

## Code hygiene review (CLAUDE.md §4)

- snake_case for functions/variables: ✓
- PascalCase for classes (ClaimAtom, GapRecord, SectionValidationResult): ✓
- Explicit imports throughout: ✓
- No wildcard imports: ✓
- Module-level constants in ALL_CAPS (_NUMBER_RE, _ENDPOINT_VOCAB, etc.): ✓
- Fail-soft error handling at integration boundaries (multi_section_generator atom block, refusal validator): ✓

## LAW compliance

- LAW I (APD synchronization): docs/todo_list + iteration_trajectory updated.
- LAW II (no fake working): 109/109 real tests, no mocks in src/.
- LAW III (proactive info seeking): Codex consulted at every architectural decision (design briefs + diff reviews).
- LAW IV (persistence of state): iteration_trajectory.md logs every Codex round.
- LAW V (hygiene): code follows §4 conventions.
- LAW VI (zero hard-coding): atom thresholds + endpoint vocab are module constants, not magic numbers in flow.
- LAW VII (CLI isolation): generator modules import via src.polaris_graph.*, no cross-phase imports.

## §-1.1 clinical-safety check

The atom-first architecture is the structural defense against the lethal failure mode flagged in CLAUDE.md §-1.1 (pattern-matching evaluation misses real fabrications; "Patients can be hurt by a wrong dose, wrong contraindication, wrong indication population"). Key trade-offs:

- Eligibility-frame sentences with endpoint+number now require atom citation (over-refuse benign eligibility prose is RECOVERABLE; under-refuse real outcome claims is LETHAL).
- Coordinated endpoint lists where binding is ambiguous → refused atom (no false binding).
- CI bounds (parenthesized + non-parenthesized) filtered out as outcome values to prevent reverse-claim attribution.

## Risk areas flagged for Step 3b

1. atom catalog mismatch between prompt-time and post-hoc validation if Step 3b rebuilds catalog (must pass-through, not rebuild — per Codex iter-2 P2).
2. atom_NNN being parsed as integer by strict_verify's numeric matching (must strip before that pass — per Codex iter-2 P2).
3. Refusal rate calibration unknown without real-run data; start logging-only behind flag (per Codex iter-2 P2).

## Verdict

The architecture is sound. Per-component Codex APPROVE at every layer. Codex umbrella APPROVE on aggregation. Tests pass. Step 3b appropriately deferred to separate PR with logging-only rollout.

Ready for merge.
