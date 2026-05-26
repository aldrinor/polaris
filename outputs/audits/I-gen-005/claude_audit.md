# PR #911 — I-gen-005 Step 3g Claude architect review

Resolves pre-existing test_provenance_generator failure (flagged
out-of-scope in PR #908).

Two replacement tests document the §-1.1 trade-off explicitly:
1. local_support_window rescues narrow-cite-but-data-in-evidence
2. safety floor: numbers absent from evidence STILL fail

14/14 test_provenance_generator pass. Codex iter-1: APPROVE.
