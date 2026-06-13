"""G2 run-sweep blocker tests — fail-open readiness gates in scripts/run_honest_sweep_r3.py.

Forensic: dual Claude+Codex 2026-06-12, .codex/I-bench-veracity-003-forensic/. The drb_72
benchmark run surfaced a cluster of run-sweep gates that FAIL OPEN: a skewed corpus is accepted
as sweep-ready with only a disclosure (#1235), a V30-contract Phase-2 fault silently degrades to
the legacy generator (#1238), a CITED bibliography entry renders a blank URL (#1239), the Methods
tier-mix "11%/12%" disagrees with the Limitations "13%" (#1242), a manifest can read `success`
without the 4-role D8 audit ever running (#1226), and an enabled-but-empty quantified
differentiator passes silently (#1237).

Fix: ONE shared env ``PG_BENCHMARK_STRICT_GATES`` (default "0"/off) turns the four fail-open paths
LOUD (#1235/#1238/#1226/#1237); #1239 and #1242 get their own narrow flags. OFF == byte-identical.

These tests exercise the PURE run-sweep helpers directly (no async pipeline, no network, no spend):
  flag-OFF identity  — every shared-flag helper returns the no-op value when strict is off
  flag-ON loud-abort — each strict helper returns the block/raise/hold signal when strict is on
  #1242 single-src   — the tier-mix helper returns ONE consistent percentage used everywhere
  #1239 bib render   — flag-OFF byte-identical; flag-ON relabels a cited-but-blank entry to a gap

FAITHFULNESS: untouched. None of these helpers touch strict_verify / the NLI judge / the 4-role D8
release decision / provenance — they only forbid mislabeling an un-audited, skewed, or empty run as
ready/success, or relabel a locator-less citation DOWN to a disclosed gap (never fabricating a URL).
Plain assertions, no unittest.mock.
"""
from __future__ import annotations

import os

import scripts.run_honest_sweep_r3 as sweep


# ── env helper: set for the body, restore exactly on exit (no mock) ──────────────
class _env:
    def __init__(self, **kv: "str | None") -> None:
        self._kv = kv
        self._prev: dict[str, "str | None"] = {}

    def __enter__(self) -> "_env":
        for k, v in self._kv.items():
            self._prev[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *exc: object) -> None:
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ── shared strict-gate reader (default OFF) ──────────────────────────────────────
def test_shared_strict_flag_default_off():
    with _env(PG_BENCHMARK_STRICT_GATES=None):
        assert sweep._benchmark_strict_gates_on() is False


def test_shared_strict_flag_on():
    with _env(PG_BENCHMARK_STRICT_GATES="1"):
        assert sweep._benchmark_strict_gates_on() is True


def test_shared_strict_flag_explicit_zero_is_off():
    # An explicit "0" / "false" must NOT enable the gate (off == identical).
    for val in ("0", "false", "False", "no", ""):
        with _env(PG_BENCHMARK_STRICT_GATES=val):
            assert sweep._benchmark_strict_gates_on() is False


# ── #1235 corpus-skew readiness gate ─────────────────────────────────────────────
def test_1235_corpus_skew_off_never_blocks():
    # strict OFF -> the weighted-corpus auto-approve is never bypassed, regardless of deviation.
    assert sweep._corpus_skew_blocks_ready(False, True) is False
    assert sweep._corpus_skew_blocks_ready(False, False) is False


def test_1235_corpus_skew_on_blocks_only_material_deviation():
    # strict ON -> bypass the weighted auto-approve ONLY when there is a material deviation
    # (a clean corpus still auto-approves; off==identical for the no-deviation case).
    assert sweep._corpus_skew_blocks_ready(True, True) is True
    assert sweep._corpus_skew_blocks_ready(True, False) is False


# ── #1238 V30 contract broad-except ──────────────────────────────────────────────
def test_1238_v30_off_never_reraises():
    # strict OFF -> the V30 fault falls back to legacy (no re-raise), as today.
    assert sweep._v30_should_reraise(False, False) is False
    assert sweep._v30_should_reraise(False, True) is False


