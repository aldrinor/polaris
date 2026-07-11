#!/usr/bin/env python3
"""S2 SELECT+WEIGH v2 — box-2 line-level three-way select/drop replay harness.

Design: `.codex/I-arch-plan/01_offtopic_subquery.md` §6 (SELECT+WEIGH v2) + master plan S2
row. Standalone CLI (LAW VII): loads a banked ``corpus_snapshot.json``, runs the LINE-LEVEL
three-way drop reader (``src/polaris_graph/retrieval/line_screen.py``) 32-wide with a
crash-resilient incremental checkpoint (``--resume``), and writes the S2 checkpoint plus a
fully-quoted disclosure and the lock-bar metrics.

Outputs (into ``--out``):
  * ``cp2_corpus_snapshot.json`` — the screened corpus (kept lines only; whole-drops removed;
    every kept row carries a ``line_screen`` sidecar). Same shape as the input snapshot.
  * ``disclosure.txt``          — EVERY dropped line QUOTED with its reason + source (§-1.3.1
    fail-loud, never silent).
  * ``summary.json``            — the five §6.4 lock-bar pass-condition metrics.
  * ``line_screen_verdicts.jsonl`` — the crash-resilient incremental checkpoint (V7).

The LLM is the REAL production model on box 2 (mirror role, temperature 0.0). ``--stub`` runs
a deterministic offline heuristic (chrome→JUNK, else KEEP) to smoke the plumbing with no key.

USAGE
  python scripts/s2_select_replay.py --out outputs/s2_replay [--only 50] [--source <eid>]
  python scripts/s2_select_replay.py --scope '{"date_start":"2023-01"}' --out outputs/s2_scope
  python scripts/s2_select_replay.py --resume --out outputs/s2_replay   # resume after a crash
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure the repo root is importable when run as a script.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph.retrieval import line_screen as ls  # noqa: E402

# The box-2 canonical snapshot (present on the VM when the paid drb_72 run has landed). The
# harness accepts any snapshot via ``--snapshot`` and falls back to the newest banked drb_72
# corpus when the box-2 path is absent (local build / offline test).
_BOX2_SNAPSHOT = "outputs/paid_drb72_deep/workforce/drb_72_ai_labor/corpus_snapshot.json"


# ─────────────────────────────────────────────────────────────────────────────
# LLM callables
# ─────────────────────────────────────────────────────────────────────────────
def _build_real_llm(model: str | None, max_tokens: int):
    """The REAL production judge callable (mirrors run_honest_sweep_r3.py:13262-13321). Builds
    its own OpenRouterClient per call, own event loop in a worker thread, temperature 0.0."""
    from src.polaris_graph.llm.openrouter_client import (  # noqa: PLC0415
        OpenRouterClient, PG_GENERATOR_MODEL,
    )
    _model = model or os.getenv(ls._ENV_MODEL, "") or os.getenv("PG_SCOPE_TOPIC_MODEL", "") or PG_GENERATOR_MODEL

    def _llm(prompt: str) -> str:
        import asyncio as _asyncio  # noqa: PLC0415
        import concurrent.futures as _futures  # noqa: PLC0415

        async def _run() -> str:
            client = OpenRouterClient(model=_model)
            try:
                resp = await client.generate(prompt=prompt, max_tokens=max_tokens, temperature=0.0)
                return (resp.content or "").strip()
            finally:
                if hasattr(client, "close"):
                    try:
                        await client.close()
                    except Exception:
                        pass

        with _futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: _asyncio.run(_run())).result()

    return _llm


def _stub_llm(prompt: str) -> str:
    """Deterministic OFFLINE stub (no key): parses the numbered LINES block out of the prompt
    and returns JUNK for a line carrying obvious chrome vocab, else KEEP. Exercises the harness
    plumbing end-to-end; it is NOT a semantic judge (that is the real box-2 model)."""
    chrome_hints = (
        "cookie", "consent", "subscribe", "sign in", "log in", "newsletter", "©",
        "all rights reserved", "skip to", "watch later", "share", "download citation",
        "[#", "accept all", "privacy policy", "terms of use", "follow us", "menu",
    )
    lines = prompt.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == "LINES:") + 1
    except StopIteration:
        return ""
    out: list[str] = []
    for ln in lines[start:]:
        s = ln.strip()
        if not s or ":" not in s:
            continue
        idx_part, _, text = s.partition(":")
        idx = idx_part.strip()
        if not idx.isdigit():
            continue
        low = text.lower()
        verdict = "JUNK" if any(h in low for h in chrome_hints) else "KEEP"
        out.append(f"{idx}: {verdict}")
    return "\n".join(out)


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot IO
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_snapshot(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    p = _REPO_ROOT / _BOX2_SNAPSHOT
    if p.is_file():
        return p
    # offline fallback: newest banked drb_72 corpus snapshot
    candidates = sorted(
        _REPO_ROOT.glob("outputs/**/drb_72_ai_labor/corpus_snapshot.json"),
        key=lambda x: x.stat().st_mtime, reverse=True,
    )
    if candidates:
        return candidates[0]
    return p  # non-existent box-2 path (loader will error loudly)


def _load_snapshot(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or "evidence_for_gen" not in data:
        raise SystemExit(f"[s2] snapshot {path} missing 'evidence_for_gen'")
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="S2 line-level three-way select/drop replay")
    ap.add_argument("--snapshot", default=None, help="corpus_snapshot.json (default: box-2 path / newest drb_72)")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--only", type=int, default=0, help="screen only the first N sources")
    ap.add_argument("--source", default="", help="screen only this evidence_id")
    ap.add_argument("--scope", default="", help='explicit RunConfig scope JSON, e.g. {"date_start":"2023-01"}')
    ap.add_argument("--scope-from-question", action="store_true",
                    help="extract the explicit scope from the question text (opt-in; default leaves the scope leg inert)")
    ap.add_argument("--parallel", type=int, default=32, help="source fan-out width (slate 32)")
    ap.add_argument("--max-lines", type=int, default=0, help="max lines per LLM call (0=default 120)")
    ap.add_argument("--resume", action="store_true", help="resume from the checkpoint (replay screened rows)")
    ap.add_argument("--stub", action="store_true", help="offline deterministic stub LLM (no key)")
    ap.add_argument("--model", default="", help="override the judge model")
    ap.add_argument("--max-tokens", type=int, default=4096, help="judge completion budget")
    ap.add_argument("--no-topic-judge", action="store_true",
                    help="skip the whole-source semantic topic judge (Fix 2a); default runs it "
                         "to stamp topic_off_subject before the line screen")
    args = ap.parse_args(argv)

    # Activate the line screen (defaults are OFF ⇒ byte-identical when unset).
    os.environ[ls._ENV_ENABLED] = "1"

    snap_path = _resolve_snapshot(args.snapshot)
    if not snap_path.is_file():
        print(f"[s2] ERROR: snapshot not found: {snap_path}", file=sys.stderr)
        return 2
    data = _load_snapshot(snap_path)
    question = str(data.get("question", "") or "")
    rows = [r for r in data.get("evidence_for_gen", []) if isinstance(r, dict)]

    # Build the explicit scope (default INERT — credible non-journal institutions survive).
    scope = ls.ScreenScope()
    if args.scope.strip():
        try:
            scope = ls.build_scope_from_dict(json.loads(args.scope))
        except json.JSONDecodeError as exc:
            print(f"[s2] ERROR: bad --scope JSON: {exc}", file=sys.stderr)
            return 2
    elif args.scope_from_question:
        scope = ls.build_scope_from_question(question)
    if scope.armed:
        os.environ[ls._ENV_SCOPE] = "1"  # arm the out_of_scope leg

    # Subset selection.
    if args.source:
        rows = [r for r in rows if str(r.get("evidence_id", "")) == args.source]
    elif args.only and args.only > 0:
        rows = rows[: args.only]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = out_dir / "line_screen_verdicts.jsonl"
    if not args.resume and ckpt_path.exists():
        ckpt_path.unlink()  # fresh run — start a clean checkpoint

    llm = _stub_llm if args.stub else _build_real_llm(args.model or None, args.max_tokens)

    print(f"[s2] snapshot={snap_path}")
    print(f"[s2] sources={len(rows)} parallel={args.parallel} scope_armed={scope.armed} "
          f"scope_active={scope.is_active()} stub={args.stub} resume={args.resume}")
    print(f"[s2] question: {question[:140]}")

    # S2/S3 re-pass Fix 2(a): wire the WHOLE-SOURCE semantic topic judge into the S2 path.
    # classify_topic_relevance stamps topic_off_subject=True (in place) on rows a meaning-level
    # judge confirms are OFF_SUBJECT (a CLEARLY DIFFERENT subject entity than the FULL research
    # question) — the OFF_TOPIC whole-drop CONCURRENCE key the line screen keys on
    # (_row_stamped_off_subject). FAIL-OPEN (doubt => KEEP); marquee / occupation-page sources
    # are exempt / on-topic; judge verdict ONLY (never tier / keyword / number). A stub LLM
    # cannot judge topicality (fail-open => zero stamps), so this is inert under --stub.
    topic_off_subject_stamped = 0
    if not args.no_topic_judge and question.strip():
        try:
            from src.polaris_graph.retrieval.topic_relevance_gate import (  # noqa: PLC0415
                classify_topic_relevance,
            )
            tg = classify_topic_relevance(rows, question, llm)
            topic_off_subject_stamped = sum(1 for r in rows if r.get("topic_off_subject") is True)
            print(f"[s2] topic-judge: off_subject_stamped={topic_off_subject_stamped} "
                  f"gate_dropped_offtopic={tg.n_dropped_offtopic} "
                  f"gate_demoted={getattr(tg, 'n_demoted_offtopic', 0)} "
                  f"gate_exempt={tg.n_exempt}")
        except Exception as exc:  # noqa: BLE001 — fail-open: a judge defect never blocks S2
            print(f"[s2] topic-judge SKIPPED (fail-open): {str(exc)[:160]}", file=sys.stderr)

    # Incremental per-source printer (read-every-line forensic surface, §-1.1).
    def _on_result(result: ls.SourceScreenResult, row: dict) -> None:
        t = str(row.get("title") or row.get("statement") or row.get("evidence_id") or "")[:70]
        counts = result.reason_counts()
        tag = "WHOLE-DROP:" + result.whole_drop_reason if result.whole_dropped else (
            "DISAGREE-KEEP" if result.disagreement else "screened")
        print(f"[s2] {result.evidence_id[:34]:34s} lines={result.n_lines:4d} "
              f"kept={result.n_kept:4d} off={counts['off_topic']:3d} "
              f"oos={counts['out_of_scope']:3d} junk={counts['junk']:3d} {tag} | {t}")

    corpus = ls.screen_corpus(
        rows, question, llm,
        scope=scope,
        parallel=args.parallel,
        max_lines=(args.max_lines or None),
        checkpoint_path=ckpt_path,
        on_result=_on_result,
    )

    # Build cp2: kept rows (whole-drops removed) with kept-lines-only bodies + sidecar.
    result_by_id = {r.evidence_id: r for r in corpus.results}
    kept_rows: list[dict] = []
    dropped_line_records: list[dict] = []
    whole_drop_records: list[dict] = []
    for row in rows:
        eid = str(row.get("evidence_id", ""))
        res = result_by_id.get(eid)
        if res is None:
            kept_rows.append(row)
            continue
        title = str(row.get("title") or row.get("statement") or "")
        url = str(row.get("source_url") or row.get("url") or "")
        for d in res.dropped:
            dropped_line_records.append({
                "evidence_id": eid, "title": title, "url": url,
                "line_idx": d.get("line_idx"), "reason": d.get("reason"),
                "quote": d.get("quote", ""),
            })
        if res.whole_dropped:
            whole_drop_records.append({
                "evidence_id": eid, "title": title, "url": url,
                "reason": res.whole_drop_reason, "n_lines": res.n_lines,
            })
            continue  # excluded from the grounding pool (disclosed)
        kept_rows.append(ls.apply_result_to_row(row, res))

    # ── cp2_corpus_snapshot.json ──
    cp2 = dict(data)
    cp2["evidence_for_gen"] = kept_rows
    cp2["stage"] = "s2_line_screened"
    cp2["line_screen_summary"] = {
        "n_sources_in": len(rows),
        "n_sources_kept": len(kept_rows),
        "n_whole_dropped": len(whole_drop_records),
        "n_dropped_lines": len(dropped_line_records),
        "scope_armed": scope.armed,
        "scope_active": scope.is_active(),
        # §-1.3.1 fail-loud DISCLOSURE (S2/S3 re-pass iter-6): count of rows the meaning-level
        # topic judge CONFIDENTLY stamped OFF_SUBJECT that nonetheless SURVIVED into cp2. These
        # are the disclosed FAIL-OPEN residual: the OFF_TOPIC whole-drop is a TWO-KEY concurrence
        # (topic-judge OFF_SUBJECT stamp + line-screen 100%-off_topic) precisely so a single-pass
        # judge FALSE-POSITIVE on a credible ON-TOPIC source is NEVER deleted (a drb_72 example is
        # the Roosevelt-Institute "Good Life Agenda", which explicitly discusses AI's labor impact
        # yet was stamped OFF_SUBJECT; the two-key gate correctly KEEPS it). Surfacing the count
        # makes the residual AUDITABLE instead of silent; these rows stay DEMOTED (weight, not
        # filter) and flow to composition where the faithfulness engine is the only hard gate.
        "n_offsubject_stamped_kept": sum(
            1 for r in kept_rows if r.get("topic_off_subject") is True
        ),
    }
    (out_dir / "cp2_corpus_snapshot.json").write_text(
        json.dumps(cp2, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    # ── disclosure.txt (every dropped line quoted) ──
    lines_out: list[str] = []
    lines_out.append("S2 LINE-SCREEN DISCLOSURE — every dropped line quoted (§-1.3.1 fail-loud)")
    lines_out.append(f"snapshot: {snap_path}")
    lines_out.append(f"question: {question}")
    lines_out.append(f"sources_in={len(rows)} sources_kept={len(kept_rows)} "
                     f"whole_dropped={len(whole_drop_records)} dropped_lines={len(dropped_line_records)}")
    lines_out.append(f"scope_armed={scope.armed} scope_active={scope.is_active()} "
                     f"trigger_spans={scope.trigger_spans}")
    lines_out.append("")
    if whole_drop_records:
        lines_out.append("=== WHOLE-SOURCE DROPS (two-key; marquee-exempt) ===")
        for w in whole_drop_records:
            lines_out.append(f"[{w['reason']}] {w['evidence_id']} — {w['title'][:90]} ({w['url'][:80]})")
        lines_out.append("")
    lines_out.append("=== DROPPED LINES (quoted) ===")
    by_src: dict[str, list[dict]] = {}
    for d in dropped_line_records:
        by_src.setdefault(d["evidence_id"], []).append(d)
    for eid, recs in by_src.items():
        title = recs[0]["title"][:90]
        lines_out.append(f"--- {eid} — {title} ---")
        for d in recs:
            lines_out.append(f"  [{d['reason']}] L{d['line_idx']}: {d['quote'][:300]}")
    (out_dir / "disclosure.txt").write_text("\n".join(lines_out) + "\n", encoding="utf-8")

    # ── summary.json (the five §6.4 lock-bar metrics) ──
    n_lines_total = sum(r.n_lines for r in corpus.results)
    n_kept_total = sum(r.n_kept for r in corpus.results)
    by_reason = {"off_topic": 0, "out_of_scope": 0, "junk": 0}
    for d in dropped_line_records:
        r = str(d.get("reason", ""))
        if r in by_reason:
            by_reason[r] += 1
    partial_sources = [
        {"evidence_id": r.evidence_id, "n_lines": r.n_lines, "n_kept": r.n_kept,
         "n_dropped": len(r.dropped)}
        for r in corpus.results
        if r.n_lines > 0 and 0 < len(r.dropped) < r.n_lines and not r.whole_dropped
    ]
    all_quoted = all("quote" in d for d in dropped_line_records)
    n_source_scope_drops = sum(
        1 for w in whole_drop_records if str(w["reason"]).startswith("out_of_scope"))
    summary = {
        "snapshot": str(snap_path),
        "question": question,
        "totals": {
            "n_sources_in": len(rows),
            "n_sources_kept": len(kept_rows),
            "n_lines_total": n_lines_total,
            "n_lines_kept": n_kept_total,
            "n_dropped_lines": len(dropped_line_records),
            "n_whole_dropped": len(whole_drop_records),
            "n_screened_llm": corpus.n_screened_llm,
            "n_replayed": corpus.n_replayed,
        },
        # (a) off-topic / out-of-scope / junk LINES dropped with the exact line QUOTED
        "cond_a_lines_dropped_quoted": {
            "n_dropped_lines": len(dropped_line_records),
            "by_reason": by_reason,
            "all_lines_quoted": all_quoted,
        },
        # (b) a credible on-topic in-scope source is NEVER whole-dropped (marquee + V5 two-key)
        "cond_b_no_credible_whole_drop": {
            "n_whole_dropped": len(whole_drop_records),
            "whole_drop_reasons": [w["reason"] for w in whole_drop_records],
            "n_marquee_or_disagreement_protected": corpus.n_disagreement,
            # Fix 2(a): the semantic topic-judge OFF_SUBJECT stamps that ARMED the OFF_TOPIC
            # whole-drop concurrence key (0 under --stub / --no-topic-judge, as expected).
            "n_topic_off_subject_stamped": topic_off_subject_stamped,
            "note": "whole-drop fires only on the two-key concurrence; marquee never whole-drops",
        },
        # (c) a rich MIXED source keeps its relevant lines and drops only the bad ones
        "cond_c_mixed_partial_keep": {
            "n_partial_sources": len(partial_sources),
            "examples": partial_sources[:20],
        },
        # (d) the user-scope filter drops out-of-scope and KEEPS in-scope; empty scope ⇒ ZERO
        "cond_d_scope": {
            "scope_armed": scope.armed,
            "scope_active": scope.is_active(),
            "n_out_of_scope_line_drops": by_reason["out_of_scope"],
            "n_source_scope_whole_drops": n_source_scope_drops,
            "note": ("ARMED — out_of_scope leg active" if scope.is_active()
                     else "INERT — zero out_of_scope drops (activation rule)"),
        },
        # (e) fail-open on uncertainty (disagreement-restore, checkpoint resume identity)
        "cond_e_fail_open": {
            "n_disagreement_restored": corpus.n_disagreement,
            "n_replayed_on_resume": corpus.n_replayed,
            "checkpoint": str(ckpt_path),
            "note": "malformed verdict / LLM error ⇒ chunk KEEP; kill mid-run ⇒ resume replays",
        },
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    print(f"\n[s2] DONE. sources_in={len(rows)} sources_kept={len(kept_rows)} "
          f"whole_dropped={len(whole_drop_records)} dropped_lines={len(dropped_line_records)} "
          f"(off={by_reason['off_topic']} oos={by_reason['out_of_scope']} junk={by_reason['junk']})")
    print(f"[s2] offsubject_stamped_kept="
          f"{sum(1 for r in kept_rows if r.get('topic_off_subject') is True)} "
          f"(topic-judge OFF_SUBJECT but KEPT — disclosed fail-open residual; two-key gate "
          f"protects credible on-topic from a single-pass judge false-positive, §-1.3.1)")
    print(f"[s2] wrote: {out_dir/'cp2_corpus_snapshot.json'}")
    print(f"[s2] wrote: {out_dir/'disclosure.txt'}")
    print(f"[s2] wrote: {out_dir/'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
