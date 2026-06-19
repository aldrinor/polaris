HARD ITERATION CAP: 3. This is iter 3 of 3 (final). Verdict APPROVE iff zero P0 and zero P1.
3-PRONG: reject your own suggestion if it (1) relaxes faithfulness, (2) grandfathers, (3) adds a cap/floor/throttle. (Stricter fail-closed parsing/validation is pro-faithfulness.)

STATIC review (do NOT run pytest) of C:/POLARIS/.codex/iarch011_campaign/judge_iter3.patch — iter-3 fix for the two iter-2 P1s.

ITER-2 P1#1 (accepted): a verdict object nested inside a JSON container (e.g. [{"verdict":...}]) was extracted (fail-open; pre-B12 json.loads returned a list and .get failed closed).
ITER-2 P1#2 (accepted): semantic_conflict mapped an unknown verdict string to "neutral" via .get(...,"neutral") (fail-open under strict gates).

ITER-3 FIX to verify:
(1) BOTH extractors now scan for the EARLIEST of the next "{" or "[" and raw_decode the OUTERMOST value; a dict-with-verdict returns; any other COMPLETE value (non-verdict object, ARRAY, scalar) is skipped by its end offset and the scan NEVER descends into a container interior; a raw_decode failure RAISES. New regression cases: [{"verdict":...}], [{"note":...},{"verdict":...}], {"items":[{"verdict":...}]} all FAIL CLOSED.
(2) semantic_conflict now validates verdict in {"CONTRADICT","ENTAIL","NEUTRAL"} and RAISES otherwise -> routed to the existing strict-HOLD/fail-closed except; the label map is now a direct [verdict] index (no default).

VERIFY: (a) the array/container salvage path is closed in BOTH judges; (b) the garbled-200, leading-scratchpad-object, fenced-json, and nested-object-WITH-top-level-verdict success cases still parse; (c) the verdict-validation fails closed on an out-of-vocab verdict; (d) no new fail-open. Output schema; final line `verdict: APPROVE|REQUEST_CHANGES`.
