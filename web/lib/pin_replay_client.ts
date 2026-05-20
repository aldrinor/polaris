/**
 * I-cd-017 (#627): Pin-replay HTTP client.
 *
 * Thin re-export of the live route in `web/lib/api.ts` so consumers in
 * `web/app/pin_replay/` import from a stable module name. Backend route
 * synthesizes PinSnapshot from manifest.json + run_store (no separate
 * pin-write path). Full /pin_replay UX rebuild lands at Seq 29 / #619.
 */

export { fetchPin, fetchPinList } from "@/lib/api";
export type { PinSnapshot } from "@/lib/api";
