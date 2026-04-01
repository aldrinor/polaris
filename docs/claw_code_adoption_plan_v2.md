# Claw Code Adoption Plan v2: Path to Top-Tier Research Quality

## All Loopholes Incorporated

---

## Current State

TEST_080: 75.6/100 (B). TEST_082: 46.8/100 (polish damage + evidence starvation).
v4-simplify Phase 1 applied: polish disabled, expansion disabled, adversarial verifier,
150-char quote cap, over-removal guard, word cap, redundancy 0.65.

Projected TEST_083 (Phase 1 only): 75-80/100.

**The gap to top-tier (85+/100) comes from 4 root causes:**

| Root Cause | Impact | Claw Code Pattern That Fixes It |
|-----------|--------|-------------------------------|
| Outline planned before evidence is known | -5 pts | Read-then-plan (Plan Mode) |
| Generic evidence extraction (surface-level) | -4 pts | Focused sub-agent extraction (WebFetch summarizer) |
| No structural review before writing | -3 pts | Outline critique (ULTRAPLAN critique agent) |
| Verification rubber-stamp | -3 pts | Adversarial verifier (verification specialist) — DONE |

---

## Phase 2A: Read-Then-Plan (Days 1-5)

### What Changes
Reverse the pipeline: outline is DRIVEN by evidence, not by the query alone.

### Current Flow
```
LLM reads query → generates outline → searches for evidence to fill sections
```

### New Flow
```
Search broadly → cluster evidence by topic → summarize what EXISTS →
LLM reads evidence summaries + query → generates outline matching actual evidence
```

### Implementation

**Step 1: Evidence cluster summarization (new function in synthesizer.py)**

After all evidence is collected and verified, BEFORE outline generation:

```python
async def summarize_evidence_clusters(client, evidence, query):
    """Summarize what evidence actually exists, grouped by topic."""

    # Use existing clustering (already in synthesizer.py)
    clusters = cluster_evidence(evidence)  # embedding-based

    # For each cluster, generate a SPECIFIC summary
    summaries = []
    for cluster in clusters:
        items = cluster["evidence_items"]
        summary_prompt = f"""Summarize this group of {len(items)} evidence pieces in ONE sentence.
Include: count of studies, study types (RCT/meta-analysis/review),
specific measures reported (effect sizes, CIs), populations studied.

EVIDENCE:
{format_evidence_brief(items[:10])}

Output ONE sentence. Be specific with numbers. Example:
"8 RCTs and 3 meta-analyses reporting weight loss of -0.9 to -4.3 kg (MD, 95% CI)
in overweight/obese adults over 8-52 weeks."
"""
        resp = await client.generate(prompt=summary_prompt, max_tokens=500)
        summaries.append({
            "theme": cluster["theme"],
            "count": len(items),
            "evidence_ids": [e["evidence_id"] for e in items],
            "summary": resp.content.strip(),
        })

    return summaries
```

**Step 2: Evidence-driven outline prompt (modify outline generation)**

```python
outline_prompt = f"""Research question: {query}

AVAILABLE EVIDENCE (this is what you can actually write about):
{format_cluster_summaries(summaries)}

MANDATORY SECTIONS (must be included regardless of evidence count):
- At least one section addressing BENEFITS
- At least one section addressing RISKS/SAFETY
- At least one section addressing METHODOLOGY/EVIDENCE QUALITY

RULES:
- Create one section per evidence cluster that has 3+ pieces
- For clusters with < 3 evidence: merge into the closest related section
- Section titles must reflect the SPECIFIC evidence, not generic topics
  BAD: "Metabolic Health"
  GOOD: "Glycemic Control: HOMA-IR and HbA1c Improvements Across 12 RCTs"
- Maximum {max_sections} sections (adaptive: evidence_count // 5)
- Each section must have a realistic word target based on its evidence count
  (roughly 100 words per evidence piece)

Output a structured outline with section_id, title, description,
evidence_ids (from the cluster), and target_words.
"""
```

