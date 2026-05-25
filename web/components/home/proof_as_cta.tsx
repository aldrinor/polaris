// I-ux-001c (#878) sub-PR 2: Home page proof-as-CTA card — the HERO climax.
//
// v6 spec (locked in `.codex/I-ux-001c-2/brief.md` iter-4 APPROVE):
//   - Label: "VERIFIED CLAIM · LIVE EXAMPLE"
//   - Claim text rendered in body-lg with numerics bolded green
//     (font-bold + text-verified) to make the verification visceral
//   - Footer with the EXACT count: "✓ matched <N> of <total> numbers
//     against <journal> <year> source span", null-safe (4 fallback templates
//     for missing journal/year)
//   - Conditional signature pill on signatureState (Codex iter-4 P2-001
//     sibling fix from sub-PR 1: tri-state aware — only gpg_verified may
//     render the green "Signed bundle" pill)
//   - Honest-fail fallback: when home_brief_loader returns
//     bundle_loaded=false, render the "still loading" copy + link to
//     `/inspector/v1-canonical-success` (NO numeric stamp, NO sig pill;
//     never fabricate verification — LAW II)
//
// Two-judgment separation (design_tokens_v2 §2.2): faithfulness greens
// (text-verified, --verified-bg) are reserved for verified claims; the
// evidence-strength slate-blue ordinal is NOT used on this card (the
// home hero shows verification, not certainty).
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import type { HomeBrief } from "@/lib/home_brief_loader";

interface ProofAsCtaProps {
  brief: HomeBrief;
}

/** Bold green any numeric token from the claim, leaving the rest of the
 * sentence untouched. The regex matches what `extractNumerics` in the loader
 * matches so the visual treatment lines up with the matched-numbers count. */
