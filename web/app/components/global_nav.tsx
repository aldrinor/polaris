"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * I-rdy-014 (#510) — single global navigation header for the POLARIS demo.
 *
 * Mounted once in `app/layout.tsx` so every page inherits one coherent
 * header. Carries only the non-dynamic top-level journey entries; per-run
 * pages (`/runs/[id]`, `/inspector/[id]`) are reached contextually.
 *
 * The 17 test-harness routes are hidden by suppressing the nav on their
 * URL-path prefixes (route groups are URL-neutral, so this matches the URL,
 * not the filesystem). The pre-auth `/sign-in` screen is also suppressed.
 */

const NAV_LINKS: { href: string; label: string }[] = [
  { href: "/", label: "Home" },
  { href: "/dashboard", label: "Start a run" },
  { href: "/memory", label: "Workspace memory" },
  { href: "/pin_replay", label: "Pin & replay" },
];

const SUPPRESS_PREFIXES: string[] = [
  "/sign-in",
  "/charts_test",
  "/sentence_hover_test",
  "/disambiguation_modal_preview",
];

function isSuppressed(path: string): boolean {
  return SUPPRESS_PREFIXES.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`),
  );
}

function isActive(path: string, href: string): boolean {
  if (href === "/") return path === "/";
  return path === href || path.startsWith(`${href}/`);
}

export function GlobalNav() {
  const path = usePathname() ?? "/";
  if (isSuppressed(path)) return null;

  return (
    <header className="border-border bg-background border-b">
      <nav
        aria-label="Primary"
        className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-6 py-3"
      >
        <Link href="/" className="flex flex-col" data-testid="global-nav-brand">
          <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
            POLARIS Canada
          </span>
          <span className="text-foreground text-sm font-semibold">
            Sovereign Deep Research
          </span>
        </Link>
        <div className="flex items-center gap-1">
          {NAV_LINKS.map((link) => {
            const active = isActive(path, link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                data-testid={`global-nav-${link.href === "/" ? "home" : link.href.slice(1)}`}
                aria-current={active ? "page" : undefined}
                className={
                  active
                    ? "text-foreground rounded-md px-3 py-2 text-sm font-semibold"
                    : "text-muted-foreground hover:text-foreground rounded-md px-3 py-2 text-sm"
                }
              >
                {link.label}
              </Link>
            );
          })}
          <Link
            href="/sign-in"
            data-testid="header-sign-in-link"
            className="border-border text-foreground ml-2 rounded-md border px-3 py-2 text-sm font-medium"
          >
            Sign in
          </Link>
        </div>
      </nav>
    </header>
  );
}
