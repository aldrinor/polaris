import Link from "next/link";

import { Button } from "@/components/ui/button";

import { GenerationRunner } from "./components/generation_runner";

export const metadata = {
  title: "Generation — POLARIS Canada",
  description:
    "End-to-end clinical research: intake → retrieval → generation with strict-verify. Every sentence carries a provenance token tied to a primary source.",
};

export default function GenerationPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-border bg-background border-b">
        <div className="mx-auto flex w-full max-w-4xl items-center justify-between px-6 py-4">
          <div className="flex flex-col">
            <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
              POLARIS Canada — Slice 003
            </span>
            <span className="text-foreground text-base font-semibold">
              Verified clinical research
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
              render={<Link href="/retrieval" />}
            >
              Retrieval
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
        data-testid="generation-page"
        className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-6 py-10"
      >
        <section className="flex flex-col gap-2">
          <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
            Verified clinical research, end-to-end
          </h1>
          <p className="text-muted-foreground max-w-2xl text-sm sm:text-base">
            POLARIS chains the full BPEI spine: scope discovery (slice 001),
            retrieval against verified clinical sources (slice 002), and
            generation with strict-verify (slice 003). Every shipped sentence
            carries a provenance token of the form{" "}
            <code className="bg-muted rounded px-1 py-0.5 text-xs">
              [#ev:source_id:start-end]
            </code>{" "}
            and has been numerically + semantically checked against the cited
            source span.
          </p>
        </section>

        <GenerationRunner />

        <section
          aria-label="What's next"
          className="border-border text-muted-foreground rounded-lg border p-4 text-xs"
        >
          <p>
            <strong className="text-foreground">Slice progression.</strong>{" "}
            Slice 004 (audit bundle export, GPG-signed) packages this
            verified report into a portable evidence bundle. Slice 005
            (BEAT-BOTH benchmark) compares POLARIS's output head-to-head
            against ChatGPT Deep Research and Gemini DR on 7 dimensions.
          </p>
        </section>
      </main>

      <footer className="border-border bg-background border-t">
        <div className="text-muted-foreground mx-auto flex w-full max-w-4xl items-center justify-between px-6 py-4 text-xs">
          <span>POLARIS v6.2 — Slice 003 (BPEI generator + strict-verify)</span>
          <span>Sovereign Canadian deep research</span>
        </div>
      </footer>
    </div>
  );
}
