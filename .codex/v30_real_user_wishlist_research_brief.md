REAL user wishlist research — xhigh reasoning + full web access.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## User mandate (verbatim, the corrective)

> "You just repeated what I wrote, why you and codex, don't
> really go on github and forum, to find the user wish list
> here, and give me the full wish list, so we can plan from
> that"

The user is correctly calling out that the prior analysis only
analyzed the user's OWN message verbatim. That's not user
research; that's a self-mirror. The real wishlist lives in:

  - GitHub issues + discussions of NotebookLM clones (e.g.
    open-notebooklm, llama-stack, AnythingLLM, Khoj, Cline,
    private-gpt, OpenWebUI)
  - GitHub issues for Perplexity-style projects (Perplexica,
    farfalle, etc.)
  - Manus AI feedback threads, X/Twitter discourse, ProductHunt
    comment threads
  - r/ChatGPTPro, r/OpenAI, r/perplexity_ai, r/LocalLLaMA,
    r/singularity, r/MachineLearning, r/medicine,
    r/medicalresearch, r/biotech, r/RegulatoryAffairs
  - Hacker News comment threads on NotebookLM, ChatGPT Deep
    Research, Gemini Deep Research, Manus launches
  - Discord communities (Cursor, Aider, OpenInterpreter, etc.)
  - GitHub Discussions for major OSS deep-research repos
  - Researcher / clinician / regulatory-affairs pain-point posts

## Your job

GO TO THE WEB. Use WebSearch + WebFetch aggressively. Don't
synthesize from training data — pull actual quotes, GitHub issue
URLs, Reddit thread URLs, HN comment URLs.

