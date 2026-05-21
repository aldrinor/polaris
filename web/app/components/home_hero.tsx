"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";

/**
 * I-cd-ui-001 — frontier-research-tool home hero (Perplexity-style).
 * Single-question entry that POSTs the query into the intake flow.
 */
export function HomeHero(): React.ReactElement {
  const router = useRouter();
  const [question, set_question] = useState("");
  const [template, set_template] = useState<string>("ai_sovereignty");

  function submit(event: React.FormEvent): void {
    event.preventDefault();
    if (!question.trim()) return;
    const params = new URLSearchParams({
      template,
      q: question.trim(),
    });
    router.push(`/intake?${params.toString()}`);
  }

  return (
    <section
      aria-labelledby="hero_heading"
      className="relative flex flex-col gap-8 py-10 sm:py-16"
      data-testid="home-hero"
    >
      <div className="flex flex-col gap-4">
        <span className="text-primary inline-flex w-fit items-center gap-2 text-xs font-medium tracking-[0.18em] uppercase">
          <span
            aria-hidden="true"
            className="bg-primary inline-block h-1.5 w-6 rounded-full"
          />
          Sovereign Canadian deep research
        </span>
        <h1
          id="hero_heading"
          className="text-foreground text-3xl leading-tight font-semibold tracking-tight sm:text-5xl md:text-6xl"
        >
          What can POLARIS
          <br />
          verify for you today?
        </h1>
        <p className="text-muted-foreground max-w-2xl text-base sm:text-lg">
          Every claim carries a provenance token tied to a primary source.
          Two‑family verification: generator and evaluator from different model
          lineages. Built for Government of Canada policy work.
        </p>
      </div>

      <form
        aria-label="Start a research run"
        className="ring-border bg-card focus-within:ring-primary/30 relative flex flex-col gap-3 rounded-2xl p-3 ring-1 transition-shadow focus-within:ring-2 sm:flex-row sm:items-end sm:gap-2"
        data-testid="home-hero-form"
        onSubmit={submit}
      >
        <div className="flex-1">
          <label
            className="text-muted-foreground sr-only"
            htmlFor="home_hero_question"
          >
            Research question
          </label>
          <textarea
            autoFocus
            className="placeholder:text-muted-foreground w-full resize-none border-0 bg-transparent text-base outline-none sm:text-lg"
            data-testid="home-hero-question"
            id="home_hero_question"
            onChange={(e) => set_question(e.target.value)}
            placeholder="Ask anything — clinical, policy, AI sovereignty, Canada-US, due diligence …"
            rows={2}
            value={question}
          />
        </div>
        <div className="flex items-center gap-2">
          <label
            className="text-muted-foreground sr-only"
            htmlFor="home_hero_template"
          >
            Template
          </label>
          <select
            className="border-border bg-background rounded-md border px-3 py-2 text-sm"
            data-testid="home-hero-template"
            id="home_hero_template"
            onChange={(e) => set_template(e.target.value)}
            value={template}
          >
            <option value="ai_sovereignty">AI sovereignty</option>
            <option value="clinical">Clinical</option>
            <option value="policy">Public policy</option>
            <option value="tech">Technology</option>
            <option value="canada_us">Canada–US</option>
            <option value="due_diligence">Due diligence</option>
            <option value="workforce">Workforce</option>
            <option value="custom">Custom</option>
          </select>
          <Button
            data-testid="home-hero-submit"
            disabled={!question.trim()}
            type="submit"
          >
            Start research →
          </Button>
        </div>
      </form>

      <p className="text-muted-foreground text-xs">
        Or{" "}
        <Link
          className="text-primary underline-offset-4 hover:underline"
          href="/dashboard"
        >
          open the dashboard
        </Link>{" "}
        ·{" "}
        <Link
          className="text-primary underline-offset-4 hover:underline"
          href="/benchmark"
        >
          BEAT-BOTH benchmark
        </Link>{" "}
        ·{" "}
        <Link
          className="text-primary underline-offset-4 hover:underline"
          href="/transparency"
        >
          sovereignty disclosure
        </Link>
      </p>
    </section>
  );
}
