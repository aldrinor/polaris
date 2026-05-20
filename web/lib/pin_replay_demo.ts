/**
 * I-cd-017 (#627): DEMO_PIN_REGISTRY removed; data now sourced from the
 * live backend route `/api/v6/runs/{run_id}/pins[/{date}]` via
 * `@/lib/pin_replay_client`. This file keeps a back-compat type re-export
 * + an empty registry so existing imports continue to resolve while the
 * full /pin_replay rebuild ships in Seq 29 / I-A-12 / #619.
 */

import type { PinSnapshot } from "@/lib/pin_replay_client";

export type { PinSnapshot };

export const DEMO_PIN_REGISTRY: Record<string, PinSnapshot> = {};
