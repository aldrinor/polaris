M-16 v3 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-16 v2 verdict: PARTIAL with edits. Concrete callout:

> `_normalize_url()` is still unstable for URLs like
> `?utm_source=x&id=1` vs `?id=1`, so identical evidence can still
> surface as false add/remove deltas.

v2 used a regex that stripped tracking params but left the `&`
separator behind. v3 rewrites the function with `urllib.parse`.

## What changed in v3 (commit 971769b)

`src/polaris_graph/audit_ir/run_diff.py`:

```python
def _normalize_url(url: str) -> str:
    if not url:
        return ""
    raw = url.strip()
    if not raw:
        return ""
    has_scheme = raw.lower().startswith(("http://", "https://"))
    if not has_scheme:
        raw = "http://" + raw
    from urllib.parse import urlsplit, parse_qsl, urlencode
    parts = urlsplit(raw)
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/")
    qs_pairs = parse_qsl(parts.query, keep_blank_values=True)
    kept = sorted(
        (k.lower(), v) for (k, v) in qs_pairs if not _is_tracking_param(k)
    )
    new_query = urlencode(kept)
    out = netloc + path
    if new_query:
        out = f"{out}?{new_query}"
    return out
```

Tracking param set unchanged (utm_*, fbclid, gclid, mc_*, ref,
source). Behavior:
- `?utm_source=x&id=1` → `id=1`
- `?id=1` → `id=1`
- `?id=1&utm_source=x` → `id=1`
- `?b=2&a=1` → `a=1&b=2` (sorted)

Two regression tests added:
- `test_evidence_url_with_tracking_param_alongside_real_param`
  asserts `?utm_source=x&id=1` and `?id=1` collapse to the same handle.
- `test_evidence_url_query_param_order_does_not_matter` asserts
  `?b=2&a=1` and `?a=1&b=2` collapse to the same handle.

Module: 27/27 tests green.

## Your job

Final verdict on M-16. GREEN / PARTIAL / DISAGREE.

If GREEN, M-16 locks and Phase C continues. The other v2 fixes
(route order, real V30 tier keys, stable claim handle, stable
evidence handle) you already approved last round; only the URL
normalization changed.

## Output

Write to `outputs/codex_findings/m16_v3_review/findings.md`:

```markdown
# Codex re-review of M-16 v3

## Verdict
GREEN / PARTIAL / DISAGREE

## URL normalization stability
- [x/no] tracking + real param mix collapses to same handle
- [x/no] param order does not matter
- [x/no] no orphan `&` or `?` artifacts

## Final word
GREEN to lock M-16 + proceed / PARTIAL with edits.
```

Be terse. Under 80 lines.
