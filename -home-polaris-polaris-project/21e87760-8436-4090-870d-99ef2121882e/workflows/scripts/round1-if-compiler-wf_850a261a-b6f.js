export const meta = {
  name: 'round1-if-compiler',
  description: 'Round 1: build + unit-test the Instruction-Following compiler, source-eligibility gate, comparison bundles, and mechanical polish in the CHAMPION pipeline. Faithfulness FROZEN. No live scoring.',
  phases: [
    { title: 'Recon', detail: 'Read-only: map exact seams in champion + port sources in flywheel' },
    { title: 'Implement', detail: 'Additive, flag-gated, unit-tested changes on a new branch' },
    { title: 'Verify', detail: 'Faithfulness-untouched + OFF-path + run unit tests' },
  ],
}

// ---- Shared guardrail text injected into every agent ----
const GUARD = `
HARD GUARDRAILS (violating any = failure):
- WORKING REPO = the CHAMPION at /home/polaris/wt/outline_agent. This is the ONLY place you may EDIT.
- /home/polaris/wt/flywheel (cellcog) is READ-ONLY. You may READ it to copy logic or read data, but NEVER edit anything there.
- The champion driver filename scripts/compose_agentic_report_s3gear329.py ALSO exists in flywheel; only ever edit the /home/polaris/wt/outline_agent copy.
- FAITHFULNESS IS FROZEN: never modify src/polaris_graph/generator/provenance_generator.py or any strict_verify / citation-verification logic. Treat it READ-ONLY. No new verification pass, no new faithfulness test.
- All new behavior MUST sit behind a default-OFF env flag so the OFF path is byte-identical to today. Follow the repo's existing flag pattern (e.g. os.environ.setdefault / PG_* flags).
- Prefer NEW modules over rewriting existing code. Keep diffs additive and minimal.
- Do NOT run the full ~35-min live compose or any RACE/FACT scoring. Use fast offline unit tests only. If a test needs an LLM, mock it or use one tiny cheap call.
- If a task would require touching a frozen/forbidden file, STOP and report instead of doing it.
`

phase('Recon')
const recon = await parallel([
  () => agent(`${GUARD}
RECON R1 — champion outline/writer seams. READ-ONLY (do not edit).
Read in /home/polaris/wt/outline_agent:
- scripts/compose_agentic_report_s3gear329.py — the call to generate_multi_section_report (around line 249). Report EXACTLY which kwargs it passes today and which it omits (esp. deliverable_spec, scope_spec).
- src/polaris_graph/generator/multi_section_generator.py — generate_multi_section_report signature (around line 3010); how deliverable_spec/scope_spec/required_sections are read (_spec_read, _required_sections around 3038-3053); OUTLINE_SYSTEM_PROMPT_REQUIRED (~1628) and the required-sections conform-remap (~1966-2107).
Return a precise map: exact call site, exact param names, how required_sections flows into the outline prompt, and the minimal wiring needed to pass a deliverable_spec (with required_sections) + scope_spec (with a source-eligibility policy) from the driver — behind a default-OFF flag. Cite file:line.`, { label: 'recon:champion-seams', phase: 'Recon' }),

  () => agent(`${GUARD}
RECON R2 — source-eligibility logic to PORT from cellcog. READ-ONLY everywhere.
In /home/polaris/wt/flywheel read: scripts/provenance.py (derive_source_type ~1783), scripts/weighting.py (gate_eligibility ~362), scripts/argument_planner.py (class ResearchContract), and any code from the Rank12 "source-eligibility firewall" (git commit 8589849). 
Also read the champion corpus schema: /home/polaris/wt/outline_agent/data/cp4_corpus_s3gear_329.json (fields per evidence row — url, tier, venue, doi, etc.).
Return: a self-contained, portable spec for a function that, given a champion corpus row, classifies it as JOURNAL vs NON-JOURNAL and ENGLISH vs NON-ENGLISH (peer-reviewed journal article = eligible; Wikipedia, WEF/OECD/ILO/IMF reports, NBER/IZA working papers, news, blogs, personal sites, bank notes = ineligible). Describe the concrete signals (URL host, venue string, doi presence, tier) and how to make it a positive proof, not a tier guess. Cite file:line.`, { label: 'recon:eligibility-port', phase: 'Recon' }),

  () => agent(`${GUARD}
RECON R3 — mechanical-polish targets in champion. READ-ONLY (do not edit).
In /home/polaris/wt/outline_agent read:
- src/polaris_graph/generator/citation_truncation_normalizer.py (the repair that kills '].[' — confirm it exists and its entry function) and grep for where/whether it is called in the render path (multi_section_generator.py). 
- multi_section_generator.py: where references/bibliography are rendered; where same_work_groups is applied (and whether it is applied to the bibliography); the _normalize_citation_punctuation / _MISSING_TERMINATOR_RE logic (~5048-5063); how a blank/empty URL reference and a leaked "(tier T4)" string reach the references.
Return: exact functions + line ranges for: (1) wiring citation_truncation_normalizer into production render, (2) deduping the bibliography by work identity via same_work_groups, (3) dropping/fixing an empty-URL reference, (4) stripping "(tier …)" from references, (5) where the Limitations section text is produced (to humanize telemetry-speak). Cite file:line.`, { label: 'recon:polish-targets', phase: 'Recon' }),

  () => agent(`${GUARD}
RECON R4 — comparison-bundle logic to PORT from cellcog. READ-ONLY everywhere.
In /home/polaris/wt/flywheel read scripts/argument_planner.py: find_bundles, derive_facets, _comparability, span_eligibility. Understand how it groups studies that measure a common outcome and records why figures are/aren't comparable.
Cross-reference the champion corpus fields (/home/polaris/wt/outline_agent/data/cp4_corpus_s3gear_329.json) to see what comparison dimensions (outcome, unit, population, industry, period/horizon, method, direction, magnitude) are available or derivable per evidence row.
Return: a portable spec for a champion-side comparison-bundle builder that consumes champion corpus rows and emits bundles (list of {outcome, members[], comparable: bool, why}) to feed the existing writer's starved synthesis/policy/conclusion sections. Note which fields are missing in the champion corpus and how to derive them cheaply. Cite file:line.`, { label: 'recon:bundle-port', phase: 'Recon' }),
]).then(r => r.map(x => x || 'RECON FAILED — proceed cautiously and re-read the files yourself.'))

