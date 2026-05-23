# Codex BRIEF review — I-p2-023 (#762): honest sovereignty wording across shell + panel

HARD ITERATION CAP: 5. iter 1.
- Front-load ALL real findings. Reserve P0/P1 for real risks.
- Verdict APPROVE iff zero NOVEL/continuing P0 AND zero P1.

## OPERATOR-LOCKED context (HARD constraints)
- Sovereignty GOAL = non-US LLM inference at runtime + Canadian data residency (operator memory). The GPU sovereign cluster (OVH Québec vLLM) lands at Session-A (#644), NOT YET live.
- GROUND TRUTH (docs/transparency.md:59 + carney_demo_runbook.md:12): production LLM inference is CURRENTLY OpenRouter (US, deepseek-v4-pro + gemma-4-31b), explicitly "transitional" until the sovereign GPU. transparency.md already discloses this honestly.

## THE PROBLEM (live honesty violation, §-1.1)
The shell mark asserts "⬡ Canadian AI · no external AI vendor" as a PRESENT FACT on every page (app_shell.tsx:44, home_keyboard_shell.tsx:60, + sovereignty_panel.tsx:59). But OpenRouter IS an external US AI vendor at runtime RIGHT NOW. So the mark is FALSE today — it claims the sovereignty goal is already achieved when it isn't (it's disclosed-transitional). This is the same overclaim Codex caught on the #752 home ("no external AI vendor").

## FIX (make the UI tell the truth about current state vs goal)
Replace the false present-tense "no external AI vendor" with TRUE claims + honest transitional disclosure:
- Visible mark → "⬡ Sovereign Canadian deep research" (positioning/mission — same wording the home eyebrow already uses, Codex-APPROVE'd as honest) OR "⬡ Canadian-hosted". (Both true: the app is hosted in OVH Québec.)
- Tooltip (title) → honest: "Hosted in Canada (Québec); public sources fetched via logged Canadian egress. LLM inference is currently routed via OpenRouter (disclosed in /transparency) pending the sovereign Canadian GPU cluster."
- sovereignty_panel.tsx:59 → drop "no external AI vendor"; keep "logged Canadian egress"; add the transitional-LLM honest line (the panel already has honesty guards for signature/two-family — extend the same discipline to the vendor claim).
- 3 files: app_shell.tsx, home_keyboard_shell.tsx, sovereignty_panel.tsx. transparency.md already honest — no change.

## Files I have ALSO checked
- docs/transparency.md (already discloses OpenRouter honestly — the source of truth), docs/carney_demo_runbook.md (LLM=OpenRouter US, transitional), sovereignty_panel.tsx (existing honesty guards).

## Review focus
1. Is dropping "no external AI vendor" + the transitional-LLM disclosure the correct honest reconciliation? Any remaining present-tense sovereignty overclaim in the mark/panel/tooltip?
2. Is "Sovereign Canadian deep research" / "Canadian-hosted" honest (the VM IS in Québec)? Or does even "sovereign" overclaim given transitional US LLM? (If so, prefer "Canadian-hosted".)
3. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
```

---
## iter-2 revision (all iter-1 findings folded)
Implementation targets (the 4 live overclaim sites):
1. **web/components/app_shell.tsx:42,44** — mark → `⬡ Canadian-hosted` (Codex P2: safest visible wording; the VM IS in OVH Québec). Tooltip → "Hosted in Canada (Québec); public sources fetched via logged Canadian egress. LLM inference is currently routed via OpenRouter (US, disclosed in /transparency) pending the sovereign Canadian GPU cluster." DROP "no external AI vendor".
2. **web/app/components/home_keyboard_shell.tsx:58,60** — same mark + tooltip.
3. **web/components/sovereignty/sovereignty_panel.tsx:56-59** — drop "no external AI vendor"; keep "logged Canadian egress"; add an honest transitional-LLM line ("LLM inference currently via OpenRouter, disclosed; sovereign GPU pending").
4. **docs/transparency.md:72** — reconcile the self-contradiction: it currently says the LLM inference path "run on … Vexxhost + OVH H200 inference" (overclaims sovereign-now). Fix to honest CURRENT state consistent with line 59: the LLM inference path is DESIGNED for sovereign Canadian infra (OVH H200 vLLM) but CURRENTLY routes via OpenRouter (US, transitional, disclosed above); the sovereignty constraint is the TARGET, met at the Session-A GPU bring-up.

Net: every present-tense "no external AI vendor" / "runs on sovereign infra" claim becomes honest about the transitional OpenRouter reality + the sovereign target. transparency.md stays the single honest source; the tooltip can safely point there once :72 is fixed (this PR).
Re-confirm APPROVE or list only true remaining P0/P1.
