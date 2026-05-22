// I-p2-034 (#790): responsive primary nav. Inline links on desktop (md+);
// a hamburger menu below md so the 9 routes never overflow off-screen on a
// phone (the prior single-row nav clipped half the links). Shared by AppShell
// + HomeKeyboardShell (single nav source @/lib/nav). a11y: aria-expanded +
// aria-controls + Escape-to-close + focus-visible; closes on navigation.
"use client";

import { Menu, X } from "lucide-react";
import { useEffect, useState } from "react";

import { NavLink } from "@/components/nav_link";
import { PRIMARY_NAV, navForRole } from "@/lib/nav";
import { DEFAULT_ROLE } from "@/lib/roles";

export function PrimaryNav() {
  const [open, setOpen] = useState(false);
  const items = navForRole(PRIMARY_NAV, DEFAULT_ROLE);

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
      {/* Desktop: inline links */}
      <nav className="hidden items-center gap-1 md:flex" aria-label="Primary">
        {items.map((item) => (
          <NavLink key={item.href} href={item.href}>
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Mobile: hamburger + dropdown */}
      <div className="md:hidden">
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
