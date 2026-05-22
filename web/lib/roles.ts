// I-p2-029 (#768): role MODEL — PRESENTATION-ONLY.
//
// This determines which nav items / affordances a role SEES. It is NOT an
// authorization mechanism: per-route RBAC ENFORCEMENT is the security gate
// (G-SEC / a follow-up issue). Never rely on this for access control.

export const ROLES = [
  "analyst",
  "policy",
  "counsel",
  "clinical",
  "records",
] as const;

export type RoleId = (typeof ROLES)[number];

export const ROLE_LABELS: Record<RoleId, string> = {
  analyst: "PMO analyst",
  policy: "Policy advisor",
  counsel: "Legal counsel",
  clinical: "Clinical / regulatory reviewer",
  records: "Records / security officer",
};

export const DEFAULT_ROLE: RoleId = "analyst";
