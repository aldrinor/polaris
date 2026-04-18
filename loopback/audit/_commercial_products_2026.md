# Commercial LLM Research-Report Products — Skeptical Review (April 2026)

**Source-quality note.** Most 2026 "review" pages are SEO/affiliate content farms. Numbers from those sources are flagged **vendor-adjacent**. Independent signals come from vendor pages, peer-reviewed outlets (Nature / npj / PMC / Cambridge Core / JMIR), FutureSearch's Deep Research Bench, Fortune/TechCrunch, and court filings.

---

## 1. OpenAI Deep Research (GPT-5.x class)

**Vendor claim.** Inside ChatGPT Pro ($200/mo, 250 runs/mo) and Plus ($20/mo, 10 runs/mo). Feb 10 2026 added MCP/app connections, trusted-site restrictions, live-progress interruption (https://help.openai.com/en/articles/9793128-about-chatgpt-pro-plans ; https://openai.com/index/introducing-deep-research/). OpenAI admits it "can sometimes hallucinate facts" but claims GPT-5 web-search is ~45% less error-prone than GPT-4o (https://cdn.openai.com/gpt-5-system-card.pdf, Aug 13 2025).

**Independent signal.** Vectara puts GPT-5.2 at 8.4% hallucination — behind DeepSeek's 6.3% (https://aimultiple.com/ai-hallucination). npj Digital Medicine finds *adversarial* hallucination of 65% unmitigated on GPT-5, higher than GPT-4o's 53% (https://www.nature.com/articles/s41746-026-02584-8). Clearest applied failure: Benedict Evans / Gijs showed Deep Research's own marketing example on Japan smartphone share reported "69% iOS / 31% Android" while Statcounter had 59.7% and regulators ~47%, pulling weak sources without pushback (https://gijs.substack.com/p/openais-deep-research-demonstrates). Fortune/GPTZero analyzed >4,000 NeurIPS 2025 accepted papers and found hundreds of fabricated citations across ≥53 — fake authors, invented journals, blended refs (https://fortune.com/2026/01/21/neurips-ai-conferences-research-papers-hallucinations/).

**Honest read.** Best-of-class depth; still hallucinates confidently; "if I have to check every number it hasn't saved me any time" (Evans).

## 2. Perplexity Deep Research / Labs

**Vendor claim.** Pro $20/mo (20/day), Enterprise Pro $40/user, Enterprise Max $325/user with Perplexity Computer agent (https://www.finout.io/blog/perplexity-pricing-in-2026). March 15 2026 relaunch moved Deep Research onto Claude Opus 4.5 for Max/Pro with "SOTA on DeepMind Deep Search QA and Scale AI Research Rubric" (https://www.perplexity.ai/changelog/what-we-shipped---february-6th-2026).

**Independent signal.** Two IP suits cut against the "best citations" marketing. **Reddit v. Perplexity** (SDNY, Oct 22–23 2025) alleges DMCA §1201 circumvention; Reddit citations rose ~40x after a cease-and-desist (https://natlawreview.com/article/anti-circumvention-reddits-case-against-perplexity). **Britannica & Merriam-Webster v. Perplexity** (SDNY) alleges "incorrect citations and attributions" with plaintiff logos implying endorsement (https://www.reedsmith.com/our-insights/blogs/viewpoints/102loki/citation-frustration-when-ai-makes-stuff-up-and-gets-sued-for-it/). Academic analysis: Perplexity answered "incorrectly in ~37%" of cases and frequently links homepages/mirrors rather than the specific article (https://www.datastudios.org/post/perplexity-ai-for-academic-research-how-reliable-are-the-sources). Re-quoted "94% / 96-of-100 accuracy" numbers trace to vendor-adjacent pages — **marketing, not evaluation.**

**Honest read.** Fast and strong on primary regulatory docs; the "verifiable citations" story is contested in court and by independent testing.

## 3. Google Gemini Deep Research / NotebookLM

**Vendor claim.** Deep Research ingests user files/images; Jan 2026 rollout pushes its reports into NotebookLM as sources while the agent runs in background (https://9to5google.com/2026/01/28/gemini-app-google-ai-plus/ ; https://www.marketingaiinstitute.com/blog/googles-deep-research-and-notebooklm). Free: 5 reports/mo. Gemini 3.1 Pro backs the Deep Research agent since Feb 19 2026 (https://gemini.google/release-notes/).

**Independent signal.** The product with the loudest critical literature. "Garbage In, Garbage Out: Why Gemini Deep Research can't do Basic Humanities Research" (https://medium.com/age-of-awareness/garbage-in-garbage-out-why-gemini-deep-research-cant-do-basic-humanities-research-0311c54bdb91); a Section test called one tool "unusable" (https://www.sectionai.com/blog/chatgpt-vs-gemini-deep-research); a DEV post where Gemini misdescribed its own Deep Research, ~half of the self-description inaccurate (https://dev.to/shimo4228/i-asked-gemini-how-its-own-deep-research-works-half-of-it-was-inaccurate-1ki1). English-biased retrieval and crashes on revision are widely reported; Google itself keeps an "outputs may contain inaccuracies" disclaimer (https://support.google.com/gemini/answer/15719111).

**Honest read.** Depth on structured/scientific PDFs is real; humanities, multilingual, and self-descriptive accuracy are weak.

## 4. Anthropic Claude (Research, Managed Agents, Skills)

**Vendor claim.** Claude "Research" searches web + Workspace + integrations with a lead agent + parallel sub-agents; Anthropic claims Opus-4-lead + Sonnet-4-subagents beat solo Opus-4 by 90.2% on *internal* evals (https://www.anthropic.com/engineering/multi-agent-research-system). April 8 2026 launched Claude Managed Agents public beta (https://siliconangle.com/2026/04/08/anthropic-launches-claude-managed-agents-speed-ai-agent-development/). Claude for Life Sciences (Oct 2025) + Agent Skills are the research surface; Opus 4.7 advertises multi-hour autonomy (https://claude.com/blog/research).

**Independent signal.** Thin. No rigorous independent end-to-end evaluation of Claude Research as a report generator surfaced — most "2026 review" pages are general chatbot comparisons. Adjacent: Claude 4.6 Sonnet leads AA-Omniscience (~38% hallucination vs Sonnet 4.5's 48%) (https://sqmagazine.co.uk/llm-hallucination-statistics/), and Anthropic's models are independently characterized as calibrated to *refuse rather than guess* — helps faithfulness, depresses raw coverage. **Independent evaluation of Claude Research as a product is scarce in public as of April 2026.**

## 5. Elicit

**Vendor claim.** Systematic Review (80-paper reports, strict screening, auto extraction across 138M papers); API launched March 2026. Plus $12/mo, Pro $49, Team $79, Enterprise to $780 (https://elicit.com/).

**Independent signal.** PMC product review + peer-reviewed comparative study: extraction accuracy ~80–94% depending on task, but **missed ~15% of relevant studies** in SR testing; struggles with images/diagrams/raw data (flattened to prose) (https://pmc.ncbi.nlm.nih.gov/articles/PMC11921719/). Cambridge Core and JMIR scoping reviews conclude GenAI including Elicit should not be used without human oversight for evidence synthesis (https://www.cambridge.org/core/journals/research-synthesis-methods/article/generative-artificial-intelligence-use-in-evidence-synthesis-a-systematic-review/2DACF6D129AA6E46CB8A8740A03D0675 ; https://www.jmir.org/2026/1/e81597). Elicit has re-extended into end-to-end SR, but is explicit about human-in-loop positioning.

## 6. Consensus

**Vendor claim.** Consensus Meter (yes/no claim agreement %), Pro Analysis (GPT-4), Ask Paper, Study Snapshots. Pro $15/mo; LibKey library integration from 2025–26 academic year (https://consensus.app/pricing/).

**Independent signal.** Per-claim verification remains the architecture. No major independent 2026 evaluation surfaced — positive reviews are SEO-tier. Docs admit "occasional errors can occur."

## 7. Scite.ai

**Vendor claim.** 1.6B+ classified citation statements across 280M+ sources; Smart Citations tag Supporting / Contrasting / Mentioning; MCP integration with ChatGPT, Claude, Copilot, Cursor, Claude Code; Zotero plug-in. Individual $20/mo, Team $40/user (https://scite.ai/blog/february-2026-release-notes).

**Independent signal.** Scite's classifier is peer-reviewed infrastructure, not a report generator. Honest positioning: **citation-context layer for other tools** — maps well to POLARIS's per-claim verification need.

## 8. New 2025–2026 entrants

- **Undermind.ai** (YC 2025, MIT founders). Iterative agentic search over Semantic Scholar (225M papers). PMC product review positive on precision/recall vs Google Scholar, but confirms it is discovery + summaries, not a full report generator (https://pmc.ncbi.nlm.nih.gov/articles/PMC12352444/).
- **Rocket 1.0** (Accel / Salesforce Ventures, $15M seed). "McKinsey-style" reports, $25–$350/mo, over Meta ad libraries, Similarweb API, proprietary crawlers. TechCrunch framing (April 6 2026) is explicitly compete-on-price-vs-consulting, not academic rigor (https://techcrunch.com/2026/04/06/indian-startup-rocket-wants-its-ai-to-do-mckinsey-style-consulting-at-a-fraction-of-the-cost/).
- Otherwise crowded with retreads (Paperpal, Otio, Genspark). No clearly novel academic-grade entrant surfaced.

---

## Honest frontier comparison

**Common failure modes across all seven:**
1. **Citation fabrication persists even in reasoning models.** Fortune/GPTZero (NeurIPS 2025) and Stanford HAI show 22–94% hallucination ranges; Britannica v. Perplexity shows misattribution survives even when a "citation" is rendered (https://www.nature.com/articles/d41586-025-02853-8).
2. **Citation-to-wrong-URL.** Pointing at homepages / mirrors / secondary blogs — documented against Perplexity specifically, generalizes broadly.
3. **Weak-source selection.** Statista/Statcounter-grade inputs get chosen when better primary data exists (Evans).
4. **Paywall + English-only bias.** Gemini's English-only retrieval and flattened-PDF handling are the clearest admissions; affects every retrieve-then-synthesize product.
5. **Self-evaluation substitutes for independent evaluation.** OpenAI's 45%/80% claims, Perplexity's "SOTA on our benchmarks," Anthropic's 90.2% internal number — all vendor-internal. FutureSearch Deep Research Bench (https://futuresearch.ai/deep-research-bench/) is the only general-purpose independent benchmark currently public, and its live leaderboard failed to load when fetched.

**Genuine differentiation.** Perplexity on speed + structured-doc retrieval; Gemini on multimodal/Workspace; Claude on long-horizon autonomy + refusal-calibrated hallucination; OpenAI on depth per run; Elicit on structured SR with honest human-in-loop positioning; Scite as citation-context utility layer; Consensus on per-claim agreement mapping.

**Takeaway for POLARIS.** No incumbent *guarantees* faithfulness — they manage it with disclosure, UX ("easy-to-check citations"), and human-in-loop handoffs. Faithfulness + credibility + unique analytical view is not a solved problem anyone is shipping; the products that ship honestly say "human oversight required." Realistic differentiation: (a) strict per-claim grounding with contradiction surfacing, (b) credible source-tier scoring that pushes back on Statista-grade inputs, (c) explicit paywall / non-English handling — all weak points the incumbents admit.
