"use client";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  type DropReason,
  type EvidencePool,
  type ReportVerifiedSentence,
  type RetrievalSource,
  type RetrievalSourceTier,
} from "@/lib/api";
import { parseAllTokens, type ParsedToken } from "@/lib/provenance_tokens";

const DROP_REASON_LABEL: Record<DropReason, string> = {
  invalid_token: "Invalid token (source not in pool)",
  span_out_of_range: "Span out of range",
  numeric_mismatch: "Numeric mismatch (decimal not in cited span)",
  overlap_too_low: "Content-word overlap too low",
  no_provenance_token: "No provenance token",
};

const TIER_RATIONALE: Record<RetrievalSourceTier, string> = {
  T1: "Regulatory & Cochrane systematic reviews — highest evidentiary weight",
  T2: "Peer-reviewed primary research (RCTs, cohorts, meta-analyses)",
  T3: "Registries, clinical guidelines, government health agencies",
};

const TIER_TONE: Record<RetrievalSourceTier, string> = {
  T1: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  T2: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  T3: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300",
};

function AgreementBadge({
  evaluator_agrees,
}: {
  evaluator_agrees: boolean | null;
}) {
  if (evaluator_agrees === true) {
    return (
      <span
        data-testid="inspector-agree"
        className="inline-flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium tracking-widest text-emerald-700 uppercase dark:text-emerald-300"
        title="Two-family evaluator agrees with generator claim"
      >
        Agree
      </span>
    );
  }
  if (evaluator_agrees === false) {
    return (
      <span
        data-testid="inspector-disagree"
        className="inline-flex items-center gap-1 rounded-full border border-rose-500/40 bg-rose-500/10 px-2 py-0.5 text-[10px] font-medium tracking-widest text-rose-700 uppercase dark:text-rose-300"
        title="Two-family evaluator disagrees with generator claim"
      >
        Disagree
      </span>
    );
  }
  return (
    <span
      data-testid="inspector-agree-pending"
      className="border-border bg-muted/40 text-muted-foreground inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium tracking-widest uppercase"
      title="Two-family evaluator pass not yet recorded"
    >
      Pending
    </span>
  );
}

function SourceCard({
  token,
  source,
  idx,
}: {
  token: ParsedToken;
  source: RetrievalSource | undefined;
  idx: number;
}) {
  if (!source) {
    return (
      <div
        data-testid={`inspector-source-missing-${idx}`}
        className="rounded border border-rose-500/40 p-2 text-xs text-rose-700 dark:text-rose-300"
      >
        Source <code>{token.source_id}</code> not in pool — token {token.raw}.
      </div>
    );
  }
  const text = source.full_text ?? source.snippet ?? "";
  const out_of_range = token.end > text.length;
  const span = out_of_range ? "" : text.slice(token.start, token.end);
  return (
    <div
      data-testid={`inspector-source-${idx}`}
      className="border-border flex flex-col gap-1 rounded border p-2 text-xs"
    >
      <div className="flex items-center justify-between gap-2">
        <a
          data-testid={`inspector-source-url-${idx}`}
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-700 underline dark:text-blue-300"
        >
          {source.domain}
        </a>
        <span
          data-testid={`inspector-tier-${source.tier}`}
          title={TIER_RATIONALE[source.tier]}
          className={`rounded-full border px-2 py-0.5 text-[10px] tracking-widest uppercase ${TIER_TONE[source.tier]}`}
        >
          {source.tier}
        </span>
      </div>
      <p
        data-testid={`inspector-trace-${idx}`}
        className="text-muted-foreground"
      >
        <strong className="text-foreground">{source.title}</strong>
        {source.publication_date && <> · {source.publication_date}</>}
        {source.authors[0] && (
          <>
            {" "}
            · {source.authors.slice(0, 2).join(", ")}
            {source.authors.length > 2 ? " et al." : ""}
          </>
        )}
      </p>
      {out_of_range ? (
        <p
          data-testid={`inspector-span-out-of-range-${idx}`}
          className="text-rose-700 dark:text-rose-300"
        >
          (span out of range: {token.start}-{token.end} of {text.length})
        </p>
      ) : (
        <blockquote
          data-testid={`inspector-span-${idx}`}
          className="border-l-2 border-yellow-400 bg-yellow-50 px-2 py-1 italic dark:bg-yellow-900/20"
        >
          {span || "(empty span)"}
        </blockquote>
      )}
    </div>
  );
}

export function SentenceInspector({
  open,
  onOpenChange,
  sentence,
  sentence_id,
  pool,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  sentence: ReportVerifiedSentence | null;
  sentence_id: string | null;
  pool: EvidencePool | null;
}) {
  const tokens = sentence ? parseAllTokens(sentence.provenance_tokens) : [];
  const pool_index = new Map(pool?.sources.map((s) => [s.source_id, s]) ?? []);
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        data-testid="sentence-inspector-sheet"
        side="right"
        className="data-[side=right]:w-full data-[side=right]:sm:w-2/5 data-[side=right]:sm:max-w-none"
      >
        <SheetHeader>
          <SheetTitle data-testid="sentence-inspector-id">
            {sentence_id ?? "Sentence inspector"}
          </SheetTitle>
          <SheetDescription>
            Provenance and verification details for the selected sentence.
          </SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-3 px-4 pb-4 text-sm">
          {sentence && (
            <>
              <div className="flex items-start justify-between gap-2">
                <p
                  data-testid="sentence-inspector-text"
                  className="text-foreground flex-1"
                >
                  {sentence.sentence_text}
                </p>
                <AgreementBadge
                  evaluator_agrees={sentence.evaluator_agrees}
                />
              </div>
              {tokens.length === 0 ? (
                <p className="text-muted-foreground text-xs italic">
                  No provenance tokens.
                </p>
              ) : (
                <div
                  data-testid="inspector-sources"
                  className="flex flex-col gap-2"
                >
                  {tokens.map((tok, i) => (
                    <SourceCard
                      key={i}
                      token={tok}
                      source={pool_index.get(tok.source_id)}
                      idx={i}
                    />
                  ))}
                </div>
              )}
              {sentence.drop_reason && (
                <p
                  data-testid="sentence-inspector-drop"
                  className="text-xs tracking-widest text-rose-700 uppercase dark:text-rose-300"
                >
                  dropped —{" "}
                  {DROP_REASON_LABEL[sentence.drop_reason as DropReason]}
                </p>
              )}
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
