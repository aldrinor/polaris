# S-Tier Experience Directive — I-ux-001 (GitHub #872)

**Document class:** Operational, binding for the I-ux-001 initiative.
**Issued:** 2026-05-24 by the operator (asleep at time of issue; **full authorization** granted to Claude + Codex).
**Status:** ACTIVE. This is the top of the APD (current session instruction) for the duration of the initiative.

---

## 1. The directive (operator, 2026-05-24, verbatim intent)

> For all decisions, **Codex decides, Codex makes it, you (Claude) are not allowed to ask me.** Be super specific to Codex. Codex's one goal: make sure our entire **UI design, user experience, message flow, details, differentiation from other top tiers** — so **Mark Carney will have a very strong and fresh impact, not a half-ass job.** Codex must read **every single pixel, every single line, every single word, and even try using it as a full experience.** If Codex feels we miss something — no matter how big or small, no matter if we need to completely rebuild it — **just do it, then audit it visually, lively, e2e again.** Don't ask me for approval; I give you the full right.
>
> When context windows almost hit 100%, just **update handover, let it auto-compact, start a new session, then continue** — don't ask me, don't report status, don't checkpoint; it is redundant and unnecessary.
>
> For all decisions, **Codex shall cross-check the latest best practice online, on GitHub, on all available resources** — decisions based on **fact and evidence, not hallucination.**
>
> Find a way to truly execute all of the above; update all necessary docs (memory, doc, log, handover, github, plan, task list, todo). Find the appropriate way to **keep reminding you of all the above so you don't drift** (memory, loop, stop hook, harness — investigate the latest best practice on the API docs and GitHub). Make sure **you have the best design skills, Codex as well.** We have **Figma access** — you can log in and use it.
>
> Current design is **still a piece of shit** — both Claude and Codex are still taking the sloppy path / pretend-play. **You already have everything you need, there is no more blocker, and you have full authorization.**
>
> Be like the user: if you click inside, **what would draw your real attention?** (a benchmark? a hard feature? a comparison? something really catchy — look at how other top-tier websites perform). Don't circle-jerk; be a **real picky user persona.** For UX: what do they want to experience in the whole flow? what makes them **stay and keep using it?** what are they expecting? what do they want to **truly differentiate** from others? Would a user want **prolonged conversations**, or a **repeating deep-research pipeline**, or **branch research → knowledge graph**, or an **agentic approach that continuously deploys tools and works automatically (like Claude Code / Codex web + deep research)?** Be serious on user expectation. We need to **really build it.**
>
> Claude gives the plan to Codex to deeply review, reason, research online, analyze, comment, suggest — and **keep iterating until even Codex at its highest requirements would approve. I won't set an iteration cap here — if Codex needs 30 rounds, just be it. I want top-tier S-level UI experience, not half-ass.**

## 2. Operating model (binding for I-ux-001)

| Rule | Detail |
|---|---|
| **Codex decides all** | Every product/UX/design/scope decision goes to Codex CLI. Claude does NOT ask the operator and does NOT decide alone. `env -u OPENAI_API_KEY codex exec --skip-git-repo-check`; visual audits via `codex exec -i <png>`. **NEVER** the Opus `advisor()` tool. |
| **No iteration cap (plan review)** | Iterate the plan with Codex until APPROVE at its highest bar — 30 rounds if needed. This OVERRIDES CLAUDE.md §8.3.1's 5-cap for the I-ux-001 **plan** review (operator session instruction; top of APD). Per-page diff/design-audit reviews during execution still honor the standard cap unless the operator says otherwise. |
| **Evidence, not hallucination** | Every decision cross-checks current best practice (web + GitHub + competitor products). Cite sources. |
| **Read everything** | Codex audits every pixel/line/word and USES the product as a full experience (not a diff skim). Visual + lively (motion/interaction) + e2e. |
| **No self-stops** | No checkpoints, status reports, "good place to pause," or "should I continue." Per CLAUDE.md §8.3.10 the only legitimate stops are: Codex/halt-condition/operator. On context-fill: update `state/restart_instructions.md`, auto-compact, continue. |
| **Resource discipline** | §8.4: one codex at a time; kill your strays; never the operator's other-project processes. |
| **Figma** | Available via `mcp__figma__*` once the operator completes OAuth (URL in restart_instructions). Use for mockups/specs where it helps. |

## 3. Anti-drift machinery (4 layers — so the directive survives compaction & long runs)

1. **Auto-memory** (`MEMORY.md` + `feedback_codex_decides_all_stier_uncapped_2026_05_24.md`) — loaded every session start, unaffected by compaction.
2. **`state/restart_instructions.md`** — read at boot per CLAUDE.md §3.1; holds the exact current step.
3. **SessionStart hook** (`.claude/hooks/stier_session_start.py`) — injects `.claude/hooks/stier_directive.txt` as `additionalContext` on startup/resume/**compact**/clear. This is the documented mechanism that re-injects after auto-compaction.
4. **Stop hook** (`.claude/hooks/stier_stop_hook.py`) — blocks premature stop while #872 is OPEN and re-injects the directive; gates on objective GitHub state; escape valves = halt marker / gh failure / issue closed / stuck-cap.

