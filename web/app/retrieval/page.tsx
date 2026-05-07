import Link from "next/link";

import { Button } from "@/components/ui/button";

import { RetrievalRunner } from "./components/retrieval_runner";

export const metadata = {
  title: "Retrieval — POLARIS Canada",
  description:
    "Retrieve verified clinical sources for a research question. POLARIS runs the slice 001 scope gate, then retrieves T1/T2/T3 sources from approved clinical domains.",
};

export default function RetrievalPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-border bg-background border-b">
        <div className="mx-auto flex w-full max-w-4xl items-center justify-between px-6 py-4">
          <div className="flex flex-col">
            <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
              POLARIS Canada — Slice 002
            </span>
            <span className="text-foreground text-base font-semibold">
              Clinical retrieval
            </span>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              nativeButton={false}
              render={<Link href="/intake" />}
            >
              Intake
            </Button>
            <Button
              variant="outline"
              nativeButton={false}
              render={<Link href="/" />}
            >
              Home
            </Button>
          </div>
        </div>
      </header>

      <main
        data-testid="retrieval-page"
        className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-6 py-10"
      >
        <section className="flex flex-col gap-2">
          <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
            Clinical evidence retrieval
          </h1>
          <p className="text-muted-foreground max-w-2xl text-sm sm:text-base">
            Submit a clinical question. POLARIS runs the slice 001 scope gate
            first; if the question is in-scope clinical, the slice 002 retriever
            fans out queries across regulatory (T1), peer-reviewed (T2), and
            registry (T3) sources, deduplicates, and assembles a corpus brief
            with adequacy verdict.
          </p>
        </section>

        <RetrievalRunner />

        <section
          aria-label="What's next"
          className="border-border text-muted-foreground rounded-lg border p-4 text-xs"
        >
          <p>
            <strong className="text-foreground">Slice progression.</strong>{" "}
            Slice 003 (generation with strict-verify) runs against the
            EvidencePool returned here. An inadequate corpus aborts the pipeline
            before any generator token is billed.
          </p>
        </section>
      </main>

      <footer className="border-border bg-background border-t">
        <div className="text-muted-foreground mx-auto flex w-full max-w-4xl items-center justify-between px-6 py-4 text-xs">
          <span>POLARIS v6.2 — Slice 002 (BPEI retrieval half)</span>
          <span>Sovereign Canadian deep research</span>
        </div>
      </footer>
    </div>
  );
}
