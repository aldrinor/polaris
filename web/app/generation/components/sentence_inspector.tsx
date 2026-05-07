"use client";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { type DropReason, type ReportVerifiedSentence } from "@/lib/api";

const DROP_REASON_LABEL: Record<DropReason, string> = {
  invalid_token: "Invalid token (source not in pool)",
  span_out_of_range: "Span out of range",
  numeric_mismatch: "Numeric mismatch (decimal not in cited span)",
  overlap_too_low: "Content-word overlap too low",
  no_provenance_token: "No provenance token",
};

export function SentenceInspector({
  open,
  onOpenChange,
  sentence,
  sentence_id,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  sentence: ReportVerifiedSentence | null;
  sentence_id: string | null;
}) {
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
              <p
                data-testid="sentence-inspector-text"
                className="text-foreground"
              >
                {sentence.sentence_text}
              </p>
              {sentence.provenance_tokens.length > 0 ? (
                <ul
                  data-testid="sentence-inspector-tokens"
                  className="text-muted-foreground font-mono text-xs"
                >
                  {sentence.provenance_tokens.map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground text-xs italic">
                  No provenance tokens.
                </p>
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