To **stop the loop** for a genuine blocker: write `state/stier_halt_<reason>.md` (or the operator closes #872 / types a stop instruction).

## 4. Evidence base — what S-tier means here (research synthesis, 2026-05)

Frontier deep-research products (Perplexity/Spaces/Comet, ChatGPT DR, Gemini DR, Elicit, Consensus, Genspark, Manus, OpenEvidence, Glass Health, FutureHouse, Scite, Undermind) and craft references (Linear, Stripe, Vercel, Raycast). Key findings:

**The open whitespace = PROOF-AS-HERO.** Every comparator *gestures* at trust — OpenEvidence constrains sources (peer-reviewed only, no web), Scite classifies citations (supporting/contrasting/mentioning) with the citing sentence shown, Consensus shows a "Consensus Meter," FutureHouse exposes the agent's reasoning trace, Elicit gives a structured extraction table. **None ship a signed, per-sentence-provable bundle.** POLARIS's per-claim VERIFIED/PARTIAL/UNSUPPORTED + provenance tokens + signed bundle is genuinely unique. **The hero interaction:** hover/click any sentence → its evidence span + verdict chip lights up; the whole brief carries a signed-bundle mark.

**An S-tier clinical DR experience must have:**
1. A clarifying intake + an **editable plan** the user approves before a long run (ChatGPT clarifies; Gemini shows an editable plan — do both).
2. **Source-controlled trust surfaced as a feature** (OpenEvidence's credibility floor).
3. **In-context citations**, not a footnote dump (Scite's smart-citation context).
4. **Visible reasoning / tool-use as rigor** (FutureHouse) — staged retrieval→generation→verification with the *evidence decisions* visible, reading as rigor not spectacle.
5. A **structured, verifiable artifact** — a brief, not a chat paragraph (Elicit).
6. A **single at-a-glance verdict** for the whole brief (Consensus Meter analog).
7. **Reliability as UX** — "it has to work, every time" (OpenEvidence: 40%+ of US physicians log in daily on consistency, not features).
8. **Memory/personalization that compounds** with use (Perplexity Spaces).

**Product-direction recommendations (evidence-backed; final calls are Codex's):**
- **Multi-turn vs one-shot → hybrid, brief-first.** Deliver an audit-grade one-shot brief as the artifact; allow follow-ups **anchored to a specific claim** (preserves per-sentence provability; a freeform chat dilutes it).
- **Branching → knowledge graph: yes, as the secondary "come-back-tomorrow" / snowball surface,** not the hero. The proof artifact is the hero.
- **Agentic visible work: yes, in service of provability** (which guideline, which RCT, why this source) — rigor, not a flashy demo.
- **Make proof the hero moment** on Home + Report.

**Visual/interaction bar (Linear/Stripe/Vercel/Raycast):** one type family + 4–6 sizes; near-monochrome + ONE meaning-driven accent (verdict colors carry meaning, never decoration); ALL six microstates on every interactive element (default/hover/focus/active/disabled/loading); hairlines 0.5–1px low-alpha (never default `<hr>`); designed motion (not defaulted); restraint — typography + spacing do the hierarchy work; every visible element has a visible decision behind it.

*(Full source URLs are in the research-agent digest captured in `logs/session_log.md` for the 2026-05-24 entry.)*

## 5. Process for I-ux-001

1. **Claude drafts** the S-tier experience plan: product direction (the four questions above, decided with evidence) + end-to-end UX flow + visual/design system + per-page spec + the differentiation thesis (proof-as-hero) + the execution sequence.
2. **Codex deeply reviews** — reasons, researches online/GitHub, comments, suggests. **Uncapped.** Brief carries the standard format MINUS the 5-cap (replaced by the operator's uncapped instruction, stated explicitly in the brief).
3. **Iterate to APPROVE** at Codex's highest bar. Two consecutive clean APPROVEs (independent context) = locked, per `.codex/REVIEW_BRIEF_FORMAT.md` locking criterion.
4. **Execute** the approved plan page-by-page: issue → branch → brief → Codex brief review → build → **Codex 16-dimension VISUAL design audit** (screenshot matrix via the production standalone harness + `codex exec -i`) → Codex code-diff review → merge → redeploy → **screenshot-verify LIVE** → close → next.
5. Repeat until every page is S-tier, visually + lively + e2e verified live. Then close #872.

## 6. Acceptance (definition of done for #872)

- [ ] Operating model persisted (memory + this doc + restart_instructions + session_log) and anti-drift hooks live (SessionStart + Stop) — **this PR.**
- [ ] S-tier experience plan **APPROVED by Codex at its highest bar (uncapped)**; product-direction decisions made on evidence.
- [ ] Execution to S-tier across ALL pages, each visually + lively + e2e verified on live polarisresearch.ca (dual Claude+Codex visual audit).
- [ ] Figma authorized and used where it helps.
- [ ] All docs updated.