function highlightNumerics(text: string): React.ReactNode[] {
  const regex = /([−-]?\d+(?:\.\d+)?(?:%|\s*percentage\s+points?)?)/g;
  const parts = text.split(regex);
  return parts.map((part, i) => {
    if (i % 2 === 1) {
      return (
        <span
          key={i}
          className="text-verified font-bold tabular-nums"
          data-testid="proof-numeric"
        >
          {part}
        </span>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

/** Render the null-safe "against <journal> <year> source span" tail. */
function sourceTail(journal: string | null, year: number | null): string {
  if (journal && year) return `against ${journal} ${year} source span`;
  if (journal && !year) return `against ${journal} source span`;
  if (!journal && year) return `against the ${year} source span`;
  return "against the cited source span";
}

export function ProofAsCta({ brief }: ProofAsCtaProps) {
  if (!brief.bundle_loaded) {
    // Honest-fail (LAW II): no verified claim available right now.
    // Don't fabricate a count or a signature pill — link out instead.
    return (
      <section
        aria-label="Verified clinical brief"
        data-testid="proof-as-cta"
        data-state="loading"
        className="bg-card ring-foreground/10 shadow-card mx-auto w-full max-w-3xl rounded-2xl px-6 py-6 ring-1 sm:px-8 sm:py-8"
      >
        <div className="flex flex-col gap-3">
          <span className="text-muted-foreground text-[10px] font-medium tracking-[0.14em] uppercase">
            Verified Claim · Live Example
          </span>
          <p className="text-muted-foreground text-base sm:text-lg">
            Verified clinical brief loading — see the full proof now.
          </p>
          <Link
            href={`/inspector/${brief.run_id}`}
            data-testid="proof-as-cta-link"
            className="text-primary focus-visible:ring-ring/70 inline-flex items-center gap-1.5 text-sm font-medium underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
          >
            See the full proof
            <ArrowRight aria-hidden className="h-4 w-4" />
          </Link>
        </div>
      </section>
    );
  }

  // bundle_loaded === true: render the real proof card.
  const claim = brief.claim ?? "";
  const journal = brief.source.journal;
  const year = brief.source.year;
  const matched = brief.matched_numerics;
  const total = brief.total_numerics;

  return (
    <section
      aria-label="A real verified claim"
      data-testid="proof-as-cta"
      data-state="loaded"
      className="bg-card ring-foreground/10 shadow-card hover:shadow-card-hover ease-standard mx-auto w-full max-w-3xl rounded-2xl px-6 py-6 ring-1 transition-shadow duration-150 sm:px-8 sm:py-8"
    >
      <div className="flex flex-col gap-5">
        <div className="flex items-center justify-between gap-3">
          <span className="text-muted-foreground text-[10px] font-medium tracking-[0.14em] uppercase">
            Verified Claim · Live Example
          </span>
          {/* Codex visual iter-1 source_pill PARTIAL: reframed as
              "Primary evidence · T<n>" with verified-green tint and a
              bullet glyph (·) so it reads as an evidence-tier control,
              not stray metadata. Restrained tint — no full pill green. */}
          {brief.source.tier ? (
            <span
              data-testid="proof-source-pill"
              className="border-verified/30 text-verified bg-verified/5 inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-0.5 text-[10px] font-medium whitespace-nowrap tracking-[0.04em] uppercase"
            >
              <span aria-hidden>◆</span>
              {brief.source.tier} · Primary evidence
            </span>
          ) : null}
        </div>

        {/* The claim — body-lg, numerics bolded green */}
        <p
          data-testid="proof-claim"
          className="text-foreground text-lg leading-relaxed font-medium text-pretty break-words sm:text-xl"
        >
          {highlightNumerics(claim)}
        </p>

        {/* Trust strip — two-row layout that gives both the verification
            stamp AND the signature pill enough weight to read as serious
            affordances (Codex visual iter-1 honest_signature_pill PARTIAL
            + mobile_fidelity PARTIAL: the previous single-row inline
            layout broke awkwardly on 390px and the signature signal lost
            affordance). Now each signal owns its own row on mobile and
            shares a row on tablet+ with explicit weight + border. */}
        <div className="border-border/60 flex flex-col gap-2 border-t pt-4 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-4 sm:gap-y-2">
          {/* Matched-numbers stamp — promoted to verified-tinted pill */}
          {total > 0 ? (
            <span
              data-testid="proof-matched-stamp"
              className="border-verified/30 text-verified bg-verified/5 inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium tabular-nums sm:text-[13px]"
            >
              <span aria-hidden className="text-verified">✓</span>
              Matched {matched} of {total} number{total === 1 ? "" : "s"}{" "}
              {sourceTail(journal, year)}
            </span>
          ) : (
            <span
              data-testid="proof-matched-stamp"
              className="border-verified/30 text-verified bg-verified/5 inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium sm:text-[13px]"
            >
              <span aria-hidden className="text-verified">✓</span>
              Verifier passed {sourceTail(journal, year)}
            </span>
          )}

          {/* Tri-state signature pill — promoted from inline microcopy to
              its own pill with explicit border + slightly larger glyph.
              Only gpg_verified renders the green "Signed bundle"
              affordance (sub-PR-1 Codex iter-1 P1-005 carry-forward:
              never overclaim a signature). */}
          {brief.signature_state === "gpg_verified" && (
            <span
              data-testid="proof-sig-pill"
              data-state="gpg_verified"
              className="border-verified/30 text-verified bg-verified/5 inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium sm:text-[13px]"
              title="Bundle cryptographically signed; signature verified offline against the pinned trust root."
            >
              <span aria-hidden className="text-verified text-[14px] leading-none">
                ⬡
              </span>
              Signed bundle · verifiable offline
            </span>
          )}
          {brief.signature_state === "present_unverified" && (
            <span
              data-testid="proof-sig-pill"
              data-state="present_unverified"
              className="border-amber-700/40 text-amber-800 bg-amber-50 inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium sm:text-[13px]"
              title="Signature attached but not GPG-verified in this browser context; re-verify offline."
            >
              <span aria-hidden className="text-[14px] leading-none">⊟</span>
              Signature attached · verify offline
            </span>
          )}
          {brief.signature_state === "missing" && (
            <span
              data-testid="proof-sig-pill"
              data-state="missing"
              className="border-contradiction-foreground/30 text-contradiction-foreground bg-contradiction/10 inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium sm:text-[13px]"
              title="No signature on disk — trust not cryptographically established."
            >
              <span aria-hidden className="text-[14px] leading-none">⊠</span>
              Not signed · trust not established
            </span>
          )}
        </div>

        {/* Link to the full proof — anchored to this card */}
        <div className="flex items-center justify-end pt-1">
          <Link
            href={`/inspector/${brief.run_id}`}
            data-testid="proof-as-cta-link"
            className="text-primary focus-visible:ring-ring/70 inline-flex items-center gap-1.5 text-sm font-medium underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
          >
            See the full proof
            <ArrowRight aria-hidden className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </section>
  );
}
