# Phase 2A Walkthrough — 24-Input Corpus

## Block A — Live audit run (5)
1. Start a clinical query → expect SSE events visible within 1s; 5 affordances panel renders
2. Mid-run, click Cancel → expect graceful cancel within 5s; partial state persisted
3. SSE drops mid-run (kill-9 dev server) → expect reconnect with state preserved
4. Two tabs same run → expect both update independently; cancel in one cancels for both
5. 80% source-fetch failure → expect partial-evidence warning visible

## Block B — Inspector 5-tab (8)
6. Click claim sentence → side pane within 1s with source span highlighted
7. 50-sentence report → all clickable; 100-sentence → all clickable; 500-sentence → still <1s
8. Frames tab — verify above-the-fold with progress bar
9. Frames tab — gap shows "what would unblock this" action
10. Contradictions tab — every flag clickable; side pane shows all sides + tiers
11. Contradictions — T1-vs-T1 conflict shows both with sample sizes (no false hierarchy)
12. Pool tab — sources listed by tier
13. Charts tab — Vega-Lite SVG renders within 2.5s

## Block C — Two-family disagreement signal (4)
14. Verify KPI card on every Inspector view
15. PASS run → green styling
16. FAIL run (synthetic invariant violation) → red destructive banner
17. Click disagreement detail → side pane with generator vs evaluator readings

## Block D — Defense + Climate templates (4)
18. Defense template — query about cyber threats → expect NIST + MITRE sources cited
19. Defense template — frame coverage panel surfaces required entities (CVE, CWE, ATT&CK technique)
20. Climate template — query about emissions reduction → expect IPCC + ECCC + NRCan
21. Climate template — frame coverage shows jurisdictional scoping

## Block E — Cross-cutting (3)
22. Pin a run → reload → pinned state persists
23. Open same run on mobile (375px viewport) → essential affordances visible
24. axe-core: any new accessibility violations vs Phase 1 baseline → P1 finding
