# V4 Simplification Plan

## Principle
One clean generation pass > messy generation + 6 correction passes.
The intelligence is in the prompt and the evidence, not the post-processing.

## Phase 1: Foundation Reset (Day 1-2)

### 1.1 Switch back to Qwen 3.5 Plus
- No CoT leakage (no always-reason architecture)
- Clean content/reasoning separation native
- Excellent structured output (JSON schema)
- Remove ALL GLM-5 workarounds:
  - `_ALWAYS_REASON_MODELS` frozenset
  - Two-pool architecture (not needed for Qwen)
  - Min token floor (not needed)
  - COT-1/COT-2/COT-3 fallback paths
  - FIX-GLM5-COT stripping
  - `_PosHolder` class
  - Temperature forcing
- **Estimated lines removed: ~300**

### 1.2 Remove damaging post-processors
Already disabled, now DELETE the dead code:
- `_soften_uncited_numerics()` — destroyed precise numbers
- FIX-R1 unit correction — broke 3/4 times
- MoST (cross_section_reflector, evidence_explorer, all MoST modules)
- Expansion pass — injected CoT, prompt echoes, broken tables
- Polish pass — compressed content 29%, rejected 40% of edits
- Redundancy removal — emptied 5 sections in TEST_076
- Transition stripping — removed useful logical connectors
- **Estimated lines removed: ~2000**

### 1.3 Keep what works
- Config-based domain lists (YAML loader)
- B1 embedding citation check
- Starvation rescue (embedding + keyword)
- Adaptive section cap (evidence // 5)
- Meta-commentary scrubber (defense-in-depth, keep but simplify)
- Evidence deepener (citation chasing, mechanism search)
- Two-iteration pipeline (search → analyze → verify → deepen → iterate → synthesize)
- GRADE ratings in prompts
- SO WHAT analytical rules

## Phase 2: Evidence Depth (Day 3-5)

### 2.1 Reduce search breadth, increase fetch depth
- Current: 50 queries → 200+ URLs → snippets for all
- New: 20 targeted queries → 50 best URLs → full text for top 20
- Change PG_QUERIES_PER_VECTOR from 50 to 20
- Change PG_MAX_SOURCES_TO_ANALYZE from 300 to 50
- Increase content cap: PG_CONTENT_PER_SOURCE from 25000 to 50000
- More time per source = better evidence extraction

### 2.2 Sub-agent evidence gathering (design)
- Query decomposition: break query into 4-6 subtopics
- Parallel sub-agents per subtopic, each with:
  - Fresh context window
  - Focused search queries (5 per subtopic)
  - Independent evidence extraction
  - Returns 10-15 evidence pieces
- Merge: combine, deduplicate, quality score
- This is the biggest architectural change — design first, implement in Phase 3

### 2.3 Improve deepener ROI
- Current: 38 papers found, 2 evidence extracted (2.3% ROI)
- Root cause: most S2 papers are behind paywalls
- Fix: prefer open-access papers (filter by openAccessPdf before chasing)
- Fix: use deepener full_text directly as evidence (not re-analyze through pipeline)
- Fix: reduce deepener paper count, increase per-paper depth

## Phase 3: Section Writing Quality (Day 6-8)

### 3.1 Increase section writer token budget
- Current: PG_SECTION_WRITER_MAX_TOKENS = 16384
- New: 32768 (Qwen supports 65K output)
- More budget = deeper analysis per section

### 3.2 One pass, no correction
- Section writer generates final content in ONE call
- No expansion, no polish, no redundancy removal
- Quality comes from: good evidence + good prompt + sufficient tokens
- If a section is thin, it's because evidence is thin — fix evidence, not post-processing

### 3.3 Cross-reference via prompt, not code
- Instead of MoST cross-section reflector, add to section writer prompt:
  "When referencing findings from other sections, use 'as established in [Section Title]'"
- The LLM handles cross-references naturally when the outline is visible

### 3.4 Table formatting via prompt, not regex
- Instead of 7 table-fixing regex patterns, add to prompt:
  "Format all tables with proper markdown: one row per line, header separator with |---|"
- If Qwen produces clean tables (it usually does), the regex is unnecessary

## Phase 4: Verification (Day 9-10)

### 4.1 Keep NLI verification
- MiniCheck flan-t5-large on CUDA for faithfulness
- LLM fallback when NLI below floor
- Per-claim NLI score preservation

### 4.2 Add post-write review (new)
- After ALL sections written, spawn a reviewer sub-agent
- Reviewer reads the complete report + evidence pool
- Checks: citation accuracy, cross-section consistency, completeness
- Returns: list of specific issues (not a score)
- Main agent fixes specific issues (targeted, not full rewrite)

### 4.3 Manifest-based completion verification
- Before synthesis: create manifest of expected sections + key topics
- After synthesis: reconcile manifest against actual output
- Log gaps explicitly

## Phase 5: Operational Discipline (Ongoing)

### 5.1 Ralph Loop
- One task → test → commit → clear → next
- Never marathon sessions
- Maximum 3 fix iterations before clear

### 5.2 TaskCreate mandatory for multi-step work
- Anthropic data: doubles completion rate
- Every multi-file or multi-issue task starts with numbered manifest

### 5.3 Confidence labels
- TESTED: verified with real data
- UNTESTED: code change only
- STRUCTURAL: requires pipeline run
- Every STATUS block includes confidence

## Metrics to Track

| Metric | Current (TEST_080) | Target (v4) |
|--------|-------------------|-------------|
| Words | 13,786 (post-polish) | 12,000-15,000 (one pass) |
| Citations | 122 | 100+ |
| Sources | 43 | 30+ (fewer but deeper) |
| Sections | 14 | 10-12 (adaptive cap) |
| Faithfulness | 75.9% real | 80%+ real |
| CoT lines | 0 (after fixes) | 0 (no fixes needed) |
| Empty sections | 0 (after fixes) | 0 (no fixes needed) |
| Broken tables | 2 (after fixes) | 0 (no fixes needed) |
| Pipeline time | 244 min | 90-120 min |
| Pipeline cost | $2.81 | $1.50-2.00 |
| Post-processors | 8 (most disabled) | 2 (scrub + citation map) |
| Lines of synthesis code | ~8000 | ~3000 |

## What This Achieves

By removing 60% of the synthesis code and switching to a model that doesn't fight us, we get:
1. Faster pipeline (no MoST, no polish, no expansion, no CoT defense)
2. Cleaner output (one generation pass, no post-processing damage)
3. Easier debugging (less code = fewer places to break)
4. More time budget for evidence depth (saved from post-processing)
5. Foundation for sub-agent architecture (Phase 2.2)

## What This Won't Achieve

- Gemini-level model quality (Qwen 3.5 Plus is ~80% of Gemini 2.5 Pro)
- Perfect citation accuracy (model-level limitation)
- 100% source depth (paywall barrier)
- The last 15-20% gap requires either a stronger model or breakthrough in evidence access
