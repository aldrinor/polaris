// I-p2-029 (#768): single source of truth for the primary nav.
// Consumed by BOTH AppShell and HomeKeyboardShell so the nav can never drift
// between shells (previously the PRIMARY_NAV const was duplicated in each).

import type { RoleId } from "@/lib/roles";

export interface NavItem {
  href: string;
  label: string;
  /** Roles that may SEE this item (presentation-only — not authorization).
   * Omitted = visible to all roles. */
  roles?: readonly RoleId[];
}

export const PRIMARY_NAV: readonly NavItem[] = [
  { href: "/", label: "Home" },
  { href: "/intake", label: "Intake" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/upload", label: "Upload" },
  { href: "/benchmark", label: "Benchmark" },
  { href: "/compare", label: "Compare" },
  { href: "/contracts", label: "Contracts" },
  { href: "/pin_replay", label: "Pin Replay" },
  { href: "/memory", label: "Memory" },
];

/** Presentation-only nav filter by role. Pure + isomorphic (safe in server or
 * client). Items without a `roles` list are visible to every role. */
export function navForRole(
  items: readonly NavItem[],
  role: RoleId,
): readonly NavItem[] {
  return items.filter((item) => !item.roles || item.roles.includes(role));
}