def test_1238_v30_on_reraises_unless_fallback_allowed():
    # strict ON + fallback NOT allowed -> fatal (re-raise). strict ON + fallback allowed -> legacy.
    assert sweep._v30_should_reraise(True, False) is True
    assert sweep._v30_should_reraise(True, True) is False


# ── #1226 no success before D8 ───────────────────────────────────────────────────
def test_1226_d8_off_never_blocks_success():
    # strict OFF -> a `success` manifest without D8 is left alone (legacy single-evaluator path).
    assert sweep._d8_success_without_audit(False, "success", False) is False


def test_1226_d8_on_blocks_success_without_audit():
    # strict ON + would-be success + D8 did NOT run -> must convert to a loud hold.
    assert sweep._d8_success_without_audit(True, "success", False) is True


def test_1226_d8_on_allows_success_when_audit_ran():
    # strict ON + success + D8 DID run -> allowed (the audit produced a binding decision).
    assert sweep._d8_success_without_audit(True, "success", True) is False


def test_1226_d8_on_ignores_non_success_status():
    # A partial/abort status is already a non-success signal; the guard must not touch it.
    assert sweep._d8_success_without_audit(True, "partial_thin_corpus", False) is False
    assert sweep._d8_success_without_audit(True, "abort_no_sources", False) is False


# ── #1237 quantified readiness ───────────────────────────────────────────────────
def test_1237_quantified_off_never_fails():
    # strict OFF -> never fail readiness regardless of the quantified telemetry.
    assert sweep._quantified_readiness_failed(False, True, {"fired": False}) is False
    assert sweep._quantified_readiness_failed(False, True, None) is False


def test_1237_quantified_not_force_enabled_never_fails():
    # strict ON but quantified NOT force-enabled -> the differentiator was optional; never fail.
    assert sweep._quantified_readiness_failed(True, False, {"fired": False}) is False
    assert sweep._quantified_readiness_failed(True, False, None) is False


def test_1237_quantified_force_on_but_empty_fails():
    # strict ON + force-enabled + produced NO verified output (fired=False / no telemetry) -> fail.
    assert sweep._quantified_readiness_failed(True, True, {"fired": False}) is True
    assert sweep._quantified_readiness_failed(True, True, None) is True
    # Robust to the typed-status strings quantified_analysis.py emits: keys on `fired`, so an
    # empty_transport / parse_error / declined telemetry without a true `fired` still fails.
    assert sweep._quantified_readiness_failed(
        True, True, {"quantified_status": "empty_transport", "fired": False}
    ) is True


def test_1237_quantified_force_on_and_fired_passes():
    # strict ON + force-enabled + the differentiator FIRED -> readiness passes.
    assert sweep._quantified_readiness_failed(True, True, {"fired": True}) is False


# ── #1242 tier-disclosure single source of truth ─────────────────────────────────
def test_1242_tier_mix_summary_byte_identical_to_inline_builder():
    # The helper must reproduce the prior inline ", ".join(f"{k}={v*100:.0f}%" ...) builder EXACTLY,
    # so default-ON introduces no string change (the forensic Methods line read "T1=12%, ...").
    fractions = {"T1": 0.123, "T2": 0.01, "T3": 0.03, "T4": 0.40, "UNKNOWN": 0.27}
    expected_inline = ", ".join(
        f"{k}={v * 100:.0f}%" for k, v in sorted(fractions.items())
    )
    assert sweep._tier_mix_disclosure_summary(fractions) == expected_inline


