"""Phase 0: Focused integration test for FIX-HALLUC-REMEDIATE.

Closes advisor gap 3 at $0 in 30 min: proves remediation mutates
sections[i]['content'] to a non-fabricated rewrite in the final JSON.

Approach: mock OpenRouterClient with deterministic responses.
  - First compose call: returns known fabrication with [REF:1] tokens
  - Remediation call (detected by 'REMEDIATION' in prompt): clean rewrite
  - Abstract call: simple abstract

Then call compose_from_wiki() directly and assert G0a-G0e.

Usage: python scripts/pg_remediation_integration_test.py
"""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(override=False)


FABRICATED_SPAN_MARKER = "Thompson et al."
FABRICATED_SECTION_CONTENT = (
    "Intermittent fasting is a popular dietary approach. A 2024 JAMA "
    "Internal Medicine meta-analysis by Thompson et al. (PMID 39234567) "
    "of 14 randomized controlled trials (n=2,847) found that alternate-day "
    "fasting reduced LDL-C by 8.3 mg/dL compared to continuous energy "
    "restriction [REF:1]. Parallel analyses from the AHA 2024 scientific "
    "sessions by Chen and Rodriguez confirmed a 23% reduction in "
    "cardiovascular mortality over 18 months [REF:1]. The Zurich Institute "
    "of Advanced Hydrology independently replicated these findings across "
    "47 countries. These results establish alternate-day fasting as superior "
    "to continuous restriction for cardiovascular outcomes [REF:1]."
)

CLEAN_REWRITE_CONTENT = (
    "Intermittent fasting regimens have been evaluated against continuous "
    "energy restriction in multiple trials. Evidence indicates that "
    "alternate-day fasting produces weight loss broadly comparable to "
    "continuous energy restriction, without establishing superiority on "
    "cardiovascular endpoints [REF:1]. The primary supported conclusion "
    "is equivalence of weight-loss outcomes under matched energy deficit. "
    "Further research is warranted to characterize long-term effects. "
    "This rewrite omits claims not substantiated by the provided evidence."
)


class MockClient:
    """Mock OpenRouterClient that returns deterministic content based on prompt."""

    def __init__(self):
        self.calls = []
        # BUG-70 verification: track abstract content across calls so the test
        # can assert the post-remediation abstract differs from the initial one.
        self._abstract_call_count = 0

    async def generate(self, prompt, system=None, **kwargs):
        is_remediation = "REMEDIATION" in prompt or "UNSUPPORTED" in prompt
        is_abstract = "abstract" in (system or "").lower() or "200-word abstract" in prompt.lower()

        self.calls.append({
            "is_remediation": is_remediation,
            "is_abstract": is_abstract,
            "prompt_head": prompt[:120],
        })

        if is_abstract:
            # BUG-70 verification: return a DIFFERENT abstract body on the
            # second (post-remediation) abstract call so the test can detect
            # that regeneration actually happened (versus reusing the first
            # abstract string via regex extraction, which was the old bug).
            self._abstract_call_count += 1
            if self._abstract_call_count == 1:
                content = (
                    "PRE-REMEDIATION ABSTRACT: This review synthesizes evidence on "
                    "intermittent fasting and weight outcomes. Initial draft reflects "
                    "section content that included unsupported claims about Thompson et "
                    "al. (PMID 39234567) and AHA 2024 Chen and Rodriguez findings. Across "
                    "sources, alternate-day fasting yields weight loss comparable to "
                    "continuous energy restriction [1]."
                )
            else:
                content = (
                    "POST-REMEDIATION ABSTRACT: This review synthesizes the remediated "
                    "evidence on intermittent fasting. The body of the review summarizes "
                    "equivalence of alternate-day fasting vs continuous energy restriction "
                    "on weight-loss outcomes [1], without the invented author or PMID "
                    "references that appeared in the initial draft. Further research "
                    "remains warranted."
                )
        elif is_remediation:
            content = CLEAN_REWRITE_CONTENT
        else:
            content = FABRICATED_SECTION_CONTENT

        return SimpleNamespace(content=content)


