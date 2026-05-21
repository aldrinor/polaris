# Codex DIFF review — I-pip-001 full pip-gate fix (your DECISION A implemented)

HARD ITERATION CAP: 5. iter 1. APPROVE iff zero P0/P1. Final line MERGE AUTHORIZED if mergeable. Touches web/requirements*.txt + requirements.txt + src/llm/gemini_client.py (NOT .github/workflows).

Canonical-diff-sha256: `b48e1ad72de96557074ece53c2e67e9beb7e6bc4391fc07c19aefd78ee7cd8f9`. 4 files.

## EMPIRICAL RESULT
The CI pip dry-run on this PR now **PASSES** (was resolution-too-deep). The fix is verified working on Linux CI, not just locally.

## What I implemented (your DECISION A, verbatim)
1. web/requirements.txt + web/requirements-v6.txt forwarding shims (-r ../) — fixes the working-dir half (pip runs from web/).
2. requirements.txt: pinned all 62 top-level packages to their requirements.lock ==versions; protobuf<5.0.0 → protobuf==6.33.6; DROPPED google-generativeai (EOL, forces protobuf<5). Tidied the now-obsolete protobuf comment block.
3. src/llm/gemini_client.py: 'import google.generativeai as genai' wrapped try/except → genai=None; GeminiClient.__init__ raises a clear ImportError if genai is None. Verified locally: module loads with genai absent; GeminiClient() raises.

## Guardrail status
- gemini_client.genai usage is ONLY in __init__ (lines 89-94) — all behind the new guard.
- src/llm/__init__.py eagerly imports gemini_client — module-load now stays cheap (genai=None), so that import won't fail on the missing package. (Note: src/llm/__init__.py ALSO imports src.llm.deberta_client which does NOT exist in the repo — a PRE-EXISTING broken import, unrelated to this change, not introduced or fixed here.)

## Review focus
1. Is pinning requirements.txt to requirements.lock versions sound (the lock is the proven Docker install set; pins are mutually compatible by construction)?
2. The google-generativeai drop + lazy gemini_client guard — correct + safe?
3. protobuf==6.33.6 (matches lock + requirements-v6.txt + CVE-2026-0994 patched)?
4. Any NOVEL P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
remaining_blockers_for_execution: [...]
```
