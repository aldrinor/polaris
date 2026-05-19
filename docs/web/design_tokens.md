# POLARIS web — canonical design tokens (I-cd-004, locked)

The canonical token set IS the shadcn-ui default theme currently defined in
`web/app/globals.css` (`@theme inline` block). I-cd-004 LOCKS this set: the
I-cd-013..030 per-route rebuilds use ONLY these names. No new tokens are
invented; no token in this list is renamed without a follow-up issue.

`globals.css` itself is unchanged by I-cd-004.

## Color tokens

Base surface / text:
- `--color-background`, `--color-foreground`
- `--color-card`, `--color-card-foreground`
- `--color-popover`, `--color-popover-foreground`

Interaction palette (use exactly these for buttons, links, focus rings):
- `--color-primary`, `--color-primary-foreground`
- `--color-secondary`, `--color-secondary-foreground`
- `--color-accent`, `--color-accent-foreground`
- `--color-muted`, `--color-muted-foreground`
- `--color-destructive`, `--color-destructive-foreground`

Forms / chrome:
- `--color-border`, `--color-input`, `--color-ring`

Sidebar (reserved — used by future left-nav surfaces; not consumed by the
I-cd-004 top-nav shell):
- `--color-sidebar`, `--color-sidebar-foreground`
- `--color-sidebar-primary`, `--color-sidebar-primary-foreground`
- `--color-sidebar-accent`, `--color-sidebar-accent-foreground`
- `--color-sidebar-border`, `--color-sidebar-ring`

Charts (reserved for forest-plot / comparison-table / timeline surfaces):
- `--color-chart-1` .. `--color-chart-5`

## Radius scale

- `--radius-sm`, `--radius-md`, `--radius-lg`, `--radius-xl`,
  `--radius-2xl`, `--radius-3xl`, `--radius-4xl`

## Font tokens

- `--font-sans`, `--font-mono`, `--font-heading`

## Usage rule

Per-route rebuilds (I-cd-013..030) reference these via the existing Tailwind v4
`@theme inline` mapping (e.g. `bg-background`, `text-foreground`,
`border-border`, `text-accent-foreground`, `rounded-md`). Page-local
component styles must NOT introduce ad-hoc color/radius/font tokens outside
this list.
