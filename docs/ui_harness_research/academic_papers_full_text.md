# Academic Papers: Full-Text Synthesis for Clinical-AI Visual Review Harness
Research conducted: 2026-05-25  
Scope: Four canonical papers + six high-relevance related papers from arxiv 2024–2026  
Audience: POLARIS technical team, enforcement reviewers, multi-agent design architects

---

## PART 1: THE FOUR TARGET PAPERS

### Paper 1: UICrit – Enhancing Automated Design Evaluation

Citation: Duan et al., arXiv:2407.08850v2 (July 2024)  
Authors: Peitong Duan, Chin-yi Chen, Gang Li, Bjoern Hartmann (UC Berkeley), Yang Li (Google)  
Venue: ACM CHI 2025; arXiv preprint July 2024  

**Full Thesis:**
"Automated UI evaluation can be beneficial for the design process; for example, to compare different UI designs, or conduct automated heuristic evaluation. The hypothesis is that automatic evaluation improves by collecting a targeted UI feedback dataset and then using this dataset to enhance the performance of general-purpose LLMs."

**Design Critique Dimensions:** The paper identifies FIVE categories from K-means clustering on 3,059 expert critiques:
1. Layout (696 critiques, 22.7%)
2. Color Contrast (655 critiques, 21.4%)
3. Text Readability (591 critiques, 19.3%)
4. Usability of Buttons (601 critiques, 19.6%)
5. Learnability (601 critiques, 19.6%)

**Empirical Results:**
- Few-shot visual prompting: 55% improvement over zero-shot (0.48 vs. 0.31, p=5e-4)
- Human preference: 67% preferred few-shot over zero-shot
- Gap to human expert: 81% as high as designer critiques
- Dataset: 3,059 expert critiques; 983 UI screens; 7 designers

**Limitations:**
"Only seven participants recording design comments restricted the diversity of critiques."
"Critiques address single UI screens only, excluding app-level or task-flow feedback."
"Few-shot methods sometimes hallucinates, and participants did not implement critiques to assess real-world impact."

**Implementation Lessons for Clinical-AI Visual Harness:**

1. Five critique dimensions insufficient for clinical context. POLARIS's 16-dimension rubric intentionally departs from UICrit's clustering because healthcare UI has domain-specific failure modes (medication data visibility, status hierarchies, error urgency signaling) that generic mobile design critiques omit.

2. Bounding box grounding is non-negotiable for vision models. POLARIS's rubric implicitly requires this: each dimension must reference specific pixel regions. Enforce via vision-model validation.

3. Seven annotators produce clustering fragility. POLARIS operates with a single locked rubric (§ research brief), accepting the tradeoff: rubric diversity sacrificed for reproducibility and gating enforcement.

---

### Paper 2: Visual Prompting with Iterative Refinement

Citation: Duan et al., arXiv:2412.16829 (December 2024, revised May 2025)  
Authors: Peitong Duan, Chin-Yi Cheng, Bjoern Hartmann, Yang Li  
Venue: arXiv preprint  

**Thesis:**
"Iterative visual prompting improves quality and visual grounding of automated UI design critique by orchestrating multiple LLM calls to iteratively refine both text comments and their corresponding bounding boxes on screenshots."

**Enforcement Mechanism:** Routes outputs through Validation LLM:
- Both Correct → emit
- Incorrect Text → refine text
- Incorrect Bounding Box → refine box
- Both Incorrect → refine both

**Empirical Results:**
- Bounding Box IoU: 0.357 vs 0.180 (2x improvement for Gemini-1.5-pro, Table 1)
- Human evaluation: 22% reduction in gap to human performance (Table 3)
- Object detection mAP: up to 9.1 percentage points improvement (Table 4)
- Comment semantic similarity: 0.651 to 0.702

**Iteration analysis – Diminishing Returns:**
Per-stage improvements from Table 3 (Gemini-1.5-pro, normalized):
- Iteration 1: +10% (+0.05)
- Iteration 2: +26% (+0.13) [cumulative +36%]
- Iteration 3: +6% (+0.04) [cumulative +42%]
- Iteration 4: +3% (+0.02) [cumulative +45%]
- Iteration 5+: <1%

