## PHASE: I-cred-008b (#1162) DIFF gate ITER 4. Iter-3 P1 fixed (1-line test correction):
- the manifest-contract test asserted the literal 'abort_credibility_coverage_gap' INSIDE the outer exception-handler source slice, but the P1-1 refactor moved that literal into the helper _credibility_abort_status (run_honest_sweep_r3.py:282-283); the handler now only CALLS the helper. FIX: assert '_credibility_abort_status' in the handler slice (the routing call), not the literal. The handler-slice assertions are now: _unified_error_status='error_unexpected' (else branch) + '"status": _unified_error_status' (manifest) + _credibility_abort_status (the router call) + manifest.json. test_manifest_contract.py now GREEN.
- P2 (quantified test temp-write) = Codex-sandbox-only (passes in the real env). P2 (some fail-loud tests are source-shape) = accept_remaining; the direct-helper + contract-site tests cover the core invariant behaviorally.
SMOKE: see the manifest-contract run above (was the only iter-3 failure).
```diff
diff --git a/tests/polaris_graph/test_manifest_contract.py b/tests/polaris_graph/test_manifest_contract.py
index f99b1718..92ff15ae 100644
--- a/tests/polaris_graph/test_manifest_contract.py
+++ b/tests/polaris_graph/test_manifest_contract.py
@@ -55,6 +55,7 @@ def test_manifest_contract_unified_taxonomy_defined() -> None:
         "abort_safety_refused",        # I-ready-007 (#1072): input harm-refusal before retrieval
         "abort_four_role_release_held",  # I-ready-016 (#1086): 4-role D8 held release
         "abort_journal_only_contract_conflict",  # I-ready-017 (#1134): journal_only required contract slot non-journal
+        "abort_credibility_coverage_gap",  # I-cred-008b (#1162): activated credibility-disclosure pass found an uncovered cited token
         "cancelled",                   # I-ready-016 (#1086): user-cancel terminal manifest status
         "error_unexpected",
         "error_journal_only_leak",     # I-ready-017 (#1134): journal_only fail-closed no-leak backstop
@@ -261,9 +262,20 @@ def test_manifest_contract_exception_writes_error_manifest() -> None:
         end = handler.end_lineno or start
         handler_sources.append("\n".join(source.splitlines()[start - 1:end]))
     combined = "\n".join(handler_sources)
-    assert '"status": "error_unexpected"' in combined, (
-        f"Outer exception handler must write manifest with "
-        f"status=error_unexpected. Got handlers:\n{combined[:600]}"
+    # I-cred-008b (#1162): the outer handler now classifies via _credibility_abort_status — a generic /
+    # non-coverage exception DEFAULTS to error_unexpected, while a coverage-gap CredibilityPassError routes
+    # to abort_credibility_coverage_gap; the manifest writes the resolved _unified_error_status. (The old
+    # literal '"status": "error_unexpected"' assertion went stale when the hardcode became the variable.)
+    assert '_unified_error_status = "error_unexpected"' in combined, (
+        f"Outer exception handler must DEFAULT generic/non-coverage exceptions to error_unexpected. "
+        f"Got handlers:\n{combined[:700]}"
+    )
+    assert '"status": _unified_error_status' in combined, (
+        "Outer exception handler must write the resolved _unified_error_status into the manifest"
+    )
+    assert '_credibility_abort_status' in combined, (
+        "Outer handler must route via _credibility_abort_status(exc) (coverage-gap -> named status, "
+        "everything else -> error_unexpected). The literal status string lives in that helper, not inline."
     )
     assert 'manifest.json' in combined, (
         "Outer exception handler must attempt to write manifest.json"
```
