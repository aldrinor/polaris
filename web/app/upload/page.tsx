import { ArrowRight, FileText, Layers, Sparkles } from "lucide-react";
import Link from "next/link";

import { UploadWorkspace } from "./components/upload_workspace";

export const metadata = {
  title: "Upload — POLARIS Canada",
  description:
    "Upload documents to POLARIS. Markdown and text files are split into chunks you can preview; PDF and DOCX are accepted too (50MB max).",
};

// I-p2-047 (#841): factual post-upload flow — describes the real
// parse → chunk → ground-intake path (no fabricated claims) — so the page
// reads intentional instead of a drop zone above empty space.
const STEPS = [
  {
    icon: FileText,
    title: "Drop your files",
    body: "PDF, DOCX, MD, or TXT — up to 50MB each.",
  },
  {
    icon: Layers,
    title: "Parsed into chunks",
    body: "Markdown and text files are split into chunks today.",
  },
  {
    icon: Sparkles,
    title: "Preview the result",
    body: "Open a parsed document to inspect a preview of its chunks.",
  },
] as const;

// I-cd-026 (#616): /upload rebuild — G6 fix. Page no longer renders its
// own <main>; AppShell (via AppShellGate, I-cd-022) is the single
// landmark provider. testid preserved on the <section> wrapper.
export default function UploadPage() {
  return (
    <section
      data-testid="upload-page"
      className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-6 py-10"
    >
      <div className="flex flex-col gap-2">
        <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
          Upload documents
        </h1>
        <p className="text-muted-foreground max-w-2xl text-sm sm:text-base">
          Drop PDFs, MD, TXT, or DOCX files (50MB per file max). POLARIS splits
          Markdown and text into chunks you can preview right here.
        </p>
      </div>

      <UploadWorkspace />

      {/* What happens after upload — sibling band (no nested card / no landmark) */}
      <div className="border-border/60 flex flex-col gap-5 border-t pt-8">
        <div className="grid gap-x-6 gap-y-5 sm:grid-cols-3">
          {STEPS.map((step, i) => (
            <div key={step.title} className="flex flex-col gap-1.5">
              <div className="text-muted-foreground flex items-center gap-2">
                <span className="bg-muted text-foreground inline-flex h-5 w-5 items-center justify-center rounded-full text-xs font-semibold tabular-nums">
                  {i + 1}
                </span>
                <step.icon aria-hidden className="text-primary h-4 w-4" />
              </div>
              <h2 className="text-foreground text-sm font-semibold">
                {step.title}
              </h2>
              <p className="text-muted-foreground text-sm leading-relaxed">
                {step.body}
              </p>
            </div>
          ))}
        </div>
        <Link
          href="/intake"
          className="text-primary focus-visible:ring-ring/70 inline-flex w-fit items-center gap-1 rounded text-sm font-medium underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
        >
          Ask a research question
          <ArrowRight aria-hidden className="h-4 w-4" />
        </Link>
      </div>
    </section>
  );
}