def test_1242_tier_mix_summary_is_single_consistent_value():
    # The SAME helper called twice yields the SAME percentage — so two disclosure strings that both
    # reference it can never quote different denominators (the "11% vs 13%" self-contradiction).
    fractions = {"T1": 0.13, "T4": 0.40}
    a = sweep._tier_mix_disclosure_summary(fractions)
    b = sweep._tier_mix_disclosure_summary(fractions)
    assert a == b
    # T1 renders ONE way only — not 12% in one place and 13% in another.
    assert "T1=13%" in a
    assert "T1=12%" not in a


def test_1242_tier_mix_summary_empty_and_none_safe():
    assert sweep._tier_mix_disclosure_summary({}) == ""
    assert sweep._tier_mix_disclosure_summary(None) == ""


# ── #1239 empty bibliography locator ─────────────────────────────────────────────
def _bib_fixture() -> "list[dict]":
    # Mirrors the drb_72 bibliography.json: entries 4 + 5 are CITED (have a `num`) but carry a
    # blank url and no doi. The bib dict shape carries no `is_cited`/`doi` keys for those rows.
    return [
        {"num": 1, "statement": "Automation and New Tasks", "tier": "T1",
         "url": "https://www.aeaweb.org/articles/pdf/doi/10.1257/jep.33.2.3"},
        {"num": 4, "statement": "Robots and Jobs: Evidence from US Labor Markets",
         "tier": "T1", "url": ""},
        {"num": 5, "statement": "Generative AI at Work", "tier": "T1", "url": ""},
    ]


def test_1239_bib_locator_check():
    assert sweep._bib_entry_has_locator({"url": "https://x", "doi": ""}) is True
    assert sweep._bib_entry_has_locator({"url": "", "doi": "10.1/x"}) is True
    assert sweep._bib_entry_has_locator({"url": "", "doi": ""}) is False
    assert sweep._bib_entry_has_locator({"url": "   ", "doi": None}) is False


def test_1239_bib_render_off_byte_identical():
    # require_locator OFF must reproduce the prior inline loop byte-for-byte (off==identical).
    bib = _bib_fixture()
    out = sweep._render_bibliography_lines(bib, require_locator=False)
    legacy = "\n\n## Bibliography\n"
    for b in bib:
        legacy += f"[{b['num']}] {b['statement'][:200]} — {b['url']} (tier {b['tier']})\n"
    assert out == legacy
    # The blank-URL cited entries STILL render as numbered citations pointing at nothing (the bug).
    assert "[4] Robots and Jobs: Evidence from US Labor Markets —  (tier T1)" in out
    assert "[5] Generative AI at Work —  (tier T1)" in out


def test_1239_bib_render_on_keeps_num_and_discloses_gap_no_orphan():
    # require_locator ON (Codex iter-1 REQUEST_CHANGES): a cited-but-locator-less entry KEEPS its
    # citation number so the report BODY's [N] marker still resolves (no orphan), AND honestly
    # discloses the missing locator. Never fabricates a URL; never drops the entry.
    bib = _bib_fixture()
    out = sweep._render_bibliography_lines(bib, require_locator=True)
    # The good entry keeps its citation number + URL.
    assert "[1] Automation and New Tasks — https://www.aeaweb.org" in out
    # The two blank-URL cited entries KEEP their numbers (body [4]/[5] still resolve) with a
    # disclosed evidence-gap note — NOT a number-less "[gap]" line that would orphan the body.
    assert (
        "[4] Robots and Jobs: Evidence from US Labor Markets — no resolvable URL/DOI locator "
        "(disclosed evidence gap, tier T1)"
    ) in out
    assert (
        "[5] Generative AI at Work — no resolvable URL/DOI locator "
        "(disclosed evidence gap, tier T1)"
    ) in out
    # No number-less orphan-gap line.
    assert "[gap]" not in out
    # The entries are STILL present (awareness preserved) — relabel-down, not drop.
    assert out.count("Robots and Jobs") == 1
    assert out.count("Generative AI at Work") == 1