**Loophole fixes incorporated:**
- #1: Mandatory anchors (benefits, risks, methodology) regardless of evidence distribution
- #2: Cluster summaries include study types, effect sizes, populations (not just topic labels)
- #3: Mandatory minimum sections from query aspects even if evidence is thin

### Estimated Effort: 4 days + 1 bug fix day
### Quality Impact: +4-5 points
### Cost Impact: +$0.05 (cluster summaries: 5-10 short LLM calls)

---

## Phase 2B: Focused Evidence Re-Extraction (Days 6-10)

### What Changes
After the outline is set, re-extract evidence from TOP sources with FOCUSED questions
per section topic. Gets 3-5 DEEP facts per subtopic instead of 8 surface-level generic facts.

### Current Flow
```
Fetch 150 URLs → extract 8-15 generic facts each →
assign to sections by embedding similarity
```

### New Flow
```
Iteration 1: Fetch 150 URLs → extract generic facts → verify → cluster → outline
Iteration 2 (FOCUSED): For each section, take its top 10-15 sources →
re-extract with section-specific question → merge into evidence pool
```

### Implementation

**Step 1: Generate focused questions from outline**

```python
async def generate_section_questions(client, outline, query):
    """For each section, create 2-3 focused extraction questions."""

    questions = {}
    for section in outline.sections:
        q_prompt = f"""Research question: {query}
Section: {section.title}
Section description: {section.description}

Generate 2-3 SPECIFIC extraction questions that a researcher would ask
when reading a paper to find evidence for THIS section.

Example for "Glycemic Control: HOMA-IR and HbA1c Improvements":
1. "What specific HOMA-IR changes were measured? Report exact values, CIs, p-values."
2. "What HbA1c reductions were found? Compare IF vs control and IF vs CER."
3. "Were there differences in glycemic response by diabetes status or medication use?"

Output 2-3 questions, one per line. Be specific.
"""
        resp = await client.generate(prompt=q_prompt, max_tokens=500)
        questions[section.section_id] = resp.content.strip().split("\n")

    return questions
```

**Step 2: Focused re-extraction for top sources per section**

```python
async def focused_extraction(client, section, sources, questions):
    """Re-extract evidence from top sources with section-specific questions."""

    # Select top 10-15 sources for this section by relevance
    # (embedding similarity of source content to section title)
    top_sources = select_top_sources(sources, section.title, n=15)

    focused_evidence = []
    for source in top_sources:
        for question in questions[:3]:
            extract_prompt = f"""FOCUS: {question}

SOURCE CONTENT:
{source["content"][:25000]}

Extract 2-3 specific findings that answer this question.
Include EXACT numbers, confidence intervals, p-values, GRADE ratings.
Quote key phrases (max 150 characters per quote).
If the source does not address this question, output: NO_RELEVANT_FINDINGS

Output JSON: {{"findings": [{{"statement": "...", "direct_quote": "...", "confidence": 0.8}}]}}
"""
            resp = await client.generate_structured(
                prompt=extract_prompt, schema=FocusedExtractionResult,
                max_tokens=2000,
            )
            # ... process findings, assign evidence_ids, merge

    return focused_evidence
```

**Step 3: Merge focused evidence with generic evidence**

```python
# Dedup by evidence_id + source_url (not by statement similarity)
# Same fact from same source = duplicate (remove)
# Same fact from different sources = corroboration (keep both)
merged = dedup_by_source(generic_evidence + focused_evidence)
```

**Loophole fixes incorporated:**
- #4: Only top 10-15 sources per section, not all 50. 15 × 5 sections × 3 questions = 225 calls max, but most sources appear in multiple sections → effective ~75-100 calls = ~$1.50
- #5: Generic extraction kept for iteration 1 (verification needs it). Focused is ADDITIVE for synthesis depth.
- #6: Generic extraction preserved — surprising findings not lost
- #7: Dedup by source_url + evidence_id, not by statement similarity

### Estimated Effort: 4 days + 1 bug fix day
### Quality Impact: +3-4 points
### Cost Impact: +$1.00-1.50 (focused extraction calls)
### Test: Combined with Phase 2A (1 pipeline run validates both)

