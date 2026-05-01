"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createRun, type TemplateId } from "@/lib/api";

const templates: { id: TemplateId; title: string; domain: string }[] = [
  {
    id: "clinical",
    title: "Clinical drug audit",
    domain: "Health Canada / FDA",
  },
  { id: "trade", title: "Trade & tariff", domain: "USMCA / WTO" },
  { id: "housing", title: "Housing & productivity", domain: "StatCan / CMHC" },
  { id: "defense", title: "Defense & Arctic", domain: "DND / NORAD" },
  {
    id: "climate",
    title: "Climate & critical minerals",
    domain: "ECCC / NRCan",
  },
  { id: "ai_sovereignty", title: "AI sovereignty", domain: "ISED / CIFAR" },
  { id: "canada_us", title: "Canada–US relations", domain: "GAC / DFAIT" },
  { id: "workforce", title: "Workforce & productivity", domain: "ESDC / IRCC" },
];

export default function DashboardPage() {
  const router = useRouter();
  const [template, setTemplate] = useState<TemplateId>("clinical");
  const [question, setQuestion] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (question.trim().length < 4) {
      setError("Question must be at least 4 characters.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const run = await createRun({ template, question: question.trim() });
      router.push(`/runs/${run.run_id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-border bg-background border-b">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex flex-col">
            <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
              POLARIS Canada
            </span>
            <span className="text-foreground text-base font-semibold">
              Sovereign Deep Research
            </span>
          </Link>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-6 py-12">
        <section className="flex flex-col gap-2">
          <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
            Start a research run
          </h1>
          <p className="text-muted-foreground max-w-2xl text-sm sm:text-base">
            Pick a template and ask a focused question. Every claim returned
            will carry a provenance token tied to a primary source.
          </p>
        </section>

        <form onSubmit={onSubmit} className="flex flex-col gap-6">
          <fieldset className="flex flex-col gap-3">
            <legend className="text-foreground text-sm font-semibold">
              Template
            </legend>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {templates.map((t) => (
                <Card
                  key={t.id}
                  className={`cursor-pointer transition ${
                    template === t.id
                      ? "border-foreground"
                      : "border-border hover:border-muted-foreground"
                  }`}
                  onClick={() => setTemplate(t.id)}
                >
                  <CardHeader>
                    <CardDescription className="text-xs tracking-widest uppercase">
                      {t.domain}
                    </CardDescription>
                    <CardTitle className="text-base">{t.title}</CardTitle>
                  </CardHeader>
                </Card>
              ))}
            </div>
          </fieldset>

          <div className="flex flex-col gap-2">
            <label
              htmlFor="question"
              className="text-foreground text-sm font-semibold"
            >
              Research question
            </label>
            <Input
              id="question"
              type="text"
              placeholder="What does the latest CMHC data say about Q3 2025 housing starts?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              minLength={4}
              maxLength={2000}
              required
              disabled={submitting}
            />
          </div>

          {error && (
            <p
              role="alert"
              className="text-destructive border-destructive/50 bg-destructive/10 rounded-md border p-3 text-sm"
            >
              {error}
            </p>
          )}

          <div className="flex items-center justify-end gap-3">
            <Button
              variant="ghost"
              nativeButton={false}
              render={<Link href="/" />}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Queuing…" : "Start run"}
            </Button>
          </div>
        </form>
      </main>

      <footer className="border-border bg-background border-t">
        <div className="text-muted-foreground mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4 text-xs">
          <span>POLARIS v6.2 — Phase 0 scaffold</span>
          <span>Sovereign Canadian deep research</span>
        </div>
      </footer>
    </div>
  );
}
