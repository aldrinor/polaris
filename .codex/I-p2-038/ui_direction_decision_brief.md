# Codex DECISION — best path to top-tier UI for the Carney demo (umbrella #821 / I-p2-038)

You are the DECISION-MAKER (CHARTER §1). Decide the UI roadmap: priority order +
the verification approach for auth-gated pages + any systemic gap. Be specific and
filter for real leverage. This is a PLANNING decision, not a gate review.

## HARD CONSTRAINTS (operator-locked — do NOT reopen, relax, or "offer a fallback")
- **Top-tier bar** = Perplexity / ChatGPT-Deep-Research-competitive AND audit-grade.
  POLARIS's differentiator is PER-SENTENCE verifiability against primary sources,
  NOT length (length is liability in clinical context).
- **"Complete" = top-tier VISUALLY-VERIFIED LIVE** on polarisresearch.ca. Merged ≠ done.
- Demo recipient: PM Mark Carney; demo window ~Aug 31–Sep 6 (one-shot gift).
- **Honest sovereignty framing ONLY**: "Canadian-hosted" (OVH Québec VM, true today);
  production LLM inference is OpenRouter (US, transitional), disclosed at /transparency.
  NO "Sovereign"/"no US vendor" present-tense overclaim (§-1.1; just fixed in footer).
- Models LOCKED: generator DeepSeek V4 Pro + evaluator Gemma 4 31B (two-family).
  Hosting LOCKED: non-US Canadian OVH Québec.
- Codex decides; Claude executes via the per-issue Codex-gated workflow.

## Grounded current state (from THIS session's LIVE screenshots of polarisresearch.ca + code, NOT docs)
- **Home (/)** — proof-as-hero: leads with a REAL verified SURPASS-2 claim + its exact
  cited source span highlighted in real context. Strong differentiator surface. Live. ~A-.
- **Report / Inspector (/inspector/<id>)** — the CENTERPIECE "Proof Replay" split-view
  (verified claims left → exact highlighted source span right). POLARIS's killer view.
  Live + offline-renderable from a signed bundle (no GPU). Strong.
- **Intake (/intake)** — clean "Ask a clinical research question", internal jargon removed,
  benefit copy. Good.
- **Global shell (every page)** — JUST SHIPPED + LIVE this session: shared institutional
  footer (honest Canadian-hosted + OpenRouter/`/transparency` disclosure, public links) +
  Sign in/Sign out affordance (was missing on every page but home). Fills the former empty
  void. BUT the primary nav is a flat **9-item bar** (Home·Intake·Dashboard·Upload·
  Benchmark·Compare·Contracts·Pin Replay·Memory) exposing internal tools to an unauth
  viewer — reads like a dev-tool menu, not institutional. "Intake" is internal jargon.
  Open Codex P2: tablet/small-desktop horizontal budget.
- **Demo-journey MIDDLE — Plan (/plan), Run-progress (/runs/<id>), Compare (/compare)**:
  BUILT (#754/#755/#757/#758) but I CANNOT verify them live — all auth-gated (401 →
  /sign-in) and need a real completed run; I do NOT hold the demo reviewer credential, so
  I have NOT seen these rendered. This is the Carney-critical click-path AND the biggest
  unknown in the product.
- **Utility pages (Upload, Contracts, Pin Replay)** — public, functional, but PLAIN: content
  top-loads then a barren expanse; Pin Replay's empty state is one gray line in a void.
  Secondary (Carney won't tour the Evidence-Contract editor).
- **Knowledge-graph (#758), Audit/export (#759)** — built, unverified-live.
- ~20 routes total; component library (#743–#751: citation chip, verdict chip, source card,
  Proof Replay, state kit, kg viz) is built and Codex-reviewed.

## DECISION REQUEST
With ~3.5 months to demo and the top-tier bar above, decide:
1. **Priority order** of UI work to reach top-tier. Candidates: (a) demo-journey-middle
   verify+polish; (b) nav-IA redesign (lean auth-aware nav, de-clutter, kill "Intake"
   jargon, fix tablet budget); (c) holistic design-system consistency pass across all pages;
   (d) utility-page polish; (e) knowledge-graph + audit/export polish.
2. **Verification approach for the auth-gated demo-journey-middle** — this is a hard blocker:
   Claude cannot certify "top-tier live" on pages it cannot see. Options: operator provides
   a demo reviewer cred so Claude screenshot-audits the live journey; build an offline/fixture
   render path (as /inspector already has); local authed render. Decide.
3. **Systemic gap** — is there a design-system / visual-consistency risk across 20+ pages
   that warrants a consistency pass BEFORE per-page polish, or is per-page the right grain?

## Claude's lean (confirm or correct — push back hard if you disagree)
The demo-journey-MIDDLE is highest-leverage: it is literally what Carney clicks through AND
it's the biggest unknown (built but unseen). So P1 = unblock its verification, then audit it
to the bar. Nav-IA is every-page chrome + a genuine "looks like a dev tool" wart → P2. A
design-system consistency pass may underpin both. Utility pages = lowest.

## Output (machine-parseable)
```yaml
decision_summary: <2-3 sentences>
priority_order:
  - <rank: item — 1-line rationale>
journey_middle_verification: <approach to unblock + audit plan/run/compare>
systemic_gap: <design-system/consistency finding, or "none">
first_issue_to_open: <the single next issue Claude should start>
risks: [...]
```
