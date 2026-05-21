# Codex DECISION — fix requirements.txt resolution-too-deep (operator asked Claude to resolve; blind to CI)

The pip dry-run gate (blocks ALL src/polaris_v6 merges) fails with `error: resolution-too-deep` on legacy requirements.txt. Never caught before — the working-dir bug fast-failed first (file-not-found), masking this. The web/ shim (#717) fixed the working-dir; this is the SECOND fault now exposed.

## Verified evidence
- requirements.txt: 63 top-level pkgs, ~30 unbounded (`neo4j>=5.0`, `openai>=1.0.0`, `ragas>=0.2.0`, `torch>=2.0.0`, …) → combinatorial explosion.
- pip thrashes on protobuf (downloads every 4.25.x→4.24.x) → resolution-too-deep.
- ROOT CONFLICT: requirements.txt line 156 `protobuf<5.0.0` (+ `google-generativeai>=0.3.0` line 102 → google-ai-generativelanguage==0.6.9 → needs protobuf<5) VS the modern stack (otel 1.41, etc.) which wants protobuf 6.x.
- `requirements.lock` (uv-compiled, what Dockerfile.v6 ACTUALLY installs, PROVEN to resolve) has: protobuf==6.33.6, langchain-google-genai==2.1.12, google-ai-generativelanguage==0.11.0, and DROPS google-generativeai entirely.
- 62 of 63 requirements.txt pkgs are present in the lock at exact ==versions. The ONLY one not in the lock: google-generativeai.
- google.generativeai is imported by src/llm/gemini_client.py:28. (Grep for who imports gemini_client: results above this brief — if empty, gemini_client is a dead module.)
- requirements-v6.txt already uses protobuf==6.33.6 (resolves clean, fast).

## The decision (operator delegated to you; Claude will execute + test locally with pip dry-run before pushing)
A. Pin ALL 63 requirements.txt entries to their requirements.lock ==versions; set protobuf==6.33.6; and for google-generativeai (not in lock) — drop it IF gemini_client.py is dead (no importer), else bump to a protobuf-6-compatible version. Rationale: the lock is the proven-resolvable set Docker already installs; pinning collapses pip's search → no resolution-too-deep; aligns requirements.txt with the lock as single source of truth.
B. Minimal: only pin/cap the few high-fanout culprits (protobuf, the unbounded ~30) without full lock-pinning.
C. Other.

My recommendation: A (full pin-to-lock, deterministic + matches production). For google-generativeai: if gemini_client.py has no importer (dead), drop both the dep line AND optionally leave the dead module (its import only fails if something imports it — nothing does). If it has a live importer, you decide: bump google-generativeai or port gemini_client off it.

Give: DECISION (A/B/C), the google-generativeai call (drop vs bump-to-version-X vs port), and any guardrail. I will then pin requirements.txt, run `pip install --dry-run -r requirements.txt` LOCALLY to confirm it resolves fast, and only push if green.
