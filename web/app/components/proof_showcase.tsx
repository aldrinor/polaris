// I-p2-037 (#794): proof-as-hero showcase. The home LEADS with a REAL verified
// claim from a real POLARIS run + its exact real source span — the differentiator
// made visceral (frontier study: verifiability is the hero). Server component:
// loads the real canonical bundle + resolves the span server-side; renders only
// if the span genuinely resolves (honest — never a fabricated showcase). Links
// to the full Proof Replay.
import { ArrowRight, BadgeCheck, Quote } from "lucide-react";
import Link from "next/link";

import {
  resolveSpan,
  spanInContext,
  type SpanInContext,
} from "@/lib/evidence_span";
import { loadBundle } from "@/lib/inspector_bundle_loader";

const DEMO_RUN_ID = "v1-canonical-success";

function tierLabel(tier: unknown): string | null {
  if (typeof tier === "string" && tier) return tier;
  if (typeof tier === "number") return `T${tier}`;
  return null;
}

export async function ProofShowcase() {
  const bundle = await loadBundle(DEMO_RUN_ID);
  if (!bundle) return null;

  // Pick the first verified sentence whose span genuinely resolves to a real
  // source quote — honest: if nothing resolves, render nothing (no fake proof).
  const sections = bundle.verifiedReport?.sections ?? [];
  let claim: string | null = null;
  let quote: string | null = null;
  let ctx: SpanInContext | null = null;
  let sourceTitle: string | null = null;
  let sourceUrl: string | null = null;
  let tier: string | null = null;

  outer: for (const section of sections) {
    for (const s of section.verified_sentences ?? []) {
      // HONESTY (Codex P1): only feature a sentence the verifier actually
      // passed — never present a dropped/failed sentence as "verified".
      if (s.verifier_pass !== true) continue;
      const tokens = (s.provenance_tokens ?? []).filter(
        (t): t is string => typeof t === "string",
      );
      // Try every token, not just the first (Codex P2): a later token may
      // resolve when an earlier one is malformed.
      for (const token of tokens) {
        const span = resolveSpan(token, bundle.evidencePool);
        // Render the EXACT cited passage full_text[start:end] (Codex P2 —
        // no trim); the length gate uses a trimmed copy only for the check.
        if (span?.quote && span.quote.trim().length > 40) {
          claim = s.sentence_text;
          quote = span.quote;
          // I-p2-038 (#821): render the exact span IN its real source context
          // (so it doesn't read as a mid-word fragment), with the exact cited
          // passage highlighted. Faithful: span === full_text[start:end].
          ctx = spanInContext(span.source?.full_text, span.start, span.end);
          sourceTitle = span.source?.title ?? null;
          sourceUrl = span.source?.url ?? null;
          tier = tierLabel(span.source?.tier);
          break outer;
        }
      }
    }
  }

  if (!claim || !quote) return null;

  const question = bundle.verifiedReport?.research_question;

  return (
    <section
      aria-label="A real verified claim"
      data-testid="proof-showcase"
      className="border-border bg-card relative overflow-hidden rounded-2xl border shadow-sm"
    >
      <div className="border-border/70 bg-muted/30 flex items-center justify-between gap-3 border-b px-5 py-3">
        <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
          A real verified claim
        </span>
        {tier ? (
          <span className="text-muted-foreground border-border rounded-full border px-2 py-0.5 font-mono text-[11px]">
            {tier} source
          </span>
        ) : null}
      </div>

      <div className="grid gap-0 md:grid-cols-2">
        {/* The claim + verdict */}
        <div className="flex flex-col gap-3 p-6">
          <div className="text-verified inline-flex items-center gap-1.5 text-xs font-semibold">
            <BadgeCheck aria-hidden className="h-4 w-4" />
            Verified against a primary source
          </div>
          <p className="text-foreground text-lg leading-relaxed font-medium text-pretty">
            {claim}
          </p>
          {question ? (
            <p className="text-muted-foreground text-xs">
              From a POLARIS brief answering:{" "}
              <span className="text-foreground/80">{question}</span>
            </p>
          ) : null}
        </div>

        {/* The exact real source span — the proof */}
        <div className="border-border/70 bg-muted/20 flex flex-col gap-3 border-t p-6 md:border-t-0 md:border-l">
          <div className="text-muted-foreground inline-flex items-center gap-1.5 text-xs font-medium">
            <Quote aria-hidden className="h-4 w-4" />
            The exact passage it came from
          </div>
          <blockquote className="border-primary/40 text-muted-foreground border-l-2 pl-3 text-sm leading-relaxed">
            {ctx ? (
              <span className="font-serif">
                {ctx.leadingEllipsis ? "… " : "“"}
                {ctx.before}
                <mark className="bg-primary/10 text-foreground rounded-[3px] decoration-clone px-0.5 font-medium">
                  {ctx.span}
                </mark>
                {ctx.after}
                {ctx.trailingEllipsis ? " …" : "”"}
              </span>
            ) : (
              <span className="text-foreground/90">“{quote}”</span>
            )}
          </blockquote>
          <p className="text-muted-foreground/80 text-[11px]">
            Highlighted text is the exact span cited by the claim.
          </p>
          {sourceTitle ? (
            <p className="text-muted-foreground truncate text-xs">
              {sourceUrl ? (
                <a
                  href={sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-foreground underline-offset-2 hover:underline"
                >
                  {sourceTitle}
                </a>
              ) : (
                sourceTitle
              )}
            </p>
          ) : null}
        </div>
      </div>

      <div className="border-border/70 flex items-center justify-between gap-3 border-t px-5 py-3">
        <span className="text-muted-foreground text-xs">
          Every sentence in a POLARIS brief is checked this way.
        </span>
        <Link
          href={`/inspector/${DEMO_RUN_ID}`}
          className="text-primary focus-visible:ring-ring/70 inline-flex items-center gap-1 rounded text-sm font-medium underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
        >
          See the full proof
          <ArrowRight aria-hidden className="h-4 w-4" />
        </Link>
      </div>
    </section>
  );
}
