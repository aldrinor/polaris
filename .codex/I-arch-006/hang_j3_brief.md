HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Reserve P0/P1 for real execution risks; classify minor as P2/P3.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW (static only — do NOT run pytest): a transport-only hotfix to src/polaris_graph/llm/entailment_judge.py, "HANG-J3". Read the diff at .codex/I-arch-006/hang_j3_clean.patch and the file itself if needed.

CONTEXT: the entailment/4-role verify judge is a SYNC httpx POST to GLM-5.1. Its httpx timeout had only read=120s, which is a per-BYTE GAP that resets on every received byte. OpenRouter/Cloudflare holds the socket ESTABLISHED and trickles keep-alive bytes -> the gap never elapses -> a single judge POST runs UNBOUNDED (15-22min hangs observed, froze entire benchmark runs over ~2500 verify calls). FIX: a HARD TOTAL per-call wall-deadline — _post_with_total_deadline() runs the POST on a ThreadPoolExecutor and waits future.result(timeout=PG_ENTAILMENT_TOTAL_S, default 150s); on TimeoutError it force-closes the client (to unstick the hung worker), shuts the executor down wait=False, and re-raises; judge() catches that, REBUILDS the client (_build_client), and raises _RetryableJudgeError so the existing bounded SAME-provider retry reopens a fresh socket; on retry exhaustion the UNCHANGED fail-closed ('ENTAILED','judge_error:...') sentinel fires (consumers DROP).

VERIFY: (1) the total-deadline genuinely bounds a trickle-hang (gap-timeout cannot); (2) verdict logic, the fail-CLOSED sentinel contract, family-segregation, and the GLM-5.1 model lock are UNCHANGED; (3) no unbounded thread/socket leak (executor shutdown + client.close on timeout); (4) rebuild-on-timeout correctness (old client force-closed before the retry uses a new one); (5) FAITHFULNESS NOT relaxed (a timed-out claim fails closed = drop, never fabricated).

Output the schema:
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
p1: [...]
p2: [...]
remaining_blockers_for_execution: [...]
