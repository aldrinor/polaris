// I-p2-038 (#821): the shared global footer — the SINGLE source of truth for
// both the home shell and AppShell (every non-chromeless route). Before this,
// only the home page had a footer, so every other page ended in an empty void
// below the fold. Honest sovereignty microcopy that matches the header
// "Canadian-hosted" mark: the VM is hosted in OVH Québec; public sources are
// fetched via logged Canadian egress; every brief is integrity-hashed. NO
// overclaim — production LLM inference is currently OpenRouter (US, transitional)
// and that is disclosed at /transparency, linked here. Every link points at a
// PUBLIC route (no auth-gated dead-ends in the footer).
import Link from "next/link";

const FOOTER_LINKS = [
  { href: "/intake", label: "Ask a question" },
  { href: "/inspector/v1-canonical-success", label: "See a verified brief" },
  { href: "/transparency", label: "Transparency & disclosure" },
] as const;

export function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="border-border bg-muted/20 mt-16 border-t">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-10 md:flex-row md:items-start md:justify-between">
        <div className="flex max-w-md flex-col gap-2">
          <span className="text-foreground font-mono text-sm font-semibold tracking-tight">
            POLARIS · Canada
          </span>
          <p className="text-muted-foreground text-xs leading-relaxed">
            Canadian-hosted deep research. Every claim in a POLARIS brief is
            verified — span by span — against its primary source by an
            independent evaluator family.
          </p>
          <span className="text-muted-foreground/80 mt-1 inline-flex items-center gap-1.5 text-[11px]">
            <span aria-hidden>⬡</span> Hosted in Canada (Québec) · public
            sources via logged Canadian egress
          </span>
        </div>

        <nav
          aria-label="Footer"
          className="flex flex-col gap-2 md:items-end md:text-right"
        >
          {FOOTER_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-muted-foreground hover:text-foreground focus-visible:ring-ring/70 w-fit rounded text-xs underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none md:self-end"
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>

      <div className="border-border/60 border-t">
        <div className="text-muted-foreground/70 mx-auto flex w-full max-w-7xl flex-col gap-1 px-6 py-4 text-[11px] sm:flex-row sm:items-center sm:justify-between">
          <span>© {year} POLARIS · Canadian-hosted deep research</span>
          <span>
            LLM inference is currently routed via OpenRouter (US), disclosed at{" "}
            <Link
              href="/transparency"
              className="hover:text-foreground underline underline-offset-2"
            >
              /transparency
            </Link>
            .
          </span>
        </div>
      </div>
    </footer>
  );
}