---

## Phase 3A: Outline Critique Agent (Days 11-13)

### What Changes
After outline generation, an adversarial critique agent reviews for structural
problems BEFORE any sections are written.

### Implementation

```python
async def critique_outline(client, outline, evidence_summaries, query):
    """Adversarial critique of report outline."""

    critique_prompt = f"""You are reviewing a research report outline.
Your job is to FIND PROBLEMS, not confirm quality.

RESEARCH QUESTION: {query}

OUTLINE:
{format_outline(outline)}

EVIDENCE AVAILABLE:
{format_summaries(evidence_summaries)}

Find SPECIFIC problems:
1. KEY ASPECTS MISSING: Does the query ask about topics with NO section?
   The query asks: "{query}"
   Check: are benefits covered? risks? safety? methodology? comparisons?

2. SECTION OVERLAP: Do any two sections cover the same topic?
   Name the specific sections and what overlaps.

3. EVIDENCE STARVATION: Any section with < 3 evidence pieces?
   Name it. Suggest: merge into which neighbor?

4. ORDERING: Is the flow logical for a reader?
   Should any section move earlier or later?

5. VAGUE TITLES: Any title too generic to guide focused analysis?
   Suggest a more specific title based on the evidence.

List ONLY problems found. Do NOT say "the outline looks good."
If genuinely no problems: output "NO ISSUES FOUND."
"""

    resp = await client.generate(prompt=critique_prompt, max_tokens=2000)
    issues = parse_critique(resp.content)

    if not issues or "NO ISSUES FOUND" in resp.content:
        return outline  # No changes needed

    # Apply SIMPLE adjustments only (no complex restructuring)
    adjusted = apply_adjustments(outline, issues)

    # Optional: second critique round
    if adjustments_made:
        resp2 = await client.generate(prompt=critique_prompt_v2, max_tokens=1000)
        # If still problematic after 2 rounds, accept and proceed

    return adjusted
```

**Adjustment types (simple only):**
- Reorder sections → swap positions in list
- Rename section → update title string
- Merge thin section → concatenate evidence_ids into neighbor, remove thin section
- Add missing section → create new section with evidence from unassigned pool

**NOT attempted:** Split oversized sections, restructure evidence assignments, change section descriptions.

**Loophole fixes incorporated:**
- #8: Adversarial prompt ("find problems, not confirm quality"). Different temperature for diversity.
- #9: Simple adjustments only. If critique finds major structural issues → regenerate outline entirely
- #10: Max 2 critique rounds. After 2, accept and proceed.

### Estimated Effort: 2 days + 1 bug fix day
### Quality Impact: +2-3 points
### Cost Impact: +$0.10-0.20 (1-2 critique calls)

---

## Phase 3B: Sequential Writing with Completion Gates (Days 14-17)

### What Changes
Write sections ONE AT A TIME. Each section is verified before the next starts.
Previous section summaries (not just covered_claims) are passed forward.

### Implementation

```python
# Change 1: Sequential concurrency
PG_SECTION_WRITE_CONCURRENCY = 1  # Was 4

# Change 2: Per-section quality gate
async def write_section_with_gate(client, section, evidence, context):
    draft = await write_section(client, section, evidence, context)

    # Quality gate
    wc = len(draft.content.split())
    cites = draft.content.count("[CITE:")
    has_cot = any(m in draft.content[:200].lower()
                  for m in ["the user", "let me", "analyze", "wait,"])

    # Relaxed gate for last 2 sections (conclusions, gaps)
    is_final = section.order >= total_sections - 1
    min_words = 300 if is_final else 400
    min_cites = 0 if is_final else 2

    if wc >= min_words and cites >= min_cites and not has_cot:
        return draft  # PASS

    # Retry once
    logger.warning("Quality gate failed for '%s' (%dw, %d cites, CoT=%s). Retrying.",
                    section.title, wc, cites, has_cot)
    draft2 = await write_section(client, section, evidence, context)
    return draft2  # Accept regardless (don't loop)

# Change 3: Section summaries passed forward
section_summaries = []
for section in outline.sections:
    context = {
        "covered_claims": covered_claims[-20:],  # Cap at 20 most recent (#12)
        "previous_summaries": section_summaries[-5:],  # Last 5 section summaries
    }

    draft = await write_section_with_gate(client, section, evidence, context)

    # Generate 1-sentence summary for next section's context
    summary = f"{section.title}: {extract_key_finding(draft.content)}"
    section_summaries.append(summary)

    # Update covered claims
    covered_claims.extend(extract_statistics(draft.content))
    covered_claims.extend(extract_cited_sentences(draft.content))
```

