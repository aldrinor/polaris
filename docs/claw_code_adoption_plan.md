# Claw Code Adoption Plan: Path to Top-Tier Research Quality

## Current State (After v4-simplify Phase 1)

TEST_080 scored 75.6/100. TEST_082 scored 46.8 (polish damage, now disabled).
Projected next run (TEST_083): 75-80/100 based on fixes applied.

**The gap to top-tier (85+/100) comes from 4 root causes:**

| Root Cause | Impact | Current State |
|-----------|--------|--------------|
| Outline-evidence mismatch | -5 pts | Outline planned BEFORE evidence is known |
| Shallow evidence extraction | -4 pts | Generic "extract 8-15 facts" from 50K text |
| No structural quality check | -3 pts | Outline never reviewed, sections never critiqued |
| Verification rubber-stamp | -3 pts | Verifier defaults to SUPPORTED (adversarial fix applied, untested) |

Each Claw Code pattern maps to one or more of these root causes.

---

## Phase 2A: Read-Then-Plan (Days 1-4)

### What
Reverse the pipeline order. Currently: plan queries → search → analyze → outline → write.
New: search broadly → fetch top sources → summarize each → THEN outline based on actual evidence.

### Why This Is The #1 Change
Gemini reads papers before deciding what sections to write. Our pipeline decides the outline
from the query alone, then searches for evidence to fill predefined sections. This causes:
- Sections with 0-2 evidence (the evidence doesn't exist for that topic)
- Missing sections (important evidence found but no section planned for it)
- Thin sections (outline expected depth that the evidence doesn't support)

### How (Specific Code Changes)

**Step 1: Add "explore" phase between search and outline generation**

Current graph:
```
plan → search → storm → analyze → verify → deepen → evaluate → synthesize
                                                                    ↓
                                                              outline → sections
```

New graph:
```
plan → search → storm → analyze → verify → deepen → evaluate → synthesize
                                                                    ↓
                                                           EXPLORE EVIDENCE
                                                                    ↓
                                                           outline (from evidence)
                                                                    ↓
                                                              sections
```

**Step 2: Build evidence explorer (in synthesizer.py)**

Before outline generation, the synthesizer:
1. Groups evidence by topic using embedding clustering (already exists: our clustering code)
2. For each cluster, generates a 1-sentence summary of what evidence EXISTS
3. Passes these summaries to the outline generator as input

New outline prompt:
```
Research question: {query}

AVAILABLE EVIDENCE (what you can actually write about):
- Cluster 1 (15 evidence): Weight loss efficacy across 8 RCTs, effect sizes -4.3 to -0.9 kg
- Cluster 2 (12 evidence): Glycemic control improvements, HOMA-IR, HbA1c reductions
- Cluster 3 (8 evidence): Cardiovascular markers, lipid profiles, CRP
- Cluster 4 (6 evidence): Safety, adverse effects, contraindications
- Cluster 5 (4 evidence): Mechanisms, autophagy, metabolic switching
- Cluster 6 (3 evidence): Methodology limitations, study quality

Create a report outline with ONE section per evidence cluster.
Do NOT create sections for topics with < 3 evidence pieces.
Each section title should reflect the SPECIFIC evidence available, not generic topics.
```

This means the outline is DRIVEN by evidence, not by the query alone.

**Step 3: Modify `write_all_sections` to use evidence-driven outline**

Currently: outline → filter evidence per section (FIX-107I embedding similarity).
New: evidence clusters → outline sections → evidence already assigned by cluster.

No FIX-107I filtering needed — evidence is pre-assigned by clustering.

### Estimated Effort: 3 days
- Day 1: Build evidence cluster summarization
- Day 2: Modify outline prompt to use evidence summaries
- Day 3: Test with pipeline run

### Dependencies: None (works with current infrastructure)

### Quality Impact: +4-5 points (fixes outline-evidence mismatch entirely)

---

## Phase 2B: Focused Sub-Agent Evidence Extraction (Days 5-8)

### What
Instead of "extract 8-15 atomic facts from this 50K paper," use focused sub-agents that
ask specific questions per subtopic.

### Why
Current extraction prompt is generic: "extract TOP 8-15 MOST relevant atomic facts."
From a 50K-char meta-analysis, this produces 8 surface-level facts.
A focused question like "What does this paper say about cardiovascular outcomes specifically?"
would extract 3-5 DEEP facts on that subtopic.

### How (Specific Code Changes)

**Step 1: After query decomposition, create subtopic questions**

```python
# From the outline (now evidence-driven from Phase 2A):
subtopics = [
    "weight loss magnitude and consistency across protocols",
    "glycemic control improvements (HOMA-IR, HbA1c, fasting glucose)",
    "cardiovascular marker changes (lipids, blood pressure, CRP)",
    "safety profile and adverse effects",
    "mechanisms (autophagy, metabolic switching, circadian)",
]
```

**Step 2: For each source, extract evidence per subtopic**

Instead of ONE extraction call per source:
```
Extract 8-15 atomic facts from this paper.
```

Do N calls per source (one per relevant subtopic):
```
Focus: cardiovascular outcomes
What does this paper say specifically about lipid profiles, blood pressure,
heart rate, CRP, or other cardiovascular markers?
Extract 3-5 specific findings with exact numbers.
```

**Step 3: Merge subtopic evidence into unified pool**

Each subtopic extraction returns 3-5 focused evidence pieces.
5 subtopics × 3-5 facts = 15-25 facts per source (vs 8-15 generic facts).
But each fact is DEEPER and more specific to a section.

### Estimated Effort: 4 days
- Day 1: Build subtopic question generator
- Day 2: Modify extraction to use focused prompts
- Day 3: Build merge/dedup for multi-subtopic extraction
- Day 4: Test with pipeline run

### Dependencies: Phase 2A (needs subtopics from evidence-driven outline)

### Quality Impact: +3-4 points (fixes shallow evidence extraction)

### Cost Impact: ~2x extraction cost ($0.50 → $1.00) — acceptable within $8 budget

---

## Phase 3A: Outline Critique Agent (Days 9-11)

### What
After outline generation, spawn a critique agent that reviews the outline for
structural problems BEFORE any sections are written.

### Why (from ULTRAPLAN pattern)
ULTRAPLAN spawns parallel agents including a CRITIQUE agent that reviews the plan.
Our outline goes directly to section writing with no review. Structural problems
(overlapping sections, missing topics, wrong section order) are only visible
after the full report is written.

### How (Specific Code Changes)

**Step 1: After outline generation, call critique agent**

```python
critique_prompt = f"""Review this research report outline for: {query}

OUTLINE:
{formatted_outline}

AVAILABLE EVIDENCE:
{evidence_cluster_summaries}

Find SPECIFIC problems:
1. Are any key aspects of the query NOT covered by a section?
2. Do any two sections overlap significantly? Name which ones.
3. Does any section have fewer than 3 evidence pieces? Which ones?
4. Is the section order logical for a reader? What should move?
5. Is any section title too vague to write a focused analysis?

List ONLY problems found. Do not say "looks good."
If you find no problems, say "NO ISSUES FOUND."
"""
```

**Step 2: If critique finds problems, adjust outline**

- Missing coverage → add a section
- Overlapping sections → merge them
- Thin sections → merge into neighbors or remove
- Wrong order → reorder
- Vague titles → make specific based on evidence

**Step 3: Proceed to section writing with reviewed outline**

### Estimated Effort: 2 days
- Day 1: Build critique agent call + response parser
- Day 2: Build outline adjustment logic + test

### Dependencies: Phase 2A (evidence-driven outline to critique)

### Quality Impact: +2-3 points (catches structural problems early)

### Cost Impact: +1 LLM call (~$0.05) — negligible

---

## Phase 3B: Sequential Section Writing with Completion Gates (Days 12-14)

### What
Write sections ONE AT A TIME, verify each before starting the next.
Currently: write 4 sections in parallel per batch.

### Why (from TodoWrite pattern)
Claude Code enforces "exactly ONE task in_progress at a time" and
"ONLY mark completed when FULLY accomplished."
Parallel writing prevents cross-referencing and produces repetition.
Sequential writing with verification ensures each section is solid before moving on.

### How (Specific Code Changes)

**Step 1: Change PG_SECTION_WRITE_CONCURRENCY from 4 to 1**

This alone makes writing sequential. Each section sees covered_claims
from ALL previous sections (not just the previous batch).

**Step 2: Add per-section quality gate**

After each section is written, check:
- Word count >= 400 (minimum substantive content)
- Citation count >= 2 (minimum evidence grounding)
- No CoT markers in content
- No prompt echoes

If gate fails: retry once with fresh prompt. If still fails: log and continue.

**Step 3: Pass section summaries to subsequent section writers**

Currently: only covered_claims (statistics and cited sentences) passed forward.
New: also pass a 1-sentence summary of each completed section to give subsequent
writers context for cross-referencing.

### Estimated Effort: 3 days
- Day 1: Set concurrency to 1, add per-section quality gate
- Day 2: Build section summary passing
- Day 3: Test with pipeline run

### Dependencies: None (independent of Phase 2)

### Quality Impact: +2-3 points (better cross-referencing, catches bad sections early)

### Cost Impact: Slower (sequential vs parallel) but same total LLM calls

---

## Phase 4: Post-Write Adversarial Review (Days 15-17)

### What
After ALL sections are written, spawn a reviewer agent that reads the complete
report and finds specific problems.

### Why (from Verification Specialist pattern)
Claude Code's verification agent is explicitly adversarial: "Your job is not to
confirm the work. Your job is to BREAK it." Our current pipeline has no post-write
review — the report goes directly from section writing to assembly.

### How (Specific Code Changes)

**Step 1: Build review agent call after all sections are written**

```python
review_prompt = f"""You are reviewing a research report. Your job is to FIND PROBLEMS.

RESEARCH QUESTION: {query}

FULL REPORT:
{all_sections_concatenated}

Check for these SPECIFIC issues:
1. CITATION ACCURACY: Does each [CITE:ev_xxx] actually support the adjacent claim?
   Pick 5 random citations and verify.
2. CROSS-SECTION CONSISTENCY: Do any two sections make contradictory claims?
3. COMPLETENESS: Does the report answer ALL aspects of the research question?
4. NUMBERS: Are any statistics repeated across sections? Are any numbers suspicious?
5. GAPS: What important topic is NOT covered that should be?

For each problem found, state:
- Section title
- The specific problem
- How to fix it

Do NOT say "the report is good." Find problems or say "NO ISSUES FOUND."
"""
```

**Step 2: Apply targeted fixes**

For each problem found:
- Citation mismatch → remove the citation
- Contradictory claims → add a reconciliation sentence
- Missing topic → flag for human attention (can't add a section post-hoc)
- Repeated statistic → add cross-reference
- Gap → add to Key Findings as "limitation"

### Estimated Effort: 3 days
- Day 1: Build review agent
- Day 2: Build targeted fix application
- Day 3: Test with pipeline run

### Dependencies: Phase 3B (sequential writing produces better sections to review)

### Quality Impact: +2-3 points (catches cross-section issues)

### Cost Impact: +1-2 LLM calls (~$0.10-0.20)

---

## Phase 5: Modular Prompt Assembly (Days 18-20)

### What
Replace our monolithic section writer prompt with modular fragments that
assemble based on context (section topic, evidence type, position in report).

### Why (from 160+ fragment architecture)
Claude Code assembles its system prompt from 160+ conditional fragments.
Our section writer uses ONE prompt for all sections. A section about
"Safety and Contraindications" needs different analytical rules than
"Metabolic Mechanisms" or "Comparative Effectiveness."

### How

**Step 1: Create section-type-specific prompt fragments**

```
fragments/
  base_rules.md           — always included (citation format, GRADE, anti-hallucination)
  analytical_comparison.md — for sections comparing interventions
  safety_assessment.md     — for sections about risks/contraindications
  mechanism_explanation.md — for sections about biological mechanisms
  methodology_critique.md  — for sections about study quality
  clinical_guidance.md     — for sections about practical recommendations
```

**Step 2: Auto-detect section type from title/evidence**

```python
if any(kw in title.lower() for kw in ['compar', 'versus', 'vs']):
    fragments.append('analytical_comparison.md')
elif any(kw in title.lower() for kw in ['safety', 'risk', 'adverse', 'contraindication']):
    fragments.append('safety_assessment.md')
# ...
```

**Step 3: Assemble prompt per section**

Each section gets a TAILORED prompt instead of a one-size-fits-all prompt.
A safety section gets instructions about "contraindication severity levels"
while a mechanisms section gets instructions about "biological plausibility assessment."

### Estimated Effort: 3 days

### Dependencies: Phase 3B (sequential writing makes per-section prompts practical)

### Quality Impact: +1-2 points (more appropriate analysis per section type)

---

## Timeline and Quality Targets

| Phase | Days | Cumulative | Quality Target |
|-------|------|-----------|---------------|
| Current (v4 Phase 1) | Done | 0 | 75-80/100 (TEST_083) |
| Phase 2A: Read-then-plan | 1-4 | 4 | 80-82/100 |
| Phase 2B: Focused extraction | 5-8 | 8 | 82-84/100 |
| Phase 3A: Outline critique | 9-11 | 11 | 84-85/100 |
| Phase 3B: Sequential + gates | 12-14 | 14 | 85-87/100 |
| Phase 4: Post-write review | 15-17 | 17 | 87-88/100 |
| Phase 5: Modular prompts | 18-20 | 20 | 88-90/100 |

**The 85+ threshold (top-tier) is reached at Phase 3A — day 11.**

---

## Cost Budget Per Run

| Component | Current | After Phase 5 |
|-----------|---------|--------------|
| Search + fetch | $0.30 | $0.30 (unchanged) |
| Evidence extraction | $0.50 | $1.00 (focused per subtopic) |
| Verification | $0.40 | $0.40 (adversarial, same calls) |
| Deepener | $0.20 | $0.20 (unchanged) |
| Outline + critique | $0.10 | $0.20 (+critique agent) |
| Section writing | $0.80 | $1.00 (sequential, +summaries) |
| Post-write review | $0.00 | $0.15 (new) |
| **Total** | **$2.30** | **$3.25** |

Within the $8 budget guard. Each run costs ~$3.25, allowing 12 runs from $40 balance.

---

## What We're NOT Adopting (and Why)

| Pattern | Why Not |
|---------|---------|
| Dream memory consolidation | Over-engineering for batch pipeline. Our session log + restart instructions serve the same purpose. |
| ToolSearch deferred loading | Our evidence pool is fixed per run. Dynamic tool loading doesn't apply. |
| Fork/subagent cache sharing | OpenRouter doesn't support KV cache sharing across calls. Not applicable. |
| Security monitor classifier | We're a batch research pipeline, not an interactive coding agent. Risk taxonomy doesn't apply. |
| Coordinator never writes | Would require full multi-agent rewrite. The outline critique (Phase 3A) captures most of the benefit. |
| "Don't peek" fork isolation | We don't use forks. Sub-agent result handling is synchronous. |
| Skillify | Useful for interactive sessions, not for batch pipeline optimization. |

---

## Success Criteria

**Top-tier (85+/100) means:**
- D1 Factual Accuracy: 8+ (adversarial verifier + focused extraction)
- D2 Source Quality: 8+ (already 80% journal in TEST_082)
- D3 Comprehensiveness: 9+ (read-then-plan ensures coverage)
- D4 Analytical Depth: 8+ (focused extraction + modular prompts)
- D5 Citation Quality: 7+ (post-write review catches misattributions)
- D6 Structure: 8+ (outline critique + no polish/expansion damage)
- D7 Topical Focus: 9+ (already strong)
- D8 Limitations: 9+ (already strong)
- D9 Contradictions: 8+ (sequential writing + post-write review)
- D10 Applicability: 7+ (clinical guidance prompt fragment)

**Weighted: 8.2/10 = 82/100 at Phase 2B, 8.6/10 = 86/100 at Phase 4.**
