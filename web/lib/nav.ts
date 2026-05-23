// I-p2-029 (#768): single source of truth for the primary nav.
// Consumed by BOTH AppShell and HomeKeyboardShell so the nav can never drift
// between shells (previously the PRIMARY_NAV const was duplicated in each).
//
// I-p2-039 (#825): the nav is now AUTH-AWARE (public/app split). An
// unauthenticated visitor sees only the lean public set (Home + Ask); the
// reviewer tools (Dashboard + the rest) appear only once signed in — so the
// pre-login product no longer reads like an internal tool suite, and gated
// links no longer dead-end at /sign-in. This is PRESENTATION only, never an
// authorization gate (per-route RBAC is the security control).

import type { RoleId } from "@/lib/roles";

export interface NavItem {
  href: string;
  label: string;
  /** I-p2-039: who SEES this item. "public" = always (signed in or not);
   * "app" = only when authenticated. Presentation-only, not authorization. */
  visibility: "public" | "app";
  /** Roles that may SEE this item (presentation-only). Omitted = all roles. */
  roles?: readonly RoleId[];
}

export const PRIMARY_NAV: readonly NavItem[] = [
  { href: "/", label: "Home", visibility: "public" },
  // "Intake" was internal jargon (I-p2-039) — the public action is "Ask".
  { href: "/intake", label: "Ask", visibility: "public" },
  { href: "/dashboard", label: "Dashboard", visibility: "app" },
  { href: "/upload", label: "Upload", visibility: "app" },
  { href: "/benchmark", label: "Benchmark", visibility: "app" },
  { href: "/compare", label: "Compare", visibility: "app" },
  { href: "/contracts", label: "Contracts", visibility: "app" },
  { href: "/pin_replay", label: "Pin Replay", visibility: "app" },
  { href: "/memory", label: "Memory", visibility: "app" },
];

/** I-p2-039: presentation-only auth filter. Public items always show; app items
 * only when authenticated. Pure + isomorphic (safe in server or client). */
export function navForAuth(
  items: readonly NavItem[],
  authed: boolean,
): readonly NavItem[] {
  return items.filter((item) => item.visibility === "public" || authed);
}

/** Presentation-only nav filter by role. Pure + isomorphic (safe in server or
 * client). Items without a `roles` list are visible to every role. Orthogonal
 * to navForAuth; retained for future per-persona nav. */
export function navForRole(
  items: readonly NavItem[],
  role: RoleId,
): readonly NavItem[] {
  return items.filter((item) => !item.roles || item.roles.includes(role));
}