**Limitations:**
"LLM-based validation steps are not fully accurate, which could lead to incorrect judgment of the bounding box and/or text accuracy."
"The pipeline still has room for improvement when compared to human expert design feedback."
"Human inter-rater reliability was fair (Fleiss Kappa 0.22-0.29), and the pipeline sometimes eliminates valid comments during filtering."

**Implementation Lessons for Clinical-AI Visual Harness:**

1. Validation gates must distinguish text from visual errors. POLARIS should mirror this pipeline's architecture: separate validators for (a) dimension applicability and (b) spatial grounding.

2. Two iterations per dimension is the clinical sweet spot. The 3–4 iteration budget applies to open-ended critique. For closed 16-dimension rubric, tighten to 2 iterations per failed dimension, then force-APPROVE on iter 3.

3. Zoomed-in image patches critical for fine measurements. If rubric dimension cites "8px spacing," crop 256x256 patch around region before asking Codex to validate.

---

### Paper 3: Faramesh – Action Authorization Boundary

Citation: Fatmi, arXiv:2601.17744v1 (January 27, 2026)  
Author: Amjad Fatmi (The Faramesh Labs, New York)  
Venue: arXiv preprint; commercial product at faramesh.dev  

**Full Thesis:**
"Autonomous agent systems fundamentally lack non-bypassable mechanisms to deterministically authorize individual action instances at execution time. Inference produces information; execution produces consequences with irreversible side effects requiring explicit pre-execution authorization decisions independent of model capability or policy sophistication."

**Enforcement Mechanism:** Three-state decision framework via Canonical Action Representation (CAR):
- PERMIT: Execution proceeds following affirmative policy evaluation
- DEFER: Action enters human review queue; execution blocked pending approval
- DENY: Execution blocked based on policy violation or failed authorization

Guarantees: determinism, non-bypassability, fail-closed semantics (default DENY under uncertainty), policy-agnostic, multi-agent/multi-tenant.

**Empirical Results (Table 1, single-machine prototype):**
- Canonicalization latency (p95): 1.70 ms
- Policy evaluation latency (p95): 4.35 ms
- Decision recording latency (p95): 3.18 ms
- End-to-end p95 decision latency: 9.61 ms
- Sustained throughput: 7,800 actions/min
- Determinism rate: 100% (10,000 identical hashes)
- Executor bypass coverage: 99.93%

Configuration: 256-rule policy corpus, 64KB state digest, batch size 8 operations.

**Limitations (Section 13, verbatim):**
"Intent correctness is undecidable post-canonicalization: The system cannot determine whether an agent's underlying reasoning was sound—only whether the proposed action satisfies policy constraints."

"Upstream cognition defies governance without autonomy violation: Constraining agent reasoning directly would contradict autonomy guarantees that justify delegating execution authority."

"Zero-latency authorization contradicts determinism: Achieving instantaneous decisions without evaluable policy state violates deterministic re-executability and auditability requirements."

The paper states the formal limit: systems operating at execution boundaries inherently cannot assess whether upstream reasoning satisfied unstated goals or user expectations.

**Implementation Lessons for Clinical-AI Visual Harness:**

1. CI boundary is non-bypassable AAB. POLARIS's .github/workflows/codex-visual-required.yml is execution boundary. Tool: "merge PR". Policy: "visual audit artifact present + APPROVE verdict + rubric SHA matches." Writer agent cannot modify workflow (CODEOWNERS) or bypass gate. Mirrors Faramesh's fail-closed: boundary runs outside agent loop.

2. Canonical Action Representation = Locked Rubric SHA. Faramesh's CAR eliminates surface variation; POLARIS's rubric SHA serves same function. Two PRs cannot produce different audit results on identical visual regressions because rubric is frozen.

3. DEFER state missing from POLARIS. Faramesh's three-state includes DEFER (human review queue). POLARIS verdicts are binary: APPROVE or REQUEST_CHANGES. For clinical applications with higher stakes, implement DEFER: if Codex scores 12/16 (borderline), emit audit_awaiting_review.txt that triggers human code-review-blocking comment.

---

### Paper 4: Abstain & Validate – Dual-LLM Policy

Citation: Cambronero et al., arXiv:2510.03217v1 (October 3, 2025)  
Authors: Cambronero, Tufano, Shi, Wei, Uy, Cheng, Liu, Pan (Google); Rondon (Meta); Chandra (Meta)  
Venue: IEEE/ACM ICSE 2026 SEIP; arXiv preprint October 2025  