const [champSeams, eligPort, polishTargets, bundlePort] = recon
log('Recon complete — beginning implementation on branch round1-if-compiler')

phase('Implement')
// Sequential on the shared champion tree to avoid file-edit races. Each stage is additive + flag-gated + unit-tested.

const s0 = await agent(`${GUARD}
STEP 0 — create an isolated, reversible branch. In /home/polaris/wt/outline_agent:
- git status; ensure clean-ish. Create and switch to a new branch: round1-if-compiler (git checkout -b round1-if-compiler). If it exists, reuse it.
- Do NOT commit anything yet; just create the branch.
Report the branch state and current HEAD.`, { label: 'impl:branch', phase: 'Implement' })

const s1 = await agent(`${GUARD}
STEP 1 — build the INSTRUCTION CONSTRAINT EXTRACTOR (new module, general, prompt-agnostic).
Create src/polaris_graph/instruction/constraint_extractor.py (new package if needed) exposing extract_constraints(prompt: str) -> dict with typed fields: source_types (e.g. ['journal_article']), languages (['en']), recency (None or a cutoff), required_coverage (list of topical slots the prompt implies/names), exclusions, format (e.g. 'literature_review'), length, tone. It must be an LLM pass, adversarially prompted to find BURIED constraints (rules phrased mid-sentence or as soft asides). Reuse the repo's existing LLM client (find how other modules call the model; do not hardcode keys).
Acceptance UNIT TEST (tests/instruction/test_constraint_extractor.py): on the task-72 prompt ("Please write a literature review on the restructuring impact of Artificial Intelligence (AI) on the labor market... Ensure the review only cites high-quality, English-language journal articles."), it must extract source_types containing journal-only, languages containing English, and format literature_review. If live LLM is unavailable in test, gate the live call and provide a fixture-based test asserting the parser/shape.
Champion seam notes for later wiring:\n${champSeams}\n
Keep it a standalone module (no wiring yet). Run the new unit test. Report files added + test result.`, { label: 'impl:extractor', phase: 'Implement' })

const s2 = await agent(`${GUARD}
STEP 2 — build the SOURCE-ELIGIBILITY GATE (new module, ported from cellcog logic).
Create src/polaris_graph/instruction/source_eligibility.py exposing classify_source(row: dict) -> {'eligible': bool, 'source_class': str, 'language_ok': bool, 'reasons': [...]} and filter_eligible(rows, policy) -> (eligible_rows, rejected_rows). Journal/peer-reviewed = eligible; Wikipedia, WEF/OECD/ILO/IMF reports, NBER/IZA/working papers, news, blogs, personal sites, bank notes = ineligible. Use the concrete signals from the port spec below.
Port spec (READ-ONLY source in flywheel):\n${eligPort}\n
Acceptance UNIT TEST (tests/instruction/test_source_eligibility.py): load the champion corpus /home/polaris/wt/outline_agent/data/cp4_corpus_s3gear_329.json, run classification, and ASSERT that known-bad hosts (en.wikipedia.org, morganstanley.com, weforum.org, oecd.org, ilo.org, nber.org, docs.iza.org) are classified INELIGIBLE and known-journal hosts (pmc.ncbi.nlm.nih.gov, sciencedirect.com, aeaweb.org, pubmed) are ELIGIBLE. Print an eligibility summary (counts). Run the test. Report files + test result + the eligibility summary numbers.`, { label: 'impl:eligibility', phase: 'Implement' })

