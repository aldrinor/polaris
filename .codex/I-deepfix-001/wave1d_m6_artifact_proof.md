# Wave-1d — proof that Codex iter-2 P1 is a diff-presentation artifact (NOT a real change)

**Codex iter-2 P1 claim:** "`_run_m6_firing_canary` adds an unrelated success-path `return "ok"` outside the PG_SHALLOW_REPORT_CANARY guard. With shallow canary OFF but M6 enabled, `m6_cross_source_canary` changes from prior null/None to "ok", so OFF is still not byte-identical."

**Why Codex was misled:** its shell sandbox could not launch, so it reviewed the DIFF TEXT only. The unified diff shows `+    return "ok"` right under the `@@ ... def _run_m6_firing_canary(` hunk header. That header just names the nearest preceding `def`; the 136-line hunk actually contains the NEW `_run_shallow_report_canary` function inserted AFTER `_run_m6_firing_canary`. Because BOTH functions end with the identical two-line pair `print(f"<<< {domain} / {slug}: ... canary=ok")` + `return "ok"`, every minimal-diff algorithm (myers, patience, histogram all tested — all give the same 3-deletion diff) anchors on the wrong `return "ok"`: it displays HEAD's real M6 return as an addition (`+return "ok"` at the top) and the NEW shallow function's return as unchanged context (line 147). Net effect of the diff: +1 `return "ok"` — which correctly belongs to the newly-added `_run_shallow_report_canary`, NOT to M6.

## Primary-source proof (the real file, not the diff)

**1. The `M6 cross-source firing canary=ok` print appears exactly ONCE in both HEAD and working** (so no duplicated / added M6 return):
```
HEAD: 1
WORK: 1
```

**2. `_run_m6_firing_canary` is BYTE-FOR-BYTE identical HEAD vs working** — extracted the whole function (def → its final `return "ok"`) from `git show HEAD:` and from the working tree; `diff` is EMPTY and the SHA256 matches:
```
HEAD M6 function: 31 lines   SHA256 e5bbd962a0636c40e1e9a31b26080d7f654319c030fb2a9394f50786cd999209
WORK M6 function: 31 lines   SHA256 e5bbd962a0636c40e1e9a31b26080d7f654319c030fb2a9394f50786cd999209
diff /tmp/m6_head.txt /tmp/m6_work.txt  → (empty) → IDENTICAL
```

**3. HEAD already ended `_run_m6_firing_canary` with `return "ok"`** (HEAD line 2561-2562):
```
2561:    print(f"<<< {domain} / {slug}: M6 cross-source firing canary=ok")
2562:    return "ok"
```
Working tree is the same, shifted +1 only because `import re` was added at the top of the file (line 2562-2563).

**Conclusion:** `m6_cross_source_canary` is genuinely unchanged when PG_SHALLOW_REPORT_CANARY is OFF. OFF is byte-identical. Codex's P1 is a false positive caused by the diff's unavoidable anchoring ambiguity + the failed shell sandbox. The `+return "ok"` semantically belongs to the new `_run_shallow_report_canary` function. No code change is needed; the finding is refuted by the real file.