def build_fixtures():
    """Construct minimal WikiResult + outline that routes through compose_from_wiki."""
    from src.polaris_graph.wiki.wiki_builder import WikiResult

    # One claim whose direct_quote contradicts the fabrication (evidence says
    # "comparable", fabrication claims "superior" and invents numbers/authors).
    claim = {
        "evidence_id": "ev_1",
        "ref_num": 1,
        "statement": (
            "Alternate-day fasting produces weight loss comparable to "
            "continuous energy restriction in adults with overweight or obesity."
        ),
        "direct_quote": (
            "alternate-day fasting produced weight loss comparable to "
            "continuous energy restriction, with no significant difference "
            "in LDL-C between arms at 6 months"
        ),
        "source_url": "https://example.org/trial/if-01",
        "source_title": "Alternate-day fasting vs continuous restriction: RCT",
        "source_type": "journal_article",
        "quality_tier": "GOLD",
        "relevance_score": 0.95,
        "perspective": "Scientific",
        "authors": ["Example A", "Example B"],
        "year": 2023,
        "doi": "10.9999/example.01",
    }

    wiki_result = WikiResult(
        wiki_path="/tmp/mock_wiki",
        section_claims={"s1": [claim]},
        bibliography=[{
            "ref_num": 1,
            "url": "https://example.org/trial/if-01",
            "title": "Alternate-day fasting vs continuous restriction: RCT",
            "authors": ["Example A", "Example B"],
            "year": 2023,
            "doi": "10.9999/example.01",
        }],
        stats={"total_claims": 1, "unique_sources": 1},
    )

    outline = [{
        "section_id": "s1",
        "title": "Effects on weight and cardiometabolic outcomes",
        "description": "Evidence on IF vs continuous restriction for weight and CV outcomes",
        "order": 1,
        "target_words": 300,
        "evidence_ids": ["ev_1"],
    }]

    return wiki_result, outline