def test_1239_bib_render_on_renders_doi_only_locator():
    # require_locator ON: an entry with a DOI but blank URL renders the DOI as a doi.org locator
    # (a real DOI the entry already carries — never fabricated) and stays a numbered citation.
    bib = [{"num": 7, "statement": "DOI-only entry", "tier": "T1", "url": "",
            "doi": "10.1257/jep.29.3.3"}]
    out = sweep._render_bibliography_lines(bib, require_locator=True)
    assert "[7] DOI-only entry — https://doi.org/10.1257/jep.29.3.3 (tier T1)" in out
    assert "[gap]" not in out


# ── #1242 tier-disclosure override threads ONE canonical string into the telemetry block ──────────
def test_1242_telemetry_block_override_emits_canonical_string_verbatim():
    # Codex iter-1 REQUEST_CHANGES: when tier_disclosure_override is supplied, _format_telemetry_block
    # emits that EXACT canonical string and does NOT re-derive a per-tier list from the fractions — so
    # the LLM-authored Limitations quotes the SAME tier mix the deterministic Methods disclosure quotes.
    from src.polaris_graph.generator.live_deepseek_generator import _format_telemetry_block

    fractions = {"T1": 0.13, "T4": 0.40}
    canonical = sweep._tier_mix_disclosure_summary(fractions)  # "T1=13%, T4=40%"
    block = _format_telemetry_block(
        fractions, None, None, None, tier_disclosure_override=canonical,
    )
    # The canonical string appears verbatim.
    assert canonical in block
    # And the per-tier re-derived list is NOT separately present (no standalone "  T1: 13%" line).
    assert "  T1: 13%" not in block
    assert "  T4: 40%" not in block


def test_1242_telemetry_block_override_none_is_unchanged():
    # override None => legacy per-tier derivation (byte-identical to today).
    from src.polaris_graph.generator.live_deepseek_generator import _format_telemetry_block

    fractions = {"T1": 0.13, "T4": 0.40}
    legacy = _format_telemetry_block(fractions, None, None, None)
    explicit_none = _format_telemetry_block(
        fractions, None, None, None, tier_disclosure_override=None,
    )
    assert legacy == explicit_none
    # The per-tier derived lines ARE present on the legacy path.
    assert "  T1: 13%" in legacy
    assert "  T4: 40%" in legacy


# ── #1240 per-run token-honesty telemetry reset + snapshot ────────────────────────────────────────
def test_1240_token_honesty_reset_zeroes_counters():
    # Codex iter-1 REQUEST_CHANGES: the per-run reset must zero the module-global counters so counts
    # do not accumulate across queries. Drive the real provenance-generator helpers.
    from src.polaris_graph.generator import provenance_generator as pg

    pg.reset_token_honesty_telemetry()
    snap = pg.get_token_honesty_telemetry()
    assert snap == {"malformed_canonicalized": 0, "malformed_dropped": 0}
    # Simulate accumulation, then reset again -> back to zero (no leak across runs).
    pg._TOKEN_HONESTY_TELEMETRY["malformed_canonicalized"] = 4
    pg._TOKEN_HONESTY_TELEMETRY["malformed_dropped"] = 2
    assert pg.get_token_honesty_telemetry()["malformed_canonicalized"] == 4
    pg.reset_token_honesty_telemetry()
    assert pg.get_token_honesty_telemetry() == {
        "malformed_canonicalized": 0, "malformed_dropped": 0,
    }


def test_1240_token_honesty_snapshot_is_a_copy_not_a_live_ref():
    # The snapshot surfaced into the manifest must be a COPY, so a later increment in a sibling run
    # cannot retroactively mutate an already-written manifest's recorded counts.
    from src.polaris_graph.generator import provenance_generator as pg

    pg.reset_token_honesty_telemetry()
    snap = pg.get_token_honesty_telemetry()
    pg._TOKEN_HONESTY_TELEMETRY["malformed_dropped"] = 9
    assert snap["malformed_dropped"] == 0  # the earlier snapshot is unaffected
    pg.reset_token_honesty_telemetry()
