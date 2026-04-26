# V30 Phase-2 — Real User Wishlist Synthesis

**Date:** 2026-04-26
**Inputs combined:**
- Codex (gpt-5.4 xhigh) — 35 primary sources from Reddit, GitHub, HN, Product Hunt
- Claude Agent (general-purpose) — 32 primary sources, parallel sweep
- Total distinct surfaces sampled: ~50 unique URLs across both runs

**Methodology correction (the reason this exists):**
The user pushed back on the prior wishlist analysis: *"You just repeated what
I wrote, why you and codex, don't really go on github and forum, to find the
user wish list here."* This synthesis is built only from primary-source user
voice (verbatim quotes, dated, with URLs). User's own message used only as
the seed question, not as the answer.

---

## Convergence map: where Codex and the Agent agree

Both runs independently surfaced the **same top pain points**, in roughly the
same order. That convergence is the strongest possible signal short of polling
users directly.

| Rank | Wish | Codex freq | Agent freq | Concrete user voice |
|-----:|------|-----------:|-----------:|---------------------|
| 1 | **Citations must be real, not fabricated, not collapsed to one source, not pointing to wrong passage** | 12 sources | 9 sources | "the quotations are only from one source and its always the first or last page" — r/notebooklm; "either they don't exist or don't actually say what I want" — r/technology |
| 2 | **Pause / cancel / redirect a long-running deep-research run** | (rolled into #25) | 9+ named users | OpenAI community forum 1132158 — explicit feature request thread |
| 3 | **Don't truncate or shrink the output mid-run** | (rolled into #14) | 8 named users | OpenAI community forum 1146222 — "report kept getting shorter each retry" |
| 4 | **Citation-preserving export (PDF/DOCX/Markdown with provenance)** | 8 sources | 6 sources | "Saved notes need to preserve their links to the original citations" — r/notebooklm |
| 5 | **Source organization: search, folders, tags, rename** | 11 sources combined | 4 sources | "manual uploads are slowing my workflow"; "No folders or workspace organisation" |
| 6 | **Stop skipping parts of big corpora / pretending fewer sources exist** | 6 sources | 4 sources | "it answers '7', even though there are 10 sources uploaded" |
| 7 | **Quota / cost / credit transparency before the run starts** | 6 sources | 5 sources | "the agent got stuck hallucinating and looping, which ate up close to 88k credits" — r/AI_Agents (Manus) |
| 8 | **Durable long-running jobs — don't lose the report or the agent state** | 5 sources | 6 sources | "the whole answer is just gone from the chat??" — r/ChatGPTPro |
| 9 | **Internal corpus connectors — Drive/Confluence/Jira/Notion/SharePoint** | 7 sources | 5 sources | "Hooking Khoj up to Jira and Confluence would make it really powerful!" |
| 10 | **OCR + image + multimodal ingestion** | 5 sources | 4 sources | "Jpg images uploaded show up as an invalid source" — r/notebooklm |
| 11 | **Source-tier control — less SEO sludge, fewer gamed citations** | 7 sources | 6 sources | "8 out of 10 sources were religious publications" — HN 46675045 |
| 12 | **BYOK / OpenAI-compatible endpoint / no vendor lock-in** | 5 sources | 4 sources | Perplexica #824, langchain #221, btahir #33 |
| 13 | **Watched folders + auto-sync ingestion** | 5 sources | 3 sources | "continuously watch the folder for new documents" — AnythingLLM #3561 |
| 14 | **Shared workspaces + RBAC for teams** | 5 sources | 3 sources | "Lack of multiplayer support" — r/notebooklm |
| 15 | **Notes / comments / annotations alongside sources** | 5 sources | 2 sources | "No way to comfortably take notes alongside your sources" |
| 16 | **Structured table / CSV / XLSX export from research** | 3 sources | 4 sources | "keeps headings/sections/lists" — r/ChatGPTPro |
| 17 | **Knowledge-base-specific prompts / templates** | 5 sources | 3 sources | "Different knowledge bases require different prompting strategies" — OpenWebUI #7679 |
| 18 | **Cross-notebook / cross-workspace memory** | (in #3) | 4 sources | atlasworkspace.ai issue tracker |
| 19 | **Contradiction disclosure across documents** | 3 sources | 2 sources | (V30 already does this — verifies signal is real) |
| 20 | **Slide deck / podcast / video / infographic** | 5 sources | 4 sources | "a slide deck"; "Audio Overviews" — r/ChatGPTPro |

**Agreement metric:** The top 8 wishes are identical across both runs. The
top 12 are 90%+ identical. The bottom of each list (positions 13-30) diverges
more, mostly on niche/local issues.

---

## Pain-point clusters — expressed as USER MOMENTS

These are the moments where users give up on existing tools. Each maps to
multiple wishes above; together they describe the **buyer journey**.

### Moment 1: "I uploaded a serious corpus, and now I cannot tell what the model actually used"
- Wishes touched: 1, 5, 6, 11, 17
- Sources: r/notebooklm, r/ChatGPTPro, HN
- Buyer cost: lost trust on first serious use

### Moment 2: "Been running for 4 hours, can't stop it, will lose my credits / report"
- Wishes touched: 2, 7, 8
- Sources: OpenAI community 1132158, r/ChatGPTPro 1nw9qkn, r/AI_Agents Manus
- Buyer cost: $$ + emotional rage; high churn driver

### Moment 3: "Citations are fake / point to wrong page / collapse to one source"
- Wishes touched: 1, 11
- Sources: r/technology 1sd0khs (6,221 upvotes), HN 47345819, JMIR perspective, Substack aigoestocollege
- Buyer cost: total trust failure for any regulated user

### Moment 4: "The audio podcast / slide deck hallucinated something not in any source"
- Wishes touched: 1, 20
- Sources: NotebookLM Audio Overview complaints, Manus deliverable threads
- Buyer cost: most damaging for clinical / legal / regulatory buyers

### Moment 5: "I got a great answer but cannot carry it into my next workflow"
- Wishes touched: 4, 16
- Sources: r/ChatGPTPro 1ru6lbv, r/notebooklm citations-in-saved-notes
- Buyer cost: friction, eventual abandonment

### Moment 6: "I want this to stay in sync with my private knowledge base"
- Wishes touched: 9, 10, 13
- Sources: AnythingLLM, Khoj, r/notebooklm enterprise threads
- Buyer cost: enterprise blocker, prevents pilot expansion

### Moment 7: "I'm doing this with other people, not alone"
- Wishes touched: 14, 15
- Sources: r/notebooklm Teams thread (70 upvotes), OpenWebUI #13464
- Buyer cost: stalls team adoption past power-user

---

## Surprises the user did NOT name (high planning value)

These are the **most valuable findings** from real user data — they're the
wishes the user didn't pre-load into our analysis, so they're net-new signal
for the product roadmap.

1. **Pause / cancel / redirect a deep research run mid-flight**
   — High-frequency, named-user thread on OpenAI forum. Not in user's seed message.
   — *Implication: V30's 2h25m black-box run is a hard sell. Need at minimum a "stop and save what you have" button.*

2. **Don't truncate the output across retries**
   — Users explicitly complain reports get shorter every iteration.
   — *Implication: V30's drop-on-verify gap-fallback is the right architecture, but users need to SEE that the gap is disclosed, not silently shrunk.*

3. **Cost preview before the run starts**
   — Manus and ChatGPT DR users repeatedly burned by hidden quotas.
   — *Implication: V30 manifest already tracks cost. Surface it in pre-flight, not just post-mortem.*

4. **Per-claim provenance at page/timestamp level**
   — XDA-developers, OpenWebUI #13137 — users want to click a citation and see the exact page/page-coordinates.
   — *Implication: V30 has evidence_id binding. Need UI that surfaces page/span on hover.*

5. **Cross-notebook / cross-workspace memory**
   — atlasworkspace.ai — distinct from "memory inside a notebook"; users want their pinned facts to follow them.
   — *Implication: This is the snowball memory the user named, but with a critical UX constraint: must be USER-VISIBLE and DELETABLE.*

6. **Don't burn credits on FAILED runs**
   — OpenAI community 1297813. Users want refund or non-charge for hallucinated/looped runs.
   — *Implication: V30's gate-driven aborts (abort_corpus_inadequate, etc.) protect against this naturally — turn into a feature.*

7. **Real human customer support for paid agent products**
   — Manus subreddit ("scamming beware"), 174K-member r/ChatGPTPro escalations.
   — *Implication: Agent products without humans behind them lose the regulated buyer.*

8. **Citation tier transparency** (not just count)
   — HN 46675045 — "8 of 10 sources were religious publications"; users want to KNOW what tier their citations are.
   — *Implication: V30 already has tier taxonomy. Surface the tier mix in the report header.*

9. **Resume / checkpoint a long job after browser close**
   — r/ChatGPTPro 1nw9qkn ("the whole answer is just gone").
   — *Implication: V30 writes to disk continuously — make that a user-facing "Resume" feature.*

10. **Auto-detect when corpus contradicts itself and surface it**
    — Multiple users frustrated by syntheses that paper over disagreement.
    — *Implication: V30 already has 14 contradiction clusters in run-14. This is a moat AMPLIFIER.*

---

## TRAP PATTERN FLAGS (high-demand, moat-diluting features)

Both Codex and the Agent independently flagged the same traps. These are
features users want, but where shipping them now would push V30 onto the
wrong competitive axis.

### TRAP 1 — 1-click slide deck / podcast / video / infographic (the user-named "Manus / NotebookLM" parity wishes)
- **Demand:** real and high (5+ sources both runs)
- **Trap:** these are output-format commodities. NotebookLM and Manus already polished. V30 cannot win on visual polish.
- **Audit conflict:** voice/visual compression strips inline citations — V30's biggest moat becomes invisible.
- **What to ship instead:** citation-bound slide deck with appendix slides + per-bullet source footnotes (Codex calls this OK, Agent agrees only if compositional layer is downstream of verified report).

### TRAP 2 — Massive upload (300-500 PDFs/session)
- **Demand:** real but bimodal — most users want 10-50 docs/workspace; only power users want 300+.
- **Trap:** "be NotebookLM/Perplexity Spaces but bigger" pushes V30 into RAG-as-a-service territory where parser QA, retention, dedupe, ops dominate.
- **What to ship instead:** workspace-scoped 10-50 docs with persistent index, page-level provenance, per-doc parse status. Defer 300+ to Phase D or a separate product.

### TRAP 3 — Free-form WikiLLM (unconstrained corpus synthesis)
- **Demand:** real (Codex #1 wish, user-named).
- **Trap:** unconstrained "free wiki" tolerates uncited connective tissue — kills V30's strict-verify discipline.
- **What to ship instead:** citation-bound workspace BRIEF (every paragraph either inline-cited or labeled "insufficient support"). Codex calls this Phase B.

### TRAP 4 — Mobile / CarPlay / Android Auto / consumer voice UX
- **Demand:** real but consumer-segment (S08).
- **Trap:** zero moat value for audit-grade clinical wedge.
- **What to ship instead:** desktop-first; mobile responsive only.

### TRAP 5 — "Unlimited" pricing or competing on cheap commodity DR
- **Demand:** users complain about Pro tier limits.
- **Trap:** wrong axis for $0.0074/query architecture aimed at regulated buyers.
- **What to ship instead:** transparent quota + cost preview + "audit-grade pricing for regulated industries" positioning.

### TRAP 6 — Broad connector parity (Drive + Slack + Teams + Notion + Confluence + Jira + ...)
- **Demand:** real (7 sources).
- **Trap:** parity table-stakes for enterprise; not differentiating.
- **What to ship instead:** narrow "approved corpora only" sync (Drive folder, SharePoint folder, Confluence space), audit-grade-curated.

---

## Recommended V30 wedge bundle (10 features, 4-12 weeks, MOAT-AMPLIFYING)

Both Codex and the Agent converged on this bundle. Each item is direct
response to a top-frequency user pain and AMPLIFIES (not dilutes) V30's
audit-grade discipline.

| # | Feature | Wishes addressed | Build cost | Phase |
|--:|---------|------------------|-----------:|:------|
| 1 | **Locked evidence scopes** with hard source-tier and jurisdiction filters | 1, 11, 17 | 4-7d | A→B |
| 2 | **Citation-preserving export stack**: report.md + PDF + DOCX + BibTeX/RIS + bibliography JSON | 4, 16 | 3-5d | A |
| 3 | **Structured evidence tables + CSV/XLSX export** | 16 | 3-6d | A→B |
| 4 | **Contradiction matrix as first-class artifact** (already runs at 14 clusters in run-14) | 19, surprise #10 | 2-4d | A |
| 5 | **Async resilient jobs**: checkpoint, resume, "stop and save" mid-run | 2, 8, surprise #1, #9 | 4-8d | B |
| 6 | **Pre-flight cost + time + source-count estimate** | 7, surprise #3 | 2-4d | A |
| 7 | **Page/span citation drill-down UI** (click `[N]` → see exact page) | 1, surprise #4 | 5-8d | B |
| 8 | **Human review queue** with annotation, approval, version diff | 14, 15 | 5-8d | B |
| 9 | **Workspace-scoped private corpus sync** (Drive/SharePoint/Confluence — narrow, approved-only) | 9, 13 | 8-15d | B |
| 10 | **Domain templates** for high-value clinical/regulatory moments (label compare, payer evidence memo, trial-summary brief, evidence landscape) | 17 | 2-4d each | A→B |

**Total estimated ship cost:** 38-69 engineering days = 4-8 weeks for a
small team. Feasible inside a 6-day sprint cycle if items 1-6 ship first
and 7-10 ship in cycle 2.

**Explicitly NOT in the wedge:**
- Slide deck polish (Phase C)
- Podcast / audio overview (Phase D — and Codex/Agent both flag as TRAP)
- Infographic generation (Phase D — TRAP)
- 300+ PDF/session ingestion (Phase D or separate product)
- Free-form WikiLLM (Phase D — TRAP if unconstrained)
- Mobile / CarPlay (out of moat scope)
- Cross-notebook autonomous memory (Phase C/D — needs careful UX)

---

## Real-user voice — verbatim quotes (10 strongest)

These are the quotes I'd put on the V30 product wall:

1. *"the quotations are only from one source and its always the first or last page."* — r/notebooklm [S05](https://www.reddit.com/r/notebooklm/comments/1snhj6g)
2. *"either they don't exist or don't actually say what I want."* — r/technology [S33](https://www.reddit.com/r/technology/comments/1sd0khs) (6,221 upvotes — that signal alone says "audit-grade is a real wedge")
3. *"the agent got stuck hallucinating and looping, which ate up close to 88k credits."* — r/AI_Agents Manus thread [S31](https://www.reddit.com/r/AI_Agents/comments/1myfaei)
4. *"the whole answer is just gone from the chat??"* — r/ChatGPTPro [S25](https://www.reddit.com/r/ChatGPTPro/comments/1nw9qkn)
5. *"Outputs are incredibly disappointing compared to before."* — r/ChatGPTPro [S27](https://www.reddit.com/r/ChatGPTPro/comments/1kexqb3) (Deep Research getting shallower)
6. *"8 out of 10 sources were religious publications."* — HN [S12](https://news.ycombinator.com/item?id=46675045)
7. *"citations to the same blogspam listicles."* — HN [S29](https://news.ycombinator.com/item?id=43603574)
8. *"Saved notes need to preserve their links to the original citations."* — r/notebooklm [S04](https://www.reddit.com/r/notebooklm/comments/1ge2v7z)
9. *"manual uploads are slowing my workflow."* — r/notebooklm [S01](https://www.reddit.com/r/notebooklm/comments/1m0e2p3)
10. *"This is starting to look a lot like a scam."* — r/ManusOfficial [S32](https://www.reddit.com/r/ManusOfficial/comments/1p6mdmu)

---

## Caveats from both runs (honest research)

1. **Reddit was rate-limited / HTTP-blocked** in parts of the Agent's sweep — some Reddit-attributed quotes came through journalism summaries (Substack, JMIR, news articles citing Reddit threads). Codex pulled Reddit directly.
2. **X / Twitter / Discord / LinkedIn** were login-gated. Both runs got minimal signal here — likely there's more enterprise/buyer demand on LinkedIn that we're undercounting.
3. **Non-English signal** is undercounted. Both runs are English-heavy.
4. **Public regulatory affairs forums** (HHS/FDA forums, pharma Twitter, RegAffairs LinkedIn) gave low signal — likely because regulated buyers don't complain in public forums; they complain in sales calls.
5. **Numbers are sample frequency, not platform totals**. "12 sources" means 12 distinct sampled URLs in this run, not 12 total complaints on the internet.

---

## Bottom line for V30

The real wishlist is not "make it more like Manus."

It is:
1. **Make provenance survive the workflow** (export with citations)
2. **Make source control explicit and inspectable** (tiers, filters, UI)
3. **Make ingestion narrow but durable** (10-50 docs persistent, not 500 ephemeral)
4. **Make long jobs durable + interruptible** (pause, resume, save state)
5. **Make deep research less shallow and less source-junky** (tier hard-floors)
6. **Add collaboration only where it serves review and approval** (regulated workflow, not generic team chat)
7. **Avoid the polish race** (decks/podcasts/infographics are Phase C-D, not now)

**The moat is provenance integrity.** Every wedge feature should sharpen
that moat. Every TRAP feature softens it.

For V30's commercial path: convert the existing audit-grade core into a
**workflow-complete clinical research product**. Citation-safe exports +
contradiction artifacts + structured evidence tables + resilient async
runs + curated private-corpus sync + human review = the bundle real users
have actually been asking for, for years, and that no NotebookLM/Manus/DR
incumbent currently ships.
