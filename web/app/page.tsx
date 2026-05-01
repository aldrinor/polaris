import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type ResearchTemplate = {
  id: string;
  title: string;
  domain: string;
  description: string;
};

const research_templates: ResearchTemplate[] = [
  {
    id: "clinical_drug_audit",
    title: "Clinical drug audit",
    domain: "Health Canada / FDA",
    description:
      "Audit drug safety signals, labelling deltas, and post-market surveillance evidence across Health Canada, FDA, and EMA.",
  },
  {
    id: "trade_and_tariff",
    title: "Trade & tariff",
    domain: "USMCA / WTO",
    description:
      "Compare Canadian tariff schedules, retaliation scenarios, and supply-chain exposure with primary-source customs data.",
  },
  {
    id: "housing_and_productivity",
    title: "Housing & productivity",
    domain: "StatCan / CMHC",
    description:
      "Synthesize housing starts, productivity gaps, and structural drivers from StatCan, CMHC, and OECD long-form datasets.",
  },
];

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-border bg-background border-b">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex flex-col">
            <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
              POLARIS Canada
            </span>
            <span className="text-foreground text-base font-semibold">
              Sovereign Deep Research
            </span>
          </div>
          <Button
            variant="default"
            nativeButton={false}
            render={<Link href="/sign-in" />}
          >
            Sign in
          </Button>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-10 px-6 py-12">
        <section className="flex flex-col gap-3">
          <h1 className="text-foreground text-3xl font-semibold tracking-tight sm:text-4xl">
            POLARIS Canada — Sovereign Deep Research
          </h1>
          <p className="text-muted-foreground max-w-3xl text-base sm:text-lg">
            Two-family verified evidence pipelines for Government of Canada
            policy work. Every claim carries a provenance token tied to a
            primary source.
          </p>
        </section>

        <section
          aria-labelledby="research_templates_heading"
          className="flex flex-col gap-5"
        >
          <div className="flex items-baseline justify-between">
            <h2
              id="research_templates_heading"
              className="text-foreground text-xl font-semibold tracking-tight"
            >
              Research templates
            </h2>
            <span className="text-muted-foreground text-xs tracking-widest uppercase">
              Phase 1 placeholders
            </span>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {research_templates.map((template) => (
              <Card key={template.id} className="flex flex-col">
                <CardHeader>
                  <CardDescription className="text-xs tracking-widest uppercase">
                    {template.domain}
                  </CardDescription>
                  <CardTitle className="text-lg">{template.title}</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col justify-between gap-4">
                  <p className="text-muted-foreground text-sm">
                    {template.description}
                  </p>
                  <Button
                    variant="outline"
                    nativeButton={false}
                    render={<Link href="/dashboard" />}
                  >
                    Start a research run
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
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
