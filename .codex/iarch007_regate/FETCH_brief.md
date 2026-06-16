You are re-reviewing after a fix iteration. READ C:/POLARIS/.codex/iarch007_regate/FETCH.diff and the source OFF DISK (src/polaris_graph/retrieval/frame_fetcher.py src/tools/access_bypass.py src/polaris_graph/generator/contract_section_runner.py src/polaris_graph/adequacy/plan_sufficiency_gate.py src/polaris_graph/retrieval/contradiction_detector.py src/polaris_graph/generator/claim_labeler.py src/polaris_graph/synthesis/disclosure_population.py).

VERIFY:
- A1 shell-detector actually FIRES at fetch (keyed on fetch-integrity not topicality; shell -> gap/recovery signal not drop).
- A5 overlap fallback.
- A17 same-unit contradiction guard.
- A8 credibility flag-not-drop (disclosure_population never changes is_verified).

For EACH prior P0: is it now CLOSED? Any NEW issue?

PRIOR P0 (must be re-checked as CLOSED or still-open): A17 NOT CLOSED — `src/polaris_graph/retrieval/contradiction_detector.py` groups only by `(subject, predicate, unit, dose)` and records contradictions for any group with divergent values; `ExtractedNumericClaim` carries `evidence_id`/`source_url` but there was no same-source/same-unit guard, so two claims from the same evidence/source unit could still be surfaced as a cross-source contradiction.

FORBIDDEN (auto-P0): relaxing any strict_verify/NLI/4-role threshold or marking un-judged content verified/released.

Static review only. Do NOT run pytest or any code. Read the files off disk and reason.

End EXACTLY with:
verdict: APPROVE | REQUEST_CHANGES
p0:
(one per line or none)
p1:
(one per line or none)
faithfulness_ok: yes|no
wiring_complete: yes|no