## Coverage targets

  1. **NotebookLM user complaints + feature requests** (Reddit
     r/notebooklm, Google support forum threads, X/Twitter
     mentions, GitHub clone repos' issue trackers)
  2. **Perplexity Pro / Spaces / Pages user requests** (Reddit
     r/perplexity_ai, GitHub issues for Perplexica/farfalle,
     ProductHunt comments)
  3. **ChatGPT Deep Research complaints** (Reddit r/ChatGPTPro,
     r/OpenAI, HN threads)
  4. **Gemini Deep Research feedback** (Reddit, X, Google
     Workspace forums)
  5. **Manus AI complaints + wish list** (X/Twitter early
     access threads, Reddit r/ManusAI if exists, HN launch
     comment threads)
  6. **Researcher / academic / clinician pain points** (Reddit
     r/medicine, r/AskScienceDiscussion, r/AcademicTwitter,
     researcher Twitter threads on AI research tools)
  7. **OSS deep-research project issues** (open-deep-research,
     stork-search, Khoj, AnythingLLM, OpenWebUI — feature-request
     issue counts + top-upvoted)
  8. **Regulated-industry buyer feedback** (pharma Twitter,
     LinkedIn posts from regulatory affairs / medical writing
     consultants, HHS/FDA forum posts complaining about AI tool
     limitations for clinical use)

## What to extract per source

For each source you cite, capture:
  - Source URL + date
  - Verbatim quote of the user wish/complaint
  - Estimated audience size (subreddit subscriber count, GH stars,
    HN points)
  - Whether it overlaps a wish the project's user already named
    or is NEW

## Categories I want documented (the OUTPUT taxonomy)

Group findings into these categories. ADD categories if the data
demands it:

  A. INPUT — what users want to feed in
     A.1 File upload formats (PDF, DOCX, slides, audio, video,
         scanned images, EHR exports, lab data, etc.)
     A.2 Bulk/batch upload
     A.3 Continuous source ingestion (live RSS, journal feeds,
         clinicaltrials.gov)
     A.4 Internal/private corpus integration (SharePoint, Notion,
         Confluence, OneDrive)
     A.5 Scope control (date ranges, source-tier filters,
         language filters, geo filters)

  B. PROCESSING — what users want done with the input
     B.1 Wiki-style internal-corpus synthesis
     B.2 Snowball/iterative knowledge accumulation
     B.3 Cross-document conflict / contradiction surfacing
     B.4 Hypothesis testing (does X support/refute Y?)
     B.5 Temporal trend analysis
     B.6 Audit trail + reproducibility
     B.7 Custom analysis pipelines (user-defined steps)
     B.8 Multi-modal analysis (text + images + tables together)

  C. OUTPUT — what artifacts users want produced
     C.1 Long-form research report
     C.2 Slide deck (Manus-class, 1-click)
     C.3 Video / audio overview (NotebookLM-class)
     C.4 Infographic / poster
     C.5 Charts (forest plots, KM curves, scatter, etc.)
     C.6 Tables / spreadsheets (CSV/XLSX exportable)
     C.7 Citation bibliography (BibTeX/RIS/EndNote)
     C.8 PDF/DOCX with branding
     C.9 Interactive HTML / dashboard
     C.10 Email/Slack digest
     C.11 API JSON for downstream tools

  D. COLLABORATION — multi-user features
     D.1 Workspace / team sharing
     D.2 Comments / annotations
     D.3 Version history + diff
     D.4 Approval workflows (medical-writing review)
     D.5 Real-time co-edit
     D.6 Notifications

  E. INTERFACE — how users want to interact
     E.1 Chat-style conversational interface
     E.2 1-click magic ("just give me a deck")
     E.3 Long-running task ("come back in 2h")
     E.4 Progressive disclosure (preview → drill down)
     E.5 Side-by-side comparison (multi-doc)
     E.6 Mobile / responsive
     E.7 Voice input / output
     E.8 Browser extension

  F. TRUST + GOVERNANCE — what users need to trust the output
     F.1 Inline citations
     F.2 Confidence calibration / uncertainty markers
     F.3 Source-tier disclosure
     F.4 Contradiction disclosure
     F.5 Reasoning trace
     F.6 Reproducibility (same input → same output)
     F.7 Audit trail + access logs
     F.8 PII / PHI handling
     F.9 Compliance (SOC2, HIPAA, GDPR)
     F.10 Bias / hallucination flags

  G. INTEGRATION — connect to other tools
     G.1 Reference managers (Zotero, Mendeley, EndNote)
     G.2 Note-taking apps (Notion, Obsidian, Roam)
     G.3 LMS / EHR systems
     G.4 Code / IDE (Cursor, VSCode)
     G.5 BI / analytics tools
     G.6 Slack / Teams / Discord
     G.7 GitHub / GitLab

  H. CUSTOMIZATION + CONTROL
     H.1 User-defined personas / writing style
     H.2 Pinned / preferred sources
     H.3 Excluded sources / blocklists
     H.4 Custom scope templates (regulatory, oncology, etc.)
     H.5 Brand styling (corporate templates)
     H.6 Self-hosted / on-prem deployment
     H.7 BYOK (bring your own key)
     H.8 Model selection (GPT-5, Claude, open weights)

  I. ECONOMICS
     I.1 Free tier
     I.2 Pricing model (per-query, per-seat, usage-based)
     I.3 Cost preview before run
     I.4 Quota / rate limits

## What I want in the output

Write to `outputs/codex_findings/v30_real_user_wishlist/findings.md`:

```markdown
# Real User Wishlist for Top-Tier Research AI Products

Sources surveyed: [list each source with URL]
Date of research: 2026-04-26

## Methodology
[How you searched, what you sampled, what languages, what
caveats apply]

## Top 30 user wishes by frequency

For each wish:
  - Wish (1 sentence)
  - Frequency (how many distinct sources mentioned this)
  - Audience (which user segments — researcher, clinician,
    regulatory affairs, exec, student, etc.)
  - 2-3 verbatim quotes with source URLs
  - Category from taxonomy above
  - Whether V30 Phase-2 already supports / partial / not
  - Build cost estimate (engineering days)
  - Moat-impact for V30 (dilute/neutral/amplify)

## Pain-point clusters

Group wishes into 5-7 pain clusters that map to USER MOMENTS,
not features. (e.g., "I uploaded 200 PDFs and the chat got
slow", or "I gave NotebookLM 5 papers and the audio
hallucinated a result that wasn't in any of them".)

## Surprises Claude+the user did NOT name

Wishes from real user data that the user's message did NOT
mention. These are the most valuable findings.

## Trap pattern detection

Top user wishes that would be TRAPS for V30 (would force
competing on the wrong axis). Specifically: which features
have HIGH user demand but LOW differentiation potential for
audit-grade discipline?

## Recommended V30 wedge bundle

After all the data, what 8-12 features should V30 ship in the
clinical-only beta to capture the highest-priority real user
demand WITHOUT diluting the audit-grade moat?

## Real-user voice — verbatim
[5-10 longer verbatim quotes that capture the strongest user
sentiments, attributed by source URL]
```

## Constraints

  - DO NOT pad the analysis with synthesized content. Every
    finding must trace to a real source URL.
  - If a category has no real-world data after a good-faith
    search, say "no signal found" — don't make up demand.
  - Pull from at LEAST 30 distinct sources across reddit,
    github, hackernews, twitter/X, productHunt, forum threads.
  - If a region/language has different signal (Chinese
    knowledge-base community, Japanese researcher tools,
    European GDPR-driven requests), call that out.
  - Bias check: NotebookLM and Manus communities will skew
    toward those products' specific UX. Counterbalance with
    OSS deep-research community signals (open-deep-research,
    Khoj, Mirascope, etc.) which often surface different needs.

Up to 1000 lines if the data demands it. Full xhigh budget.
Pull verbatim quotes — that's the deliverable.
