# Real User Wishlist for Top-Tier Research AI Products

Sources surveyed: see Source Register below.
Date of research: 2026-04-26

## Methodology

This is web-only user research. I sampled public user feedback across Reddit, GitHub issues/discussions, Hacker News, Product Hunt, Google help/community pages, and public OSS deep-research communities. I prioritized:

- NotebookLM user complaints and extensions trying to patch them.
- Perplexity-style user requests and OSS Perplexity clone issues.
- ChatGPT Deep Research pain threads.
- Gemini Deep Research/HN feedback.
- Manus early-user complaint threads.
- OSS knowledge-base/deep-research issue trackers where users ask for missing capabilities in concrete terms.
- Research-integrity discussion where citation failure is a real cost, not a cosmetic annoyance.

Sampling notes:

- Frequency counts below are counts of distinct sampled sources in this document, not global platform totals.
- Dates are exact when the platform surfaced an exact date. When a platform only surfaced a relative timestamp in the snippet, I kept the platform-relative date signal and noted that in the source row.
- Audience size is an estimated audience signal, not exact reach. I used subreddit member count when available, GitHub star count for repos, Product Hunt followers/reviews, or HN points/comments.
- Public X/Twitter, LinkedIn, and Discord signals were weak or login-gated in this environment. I did not fabricate those.
- The sample is English-heavy. I did observe some non-English comments in Manus and NotebookLM threads, but not enough to quantify separate regional demand with confidence.
- Bias check: consumer communities overweight UX pain, while OSS issue trackers overweight integrations, self-hosting, and control. HN overweights skepticism and trust failures. I used all three on purpose.

## V30 Phase-2 Baseline Used For Support Mapping

Local repo evidence, not web synthesis:

- `docs/todo_list.md`: V30 is a report-contract architecture with deterministic fetch, explicit gap rendering, and hybrid human completion.
- `scripts/run_full_scale_v30_phase2.py`: V30 Phase-2 ships report-contract schema, deterministic live fetch, slot-bound generation, validation, coverage manifest, and human/licensed gap completion.
- `src/polaris_graph/v30_sweep_integration.py`: writes `frame_coverage_report`, `human_gap_tasks.json`, and report disclosure text; V30 is explicitly audit-oriented.
- `outputs/full_scale_v30_phase2_run14/clinical/clinical_tirzepatide_t2dm/report.md`: long-form markdown report with inline `[N]` citations, methods, explicit limitations, and contradiction disclosures.
- `outputs/full_scale_v30_phase2_run14/clinical/clinical_tirzepatide_t2dm/manifest.json`: `contradictions_found = 14`, `frame_coverage_report`, corpus tier fractions, budget, and adequacy metadata.
- `.codex/v30_phase2_run14_substance_density_audit_brief.md`: records `112` inline citations in run-14 and explicit contradiction disclosure.

Practical read: V30 already has a narrow but differentiated trust core for clinical reports. It does not yet have consumer-grade ingestion UX, collaboration, artifact generation, or connector breadth.

## Source Register