**Loophole fixes incorporated:**
- #11: Accept 4x slowdown. Quality > speed. Pipeline ~150 min total.
- #12: Cap covered_claims at 20 most recent statistics + 10 claims. Not full history.
- #13: Relaxed gate for last 2 sections (300w minimum, 0 citations OK).

### Estimated Effort: 3 days + 1 bug fix day
### Quality Impact: +2-3 points
### Cost Impact: Same LLM calls, just sequential. +$0.05 for summary generation.
### Test: Combined with Phase 3A (1 pipeline run validates both)

---

## Phase 4: Post-Write Adversarial Review (Days 18-21)

### What Changes
After ALL sections are written, a reviewer agent examines the complete report
SECTION BY SECTION (not full report at once — avoids "lost in the middle").
Reports problems. Does NOT rewrite.

### Implementation

```python
async def review_report(client, sections, evidence_pool, query):
    """Section-by-section adversarial review."""

    all_issues = []

    for section in sections:
        # Build evidence context for this section
        section_evidence = [
            e for e in evidence_pool
            if e["evidence_id"] in section.get("evidence_ids", [])
        ]

        review_prompt = f"""You are reviewing ONE section of a research report.
Your job is to FIND PROBLEMS, not confirm quality.

RESEARCH QUESTION: {query}

SECTION TITLE: {section["title"]}
SECTION CONTENT:
{section["content"]}

EVIDENCE AVAILABLE FOR THIS SECTION:
{format_evidence_for_review(section_evidence)}

Check for these SPECIFIC issues:

1. CITATION ACCURACY: For each [N] citation in the text, check if the
   evidence it references actually supports the adjacent claim.
   Compare the claim text with the evidence statement WORD BY WORD.

2. UNSUPPORTED CLAIMS: Any factual claim (number, comparison, causation)
   without a citation? Quote the specific sentence.

3. NUMBERS MATCH: Do the numbers in the text match the evidence exactly?
   "4.3 kg" in text vs "4.30 kg" in evidence is OK.
   "4.3 kg" in text vs "4.3%" in evidence is a MISMATCH.

4. OVERCLAIMING: Does the text make stronger claims than the evidence supports?
   Evidence says "associated with" but text says "causes"?

5. GAPS: Given the evidence available, what important finding is NOT discussed?

For each problem:
- Severity: CRITICAL (must fix) or ADVISORY (human should review)
- Location: exact quote from the section
- Problem: what's wrong
- Fix: specific suggestion

If no problems: output "NO ISSUES IN THIS SECTION."
"""
        resp = await client.generate(prompt=review_prompt, max_tokens=2000)
        issues = parse_review_issues(resp.content, section["section_id"])
        all_issues.extend(issues)

    return all_issues

async def apply_critical_fixes(sections, issues):
    """Apply ONLY critical fixes using regex/string operations, NOT LLM."""

    for issue in issues:
        if issue["severity"] != "CRITICAL":
            continue

        section = find_section(sections, issue["section_id"])

        if issue["type"] == "citation_mismatch":
            # Remove the specific citation marker
            section["content"] = remove_citation(section["content"], issue["citation"])

        elif issue["type"] == "overclaiming":
            # Soften the specific verb: "causes" → "is associated with"
            section["content"] = section["content"].replace(
                issue["original"], issue["suggested"]
            )

        # Do NOT use LLM for edits — that's what caused polish pass CoT (#16)

    return sections
```

