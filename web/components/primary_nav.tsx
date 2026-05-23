// I-p2-034 (#790): responsive primary nav. Inline links on desktop; a hamburger
// below the inline breakpoint so the nav never overflows off-screen.
// I-p2-039 (#825): the nav is AUTH-AWARE — unauthenticated visitors see only the
// lean public set (Home + Ask); the reviewer tools appear once signed in. Auth is
// read via useSyncExternalStore (SSR-safe, same pattern as AuthButton): server +
// first client paint render the public-only nav, then the authed set fills in
// after mount. The inline breakpoint is `xl` (1280px) — at `lg` (1024) the full
// authed set + brand + Canadian-hosted mark + AuthButton overflows (Codex P1).
// a11y: aria-expanded + aria-controls + Escape-to-close + focus-visible; closes
// on navigation.
"use client";

import { Menu, X } from "lucide-react";
import { useEffect, useState, useSyncExternalStore } from "react";

import { NavLink } from "@/components/nav_link";
import { isAuthenticated } from "@/lib/auth";
import { PRIMARY_NAV, navForAuth } from "@/lib/nav";

// Cross-tab auth changes fire a `storage` event; same-tab sign-in/out re-mounts
// the shell on navigation, so the snapshot is re-read either way.
function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

export function PrimaryNav() {
  const [open, setOpen] = useState(false);
  const authed = useSyncExternalStore(
    subscribe,
    () => isAuthenticated(), // client: real auth state
    () => false, // server / first hydration paint: public-only nav
  );
  const items = navForAuth(PRIMARY_NAV, authed);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      {/* Desktop: inline links (xl+ so the full authed header fits) */}
      <nav className="hidden items-center gap-1 xl:flex" aria-label="Primary">
        {items.map((item) => (
          <NavLink key={item.href} href={item.href}>
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Below xl: hamburger + dropdown */}
      <div className="xl:hidden">
        <button
          type="button"
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          aria-controls="primary-nav-mobile"
          onClick={() => setOpen((o) => !o)}
          className="text-foreground hover:bg-muted focus-visible:ring-ring/70 inline-flex h-9 w-9 items-center justify-center rounded-md focus-visible:ring-2 focus-visible:outline-none"
        >
          {open ? (
            <X aria-hidden className="h-5 w-5" />
          ) : (
            <Menu aria-hidden className="h-5 w-5" />
          )}
        </button>
        {open && (
          <>
            {/* click-away backdrop */}
            <div
              className="fixed inset-0 z-40"
              aria-hidden
              onClick={() => setOpen(false)}
            />
            <nav
              id="primary-nav-mobile"
              aria-label="Primary"
              className="border-border bg-background absolute inset-x-0 top-full z-50 flex flex-col gap-1 border-b p-3 shadow-md"
            >
              {items.map((item) => (
                <NavLink
                  key={item.href}
                  href={item.href}
                  onClick={() => setOpen(false)}
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </>
        )}
      </div>
    </>
  );
}
