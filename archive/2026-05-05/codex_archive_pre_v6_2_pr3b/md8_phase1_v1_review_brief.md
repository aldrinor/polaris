# Codex round 1 — M-D8 phase 1 v1

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_md8_phase1_parallel_fetch.py`
- DO NOT run rg/find — read these files directly:
  - `src/polaris_graph/audit_ir/parallel_fetch.py` (~370 lines)
  - `tests/polaris_graph/test_md8_phase1_parallel_fetch.py` (~530 lines)
  - `docs/md8_phase1_threat_model.md` (~210 lines)
- DO NOT run Python verification scripts that print Unicode

## Scope
Last unblocked Phase D milestone. Parallel-fetch substrate
that callers wire up to actual HTTP backends to fan out N
fetches concurrently with per-backend concurrency limits.

NOT integration with `live_retriever.py` — that's phase 2.
Substrate is stdlib-only (concurrent.futures + threading).

## Public API

```python
class ParallelFetcher(Protocol):
    def fetch(self, task: FetchTask) -> tuple[bytes, str, int]: ...

@dataclass(frozen=True)
class FetchTask:
    source_url: str
    backend_id: str  # rate-limit class
    task_metadata: Mapping[str, object] = field(default_factory=dict)

class FetchOutcome(str, Enum):
    SUCCESS = "success"
    ERRORED = "errored"
    TIMEOUT = "timeout"

def parallel_fetch(
    tasks: Sequence[FetchTask],
    fetcher: ParallelFetcher,
    *,
    max_workers: int = 8,
    per_backend_max_concurrent: Mapping[str, int] | None = None,
    per_task_timeout: float | None = None,
) -> ParallelFetchReport: ...
```

## Boundaries (7 documented)

1. Pure stdlib substrate (no HTTP)
2. Per-backend concurrency via threading.Semaphore (default=4)
3. Per-task timeout via deadline-wait loop (NOT
   as_completed+fut.result(timeout=) — initial bug caught)
4. Result order matches input task order
5. Duplicate (source_url, backend_id) collapses; same URL
   different backend distinct
6. ERRORED captures str(exc); FetcherProtocolError propagates
7. tuple[bytes|bytearray, str, int] shape validation

## Tests (29/29 passing)

- Empty + single-task smoke
- task_metadata round-trip
- Result-order preservation
- Concurrent-dispatch overlap (< 0.15s for 4×0.05s)
- Per-backend limit serialization (limit=1 forces ~2×0.05s)
- Per-backend limits independent across backends
- DEFAULT_PER_BACKEND_LIMIT applies
- Fetcher exception → ERRORED, others continue
- Semaphore-leak guard (limit=1, first task raises, second
  must NOT deadlock)
- Per-task timeout (0.5s task with 0.05s timeout → TIMEOUT)
- per_task_timeout=None disables
- Duplicate dedup
- Same URL different backend distinct
- Wrong-shape returns raise FetcherProtocolError (3 cases)
- 6 contract-validation negative cases

## What might Codex probe

- Best-effort Future.cancel() doesn't actually interrupt
  threads — TIMEOUT is recorded but worker may run on. Threat
  model boundary 3 documents this explicitly.
- Per-task deadline computed from submit time (not
  semaphore-acquired time) — a task delayed by semaphore
  contention could timeout before it ever ran.
- Race: protocol_error_to_raise + cancel() of remaining
  futures after the with-block exits (executor.__exit__
  waits for all submitted to finish).
- ThreadPoolExecutor leaves threads running on raise — all
  workers complete before the executor context exits.

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Boundary integration
- [x/ ] Pure substrate
- [x/ ] Per-backend semaphore correct
- [x/ ] Per-task timeout via deadline-wait
- [x/ ] Result order matches input

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
