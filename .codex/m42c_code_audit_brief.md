You are auditing M-42c — third of 4 items in the M-42 bundle.
Narrow scope: mechanism evidence floor + conditional section prompt.

## Plan reference

`outputs/audits/v25/fix_plan.md` M-42c, approved pass-3. Two
coordinated changes:
1. Selector: mechanism-evidence floor when pool has >=4 mech rows
2. Section prompt: conditional 20-35 / 15-20 / 10-15 target

## Diff

Commit at HEAD. Three files:

1. `src/polaris_graph/retrieval/evidence_selector.py`:
   - `_M42C_MECHANISM_TOKENS`: 21 mechanism-of-action tokens
   - `_m42c_row_is_mechanism_rich(row)`: substring scan across
     title + statement + direct_quote
   - `_M42C_MECHANISM_FLOOR_MIN_POOL_ROWS = 4` threshold
   - `_M42C_MECHANISM_FLOOR_SLOTS = 3` reservation count
   - Floor computed before the tier pick loop
   - T1 pick loop: M-42e primaries first, then M-42c mech, then
     fill-by-relevance
   - T2 pick loop: M-42c mech first, then fill-by-relevance
   - Telemetry note: `m42c_mechanism_floor pool_mech_rows=N
     reserved=M slots=3`

2. `src/polaris_graph/generator/multi_section_generator.py`:
   - New "M-42c MECHANISM-SECTION DEPTH RULE" block inserted
     between rule #12c (M-42a) and the EVIDENCE TIER DISCIPLINE
     block
   - 3 conditional targets (20-35 / 15-20 / 10-15) with priority
     topic list + honest disclosure requirement
   - "applies ONLY when the current section title is 'Mechanism'"

3. `tests/polaris_graph/test_m42c_mechanism_floor_and_prompt.py`:
   15 tests — detection (title/statement/quote/British spelling/
   glucagon), floor integration (fires at >=4, no-op <4, respects
   T1 quota), prompt rule (presence, 3-tier targets, 6 topics,
   scope restriction, honest disclosure, no drug names).

## What to verify

1. **Mechanism token list**: are 21 tokens the right set? Notable
   inclusions: "glucagon", "insulin secretion", "insulin
   sensitivity" are clinical-domain-specific. Is that acceptable
   or should they be removed for generalization?

2. **Floor integration order**: M-42e primaries first, then M-42c
   mech, then fill-by-relevance. Correct precedence? M-42e is the
   named-trial-primary floor; M-42c is the mechanism floor. If a
   row satisfies both (e.g. a SURPASS primary that has mechanism
   content), M-42e wins the reservation and the row counts once.
   Not double-counted.

3. **T1 quota sufficiency**: in a pool with 6+ primaries AND 5+
   mechanism rows, T1 quota might be 8; M-42e fills 6, M-42c
   gets 2 slots max, relevance-fill gets 0. Is this the right
   priority?

4. **T2 slot for mech**: M-42c can reserve in T2 too. Does the
   T2 mech floor conflict with any existing T2 floor?
   (M-25b has a general T2 floor of 1; M-42c adds to that.)

5. **Prompt rule scoping**: "applies ONLY when the current section
   title is 'Mechanism'". How does the LLM actually know its
   section title? The prompt template has `{title}` substitution.
   Does the section-writer see the title somewhere that lets it
   apply the rule? (Yes — `SECTION_SYSTEM_PROMPT_TEMPLATE.format(
   title=..., focus=...)` substitutes the title into the header
   of the prompt. The M-42c rule references "current section
   title" — is that clear enough for the LLM to self-identify?)

6. **Evidence-gated target**: the LLM is told "use 20-35 if 8+
   mech ev_ids". How does the LLM count mechanism ev_ids in its
   evidence subset? Are ev_ids tagged somewhere as mechanism-rich?
   (No — the LLM would have to scan evidence blocks for the token
   patterns itself. The rule is probabilistic at best; stronger
   enforcement would require a code-side pre-count passed into the
   prompt. Acceptable as a soft target?)

7. **Honest disclosure clause**: rule says "close with an honest
   disclosure sentence like 'The mechanistic evidence available...
   is limited to [N] rows'". Does the LLM know the N? Probably
   not without passing it explicitly. Is the disclosure
   requirement actionable?

## What counts as a blocker vs medium

- **BLOCKER**: mechanism floor crashes under empty pool; prompt
  rule contradicts existing rules; M-42c displaces an existing
  floor; drug names leak into rule body.
- **MEDIUM**: token list tightening, evidence-gated target
  needs code-side count (could pass `mechanism_ev_count` into
  format()), disclosure requires N.
- **LOW**: comments.

## Deliverable

Write `outputs/codex_findings/m42c_code_audit/findings.md` with
final verdict (READY | BLOCKED | CONDITIONAL). Under 1000 words.
