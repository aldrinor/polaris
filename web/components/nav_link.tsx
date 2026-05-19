"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * I-cd-004: client component for top-nav active-route highlight. Pure styling
 * via the locked shadcn token set (accent / muted-foreground / foreground).
 * Active when the pathname equals href, or starts with `${href}/` for nested
 * routes (e.g. `/runs/abc` highlights "Dashboard" only if we want — by default
 * an item is active for its own subtree).
 */
export function NavLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const is_active =
    pathname === href || (href !== "/" && pathname.startsWith(`${href}/`));
  return (
    <Link
      href={href}
      aria-current={is_active ? "page" : undefined}
      className={
        "rounded-md px-3 py-1.5 text-sm font-medium transition-colors " +
        (is_active
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:bg-accent/50 hover:text-foreground")
      }
    >
      {children}
    </Link>
  );
}
