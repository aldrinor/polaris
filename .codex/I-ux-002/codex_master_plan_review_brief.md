# Codex master-plan review brief — I-ux-002 UI harness, deep line-by-line audit

## CONTEXT YOU MUST UNDERSTAND BEFORE STARTING

This is the operator's third pass at the same problem. Four days of you+me
work on UI has not produced top-tier output. Operator's exact words
2026-05-25 night:

> "Now the whole AI are shit, even you and Codex spent 4 days on it, it is
> very undesirable… We cannot afford to keep missing target on the UI, from
> not being top tier."

Your job in this review is **NOT to approve, NOT to be cooperative**. Your job
is to be the harshest critic on earth and find what is wrong, what is
missing, what can still drift, what failure modes the plan does not close.

The operator's specific ask: "let Codex to review all of these, line by
line, carefully, critically, to make sure, under this harness engineering,
we can avoid all diff and drift on UI engineering."

If you cannot find a real hole in the plan or research, the operator will
not trust this work. Find holes. Find every hole. If a claim is unsupported
by the cited source, flag it. If a research output is shallow despite
purporting to be deep, flag it. If the master plan has a contradiction with
the research outputs, flag it. If the harness still permits drift in any
realistic scenario, flag it as P0.

**Iteration cap: NONE. Operator standing directive
`feedback_codex_decides_all_stier_uncapped_2026_05_24` overrides CLAUDE.md
§8.3.1 for THIS review.** Take as many rounds as you need. Don't drip-feed —
front-load every real finding in iter 1, but iter 2/3/N exist if real
findings remain.

Per CLAUDE.md §8.3.2: "Codex iter 1 of cleanup_audit caught `git clean -fdX`
would nuke `.env`... ~25 [findings] would have caused real execution
failures, 3 catastrophic. Empirical: Codex findings are real. Do not dismiss
as noise."

That is the standard. Be that critical.

## OUTPUT SCHEMA (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
review_pass: 1  # this is iter N; we are uncapped

# Per-file line-by-line analysis. EVERY file below must have a section.
# For each, score: SOLID | PARTIAL | SHALLOW | MISLEADING | FABRICATED
files:
  master_plan:
    score: SOLID | PARTIAL | SHALLOW | MISLEADING | FABRICATED
    line_by_line_findings:
      - line_or_section: "Section X, line Y"
        finding: "..."
        severity: P0 | P1 | P2 | P3
        evidence_quote: "..."
  playwright_mcp_source_deep_dive:
    score: ...
    line_by_line_findings: [...]
  browser_agent_frameworks_deep_dive: { ... }
  coding_agent_review_patterns: { ... }
  academic_papers_full_text: { ... }
  visual_regression_tools_deep_dive: { ... }
  failure_cases_compendium: { ... }
  vendor_docs_first_party: { ... }

# Cross-cutting drift surfaces. THIS IS THE CRITICAL SECTION.
# List every UI drift surface that the proposed harness DOES NOT close.
# Be specific. Real scenarios. Not "in theory" — concrete examples.
drift_surfaces_still_open:
  - id: D-001
    scenario: "Writer changes <specific file/pattern>. Harness response: <what>. Drift outcome: <what reaches production>."
    p_value: P0 | P1 | P2
    suggested_fix: "..."

# Unsupported claims in the research files.
unsupported_claims:
  - file: ...
    section: ...
    claim_quoted: "..."
    why_unsupported: "..."
    severity: P0 | P1 | P2

# Contradictions between files.
internal_contradictions:
  - claim_A: { file: ..., quote: ... }
    claim_B: { file: ..., quote: ... }
    why_contradictory: "..."

# Hallucination check: any citations that don't actually exist?
# Specifically check: file:line citations in playwright_mcp_source_deep_dive,
# browser_agent_frameworks_deep_dive, coding_agent_review_patterns,
# visual_regression_tools_deep_dive. The agents claimed to read source.
# Did they? Or did they hallucinate the citations?
suspected_fabrications:
  - file: ...
    citation: "..."
    why_suspect: "..."

# Final verdict reasoning
verdict_reason: |
  ...

# If REQUEST_CHANGES, what is the minimum bar for APPROVE?
minimum_bar_for_approve: |
  ...

