import { UploadWorkspace } from "./components/upload_workspace";

export const metadata = {
  title: "Upload — POLARIS Canada",
  description:
    "Upload documents for grounding. Drag PDFs, MD, TXT, or DOCX (50MB max).",
};

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
          Drop PDFs, MD, TXT, or DOCX files. POLARIS will parse and chunk each
          document so you can ground intake queries against your uploads (50MB
          per file max).
        </p>
      </div>

      <UploadWorkspace />
    </section>
  );
}
