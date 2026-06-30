#!/usr/bin/env python3
"""Behavioral replay-harness for the I-beatboth-011 keystone dedup/compose fixes (GH #1289, §-1.4).

FAIL-LOUD (non-zero exit) unless EVERY effect ACTUALLY FIRES in the real output of the production
functions — NOT "Codex approved", NOT "tests green". Asserts:

  (1) §3.3 PROSE keep-all consolidation: with PG_FACT_DEDUP_PROSE=1, ~5 near-identical prose
      restatements (DIFFERENT [ev_X] citations) collapse so that exactly ONE output sentence still
      carries the full claim prose AND a cross-reference appears AND every distinct citation id is
      still present in the output (count unchanged) — proves keep-all consolidation, not a drop.
  (1b) §3.3 byte-identical OFF: with PG_FACT_DEDUP_PROSE unset, those same 5 restatements yield ZERO
      prose groups (mechanical proof build_groups is unchanged when the flag is off).
  (2) §3.3 conservative: two DISTINCT prose claims (Jaccard below threshold) do NOT merge.
  (3) §3.5 placeholder-leak: a section with a "[insufficient verified evidence..." per-basket result
      emits 0 occurrences of that literal after compose.
  (4) idx8 seen-span: a duplicate (ev_id,start,end) sibling unit is dropped while the first is kept.

Run:  python scripts/iarch_beatboth011_dedup_replay_harness.py
Exit 0 => all PASS;  non-zero => a fix did not fire in the real output.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Make the repo root importable (script lives in scripts/).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── import-check the two production modules under test ────────────────────────────────────────────
import re as _re_module  # noqa: E402
import src.polaris_graph.generator.fact_dedup as fact_dedup  # noqa: E402
import src.polaris_graph.generator.verified_compose as verified_compose  # noqa: E402

# Local copy of the [#ev:<id>:<start>-<end>] provenance grammar. The shared
# fact_dedup._SPAN_PROVENANCE_TOKEN_RE was removed when the §-1.3-banned
# PG_SPAN_PER_SOURCE_CITE_CAP bolt-on was deleted (I-deepfix-001 breadth fix);
# this harness only needs to read ev_ids out of rendered prose, so it carries
# its own self-contained regex.
_EV_RE = _re_module.compile(r"\[#ev:(?P<ev_id>[^:\]]+):(?P<start>\d+)-(?P<end>\d+)\]")


def _ev_ids_in(sections: dict) -> list[str]:
    """All distinct evidence_ids cited anywhere across the rendered sections (count preservation)."""
    ids: list[str] = []
    for sents in sections.values():
        for s in sents:
            for m in _EV_RE.finditer(s):
                ids.append(m.group("ev_id"))
    return sorted(ids)


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


def _make_keepall_llm():
    """An async llm_callable stub for rewrite_redundant_sentences: returns a JSON {"rewrites":[...]}
    with EXACTLY len(redundants) entries (else the shape-mismatch branch fires), each retaining the
    redundant sentence's OWN [#ev:...] token — so keep-all is exercised through the production
    rewrite path (consolidate-keep-all cross-ref), never a drop."""
    import json
    import re as _re

    async def _llm(system: str, prompt: str):
        # Recover each "REDUNDANT: <sentence>" line, in order, and synthesize a faithful cross-ref
        # that PRESERVES the redundant's own provenance token (never invents a new ev id).
        rewrites: list = []
        for line in prompt.splitlines():
            line = line.strip()
            if not line[:1].isdigit() or "REDUNDANT:" not in line:
                continue
            sentence = line.split("REDUNDANT:", 1)[1].strip()
            toks = _re.findall(r"\[#ev:[A-Za-z0-9_]+:\d+-\d+\]", sentence)
            tok = toks[0] if toks else ""
            rewrites.append(f"as noted under the primary section {tok}".strip())
        return _FakeResponse(json.dumps({"rewrites": rewrites}))

    return _llm


def _make_citation_stripping_llm():
    """A rewrite stub that returns NON-empty, plausible-looking rewrites that DROP the redundant's
    [#ev:...] token entirely — simulating an LLM that silently strips a citation. The §-1.3 keep-all
    guard (Codex #1289 iter-1 P0) must DISCARD such a successful-but-bad rewrite and keep the original
    cited sentence, so every original source survives in the output."""
    import json

    async def _llm(system: str, prompt: str):
        rewrites: list = []
        for line in prompt.splitlines():
            line = line.strip()
            if not line[:1].isdigit() or "REDUNDANT:" not in line:
                continue
            rewrites.append("as noted under the primary section above")  # NO provenance token
        return _FakeResponse(json.dumps({"rewrites": rewrites}))

    return _llm


# ──────────────────────────────────────────────────────────────────────────────────────────────────
# (1) + (1b) §3.3 PROSE keep-all consolidation + byte-identical OFF
# ──────────────────────────────────────────────────────────────────────────────────────────────────
def _prose_restatement_sections() -> dict:
    """5 near-identical PROSE restatements of one claim, each carrying a DISTINCT [#ev:...] citation
    and NO numeric/$/year signature (so the numeric path skips them entirely). All in the SAME
    section (the audited L39/L43 intra-section case)."""
    claim = "Autor and Acemoglu argue automation displaced routine workers and depressed their wages"
    return {
        "Findings": [
            f"{claim} [#ev:src_a:0-80].",
            f"{claim} [#ev:src_b:0-80].",
            f"{claim} [#ev:src_c:0-80].",
            f"{claim} [#ev:src_d:0-80].",
            f"{claim} [#ev:src_e:0-80].",
        ],
    }


async def _check_prose_keepall() -> list[str]:
    failures: list[str] = []
    sections = _prose_restatement_sections()
    input_ids = _ev_ids_in(sections)  # 5 distinct: src_a..src_e

    # (1b) FLAG OFF => zero prose groups (byte-identical build_groups).
    os.environ.pop("PG_FACT_DEDUP_PROSE", None)
    groups_off = fact_dedup.build_groups(sections, section_order=["Findings"])
    if groups_off:
        failures.append(
            f"(1b) FLAG-OFF: expected 0 redundancy groups, got {len(groups_off)} "
            f"(build_groups not byte-identical when PG_FACT_DEDUP_PROSE unset)"
        )

    # (1) FLAG ON => the prose pass clusters the 5 restatements; route through the EXISTING keep-all
    # rewrite path; assert keep-all (citation set unchanged) + dedup fired (one full claim remains).
    os.environ["PG_FACT_DEDUP_PROSE"] = "1"
    try:
        groups_on = fact_dedup.build_groups(sections, section_order=["Findings"])
        if not groups_on:
            failures.append("(1) FLAG-ON: prose pass produced ZERO groups; the 5 restatements did not cluster")
        new_sections, telemetry = await fact_dedup.dedup_pass(
            sections, _make_keepall_llm(), section_order=["Findings"],
        )
    finally:
        os.environ.pop("PG_FACT_DEDUP_PROSE", None)

    out_ids = _ev_ids_in(new_sections)
    if out_ids != input_ids:
        failures.append(
            f"(1) KEEP-ALL VIOLATED: input citations {input_ids} != output citations {out_ids} "
            f"(a source/citation was DROPPED — dedup must consolidate, never drop)"
        )

    full_claim = "Autor and Acemoglu argue automation displaced routine workers"
    out_sents = [s for sents in new_sections.values() for s in sents]
    n_full = sum(1 for s in out_sents if full_claim in s)
    if n_full != 1:
        failures.append(
            f"(1) DEDUP DID NOT FIRE: expected exactly 1 output sentence with the full claim prose, "
            f"got {n_full} (of {len(out_sents)} sentences)"
        )
    n_xref = sum(1 for s in out_sents if "as noted under" in s)
    if n_xref < 1:
        failures.append("(1) NO CROSS-REFERENCE emitted; the redundants did not route through the keep-all cross-ref path")
    return failures


# ──────────────────────────────────────────────────────────────────────────────────────────────────
# (2) §3.3 conservative — two DISTINCT prose claims do NOT merge
# ──────────────────────────────────────────────────────────────────────────────────────────────────
async def _check_conservative() -> list[str]:
    """The LETHAL faithfulness direction is OVER-merging: two same-topic, near-identical-wording
    sentences that assert OPPOSITE things ("lowered" vs "raised" earnings) must NOT cluster — merging
    them would cross-ref one real, opposing claim away (a silent claim drop). This near-threshold pair
    (Jaccard ~0.70 < 0.82 under unigram+bigram shingles) is what actually EXERCISES the threshold;
    a completely-unrelated pair (Jaccard ~0) would pass even at threshold 0.1 and proves nothing."""
    failures: list[str] = []
    sections = {
        "Findings": [
            "Automation displaced routine factory workers and lowered their relative earnings markedly [#ev:c1:0-90].",
            "Automation displaced routine factory workers and raised their relative earnings markedly [#ev:c2:0-90].",
        ],
    }
    os.environ["PG_FACT_DEDUP_PROSE"] = "1"
    try:
        groups = fact_dedup.build_groups(sections, section_order=["Findings"])
    finally:
        os.environ.pop("PG_FACT_DEDUP_PROSE", None)
    if groups:
        failures.append(
            f"(2) CONSERVATIVE VIOLATED: two same-topic OPPOSITE-assertion claims merged into "
            f"{len(groups)} group(s) (Jaccard threshold too low — a real opposing claim would be "
            f"cross-reffed away; this is the lethal over-merge direction)"
        )
    return failures


# ──────────────────────────────────────────────────────────────────────────────────────────────────
# (5) Codex #1289 iter-1 NOVEL-P0 — a SUCCESSFUL but citation-stripping rewrite must NOT drop a source.
# ──────────────────────────────────────────────────────────────────────────────────────────────────
async def _check_rewrite_keepall_p0() -> list[str]:
    """The original harness only used a citation-PRESERVING stub, so the §-1.3 violation Codex flagged
    (a non-empty rewrite that strips the redundant's own [#ev:...] token, silently deleting a
    corroborating source) was untested. Here the stub returns plausible token-LESS rewrites: with the
    keep-all guard they are all discarded and every original [ev_X] survives (output id-set unchanged);
    without the guard (RED), src_b..src_e are replaced by citation-less cross-refs and vanish."""
    failures: list[str] = []
    sections = _prose_restatement_sections()
    input_ids = _ev_ids_in(sections)  # 5 distinct: src_a..src_e
    os.environ["PG_FACT_DEDUP_PROSE"] = "1"
    try:
        new_sections, _telemetry = await fact_dedup.dedup_pass(
            sections, _make_citation_stripping_llm(), section_order=["Findings"],
        )
    finally:
        os.environ.pop("PG_FACT_DEDUP_PROSE", None)
    out_ids = _ev_ids_in(new_sections)
    if out_ids != input_ids:
        failures.append(
            f"(5) P0 KEEP-ALL VIOLATED: a successful citation-STRIPPING rewrite dropped a source — "
            f"input {input_ids} != output {out_ids}. The keep-all guard (discard token-dropping "
            f"rewrites, keep the original cited sentence) did not fire."
        )
    return failures


# ──────────────────────────────────────────────────────────────────────────────────────────────────
# (6) Codex #1289 iter-1 P1 — polarity guard: a one-token antonym flip ABOVE the Jaccard threshold must
# NOT cluster (else a real opposing claim is cross-reffed away).
# ──────────────────────────────────────────────────────────────────────────────────────────────────
async def _check_polarity_guard() -> list[str]:
    """A LONG claim whose only difference is a single ``raised``→``lowered`` antonym flip shares almost
    every shingle (Jaccard >> 0.82), yet asserts the OPPOSITE direction. Pure content-word Jaccard is
    polarity-blind and WOULD merge them; the polarity-signature guard must keep them in separate
    clusters (0 groups). The check also asserts the pair is genuinely above threshold, so it is the
    GUARD that saves us, not Jaccard (which would make the test vacuous)."""
    failures: list[str] = []
    base_pre = (
        "A comprehensive longitudinal econometric analysis of regional United States labor markets "
        "across several decades consistently confirmed that sustained industrial automation durably"
    )
    base_post = (
        "the inflation adjusted lifetime earnings of displaced routine manufacturing production workers"
    )
    sent_up = f"{base_pre} raised {base_post} [#ev:p1:0-120]."
    sent_down = f"{base_pre} lowered {base_post} [#ev:p2:0-120]."
    sections = {"Findings": [sent_up, sent_down]}

    sh_up = fact_dedup._prose_shingles(sent_up)
    sh_down = fact_dedup._prose_shingles(sent_down)
    jac = fact_dedup._jaccard(sh_up, sh_down)
    if jac < 0.82:
        failures.append(
            f"(6) WEAK TEST: polarity pair Jaccard={jac:.3f} < 0.82, so Jaccard alone would separate "
            f"them and the guard is not exercised. Lengthen the shared base to push Jaccard above 0.82."
        )

    os.environ["PG_FACT_DEDUP_PROSE"] = "1"
    try:
        groups = fact_dedup.build_groups(sections, section_order=["Findings"])
    finally:
        os.environ.pop("PG_FACT_DEDUP_PROSE", None)
    if groups:
        failures.append(
            f"(6) POLARITY GUARD FAILED: a single 'raised'→'lowered' antonym flip merged at "
            f"Jaccard={jac:.3f} into {len(groups)} group(s) — an opposing claim would be cross-reffed "
            f"away (the lethal over-merge Codex #1289 P1 flagged)."
        )
    return failures


# ──────────────────────────────────────────────────────────────────────────────────────────────────
# (3) §3.5 placeholder-leak + (4) idx8 seen-span — at the _compose_section_per_basket altitude.
# Per advisor: monkeypatch _compose_one_basket to return canned unit outputs (correct altitude;
# avoids the _member_global_span substring/region-gate math). Restore after.
# ──────────────────────────────────────────────────────────────────────────────────────────────────
def _check_compose_filters() -> list[str]:
    failures: list[str] = []
    orig = verified_compose._compose_one_basket

    # (3) one basket yields the insufficient-evidence disclosure; one yields a real cited sentence.
    canned_3 = iter([
        "[insufficient verified evidence to compose a sentence for: some subject]",
        "Real verified prose about the topic [#ev:r1:0-40].",
    ])

    def _stub_3(basket, evidence_pool, *, writer_fn, verify_fn):
        return next(canned_3)

    try:
        verified_compose._compose_one_basket = _stub_3
        out3 = verified_compose._compose_section_per_basket(
            [object(), object()], {}, writer_fn=lambda *a, **k: "", verify_fn=lambda *a, **k: None,
        )
    finally:
        verified_compose._compose_one_basket = orig

    leaks = sum(s.strip().startswith("[insufficient verified evidence") for s in out3)
    if leaks != 0:
        failures.append(
            f"(3) PLACEHOLDER LEAK: {leaks} per-basket insufficient-evidence marker(s) survived compose "
            f"(must be filtered before append, per the :337-338 sibling precedent)"
        )
    if not any("Real verified prose" in s for s in out3):
        failures.append("(3) the REAL verified sentence was wrongly dropped by the placeholder filter")

    # (4) idx8 — two baskets compose the SAME resolved span token; the duplicate sibling is dropped,
    # the first kept.
    dup_unit = "Productivity rose after the policy [#ev:dup:10-50]."
    canned_4 = iter([dup_unit, dup_unit])

    def _stub_4(basket, evidence_pool, *, writer_fn, verify_fn):
        return next(canned_4)

    try:
        verified_compose._compose_one_basket = _stub_4
        out4 = verified_compose._compose_section_per_basket(
            [object(), object()], {}, writer_fn=lambda *a, **k: "", verify_fn=lambda *a, **k: None,
        )
    finally:
        verified_compose._compose_one_basket = orig

    n_dup = sum(1 for s in out4 if s == dup_unit)
    if n_dup != 1:
        failures.append(
            f"(4) SEEN-SPAN dedup did not fire: expected the duplicate (ev_id,start,end) sibling dropped "
            f"(1 kept), got {n_dup} occurrences"
        )

    # (7) Codex #1289 iter-1 P1 — two units that resolve to the SAME (ev_id,start,end) span but carry
    # DIFFERENT prose are DISTINCT claims; both must be kept. The old subset-span-only rule would drop
    # the second; the text-identity tightening keeps it. This is the over-drop case the byte-identical
    # (4) fixture could not catch.
    unit_a = "Productivity rose sharply after the 2021 policy change [#ev:s:10-50]."
    unit_b = "Employment fell modestly after the 2021 policy change [#ev:s:10-50]."  # SAME span, opposite claim
    canned_7 = iter([unit_a, unit_b])

    def _stub_7(basket, evidence_pool, *, writer_fn, verify_fn):
        return next(canned_7)

    try:
        verified_compose._compose_one_basket = _stub_7
        out7 = verified_compose._compose_section_per_basket(
            [object(), object()], {}, writer_fn=lambda *a, **k: "", verify_fn=lambda *a, **k: None,
        )
    finally:
        verified_compose._compose_one_basket = orig

    if unit_a not in out7 or unit_b not in out7:
        failures.append(
            f"(7) idx8 OVER-DROP: two DISTINCT claims sharing one resolved span must BOTH be kept "
            f"(subset-span alone must not drop a differing claim), got {out7!r}"
        )
    return failures


def main() -> int:
    all_failures: list[str] = []
    all_failures += asyncio.run(_check_prose_keepall())
    all_failures += asyncio.run(_check_conservative())
    all_failures += asyncio.run(_check_rewrite_keepall_p0())
    all_failures += asyncio.run(_check_polarity_guard())
    all_failures += _check_compose_filters()

    if all_failures:
        print("HARNESS RESULT: FAIL")
        for f in all_failures:
            print(f"  - {f}")
        return 1
    print("HARNESS RESULT: PASS")
    print("  (1)  §3.3 prose keep-all consolidation fired; citation set unchanged")
    print("  (1b) §3.3 byte-identical when PG_FACT_DEDUP_PROSE unset (0 prose groups)")
    print("  (2)  §3.3 conservative: distinct prose claims did not merge")
    print("  (5)  P0 keep-all: a citation-stripping rewrite was discarded; every source survived")
    print("  (6)  P1 polarity: a one-token antonym flip above threshold did NOT cluster")
    print("  (3)  §3.5 insufficient-evidence placeholder did not leak post-compose")
    print("  (4)  idx8 byte-identical duplicate span sibling dropped; first kept")
    print("  (7)  idx8 distinct claims sharing one span both kept (no subset-span over-drop)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