| ID | Source | Date | Audience signal | Overlap vs user prompt | URL |
|---|---|---:|---|---|---|
| S01 | Reddit: `r/notebooklm` "Smarter File Import & Automation" | 2025-07-15 | `r/notebooklm` about `121K` members | overlap | https://www.reddit.com/r/notebooklm/comments/1m0e2p3 |
| S02 | Reddit: `r/notebooklm` "NotebookLM not reading entire source" | 2025-02-25 | `r/notebooklm` about `121K` members | overlap | https://www.reddit.com/r/notebooklm/comments/1ixpxj4/notebooklm_not_reading_entire_source/ |
| S03 | Reddit: `r/notebooklm` "Search function for Notebook sources" | 2026-04-23 | `r/notebooklm` about `121K` members | new | https://www.reddit.com/r/notebooklm/comments/1stu5v8/search_function_for_notebook_sources/ |
| S04 | Reddit: `r/notebooklm` "Citations in saved notes" | 2025-02-25 | `r/notebooklm` about `121K` members | new | https://www.reddit.com/r/notebooklm/comments/1ge2v7z/citations_in_saved_notes/ |
| S05 | Reddit: `r/notebooklm` same-source citation bug | 2026-04-16 | `r/notebooklm` about `121K` members | overlap | https://www.reddit.com/r/notebooklm/comments/1snhj6g/notebooklm_is_quoting_the_same_source_for/ |
| S06 | Reddit: `r/notebooklm` inline source viewer workaround | 2026-03-07 | `r/notebooklm` about `121K` members | new | https://www.reddit.com/r/notebooklm/comments/1rn97qa/view_original_source_inside_notebooklm_web_pages/ |
| S07 | Reddit: `r/notebooklm` image handling complaint | 2026-03-04 | `r/notebooklm` about `121K` members | overlap | https://www.reddit.com/r/notebooklm/comments/1rkvgvz/cant_specify_images_in_notebooklm/ |
| S08 | Reddit: `r/notebooklm` "FOSS NotebookLM with no data limits" | 2026-04-22 | `111` post upvotes, `r/notebooklm` about `121K` members | overlap | https://www.reddit.com/r/notebooklm/comments/1ssb4nv/foss_notebooklm_with_no_data_limits/ |
| S09 | Reddit: `r/notebooklm` "NotebookLM for Teams" | 2026-01-27 | `70` post upvotes, `r/notebooklm` about `121K` members | overlap | https://www.reddit.com/r/notebooklm/comments/1qo9ueh/notebooklm_for_teams/ |
| S10 | Product Hunt: Perplexity reviews summary | 2026 review page | `4.7K` followers, `88` reviews | overlap | https://www.producthunt.com/products/perplexity-ai/shoutouts/292731 |
| S11 | Hacker News: "What's Your Take on Perplexity AI?" | HN relative date `7 months ago` captured 2026-04-26 | `2` points, `2` comments | overlap | https://news.ycombinator.com/item?id=44860542 |
| S12 | Hacker News: Perplexity defaulting to religious sources | HN relative date `54 days ago` captured 2026-04-26 | `1` point | new | https://news.ycombinator.com/item?id=46675045 |
| S13 | GitHub: Perplexica issue `#824` custom OpenAI provider | 2025-07-13 | Perplexica repo `28.1k` stars | overlap | https://github.com/ItzCrazyKns/Perplexica/issues/824 |
| S14 | GitHub: Perplexica issue `#918` MiniMax endpoint request | 2025-10-29 | Perplexica repo `28.1k` stars | overlap | https://github.com/ItzCrazyKns/Perplexica/issues/918 |
| S15 | GitHub: OpenWebUI issue `#13137` image import/OCR/display | 2025-04-22 | OpenWebUI repo about `16.6k` stars in source snapshot | overlap | https://github.com/open-webui/open-webui/issues/13137 |
| S16 | GitHub: OpenWebUI issue `#7679` per-knowledge-base RAG prompts | 2024-12-07 | OpenWebUI repo about `18.8k` stars in source snapshot | new | https://github.com/open-webui/open-webui/issues/7679 |
| S17 | GitHub: OpenWebUI issue `#13464` notes/search/share/collab | 2025-05-03 | OpenWebUI repo about `18.8k` stars in source snapshot | overlap | https://github.com/open-webui/open-webui/issues/13464 |
| S18 | GitHub: AnythingLLM issue `#3561` auto-add/watch folder | 2025-03-28 | AnythingLLM repo about `6.3k` stars in source snapshot | overlap | https://github.com/Mintplex-Labs/anything-llm/issues/3561 |
| S19 | GitHub Discussion: Khoj `#1250` local filesystem/network docs | 2026-01-28 | Khoj repo `34.2k` stars | overlap | https://github.com/khoj-ai/khoj/discussions/1250 |
| S20 | GitHub Discussion: Khoj `#381` Jira and Confluence | 2023-07-31 | Khoj repo `34.2k` stars, `9` votes on discussion list | overlap | https://github.com/khoj-ai/khoj/discussions/381 |
| S21 | GitHub Discussion: Khoj `#1210` PDF and Word download | 2025-07-24 | Khoj repo `34.2k` stars | overlap | https://github.com/khoj-ai/khoj/discussions/1210 |
| S22 | GitHub Discussion: Khoj `#1124` images not recognized | 2025-02-22 | Khoj repo `33.5k` stars in source snapshot | overlap | https://github.com/khoj-ai/khoj/discussions/1124 |
| S23 | Reddit: `r/ChatGPTPro` export Deep Research to NotebookLM | 2026-03-15 | `61` post upvotes, `r/ChatGPTPro` about `174K` members | overlap | https://www.reddit.com/r/ChatGPTPro/comments/1ru6lbv/oneclick_export_from_chatgpt_to_notebooklm_deep/ |
| S24 | Reddit: `r/ChatGPTPro` Deep Research quota thread | 2026-03-19 | `47` post upvotes, `r/ChatGPTPro` about `174K` members | overlap | https://www.reddit.com/r/ChatGPTPro/comments/1rxnp79/wth_is_this_new_limit_on_deep_research_use_in_pro/ |
| S25 | Reddit: `r/ChatGPTPro` report disappeared after run | 2025-10-02 | `5` post upvotes, `r/ChatGPTPro` about `174K` members | new | https://www.reddit.com/r/ChatGPTPro/comments/1nw9qkn |
| S26 | Reddit: `r/ChatGPTPro` cross-vendor synthesis because of omissions | 2025-12-09 | `r/ChatGPTPro` about `174K` members | overlap | https://www.reddit.com/r/ChatGPTPro/comments/1pi9c0k/for_anyone_whos_tried_both_how_different_is/ |
| S27 | Reddit: `r/ChatGPTPro` "Is deep research getting less deep?" | 2025-05-05 | `8` post upvotes, `r/ChatGPTPro` about `174K` members | overlap | https://www.reddit.com/r/ChatGPTPro/comments/1kexqb3 |
| S28 | Reddit: `r/ChatGPTPro` export Deep Research output | 2025-02-27 | `r/ChatGPTPro` about `174K` members | overlap | https://www.reddit.com/r/ChatGPTPro/comments/1iz30e6 |
| S29 | Hacker News: "How to Use Deep Research?" | HN relative date `11 months ago` captured 2026-04-26 | `22` points, `17` comments | overlap | https://news.ycombinator.com/item?id=43603574 |
| S30 | Hacker News: Gemini Deep Research comment thread | HN relative date `11 months ago` captured 2026-04-26 | comment on DR thread | overlap | https://news.ycombinator.com/item?id=43627354 |
| S31 | Reddit: `r/AI_Agents` Manus overhyped/scammy thread | 2025-08-23 | low-vote thread, high-severity complaint | overlap | https://www.reddit.com/r/AI_Agents/comments/1myfaei/manus_ai_the_most_overhyped_scammy_ai_platform/ |
| S32 | Reddit: `r/ManusOfficial` billing/refund complaint thread | 2025-11-28 | low-vote thread, high-severity complaint | overlap | https://www.reddit.com/r/ManusOfficial/comments/1p6mdmu/manus_is_scamming_beware/ |
| S33 | Reddit: `r/technology` hallucinated citations in literature | 2026-04-05 | `6221` upvotes | overlap | https://www.reddit.com/r/technology/comments/1sd0khs/hallucinated_citations_are_polluting_the/ |
| S34 | Hacker News comment on citation reliability | HN relative date `3 days ago` captured 2026-04-26 | single comment in active thread | overlap | https://news.ycombinator.com/item?id=47345819 |
| S35 | Hacker News: open-source NotebookLM alternative using Morphik | HN relative date `11 months ago` captured 2026-04-26 | `23` points | overlap | https://news.ycombinator.com/item?id=43529539 |