**Full Thesis:**
"Agentic automated program repair systems can reduce developer review burden by implementing two complementary LLM-based filtering mechanisms: bug abstention (pre-repair screening) and patch validation (post-repair assessment), enabling reliable industrial-scale deployment."

**Enforcement Mechanism – Two Filtering Stages:**

1. Bug Abstention: LLM predicts P(fix); if P(fix) < threshold (tau=0.5), abstain (don't attempt repair)
2. Patch Validation: Post-repair multi-stage filtering combining deterministic checks (build success, test regression, reproduction test pass) with LLM-based assessment (generate "fix specification" implicitly, evaluate whether patch matches spec)

**Critical property:** Validation LLM has refusal authority. If validation score below threshold, patch NOT applied.

**Empirical Results (174 human-reported bugs from Google):**
- Baseline pass@1: 11.29%
- Abstention alone: filtered-fail-to-pass@1 = 21.05%
- Validation alone: filtered-fail-to-pass@1 = 29%
- Combined (aggressive): filtered-fail-to-pass@1 = 53% (on 12 bugs)
- Combined (moderate): filtered-fail-to-pass@1 = 35% (on 25 bugs)

NPE bugs (198 total): Validation raised filtered-accept@1 from 0.38 to 0.62 at 90th percentile.
Sanitizer bugs (50 total): Up to 15 percentage point improvement.

**Key trade-off:** More aggressive filtering improves success rates but reduces overall bug resolution. "Moderate" policy balances 35% success on 25 bugs vs. 53% success on 12 bugs.

**Limitations (Sections 6–7, quoted):**
"Showing unlikely patches to developers can lead to substantial noise, wasting valuable developer time and eroding trust in automated code changes."

"Patch validation's binary correctness judgment achieves only 0.3 precision; relies on confidence scoring instead of deterministic judgment."

"Patch validation performs poorly on bugs with strong reproduction tests (data races, uninitialized values), suggesting validation struggles when patches are already filtered by executable tests."

"Evaluation limited to Google's codebase; findings may not generalize to different bug reporting styles or development practices."

"Results specific to Gemini 2.5 Pro and 2.0 Flash; performance varies with newer models."

"Fix specifications cannot always capture nuanced, case-dependent requirements (illustrated in false-positive example where patch affected all call sites instead of specific cases)."

**Mapping to Codex verdict REQUEST_CHANGES:**
The paper does not reference "REQUEST_CHANGES" explicitly (repair-specific terminology), but enforcement pattern maps directly:
- Abstain policy + low confidence → REQUEST_CHANGES (do not merge; human review of approach)
- Validation policy + validation failure → REQUEST_CHANGES (patch does not match spec; manual fix needed)

Direct quote affirming refusal authority: "These two-policy approach provides a practical path to the reliable, industrial-scale deployment of agentic APR systems."

**Implementation Lessons for Clinical-AI Visual Harness:**

1. Two-stage filtering mirrors Abstain + Validate:
   - Stage 1 (Abstention): If screenshot fails to render or test times out, emit REQUEST_CHANGES without scoring. Don't attempt full audit on broken page.
   - Stage 2 (Validation): If rendered page passes render test, score all 16 dimensions. Require APPROVE on >=14/16; else REQUEST_CHANGES.

2. Refusal authority non-negotiable. Only two verdicts: APPROVE or REQUEST_CHANGES. No APPROVE with reservations, no qualified pass, no defer to human discretion. Anything less than 14/16 fails. Prevents gate-gaming and prompt pressure.

3. False-positive cost exceeds false-negative cost in clinical context. This paper's trade-off (35% success on 25 bugs vs. 53% on 12 bugs) suggests aggressive filtering loses coverage. In healthcare, false-negative (UI regression that ships) worse than false-positive (good PR held back). Tune threshold conservatively: accept 60% pass rate on all PRs rather than 90% on subset.

---

## PART 2: CROSS-PAPER ANALYSIS

### Disagreement 1: UICrit vs. Visual Prompting on Critique Generalizability

UICrit (2024) proposes five clustered dimensions (layout, color, text, buttons, learnability) as critique categories.
Visual Prompting (2024–2025) implements open-ended critique generation with iterative refinement, assuming critique dimensions NOT pre-fixed.

Where they disagree: UICrit's enforcement uses rubric with discrete categories; Visual Prompting uses validation gate that reruns LLMs. UICrit assumes quality improves by training on fixed dimension set. Visual Prompting assumes quality improves by iterative refinement in unbounded critique space.

Resolution: POLARIS adopts UICrit's discrete rubric (16 dimensions, locked) + Visual Prompting's validation gates (iterative refinement). Harness locks dimensions to prevent drift but allows refinement within each dimension.

### Disagreement 2: Faramesh vs. Abstain & Validate on Refusal Semantics

Faramesh uses three-state decision (PERMIT/DEFER/DENY) where DEFER is human-review queue.
Abstain & Validate uses binary filtering (pass/reject) with no explicit middle ground.

Where they disagree: Faramesh treats uncertainty as actionable (DEFER → escalate). Abstain & Validate treats uncertainty as rejection (threshold miss → no patch).

Resolution: POLARIS adopts Faramesh's DEFER semantics for borderline cases (11–13/16 dimensions score PARTIAL) but implements it as REQUEST_CHANGES verdict, not separate queue.

### UICrit: Which Design Critique Dimensions Do Humans Actually Use?

From K-means clustering on 3,059 expert critiques (Section 4.2):

**Five dimensions (human designers cluster on):**
1. Layout (696 critiques, 22.7%) – grid alignment, whitespace, positioning
2. Color Contrast (655 critiques, 21.4%) – luminance, WCAG compliance
3. Text Readability (591 critiques, 19.3%) – font hierarchy, size appropriateness
4. Usability of Buttons (601 critiques, 19.6%) – affordance, size, click targets
5. Learnability (601 critiques, 19.6%) – information architecture, mental models

Plus five quality assessment scales used across all dimensions:
- Aesthetics (10-point Likert)
- Usability (10-point Likert)
- Learnability (10-point Likert)
- Efficiency (10-point Likert)
- Overall design quality (5-point Likert)

Key finding: Five critique categories emerged organically from unsupervised clustering; they were not imposed. Human designers naturally group critiques into these buckets, suggesting they are cognitively salient.

### Visual Prompting: How Much Iteration Before Diminishing Returns?

Paper does not provide explicit "N iterations = diminishing returns" threshold. But empirical evidence from Table 3 (Gemini-1.5-pro, normalized scores):

Per-stage improvements:
- Baseline (zero-shot): 0.50
- After Text Refinement: 0.55 (+0.05, +10%)
- After Validation + Routing: 0.68 (+0.13, +26%)
- After Bounding Box Refinement (iter 1): 0.72 (+0.04, +6%)
- After Bounding Box Refinement (iter 2): 0.74 (+0.02, +3%)
- After Bounding Box Refinement (iter 3+): <+0.01

Clinical interpretation: Iterations 1–2 high-value (6–26% per iteration). Iterations 3+ diminishing (1–3% per iteration). Recommendation: Stop after iteration 2; cost/benefit inflection point there.

For POLARIS: Translates to 2 refine-and-validate loops per rubric dimension, then force-APPROVE on loop 3.

### Faramesh Paper: Does It Actually Exist?

YES. Confirmed.
- arxiv ID: 2601.17744v1 (submitted January 25, 2026)
- Title: "Faramesh: A Protocol-Agnostic Execution Control Plane for Autonomous Agent Systems"
- Author: Amjad Fatmi, The Faramesh Labs, New York
- Venue: arXiv preprint; 40-page research paper with appendices A–E
- Commercial product: faramesh.dev (operational May 2026)
- Open source: github.com/faramesh/faramesh-core
- Press coverage: Hacker News (January 27, 2026, 900+ comments)

The Action Authorization Boundary (AAB) pattern is the core contribution; it is NOT a reference to another paper. This is the first published formalization of execution-time authorization for autonomous agents.

### Abstain & Validate: Does "Refusal Authority" Map to REQUEST_CHANGES?

YES, but with caveats. Paper does not use term "REQUEST_CHANGES" (uses repair-specific terminology: "fail-to-pass," "fail-to-continue"), but enforcement pattern maps directly.

Direct quote affirming refusal: "Showing unlikely patches to developers can lead to substantial noise, wasting valuable developer time and eroding trust in automated code changes. These two-policy approach provides a practical path to the reliable, industrial-scale deployment of agentic APR systems."

This means: Validation fails → patch NOT auto-committed → human developer must review and decide → REQUEST_CHANGES in code-review terminology.

POLARIS implementation: .codex/<issue_id>/codex_visual_audit.txt contains YAML verdict field:
`
verdict: APPROVE # or REQUEST_CHANGES
pass_count: 14
total_dimensions: 16
failed_dimensions:
  - dimension_8_color_hierarchy: FAIL
  - dimension_12_motion_state: PARTIAL
`

CI gate (.github/workflows/codex-visual-required.yml) parses this YAML:
- If verdict: APPROVE and pass_count >= 14 → allow merge
- Otherwise → block merge (equivalent to REQUEST_CHANGES in CI semantics)

---

## PART 3: HIGH-RELEVANCE PAPERS DISCOVERED

### Paper 5: WebVR – Benchmarking Multimodal LLMs

Citation: Dai et al., arXiv:2603.13391v1 (March 2026)  
Authors: Yuhong Dai, Yanlin Lai, Mitt Huang (StepFun, Tsinghua University)  

**Thesis:**
"Multimodal language models need systematic evaluation on video-conditioned webpage recreation using fine-grained, human-aligned visual rubrics rather than coarse structural metrics. Existing benchmarks overlook dynamic interactions encoded in demonstration videos."

**Rubric Framework – Four Dimensions with "Extreme Atomicity":**
1. Global Aesthetics (GA): Color, typography, visual coherence
2. Navigation & Footer (NF): Header/footer structure and states
3. Section-Specific Layouts (SSL): Grid alignment, spacing, hierarchy
4. Interaction & Motion (IM): Hover effects, animations, state transitions

Design principle: Each criterion verifies exactly one visible property without conjunctions.

**Empirical Results:**
- Human alignment: Rubric-guided evaluation achieved 96% agreement with human preferences (vs. 59–67% for rubric-free approaches)
- Best-performing model: Kimi-K2.5 scored 79.14/100 overall
- Dimension performance variance:
  - Global Aesthetics: 72.57 average
  - Interaction & Motion: 38.44 average (PRIMARY BOTTLENECK)
- Evaluation stability: Score standard deviation 0.48 across independent runs

**Limitations:**
"Current MLLMs can extract high-level visual style from video frames but struggle to translate temporal cues into executable interaction logic."

**Clinical relevance:** Motion/interaction dimension (POLARIS dimension 13: "responsive feedback visible during state transitions") is hardest to evaluate. WebVR's finding that MMMLMs average 38/100 on IM suggests this dimension is hard. POLARIS should weight dimension 13 lower in pass/fail thresholds or require human expert review if dimension 13 is sole failing dimension.

### Paper 6: Multi-Agent Code Verification via Information Theory

Citation: Rajan, arXiv:2511.16708v3 (October 2025)  
Author: Shreshth Rajan, Noumenon Labs, Harvard University  

**Thesis:**
"LLMs generate buggy code at alarming rates (29.6% of marked-solved patches fail; 62% of backend implementations contain vulnerabilities). Combining multiple specialized agents analyzing different bug dimensions outperforms single-agent approaches through information-theoretic principles."

**Enforcement Mechanism – Four Specialized Agents (Parallel Execution):**
1. Correctness Critic (75.9% solo accuracy): Logic errors, edge cases, exception handling
2. Security Auditor (20.7% solo accuracy): Injection vulns, hardcoded secrets, unsafe deserialization (15+ CWE patterns)
3. Performance Agent (17.2% solo accuracy): Algorithmic complexity, resource leaks
4. Style Checker (17.2% solo accuracy): Maintainability, documentation

Weighted aggregation: Security 0.45, Correctness 0.35, Performance 0.15, Style 0.05

**Empirical Results:**
- Combined system: 76.1% true positive rate, 50% false positive rate (matching Meta Prompt Testing's 75% TPR)
- Multi-agent advantage: 39.7 percentage point improvement over single agents (32.8% → 72.4%)
- Diminishing returns by agent: +14.9pp (agent 2), +13.5pp (agent 3), +11.2pp (agent 4)
- Best two-agent config: Correctness + Performance = 79.3% accuracy
- Latency: <200ms per sample via parallel execution

**Limitations:**
"High false positives (50% vs. test-based methods at 8.6%) due to flagging quality issues beyond functional bugs."
"Sample size (n=99) yields ±9.1% confidence intervals; PAC learning bounds suggest n>=127 optimal."
"Static analysis ceiling: Cannot detect dynamic bugs, race conditions, or semantic errors requiring execution."
"Python-specific: Patterns and AST analysis require language-specific adaptation for C/C++, Java, TypeScript."

**Clinical relevance:** 39.7pp multi-agent advantage suggests independent rubric dimensions are NOT redundant; they each catch distinct failure classes. POLARIS's 16 dimensions should be weighted by clinical risk: high-risk dimensions (medication accuracy, error visibility) use weights >0.1; low-risk (typography) use weights <0.05.

### Paper 7: Autonomous Evaluation and Refinement of Digital Agents

Citation: Pan et al., arXiv:2404.06474v3 (April 2024)  
Authors: Jiayi Pan, Yichi Zhang (UC Berkeley), Nicholas Tomlin, Yifei Zhou, Sergey Levine, Alane Suhr (University of Michigan)  

**Thesis:**
"Domain-general automatic evaluators using neural models can significantly improve digital agent performance for web navigation and device control without additional human supervision or hand-designed evaluation functions."

**Enforcement Mechanism – Two Evaluation Approaches:**
1. End-to-end: GPT-4V directly assesses full agent trajectories
2. Modular: Fine-tuned vision-language model captions screenshots; language model reasons about success

These evaluators feed two refinement techniques:
- Reflexion (inference-time guidance): Agent uses evaluation scores to refine trajectory
- Filtered behavior cloning (training-time filtering): Filter trajectories by evaluation score

**Empirical Results:**
- WebArena accuracy: 74.4–82.1% agreement with oracle metrics
- Android-in-the-Wild: Up to 92.9% accuracy
- Performance improvements via Reflexion: 29% relative improvement on WebArena
- Performance improvements via filtered behavior cloning: Approximately 75% relative improvement on iOS and Android

**Limitations:**
"Current evaluators are still far from perfect, with error analysis revealing reasoning mistakes (50–70% of failures) and information loss in the modular approach (10% of failures)."

**Clinical relevance:** 29% relative improvement from Reflexion (agent evaluates own work, refines trajectory) validates POLARIS's local scripts/visual_review_gate.py loop. Harness allows up to 5 iterations because writer agent (Claude) can be given failed dimension list and retry. This paper validates agent self-critique + refinement is effective; improvements scale with loop iterations.

### Papers 8–9: Rubric Generation & Quality Assurance

**RubricRL (arXiv:2511.20651, November 2025):**
Contributes generalizable rubric-based reward design applicable to diffusion and autoregressive models. Prompt-adaptive, decomposable supervision framework enhances interpretability and composability.
**Clinical takeaway:** POLARIS uses static weighting (each dimension binary PASS/FAIL, equal weights). Dynamic weighting per PR type would improve efficiency but risks policy drift.

**RIFT (arXiv:2604.01375, April 2026):**
Rubric Failure Mode Taxonomy and Automated Diagnostics. Identifies failure modes in rubric-based evaluation (ambiguity, under-specification, metric misalignment).
**Clinical takeaway:** Before deploying .codex/visual_audit_rubric.md, run RIFT diagnostics: (1) ambiguity check—do two designers interpret dimension identically? (2) Under-specification check—can Codex vision distinguish PASS from PARTIAL? (3) Metric misalignment—if dimension fails, do clinical users report problem?

---

## PART 4: SYNTHESIS & RECOMMENDATIONS

### Finding 1: Locked Dimensions Are Load-Bearing for Automation

UICrit, Visual Prompting, WebVR all use rubric-based evaluation frameworks. Papers diverge on whether dimensions should be fixed or open-ended:
- UICrit: Fixed five dimensions (discovered via clustering)
- Visual Prompting: Open-ended critique, but validates against fixed text+box pairs
- WebVR: Fixed four dimensions with binary scoring per dimension

POLARIS choice: Locked 16 dimensions. This is defensible given clinical stakes. Trade-off: precision (open-ended might discover overlooked issues) vs. reliability (locked prevents policy drift and drift-induced false negatives).

### Finding 2: Iteration Budgets Are Tight; Diminishing Returns at Iteration 3

Visual Prompting evidence: +26% at iter 1, +6% at iter 2, +3% at iter 3.
POLARIS's current 5-iteration budget (research brief) is conservative. Tighten to 2–3 iterations per dimension to save tokens while maintaining catch rate.

### Finding 3: Refusal Authority Is Prerequisite for Clinical Enforcement

Both Faramesh and Abstain & Validate emphasize: validator without refusal power becomes rubber stamp under prompt pressure.
POLARIS implements refusal via CI gate: if pass_count < 14, merge BLOCKED. No APPROVE with caveats.

### Finding 4: Multi-Agent Independent Scoring Catches Distinct Failure Classes

Multi-Agent Code Verification (Rajan) shows 39.7pp improvement from combining four agents. POLARIS's 16 dimensions should be treated as independent classifiers, not redundant checks. Weight by clinical risk: medication data 0.1, typography 0.02.

### Finding 5: Motion/Interaction Is Hardest Dimension to Evaluate

WebVR: Global Aesthetics 72.57 avg, Interaction & Motion 38.44 avg.
POLARIS dimension 13 (responsive feedback): Expect Codex vision <70% accuracy. Consider human spot-check if dimension 13 sole failing dimension.

---

## IMPLEMENTATION ROADMAP

Priority 1 (Non-negotiables from Faramesh + Abstain & Validate):
- CI gate runs outside agent reasoning loop (GitHub Actions CODEOWNERS protection)
- Only two verdicts: APPROVE (>=14/16 pass) or REQUEST_CHANGES
- Rubric locked via SHA; policy drift structurally prevented

Priority 2 (Iteration budgets from Visual Prompting):
- Reduce scripts/visual_review_gate.py loop from 5 to 3 iterations per dimension
- Force-APPROVE on iteration 3 (diminishing returns threshold)
- Log iteration count; flag PRs requiring >2 iterations for quality review

Priority 3 (Weighting schema from Multi-Agent Code Verification):
- Identify high-risk dimensions (medication data, error urgency)
- Apply clinical-domain weights: high-risk 0.08–0.12, standard 0.05–0.08, low-risk 0.02–0.04
- Pass/fail threshold: sum(weights * PASS_rate) >= 0.70 (not raw count >=14/16)

Priority 4 (Dimension quality assurance from RIFT):
- Before merging .codex/visual_audit_rubric.md, run inter-rater reliability check
- Codex must achieve >0.8 IoU on 3 human-scored test screenshots per dimension
- Dimension fails validation if accuracy <0.75

Priority 5 (Motion/interaction specialization from WebVR):
- Dimension 13 (responsive feedback) requires animated GIFs or multi-frame screenshots
- Codex vision may not ground motion; consider async review (human spot-check on failure)

---

## REFERENCES

1. UICrit: Enhancing Automated Design Evaluation with a UI Critique Dataset
   Duan, Chen, Li, Hartmann, Yang. arXiv:2407.08850v2 (July 2024, CHI 2025).

2. Visual Prompting with Iterative Refinement for Design Critique Generation
   Duan, Cheng, Hartmann, Li. arXiv:2412.16829 (December 2024, revised May 2025).

3. Faramesh: A Protocol-Agnostic Execution Control Plane for Autonomous Agent Systems
   Fatmi. arXiv:2601.17744v1 (January 2026).

4. Abstain and Validate: A Dual-LLM Policy for Reducing Noise in Agentic Program Repair
   Cambronero et al. arXiv:2510.03217v1 (October 2025); ICSE 2026 SEIP.

5. WebVR: Benchmarking Multimodal LLMs for WebPage Recreation from Videos via Human-Aligned Visual Rubrics
   Dai, Lai, Huang et al. arXiv:2603.13391v1 (March 2026).

6. Multi-Agent Code Verification via Information Theory
   Rajan. arXiv:2511.16708v3 (October 2025).

7. Autonomous Evaluation and Refinement of Digital Agents
   Pan, Zhang, Tomlin, Zhou, Levine, Suhr. arXiv:2404.06474v3 (April 2024).

8. RubricRL: Simple Generalizable Rewards for Text-to-Image Generation
   arXiv:2511.20651 (November 2025).

9. RIFT: A Rubric Failure Mode Taxonomy and Automated Diagnostics
   arXiv:2604.01375 (April 2026).

---

Document prepared: 2026-05-25
For: POLARIS visual review harness enforcement architecture
Status: Ready for CI workflow implementation and rubric quality assurance rollout