async def main():
    print("=" * 72)
    print("  Phase 0: FIX-HALLUC-REMEDIATE integration test")
    print("=" * 72)

    # Pre-warm NLI so the detector's 30s thread-pool timeout hits the cache
    print("\n[setup] Pre-warming NLI model...")
    from src.polaris_graph.agents.nli_verifier import load_nli_model
    scorer = await load_nli_model()
    if scorer is None:
        print("[FAIL] NLI model unavailable — cannot run test")
        return 1
    print(f"[setup] NLI model loaded: {type(scorer).__name__}")

    if os.getenv("PG_HALLUCINATION_DETECT_ENABLED", "0") != "1":
        print("[FAIL] PG_HALLUCINATION_DETECT_ENABLED=0 — enable in .env")
        return 1

    from src.polaris_graph.wiki.wiki_composer import compose_from_wiki

    client = MockClient()
    wiki_result, outline = build_fixtures()
    query = "Does intermittent fasting improve cardiometabolic outcomes vs continuous energy restriction?"

    print("\n[run] Calling compose_from_wiki() with mock client...")
    result = await compose_from_wiki(
        client=client,
        wiki_result=wiki_result,
        query=query,
        outline=outline,
    )

    # Inspect what happened
    call_summary = [
        f"{i+1}. remediation={c['is_remediation']} abstract={c['is_abstract']}"
        for i, c in enumerate(client.calls)
    ]
    print(f"\n[run] Mock received {len(client.calls)} calls:")
    for s in call_summary:
        print(f"    {s}")

    # Extract final section content from the result
    sections = result.get("sections") or []
    if not sections:
        print("[FAIL] No sections in result — pipeline collapsed upstream")
        return 1

    final_section = sections[0]
    final_content = final_section.get("content", "")
    halluc_audit = result.get("hallucination_audit", [])

    # ──── Gate assertions ────────────────────────────────────────────
    print("\n[gates] Checking G0a–G0e...")
    results = {}

    # G0a: audit non-empty, first entry has needs_rewrite=True
    g0a_ok = (
        isinstance(halluc_audit, list)
        and len(halluc_audit) > 0
        and halluc_audit[0].get("needs_rewrite") is True
    )
    results["G0a"] = (
        g0a_ok,
        f"audit_len={len(halluc_audit) if isinstance(halluc_audit, list) else 'NA'}, "
        f"needs_rewrite={halluc_audit[0].get('needs_rewrite') if halluc_audit else 'NA'}, "
        f"ratio={halluc_audit[0].get('hallucination_ratio') if halluc_audit else 'NA'}",
    )

    # G0b: a compose call was made that returned fabrication (verified via mock history)
    compose_calls = [c for c in client.calls if not c["is_abstract"]]
    initial_compose = compose_calls[0] if compose_calls else None
    g0b_ok = initial_compose is not None and not initial_compose["is_remediation"]
    results["G0b"] = (g0b_ok, f"initial_compose_was_non_remediation={g0b_ok}")

    # G0c: remediation call fired AND final content differs from the fabrication
    remediation_calls = [c for c in compose_calls if c["is_remediation"]]
    g0c_ok = (
        len(remediation_calls) >= 1
        and FABRICATED_SPAN_MARKER not in final_content
        and final_content.strip() != FABRICATED_SECTION_CONTENT.strip()
    )
    results["G0c"] = (
        g0c_ok,
        f"remediation_calls={len(remediation_calls)}, "
        f"final_contains_fabrication_marker={FABRICATED_SPAN_MARKER in final_content}, "
        f"final_equals_original={final_content.strip() == FABRICATED_SECTION_CONTENT.strip()}",
    )

    # G0d: final content does NOT contain flagged span verbatim
    # (Thompson, AHA 2024, 23%, Zurich Institute — any would prove fabrication leaked through)
    leak_markers = ["Thompson", "AHA 2024", "Chen and Rodriguez",
                    "Zurich Institute", "39234567", "n=2,847"]
    leaks = [m for m in leak_markers if m in final_content]
    g0d_ok = len(leaks) == 0
    results["G0d"] = (g0d_ok, f"leaked_markers={leaks}")

    # G0e: final content has >= 50 words (silent fallback did not fire)
    word_count = len(final_content.split())
    g0e_ok = word_count >= 50
    results["G0e"] = (g0e_ok, f"word_count={word_count}")

    # G0f (BUG-70 verification): mock should receive TWO abstract calls — one
    # pre-remediation and one post-remediation regeneration. The final report's
    # abstract must reflect the post-remediation version, not the stale pre-
    # remediation version that was the BUG-70 symptom.
    abstract_calls = [c for c in client.calls if c["is_abstract"]]
    final_report = result.get("final_report", "") or ""
    pre_leaked = "PRE-REMEDIATION ABSTRACT" in final_report
    post_present = "POST-REMEDIATION ABSTRACT" in final_report
    g0f_ok = (
        len(abstract_calls) >= 2
        and post_present
        and not pre_leaked
    )
    results["G0f"] = (
        g0f_ok,
        f"abstract_calls={len(abstract_calls)}, post_abstract_in_report={post_present}, "
        f"pre_abstract_leaked={pre_leaked}",
    )

    # ──── Report ─────────────────────────────────────────────────────
    print()
    for gate, (ok, msg) in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {gate}: {msg}")

    passed = sum(1 for ok, _ in results.values() if ok)
    total = len(results)
    print(f"\n  SUMMARY: {passed}/{total} gates passed")
    if passed == total:
        print("  ✓ Advisor gap 3 (remediation mutates sections[i]['content'] "
              "→ final JSON) is CLOSED at $0.")
    else:
        print("  ✗ Advisor gap 3 NOT CLOSED. Inspect failures above.")

    # Dump the final content for inspection
    print("\n[dump] final_content (first 400 chars):")
    print("    " + final_content[:400].replace("\n", "\n    "))
    print("=" * 72)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(asyncio.run(main()))