## Top 30 User Wishes By Frequency

### 1. Accurate, multi-source citations that do not hallucinate, collapse to one source, or point to the wrong passage

Frequency: `12` distinct sources (`S02 S04 S05 S10 S11 S12 S23 S26 S29 S30 S33 S34`)

Audience: researchers, students, analysts, clinicians, skeptical power users

Quotes:

> "the quotations are only from one source and its always the first or last page."
Source: [S05](https://www.reddit.com/r/notebooklm/comments/1snhj6g/notebooklm_is_quoting_the_same_source_for/)

> "either they don't exist or don't actually say what I want."
Source: [S33](https://www.reddit.com/r/technology/comments/1sd0khs/hallucinated_citations_are_polluting_the/)

Category: `F.1 Inline citations`, `F.4 Contradiction disclosure`, `F.10 Bias/hallucination flags`

V30 Phase-2 status: `partial`

Why: V30 already emits inline `[N]` citations and explicit contradiction disclosures, but it is not yet a general-purpose research UI and still depends on corpus quality.

Build cost estimate: `4-7d`

Moat impact for V30: `amplify`

### 2. Export the output with citations preserved, not stripped away

Frequency: `8` distinct sources (`S04 S17 S21 S23 S28 S10 S08 S06`)

Audience: researchers, students, medical writers, analysts

Quotes:

> "Saved notes need to preserve their links to the original citations."
Source: [S04](https://www.reddit.com/r/notebooklm/comments/1ge2v7z/citations_in_saved_notes/)

> "adding the PDF and Word file download capability"
Source: [S21](https://github.com/khoj-ai/khoj/discussions/1210)

Category: `C.7 Citation bibliography`, `C.8 PDF/DOCX`, `C.11 API JSON`

V30 Phase-2 status: `partial`

Why: V30 produces `report.md`, `manifest.json`, and bibliographic traceability, but not user-facing PDF/DOCX export with citation retention.

Build cost estimate: `3-5d`

Moat impact for V30: `amplify`

### 3. Search, filter, and quickly find sources inside a large notebook or workspace

Frequency: `6` distinct sources (`S03 S17 S08 S09 S04 S06`)

Audience: heavy NotebookLM users, students, researchers, operations users

Quotes:

> "a search bar would help a lot"
Source: [S03](https://www.reddit.com/r/notebooklm/comments/1stu5v8/search_function_for_notebook_sources/)

> "notes search"
Source: [S17](https://github.com/open-webui/open-webui/issues/13464)

Category: `A.5 Scope control`, `E.4 Progressive disclosure`

V30 Phase-2 status: `not`

Build cost estimate: `2-4d`

Moat impact for V30: `neutral`

### 4. Folder, tag, and grouping primitives for source organization

Frequency: `6` distinct sources (`S01 S08 S09 S17 S03 S35`)

Audience: students, knowledge workers, team researchers

Quotes:

> "Add folders, tags, and grouping features"
Source: [S01](https://www.reddit.com/r/notebooklm/comments/1m0e2p3)

> "No folders or workspace organisation"
Source: [S08](https://www.reddit.com/r/notebooklm/comments/1ssb4nv/foss_notebooklm_with_no_data_limits/)

Category: `A.4 Internal/private corpus integration`, `E.4 Progressive disclosure`

V30 Phase-2 status: `not`

Build cost estimate: `3-5d`

Moat impact for V30: `neutral`

### 5. Rename documents and manage source metadata after upload

Frequency: `3` distinct sources (`S04 S03 S08`)

Audience: academic users, students, corpus curators

Quotes:

> "why can't I rename the uploaded documents to something sensible"
Source: [S04](https://www.reddit.com/r/notebooklm/comments/1ge2v7z/citations_in_saved_notes/)

> "search the titles of the different source files"
Source: [S03](https://www.reddit.com/r/notebooklm/comments/1stu5v8/search_function_for_notebook_sources/)

Category: `A.5 Scope control`

V30 Phase-2 status: `not`

Build cost estimate: `2-3d`

Moat impact for V30: `neutral`

### 6. Batch upload multiple files at once

Frequency: `4` distinct sources (`S01 S08 S09 S35`)

Audience: researchers, students, enterprise knowledge workers

Quotes:

> "manual uploads are slowing my workflow."
Source: [S01](https://www.reddit.com/r/notebooklm/comments/1m0e2p3)

> "Drag and drop multiple files at once"
Source: [S08](https://www.reddit.com/r/notebooklm/comments/1ssb4nv/foss_notebooklm_with_no_data_limits/)

Category: `A.2 Bulk/batch upload`

V30 Phase-2 status: `not`

Build cost estimate: `3-4d`

Moat impact for V30: `neutral`

### 7. Watched folders and continuous auto-sync for new documents

Frequency: `5` distinct sources (`S01 S08 S18 S19 S20`)

Audience: ongoing researchers, ops teams, self-hosters, enterprise users

Quotes:

> "Support binding entire Drive folders to a notebook."
Source: [S01](https://www.reddit.com/r/notebooklm/comments/1m0e2p3)

> "continuously watch the folder for new documents"
Source: [S18](https://github.com/Mintplex-Labs/anything-llm/issues/3561)

Category: `A.2 Bulk/batch upload`, `A.3 Continuous source ingestion`

V30 Phase-2 status: `not`

Build cost estimate: `6-10d`

Moat impact for V30: `neutral`

### 8. Ingest from local filesystem, NAS, and network shares without crawler gymnastics

Frequency: `4` distinct sources (`S18 S19 S08 S35`)

Audience: self-hosters, IT teams, enterprise buyers

Quotes:

> "what if I already have the docs on my server?"
Source: [S19](https://github.com/khoj-ai/khoj/discussions/1250)

> "No RAG system seems to allow that."
Source: [S19](https://github.com/khoj-ai/khoj/discussions/1250)

Category: `A.4 Internal/private corpus integration`, `H.6 Self-hosted / on-prem`

V30 Phase-2 status: `not`

Build cost estimate: `5-8d`

Moat impact for V30: `neutral`

### 9. Internal connectors: Drive, Confluence, Jira, Notion, Slack, OneDrive, and similar private corpora

Frequency: `7` distinct sources (`S01 S08 S09 S19 S20 S35 S17`)

Audience: enterprise buyers, teams, internal research groups

Quotes:

> "Hooking Khoj up to Jira and Confluence would make it really powerful!"
Source: [S20](https://github.com/khoj-ai/khoj/discussions/381)

> "Limited external data sources and service integrations."
Source: [S08](https://www.reddit.com/r/notebooklm/comments/1ssb4nv/foss_notebooklm_with_no_data_limits/)

Category: `A.4 Internal/private corpus integration`, `G.6 Slack / Teams / Discord`

V30 Phase-2 status: `not`

Build cost estimate: `8-15d`

Moat impact for V30: `neutral`

### 10. Unified ingestion across PDFs, docs, slides, audio, images, and web without different rules per entry point

Frequency: `5` distinct sources (`S01 S07 S15 S22 S35`)

Audience: mixed-media researchers, educators, enterprise users

Quotes:

> "Allow all file types ... to be uploaded via both the web interface and Drive"
Source: [S01](https://www.reddit.com/r/notebooklm/comments/1m0e2p3)

> "Currently, the knowledge base in Open WebUI only supports text-based content."
Source: [S15](https://github.com/open-webui/open-webui/issues/13137)

Category: `A.1 File upload formats`, `B.8 Multi-modal analysis`

V30 Phase-2 status: `not`

Build cost estimate: `6-10d`

Moat impact for V30: `neutral`

### 11. Exact source isolation and page/timestamp-level control, so answers do not bleed across the wrong documents

Frequency: `6` distinct sources (`S03 S05 S08 S23 S26 S06`)

Audience: students, researchers, compliance-minded users

Quotes:

> "Sources often bleed together"
Source: [S08](https://www.reddit.com/r/notebooklm/comments/1ssb4nv/foss_notebooklm_with_no_data_limits/)

> "scope it to specific pages/timestamps"
Source: [S08](https://www.reddit.com/r/notebooklm/comments/1ssb4nv/foss_notebooklm_with_no_data_limits/)

Category: `A.5 Scope control`, `E.5 Side-by-side comparison`

V30 Phase-2 status: `partial`

Why: V30 has contract-bound entity scoping, but no user-facing page/time/source selection UX.

Build cost estimate: `5-8d`

Moat impact for V30: `amplify`

### 12. OCR and image-aware knowledge bases

Frequency: `5` distinct sources (`S07 S15 S22 S08 S35`)

Audience: students, analysts, mixed-media researchers

Quotes:

> "Jpg images uploaded show up as an invalid source."
Source: [S07](https://www.reddit.com/r/notebooklm/comments/1rkvgvz/cant_specify_images_in_notebooklm/)

> "Users are unable to import images, have them OCR-processed"
Source: [S15](https://github.com/open-webui/open-webui/issues/13137)

Category: `A.1 File upload formats`, `B.8 Multi-modal analysis`

V30 Phase-2 status: `not`

Build cost estimate: `7-12d`

Moat impact for V30: `neutral`

### 13. Video input and video-grounded analysis, not just text and still images

Frequency: `3` distinct sources (`S07 S35 S08`)

Audience: educators, media researchers, multimodal users

Quotes:

> "NotebookLM just adds AI photos instead of the images I uploaded"
Source: [S07](https://www.reddit.com/r/notebooklm/comments/1rkvgvz/cant_specify_images_in_notebooklm/)

> "turn articles into short video overviews"
Source: [S35](https://news.ycombinator.com/item?id=45916957)

Category: `A.1 File upload formats`, `C.3 Video / audio overview`

V30 Phase-2 status: `not`

Build cost estimate: `8-15d`

Moat impact for V30: `dilute`

### 14. Stop skipping parts of big corpora or pretending the notebook has fewer sources than it does

Frequency: `6` distinct sources (`S02 S05 S08 S23 S27 S30`)

Audience: heavy corpus users, long-form researchers, academics

Quotes:

> "it seems that it hasn't read all of them."
Source: [S02](https://www.reddit.com/r/notebooklm/comments/1ixpxj4/notebooklm_not_reading_entire_source/)

> "it answers '7', even though there are 10 sources uploaded."
Source: [S02](https://www.reddit.com/r/notebooklm/comments/1ixpxj4/notebooklm_not_reading_entire_source/)

Category: `A.2 Bulk/batch upload`, `B.1 Wiki-style internal-corpus synthesis`

V30 Phase-2 status: `partial`

Why: V30 is strong for contract-bound clinical evidence, not arbitrary giant note libraries.

Build cost estimate: `6-10d`

Moat impact for V30: `amplify`

### 15. Higher notebook/source size limits and fewer arbitrary caps

Frequency: `4` distinct sources (`S07 S08 S24 S27`)

Audience: power users, researchers, enterprise analysts

Quotes:

> "There are limits on the amount of sources you can add in a notebook."
Source: [S08](https://www.reddit.com/r/notebooklm/comments/1ssb4nv/foss_notebooklm_with_no_data_limits/)

> "You cannot have sources that exceed 500,000 words"
Source: [S08](https://www.reddit.com/r/notebooklm/comments/1ssb4nv/foss_notebooklm_with_no_data_limits/)

Category: `I.4 Quota / rate limits`, `A.2 Bulk/batch upload`

V30 Phase-2 status: `not`

Build cost estimate: `4-6d`

Moat impact for V30: `neutral`

### 16. Shared workspaces for teams, not solo-only notebooks

Frequency: `5` distinct sources (`S08 S09 S17 S20 S35`)

Audience: teams, labs, enterprise buyers, student groups

Quotes:

> "Lack of multiplayer support."
Source: [S08](https://www.reddit.com/r/notebooklm/comments/1ssb4nv/foss_notebooklm_with_no_data_limits/)

> "Real Time Collaborative Chats"
Source: [S09](https://www.reddit.com/r/notebooklm/comments/1qo9ueh/notebooklm_for_teams/)

Category: `D.1 Workspace / team sharing`, `D.5 Real-time co-edit`

V30 Phase-2 status: `not`

Build cost estimate: `10-15d`

Moat impact for V30: `neutral`

### 17. Comments, annotations, and notes beside the research itself

Frequency: `5` distinct sources (`S08 S17 S04 S06 S09`)

Audience: students, analysts, writers, research teams

Quotes:

> "No way to comfortably take notes alongside your sources"
Source: [S08](https://www.reddit.com/r/notebooklm/comments/1ssb4nv/foss_notebooklm_with_no_data_limits/)

> "share notes"
Source: [S17](https://github.com/open-webui/open-webui/issues/13464)

Category: `D.2 Comments / annotations`

V30 Phase-2 status: `not`

Build cost estimate: `5-8d`

Moat impact for V30: `neutral`

### 18. Real-time collaboration and permissioning for team research

Frequency: `4` distinct sources (`S09 S17 S08 S35`)

Audience: enterprise buyers, internal research teams

Quotes:

> "real-time collaboration"
Source: [S17](https://github.com/open-webui/open-webui/issues/13464)

> "RBAC (Role Based Access for Teams Members)"
Source: [S09](https://www.reddit.com/r/notebooklm/comments/1qo9ueh/notebooklm_for_teams/)

Category: `D.4 Approval workflows`, `D.5 Real-time co-edit`

V30 Phase-2 status: `not`

Build cost estimate: `10-20d`

Moat impact for V30: `neutral`

### 19. Export to PDF, DOCX, and Markdown as first-class output formats

Frequency: `7` distinct sources (`S04 S17 S21 S23 S28 S10 S35`)

Audience: researchers, consultants, writers, students

Quotes:

> "export as .md"
Source: [S17](https://github.com/open-webui/open-webui/issues/13464)

> "download this content as a standard file format (such as PDF or Word)"
Source: [S21](https://github.com/khoj-ai/khoj/discussions/1210)

Category: `C.8 PDF/DOCX with branding`

V30 Phase-2 status: `partial`

Why: markdown exists; office-document export does not.

Build cost estimate: `3-5d`

Moat impact for V30: `neutral`

### 20. One-click handoff into downstream tools while keeping headings and source URLs intact

Frequency: `5` distinct sources (`S23 S28 S04 S21 S35`)

Audience: multi-tool power users, researchers, content teams

Quotes:

> "Automatically extract all cited source URLs"
Source: [S23](https://www.reddit.com/r/ChatGPTPro/comments/1ru6lbv/oneclick_export_from_chatgpt_to_notebooklm_deep/)

> "the most annoying part of the workflow"
Source: [S23](https://www.reddit.com/r/ChatGPTPro/comments/1ru6lbv/oneclick_export_from_chatgpt_to_notebooklm_deep/)

Category: `C.11 API JSON for downstream tools`, `G.6 Slack / Teams / Discord`

V30 Phase-2 status: `partial`

Why: machine-readable manifest/biblio exist, but no polished downstream export flows.

Build cost estimate: `4-7d`

Moat impact for V30: `amplify`

### 21. Structured extraction to tables, CSV, XLSX, and spreadsheet-friendly outputs

Frequency: `3` distinct sources (`S17 S21 S23`)

Audience: analysts, operations, regulated workflows

Quotes:

> "Generated Text or Documents"
Source: [S21](https://github.com/khoj-ai/khoj/discussions/1210)

> "keeps headings/sections/lists"
Source: [S23](https://www.reddit.com/r/ChatGPTPro/comments/1ru6lbv/oneclick_export_from_chatgpt_to_notebooklm_deep/)

Category: `C.6 Tables / spreadsheets`, `C.11 API JSON`

V30 Phase-2 status: `partial`

Why: V30 already emits a trial-summary table and manifest JSON, but not CSV/XLSX deliverables.

Build cost estimate: `3-6d`

Moat impact for V30: `amplify`

### 22. Transparent quotas, credits, and cost signals before users burn time or money

Frequency: `6` distinct sources (`S24 S27 S31 S32 S10 S11`)

Audience: paid users, agent users, budget owners

Quotes:

> "Deep Research isn't unlimited."
Source: [S24](https://www.reddit.com/r/ChatGPTPro/comments/1rxnp79/wth_is_this_new_limit_on_deep_research_use_in_pro/)

> "the agent got stuck hallucinating and looping, which ate up close to 88k credits."
Source: [S31](https://www.reddit.com/r/AI_Agents/comments/1myfaei/manus_ai_the_most_overhyped_scammy_ai_platform/)

Category: `I.3 Cost preview before run`, `I.4 Quota / rate limits`

V30 Phase-2 status: `partial`

Why: run budget caps and cost accounting exist in manifests, but not as a user-facing preflight quote.

Build cost estimate: `2-4d`

Moat impact for V30: `amplify`

### 23. Deep research that is actually deep: more sources, more breadth, less omission

Frequency: `7` distinct sources (`S23 S26 S27 S29 S30 S11 S12`)

Audience: researchers, analysts, power users

Quotes:

> "Outputs are incredibly disappointing compared to before."
Source: [S27](https://www.reddit.com/r/ChatGPTPro/comments/1kexqb3)

> "O3 just provides details, where google will give you a nice overview."
Source: [S27](https://www.reddit.com/r/ChatGPTPro/comments/1kexqb3)

Category: `B.2 Snowball/iterative knowledge accumulation`, `C.1 Long-form research report`

V30 Phase-2 status: `partial`

Why: V30 goes deep in a narrow clinical frame, but not across broad open-web exploratory research.

Build cost estimate: `7-12d`

Moat impact for V30: `amplify`

### 24. Better source-quality control: less SEO sludge, fewer irrelevant or gamed citations, more tier control

Frequency: `7` distinct sources (`S10 S11 S12 S29 S30 S33 S34`)

Audience: researchers, clinicians, skeptical professionals

Quotes:

> "citations to the same blogspam listicles"
Source: [S29](https://news.ycombinator.com/item?id=43603574)

> "8 out of 10 sources were religious publications"
Source: [S12](https://news.ycombinator.com/item?id=46675045)

Category: `A.5 Scope control`, `F.3 Source-tier disclosure`

V30 Phase-2 status: `partial`

Why: V30 already has tier taxonomy and limitations disclosure; extending that into hard source controls would sharpen the moat.

Build cost estimate: `4-7d`

Moat impact for V30: `amplify`

### 25. Durable long-running jobs: do not lose the report, the agent state, or the built artifact

Frequency: `5` distinct sources (`S25 S31 S32 S23 S30`)

Audience: agent users, researchers, paid power users

Quotes:

> "the whole answer is just gone from the chat??"
Source: [S25](https://www.reddit.com/r/ChatGPTPro/comments/1nw9qkn)

> "the system lost everything I built"
Source: [S31](https://www.reddit.com/r/AI_Agents/comments/1myfaei/manus_ai_the_most_overhyped_scammy_ai_platform/)

Category: `E.3 Long-running task`, `F.6 Reproducibility`

V30 Phase-2 status: `partial`

Why: V30 persists artifacts to disk and manifest, but there is no resumable user job UX.

Build cost estimate: `4-8d`

Moat impact for V30: `amplify`

### 26. No vendor lock-in: BYOK, model/provider choice, and endpoint flexibility

Frequency: `5` distinct sources (`S08 S13 S14 S16 S35`)

Audience: self-hosters, advanced technical users, privacy buyers

Quotes:

> "No Vendor Lock-in"
Source: [S08](https://www.reddit.com/r/notebooklm/comments/1ssb4nv/foss_notebooklm_with_no_data_limits/)

> "I want to use Perplexica with the OpenAI-API-compatible `llama_server`"
Source: [S13](https://github.com/ItzCrazyKns/Perplexica/issues/824)

Category: `H.7 BYOK`, `H.8 Model selection`

V30 Phase-2 status: `partial`

Why: the codebase is configurable and self-hostable, but productized BYOK/provider UX is not the current differentiator.

Build cost estimate: `3-5d`

Moat impact for V30: `neutral`

### 27. Knowledge-base-specific prompts, templates, and custom analysis pipelines

Frequency: `5` distinct sources (`S16 S17 S23 S29 S35`)

Audience: domain experts, enterprise teams, advanced users

Quotes:

> "assign them at the knowledge base level"
Source: [S16](https://github.com/open-webui/open-webui/issues/7679)

> "Different knowledge bases require different prompting strategies"
Source: [S16](https://github.com/open-webui/open-webui/issues/7679)

Category: `B.7 Custom analysis pipelines`, `H.4 Custom scope templates`

V30 Phase-2 status: `full`

Why: V30 already has scope templates and report contracts; this is one of the few demand areas where the architecture is already aligned.

Build cost estimate: `2-4d`

Moat impact for V30: `amplify`

### 28. One-click artifact generation: slides, podcasts, quizzes, and derivative outputs

Frequency: `5` distinct sources (`S08 S23 S35 S09 S10`)

Audience: students, educators, creators, general consumers

Quotes:

> "a slide deck"
Source: [S23](https://www.reddit.com/r/ChatGPTPro/comments/1ru6lbv/oneclick_export_from_chatgpt_to_notebooklm_deep/)

> "Audio Overviews"
Source: [S08](https://www.reddit.com/r/notebooklm/comments/1ssb4nv/foss_notebooklm_with_no_data_limits/)

Category: `C.2 Slide deck`, `C.3 Video / audio overview`

V30 Phase-2 status: `not`

Build cost estimate: `8-15d`

Moat impact for V30: `dilute`

### 29. Better mobile and in-car audio use, not desktop-only research artifacts

Frequency: `3` distinct sources (`S08 S10 S23`)

Audience: commuters, students, general consumers

Quotes:

> "poor support for Android auto or car play."
Source: [S08](https://www.reddit.com/r/notebooklm/comments/1ssb4nv/foss_notebooklm_with_no_data_limits/)

> "What is point of those summaries when I can't listen to them while driving??"
Source: [S08](https://www.reddit.com/r/notebooklm/comments/1ssb4nv/foss_notebooklm_with_no_data_limits/)

Category: `E.6 Mobile / responsive`, `E.7 Voice input / output`

V30 Phase-2 status: `not`

Build cost estimate: `6-10d`

Moat impact for V30: `dilute`

### 30. Real human support, predictable billing, and easy cancellation for agent products

Frequency: `4` distinct sources (`S31 S32 S24 S10`)

Audience: paid agent users, enterprise evaluators

Quotes:

> "the lack of any customer support ... feels unacceptable."
Source: [S31](https://www.reddit.com/r/AI_Agents/comments/1myfaei/manus_ai_the_most_overhyped_scammy_ai_platform/)

> "You are taking people's hard-earned money"
Source: [S32](https://www.reddit.com/r/ManusOfficial/comments/1p6mdmu/manus_is_scamming_beware/)

Category: `I.2 Pricing model`, `I.4 Quota / rate limits`

V30 Phase-2 status: `not`

Build cost estimate: `2-4d` plus ops work

Moat impact for V30: `neutral`

## Pain-Point Clusters

### 1. "I uploaded a serious corpus, and now I cannot tell what the model actually used"

Mapped wishes:

- citation accuracy
- source isolation
- source search/filter
- rename/source metadata
- source-tier control

Representative sources: `S03 S04 S05 S08 S29 S33`

### 2. "I got an answer, but I cannot safely carry it into the next workflow"

Mapped wishes:

- citation-preserving export
- PDF/DOCX/Markdown export
- downstream handoff with source URLs intact
- structured table/CSV output

Representative sources: `S04 S21 S23 S28`

### 3. "I want this to stay in sync with my living private knowledge base"

Mapped wishes:

- watched folders
- NAS/local filesystem ingestion
- Drive/Confluence/Jira/Notion connectors
- unified ingestion

Representative sources: `S01 S18 S19 S20`

### 4. "The research job took time or credits, then vanished, got shallow, or got stuck"

Mapped wishes:

- deep-enough research
- quota/cost transparency
- durable long-running jobs
- human support/billing clarity

Representative sources: `S24 S25 S27 S31 S32`

### 5. "I need the tool to understand more than plain text"

Mapped wishes:

- OCR/image import
- video/multimodal support
- large corpus handling

Representative sources: `S07 S15 S22`

### 6. "I am doing this with other people, not alone"

Mapped wishes:

- shared workspaces
- notes/comments/annotations
- real-time collaboration and permissioning

Representative sources: `S08 S09 S17`

### 7. "I cannot trust this for serious research if the citations are fake or the sources are junk"

Mapped wishes:

- citation accuracy
- source-tier control
- contradiction disclosure
- anti-hallucination guardrails

Representative sources: `S11 S12 S29 S30 S33 S34`

## Surprises Claude+the User Did Not Name

These were the most valuable "not in the original ask wording" signals from real users:

1. Citation-preserving export is a recurring deal-breaker.
   Users are not just asking for better research; they are asking for outputs that survive copy/save/export without losing provenance. `S04 S21 S23 S28`

2. Source-library UX is a first-order problem.
   Search-by-title, folders, tags, and renaming show up repeatedly. That is not glamorous, but users keep tripping over it. `S01 S03 S04 S08`

3. Durability and recoverability matter almost as much as answer quality.
   Users get angry when a long research run disappears more than when it is merely mediocre. `S25 S31 S32`

4. Quota opacity erodes trust.
   Hidden caps, silent downgrades to lighter research modes, and credit burn are a core buyer pain, not an afterthought. `S24 S27 S31`

5. Downstream handoff is a real workflow category.
   Users explicitly stitch ChatGPT Deep Research to NotebookLM, notes apps, and export flows because no single tool owns the whole chain. `S23 S28`

6. Human support is part of product trust for agent tools.
   Manus complaints are as much about no human recourse as about model quality. `S31 S32`

7. Car/mobile audio is more salient than expected.
   NotebookLM users explicitly called out Android Auto/CarPlay limitations. That is adjacent to artifact usability, not just voice novelty. `S08`

## Trap Pattern Detection

These are high-demand features that look tempting but would likely push V30 onto a commodity axis:

1. Folders/tags/search.
   Demand is real, but every serious competitor and OSS clone is being pushed there. Necessary eventually, weak wedge now.

2. Broad connector parity.
   Drive/Confluence/Jira/Notion/Slack are table stakes for enterprise knowledge tools. Important, but not differentiating without an audit-grade layer.

3. Slide decks, podcasts, and flashy derivative artifacts.
   Users do want them, but shipping them early invites direct comparison with NotebookLM/Manus polish instead of V30’s audit discipline.

4. Massive model/provider matrix.
   BYOK and provider flexibility are useful, but they are not the reason a regulated buyer will trust a clinical report.

5. Mobile/carplay/audio convenience.
   Consumer demand exists, but it has almost no moat value for an audit-grade clinical wedge.

6. Price competition or "unlimited" positioning.
   Users complain about limits, but competing on cheap unlimited runs is the wrong axis for evidence-grade clinical reporting.

## Recommended V30 Wedge Bundle

Ship these `10` features for the clinical-only beta if the goal is to capture the highest-value real demand without diluting the moat:

1. Locked evidence scopes with hard source-tier and jurisdiction filters.
   Why: directly answers junk-source distrust and amplifies the existing tier taxonomy.

2. Citation-preserving export stack: `report.md`, PDF, DOCX, BibTeX/RIS, and structured bibliography JSON.
   Why: users repeatedly need provenance to survive downstream workflows.

3. Structured evidence tables plus CSV/XLSX export.
   Why: this is where clinical, regulatory, and med-writing users extract operational value.

4. Contradiction matrix with explicit endpoint/population/dose/tier labels.
   Why: V30 already discloses contradictions; turning that into a first-class artifact strengthens the moat.

5. Async resilient jobs with checkpointed manifests and resumable runs.
   Why: real users hate losing long jobs, reports, or agent work.

6. Human review queue with annotation, approval, and version diff for each run.
   Why: this matches regulated writing workflows better than generic collaboration.

7. Gap-task workflow for unverifiable slots.
   Why: this is already native to V30 and uniquely aligned with audit-grade behavior.

8. Clinical/private corpus sync for approved sources only.
   Start with narrow connectors: Drive/SharePoint/Confluence folder sync for curated corpora, not "everything everywhere."

9. Preflight run estimate.
   Show expected runtime, likely source count, and estimated cost before launch.

10. Domain templates for high-value clinical/regulatory moments.
   Examples: label comparison, evidence landscape, trial-summary brief, payer evidence memo.

Not recommended for the wedge phase:

- podcast/audio overview parity
- pretty slide generation
- generic social/mobile UX
- broad consumer notebook features before audit/export/review are solid

## No-Signal / Low-Signal Areas

After good-faith search, I did not find strong public-source signal for these in the sampled set:

- native Zotero/Mendeley/EndNote demand at meaningful frequency
- explicit EHR import requests from public clinician communities
- strong public demand for raw reasoning traces beyond citations and methods disclosure
- explicit HIPAA/SOC2/GDPR complaint threads tied to these exact consumer research products

That does not mean the demand is absent. It means I did not find enough direct public user evidence to claim it confidently.

## Real-User Voice — Verbatim

> "manual uploads are slowing my workflow."
Source: [S01](https://www.reddit.com/r/notebooklm/comments/1m0e2p3)

> "the quotations are only from one source and its always the first or last page."
Source: [S05](https://www.reddit.com/r/notebooklm/comments/1snhj6g/notebooklm_is_quoting_the_same_source_for/)

> "This is a bit of a dealbreaker."
Source: [S04](https://www.reddit.com/r/notebooklm/comments/1ge2v7z/citations_in_saved_notes/)

> "No folders or workspace organisation"
Source: [S08](https://www.reddit.com/r/notebooklm/comments/1ssb4nv/foss_notebooklm_with_no_data_limits/)

> "The annoying part was the handoff"
Source: [S23](https://www.reddit.com/r/ChatGPTPro/comments/1ru6lbv/oneclick_export_from_chatgpt_to_notebooklm_deep/)

> "the whole answer is just gone from the chat??"
Source: [S25](https://www.reddit.com/r/ChatGPTPro/comments/1nw9qkn)

> "Outputs are incredibly disappointing compared to before."
Source: [S27](https://www.reddit.com/r/ChatGPTPro/comments/1kexqb3)

> "citations to the same blogspam listicles"
Source: [S29](https://news.ycombinator.com/item?id=43603574)

> "the agent got stuck hallucinating and looping, which ate up close to 88k credits."
Source: [S31](https://www.reddit.com/r/AI_Agents/comments/1myfaei/manus_ai_the_most_overhyped_scammy_ai_platform/)

> "This is starting to look a lot like a scam"
Source: [S32](https://www.reddit.com/r/ManusOfficial/comments/1p6mdmu/manus_is_scamming_beware/)

## Bottom Line

The real wishlist is not "make it more AI." It is:

- make provenance survive the workflow
- make source control explicit and inspectable
- make ingestion continuous and enterprise-real
- make long jobs durable
- make deep research less shallow and less source-junky
- add collaboration only where it serves review and approval

For V30, the best move is not to chase NotebookLM/Manus surface polish first. The best move is to convert the existing audit-grade core into a workflow-complete clinical research product: citation-safe exports, contradiction artifacts, structured evidence tables, resilient async runs, curated private-corpus sync, and human review.