**Loophole fixes incorporated:**
- #14: Section-by-section review, not full report at once. Avoids "lost in the middle."
- #15: Evidence pool passed to reviewer for each section. Can verify citations against actual evidence.
- #16: Critical fixes applied via regex/string operations, NOT LLM calls. No CoT risk.
- #17: CRITICAL vs ADVISORY severity. Only CRITICAL gets auto-fixed. ADVISORY logged for human review.

### Estimated Effort: 3 days + 1 bug fix day
### Quality Impact: +2-3 points
### Cost Impact: +$0.10-0.20 (1 review call per section, ~10 sections)
### Test: Combined with Phase 5 (1 pipeline run validates both)

---

## Phase 5: Modular Prompt Assembly (Days 22-25)

### What Changes
Section writer uses TAILORED prompts based on evidence type, not a one-size-fits-all prompt.

### Implementation

**Step 1: Detect section type from EVIDENCE, not title (#18)**

```python
def detect_section_type(evidence_items):
    """Classify section based on evidence characteristics."""

    has_effect_sizes = any("MD " in e["statement"] or "SMD " in e["statement"]
                          or "95% CI" in e["statement"] for e in evidence_items)
    has_safety = any(kw in e["statement"].lower()
                     for e in evidence_items
                     for kw in ["adverse", "risk", "contraindic", "safety", "harm"])
    has_mechanism = any(kw in e["statement"].lower()
                       for e in evidence_items
                       for kw in ["mechanism", "pathway", "autophagy", "signaling", "mTOR"])
    has_methodology = any(kw in e["statement"].lower()
                         for e in evidence_items
                         for kw in ["meta-analysis", "systematic review", "GRADE", "RCT",
                                     "sample size", "heterogeneity"])
    has_comparison = any(kw in e["statement"].lower()
                        for e in evidence_items
                        for kw in ["compared", "versus", "superior", "equivalent", "non-inferior"])

    if has_safety: return "safety"
    if has_comparison and has_effect_sizes: return "comparison"
    if has_mechanism: return "mechanism"
    if has_methodology: return "methodology"
    if has_effect_sizes: return "clinical_outcomes"
    return "general"
```

**Step 2: Load section-type-specific fragment (EXCLUSIVE — one per section, #19)**

```
config/prompts/
  base_rules.md              — always included (citations, GRADE, anti-hallucination)
  fragment_comparison.md     — for sections comparing interventions
  fragment_safety.md         — for sections about risks/contraindications
  fragment_mechanism.md      — for sections about biological mechanisms
  fragment_methodology.md    — for sections about study quality/limitations
  fragment_clinical.md       — for sections about clinical outcomes
  fragment_general.md        — fallback for unclassified sections
```

Each fragment is MAX 300 tokens to stay within budget (#19).

Example `fragment_comparison.md`:
```
COMPARISON SECTION RULES:
- Present BOTH interventions with equal depth. Do not favor one.
- Include a comparison TABLE with: intervention, effect size, CI, certainty.
- State whether differences are clinically meaningful, not just statistically significant.
- If equivalence: state clearly and explain clinical implications of equivalence.
- Use "whereas", "in contrast", "compared to" for explicit comparison language.
```

Example `fragment_safety.md`:
```
SAFETY SECTION RULES:
- Classify adverse effects by: frequency (common/uncommon/rare), severity (mild/moderate/serious), temporality (transient/persistent).
- List ABSOLUTE contraindications first, then RELATIVE contraindications.
- For each contraindication, state the MECHANISM of harm, not just "is contraindicated."
- Include a risk-stratification table by population.
- State what monitoring is recommended for each risk.
```

**Step 3: Assemble per-section prompt**

```python
def build_section_prompt(section, evidence, section_type):
    base = load_fragment("base_rules.md")
    specific = load_fragment(f"fragment_{section_type}.md")

    return f"""{base}

{specific}

SECTION TITLE: {section.title}
EVIDENCE:
{format_evidence(evidence)}

Write this section."""
```

### Estimated Effort: 3 days + 1 bug fix day
### Quality Impact: +1-2 points
### Cost Impact: Negligible (same LLM calls, slightly different prompts)
### Test: Combined with Phase 4 (1 pipeline run validates both)

---

## Cross-Phase Design Decisions

### Evidence per section cap (#20)
Regardless of how many focused extractions we do, the section writer receives
MAX 10 evidence pieces. Selected by: tier (GOLD > SILVER > BRONZE) then
relevance score (descending). More extraction = better TOP 10, not more in prompt.

### Test-per-phase strategy (#21, #22)
- After Phase 2A+2B: TEST_084 (validates read-then-plan + focused extraction)
- After Phase 3A+3B: TEST_085 (validates critique + sequential writing)
- After Phase 4+5: TEST_086 (validates review + modular prompts)
- Total: 3 validation runs × $3.25 = $9.75

### Adversarial verifier + over-removal guard interaction (#23)
The guard ALWAYS wins. When adversarial verifier marks >60% as NOT_SUPPORTED:
1. Guard activates: all evidence kept, unfaithful ones marked
2. Section writer receives ALL evidence but sees `is_faithful=False` flag
3. Writer prompt: "Prioritize evidence marked as faithful. You may use
   unfaithful evidence for context but do not cite it as primary support."

### Deepener ROI (#24)
Phase 2B (focused extraction) partially addresses this: deeper extraction
from the same sources the deepener found. If deepener papers are in the
content cache (FIX-B5), focused extraction gets real content, not stubs.
If ROI stays < 5% after Phase 2B, consider disabling deepener to save time.

### Realistic timeline (#25)
4 + 4 + 3 + 3 + 3 = 17 implementation days + 8 bug fix days = 25 days.
Plus 3 test runs (1 day each) = 28 days total.

### Run-to-run variance (#26)
Evaluate on 2 runs minimum for Phase 2A+2B (the biggest architectural change).
Phases 3-5 need 1 run each (smaller changes, lower variance risk).
Total: 4 validation runs × $3.25 = $13.

---

## Budget

| Item | Cost |
|------|------|
| Remaining balance | $40.00 |
| Already spent (TEST_082) | -$1.72 |
| TEST_083 (Phase 1 baseline) | -$2.50 |
| TEST_084 (Phase 2A+2B) | -$3.50 |
| TEST_084b (Phase 2 variance check) | -$3.50 |
| TEST_085 (Phase 3A+3B) | -$3.25 |
| TEST_086 (Phase 4+5) | -$3.25 |
| Development testing (~5 smoke tests) | -$0.50 |
| **Remaining** | **~$21.78** |

Enough for 6-7 more production runs after all phases.

---

## Quality Trajectory

| Milestone | Score | Key Improvement |
|-----------|-------|----------------|
| TEST_083 (Phase 1) | 75-80 | Polish/expansion damage removed, adversarial verifier |
| TEST_084 (Phase 2) | 80-84 | Evidence-driven outline, focused extraction depth |
| TEST_085 (Phase 3) | 84-87 | Structural critique, sequential coherence |
| TEST_086 (Phase 4+5) | 87-90 | Cross-section review, tailored analytical prompts |

**Top-tier (85+) reached at TEST_085 — Phase 3.**

---

## Decision: What to Build First

Option A: Run TEST_083 first (Phase 1 baseline), then Phase 2A.
- Pro: Validates current fixes, establishes baseline.
- Con: Costs $2.50 + 2 hours before new quality improvements.

Option B: Build Phase 2A, then run TEST_084 (skipping Phase 1 baseline).
- Pro: Faster path to quality improvement.
- Con: If TEST_084 scores lower, unclear whether Phase 2A hurt or Phase 1 fixes helped.

Option C: Build Phase 2A + 2B together, then run TEST_084.
- Pro: Maximum quality jump in one run. Best use of the $3.50 run cost.
- Con: If something breaks, harder to debug which phase caused it.

**Recommendation: Option A.** Run TEST_083 to validate Phase 1, then build Phase 2A+2B.
Each $2.50 run teaches us something. Skipping baseline risks building on wrong assumptions.