convergence_call: continue | accept_remaining_at_iter_2_or_later
remaining_blockers_for_execution: [...]
```

## FILES TO REVIEW (each must be analyzed)

1. **MASTER PLAN** — `docs/ui_harness_master_plan_2026_05_25.md` (~404 lines)
   - Sections 1-7
   - Section 5 is the honest-limits section: scrutinize whether the limits
     listed there are the REAL limits or just the easy ones to admit
   - Section 3 R1-R8 revisions: does each actually close a real drift?
   - Section 6 operator-confirmation list: are the right decisions surfaced?

2. **PLAYWRIGHT MCP SOURCE** — `docs/ui_harness_research/playwright_mcp_source_deep_dive.md` (371 lines)
   - Cited file:line in `/packages/playwright-core/src/tools/backend/`
   - Verify the claim that the implementation lives in a different repo than the README implies

3. **BROWSER AGENT FRAMEWORKS** — `docs/ui_harness_research/browser_agent_frameworks_deep_dive.md` (207 lines)
   - Cited file:line for Browser-Use, Stagehand, Skyvern
   - Verify Skyvern's `complete_verify():2729-2831` claim — this is load-bearing for R1
   - Verify the Browser-Use `consecutive_failures` increment-bug claim

4. **CODING AGENT PATTERNS** — `docs/ui_harness_research/coding_agent_review_patterns.md`
   - Cited file:line for Aider, Cline, Roo-Code
   - Verify Cline's `CommandPermissionController` claim — load-bearing for AAB pattern
   - Verify the "Aider has NO post-application verification" claim

5. **ACADEMIC PAPERS** — `docs/ui_harness_research/academic_papers_full_text.md` (484 lines)
   - UICrit's 5-cluster claim with verbatim cluster names — load-bearing for R4
   - Visual Prompting's iter-3 diminishing-returns claim — load-bearing for R3
   - **Especially scrutinize Faramesh paper claim** — does arxiv:2601.17744 actually exist? Or was it fabricated?
   - Abstain & Validate's refusal-authority claim — load-bearing for verdict design

6. **VISUAL REGRESSION TOOLS** — `docs/ui_harness_research/visual_regression_tools_deep_dive.md` (294 lines)
   - 1,400+ files cloned claim — verify
   - ODiff dual-threshold heuristic claim — load-bearing
   - False positive rate claims (0.5-1% Applitools, 5-10% pixel tools) — verify

7. **FAILURE CASES** — `docs/ui_harness_research/failure_cases_compendium.md`
   - 25+ sourced cases — verify a sample (5+) actually exist on the cited URLs
   - Qwen3-VL 6% FNR claim — verify the source
   - Kilo Code $7.59 burn claim — verify the source

8. **VENDOR DOCS** — `docs/ui_harness_research/vendor_docs_first_party.md` (460 lines)
   - Anthropic harness blog 3-agent claim (Planner/Generator/Evaluator)
   - GitHub Squad / /fleet claims — verify these features actually exist

## SPECIFIC DRIFT SURFACES YOU MUST CHECK

Before you finish, walk through each of these and tell me whether the
proposed harness closes them:

### D-WL — `web/lib/**` changes
A writer edits `web/lib/proof_replay_adapter.ts` which changes the
rendered output of `/inspector/[runId]`. Does the harness require an audit?
The master plan Section 5 admits this is open. Is that admission honest, or
is there a way the harness COULD close it?

### D-MW — `web/middleware.ts` change
Middleware can change which routes 404 in production. A writer edits
middleware to enable a previously-404'd route. Does the harness audit it?

### D-CFG — config / env / theme tokens change
A writer changes `tailwind.config.js` brand color from `#c8102e` to
`#dc2626` (near-miss). Does any gate catch this?

### D-CDX — codex CLI itself
The CI gate parses what Claude commits as the audit artifact, NOT a fresh
Codex run on CI. Claude could in principle commit a fabricated audit file
with `verdict: APPROVE` + working SHAs. What stops this? Is the answer just
"operator reviews `git log`"? If yes, is that AAB or just hope?

### D-RBR — rubric drift
A writer (or future Claude) edits `.codex/visual_audit_rubric.md` to
soften a dimension (e.g., dim 11 sovereignty disclosure relaxed). The
rubric SHA changes, but the new audit declares the new SHA. CI matches.
Drift ships. What stops this? CODEOWNERS on the rubric file?

### D-VPI — viewport selection bypass
A writer sets `PG_VISUAL_GATE_VIEWPORTS=2000x2000` (a huge non-realistic
viewport) where most UI bugs hide. The audit passes. Production-realistic
viewports never audited. What stops this?

### D-NEW — net-new UI patterns (e.g., a modal that didn't exist before)
The rubric scores existing dimensions; what about NEW kinds of UI
problems the rubric was never built to score?

### D-LIVE — live data vs fixture
The audit runs against a `next start` of a production build with
fixture data. Production runs against real backend with real evidence
bundles. A subtle bug appears only with real-shape data. Audit passes;
production breaks. What stops this?

### D-TEMP — temporal drift in the model
Codex CLI is backed by GPT-5 (or whatever model OpenAI is currently
serving). The model updates next week. Same screenshot now scored differently.
What stops this? The rubric is SHA-pinned but the MODEL is not.

### D-ITER — iter-2 cap (R3) gaming
A writer learns the gate force-APPROVEs at iter 2. Writer ships
acceptable-but-mediocre UI knowing iter 1 will fail but iter 2 force-APPROVE
gets it through. Is this a real risk?

### D-CONS — 3-judge consensus (R2) gaming
The 3 judges are 3 Codex calls of the SAME model. They're not 3
independent models. If GPT-5 has a systematic blind spot, all 3 judges share
it. Is this real Monte Carlo independence or fake?

### D-OPC — operator post-merge spot-check (R8) failure
The plan's last line of defense is the operator's morning spot-check. But
the operator already missed the harness drift across 8 sub-PRs. What makes
this line of defense stronger now than it was then?

## RULES FOR YOUR REVIEW

- Quote with file:line OR file:section. Don't hand-wave.
- If you cannot verify a citation (URL behind paywall, repo deleted, etc.),
  flag the claim as UNVERIFIABLE not approved.
- If multiple files agree on a claim, that's NOT corroboration — they share
  the same author. Treat as a single claim.
- Be willing to mark `score: FABRICATED` if a file:line citation doesn't
  exist. Be willing to mark `score: SHALLOW` if the agent clearly skim-read.
- Pretend the operator will ship the demo to the Prime Minister of Canada
  based on whether you APPROVE. If you would not stake your reputation on
  the harness preventing drift, return REQUEST_CHANGES.
- DO NOT BE NICE. Niceness costs the operator 4 more days. The cost of
  rejecting an APPROVE that should be a REQUEST_CHANGES is far higher than
  the cost of asking for one more iter.

## CONVERGENCE RULE

`accept_remaining` is only valid when you have walked through every D-*
drift surface above and explicitly stated whether each is closed. Even
then, prefer `continue` if any P0 surfaces remain.

Begin review now. Output ONLY the YAML schema. No preamble.
