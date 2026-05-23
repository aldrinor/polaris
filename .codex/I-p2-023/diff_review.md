# Codex DIFF review — I-p2-023 (#762): honest sovereignty wording

HARD ITERATION CAP: 5. iter 1. Canonical-diff-sha256 `5994acabb64c440c59f71a05f0c60ff85d334ce24b53655a4f6ba928fe549d03`. web/ + docs/ only. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1. (Brief direction-APPROVE'd; verify the 4 sites are now honest.)

## Diff (the 4 overclaim sites from the brief)
- app_shell.tsx + home_keyboard_shell.tsx: mark "⬡ Canadian AI · no external AI vendor" → "⬡ Canadian-hosted"; tooltip → honest (Canadian-hosted Québec + logged egress + "LLM inference currently routed via OpenRouter (US, disclosed in /transparency) pending sovereign GPU"). DROPPED "no external AI vendor".
- sovereignty_panel.tsx: "Sovereign processing / ...no external AI vendor" → "Canadian-hosted" + transitional-OpenRouter disclosure.
- docs/transparency.md:72: reconciled the self-contradiction (was "LLM inference path runs on OVH H200"; now "designed-sovereign but currently routes via OpenRouter US transitional until Session-A GPU").

## §-1.1 honesty
Production LLM = OpenRouter US (transparency.md:59 + runbook:12). All present-tense "no external AI vendor" / "runs on sovereign infra" claims removed; replaced by Canadian-hosted (true: OVH Québec VM) + explicit transitional-LLM disclosure. transparency.md is now internally consistent.

## Review focus
1. Any remaining present-tense sovereignty/vendor overclaim in the 4 sites or elsewhere? Is "Canadian-hosted" honest (VM in Québec)? Is the transitional-LLM disclosure accurate + consistent with transparency.md:59?
2. transparency.md:72 now consistent with :59 (no remaining self-contradiction)? Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