const s3 = await agent(`${GUARD}
STEP 3 — build the COMPARISON-BUNDLE BUILDER (new module, ported logic).
Create src/polaris_graph/instruction/comparison_bundles.py exposing build_bundles(rows: list[dict]) -> list[dict] where each bundle = {outcome, members:[row_ids], comparable: bool, why: str}. Consume champion corpus rows; group studies measuring a common outcome; record comparability. This is PLANNING data to feed the writer's starved sections — it does NOT write prose and does NOT touch verification.
Port spec (READ-ONLY source in flywheel):\n${bundlePort}\n
Acceptance UNIT TEST (tests/instruction/test_comparison_bundles.py): on the champion corpus, build bundles and assert >=1 non-trivial bundle with >=2 members and a populated 'why'. Print bundle count + a couple examples. Run it. Report files + test result + bundle stats.`, { label: 'impl:bundles', phase: 'Implement' })

const s4 = await agent(`${GUARD}
STEP 4 — PILLAR 4 MECHANICAL POLISH (low-risk, additive/flag-gated as appropriate). Edit only the champion render path.
Using the target map below, implement: (1) wire citation_truncation_normalizer into the production render so '].[' is fixed; (2) dedup the bibliography by work identity using same_work_groups; (3) drop/fix any empty-URL reference; (4) strip "(tier …)" leakage from references; (5) humanize the telemetry-speak Limitations text. Put anything behavior-changing behind a default-OFF flag if it risks altering the OFF path.
Target map:\n${polishTargets}\n
Acceptance: add/adjust unit tests under tests/ that assert '].[' is gone, the bibliography has no duplicate-work entries, and no empty-URL / "(tier" strings remain. Do NOT run a live compose; test against existing fixture/report text where possible. Run the tests. Report exact edits (file:line), files, and test results. Remember: do NOT edit provenance_generator.py.`, { label: 'impl:polish', phase: 'Implement' })

const s5 = await agent(`${GUARD}
STEP 5 — WIRE the compiler into the driver, behind a default-OFF flag. This is the integration step.
In /home/polaris/wt/outline_agent/scripts/compose_agentic_report_s3gear329.py: at the generate_multi_section_report call (~line 249), when a new default-OFF flag (e.g. PG_IF_COMPILER=1) is set, build a deliverable_spec (required_sections derived from constraint_extractor.required_coverage) and a scope_spec (source-eligibility policy from source_eligibility) and pass them through the EXISTING seams. When the flag is OFF, pass nothing new so behavior is byte-identical to today.
Also apply the source-eligibility filter to the citable evidence menu ONLY (ineligible rows stay available for retrieval telemetry/gap detection but are withheld from what the writer can cite) — again gated by the flag.
Champion seam notes:\n${champSeams}\n
Acceptance UNIT/INTEGRATION TEST: assert that with the flag OFF, the kwargs passed to generate_multi_section_report are unchanged from today (byte-identical wiring); with the flag ON, deliverable_spec + scope_spec are populated and the ineligible sources are excluded from the citable set. Mock the heavy generator call — do NOT run the real ~35-min compose. Run the test. Report exact edits (file:line) and results.`, { label: 'impl:wire', phase: 'Implement' })

phase('Verify')
const verdict = await agent(`${GUARD}
FINAL VERIFY (read + run tests only; make no new feature edits).
In /home/polaris/wt/outline_agent on branch round1-if-compiler:
1. Confirm src/polaris_graph/generator/provenance_generator.py is UNMODIFIED vs the branch point (git diff --stat must show it untouched). Confirm no files under /home/polaris/wt/flywheel were modified.
2. Confirm every new behavior is behind a default-OFF flag and that git diff shows additive, minimal changes (report the diffstat).
3. Run the full set of new unit tests plus any existing fast outline/generator unit tests that could be affected (discover via pytest -q collection; run the relevant fast ones, NOT any live-scoring or network suite). Report pass/fail counts.
4. Summarize: what is built, what passed, the eligibility summary numbers, bundle stats, and any TODO/risk. Explicitly state whether faithfulness (provenance_generator.py / strict_verify) was left untouched.
Return a structured verdict.`, { label: 'verify', phase: 'Verify', schema: {
  type: 'object',
  additionalProperties: false,
  required: ['faithfulness_untouched', 'flywheel_untouched', 'off_path_byte_identical', 'tests_passed', 'tests_failed', 'summary', 'risks'],
  properties: {
    faithfulness_untouched: { type: 'boolean' },
    flywheel_untouched: { type: 'boolean' },
    off_path_byte_identical: { type: 'boolean' },
    tests_passed: { type: 'integer' },
    tests_failed: { type: 'integer' },
    eligibility_summary: { type: 'string' },
    bundle_stats: { type: 'string' },
    diffstat: { type: 'string' },
    summary: { type: 'string' },
    risks: { type: 'array', items: { type: 'string' } },
  },
} })

return {
  branch: 'round1-if-compiler',
  recon_ok: recon.map(r => r.slice(0, 80)),
  verdict,
}
