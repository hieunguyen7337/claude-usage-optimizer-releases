// Poll timing: the list every 15 s and an open session every 4 s while the pane is open, doubling on each
// consecutive error up to 2 minutes; the optional band reads the list every 2 minutes while the pane is closed.
export const LIST_MS = 15_000
export const SESSION_MS = 4_000
export const BAND_MS = 120_000
export const MAX_MS = 120_000

/** The wait before the next read: base after a success (failures 0), doubled per consecutive failure, capped. */
export function nextDelay(baseMs: number, failures: number): number {
  const n = Number.isFinite(failures) && failures > 0 ? Math.floor(failures) : 0
  return Math.min(baseMs * 2 ** Math.min(n, 30), MAX_MS)
}
