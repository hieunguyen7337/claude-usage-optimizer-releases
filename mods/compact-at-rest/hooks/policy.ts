const DEFAULT_NEAR = 90
const DEFAULT_IDLE_MIN = 50
const DEFAULT_IDLE_PCT = 40

/** The trigger as a percent of the compaction window: an integer 50-100, else 90. */
export function parseNear(raw: string | undefined): number {
  const text = (raw ?? '').trim()
  if (!/^\d+$/.test(text)) return DEFAULT_NEAR
  const value = Number(text)
  return value >= 50 && value <= 100 ? value : DEFAULT_NEAR
}

/**
 * Minutes to sit idle before compacting while the prompt cache is still warm.
 * An integer 1-59 (the cache lives about 60 minutes), else 50.
 */
export function parseIdleMinutes(raw: string | undefined): number {
  const text = (raw ?? '').trim()
  if (!/^\d+$/.test(text)) return DEFAULT_IDLE_MIN
  const value = Number(text)
  return value >= 1 && value <= 59 ? value : DEFAULT_IDLE_MIN
}

/** The idle trigger as a percent of the compaction window: an integer 1-100, else 40. */
export function parseIdlePercent(raw: string | undefined): number {
  const text = (raw ?? '').trim()
  if (!/^\d+$/.test(text)) return DEFAULT_IDLE_PCT
  const value = Number(text)
  return value >= 1 && value <= 100 ? value : DEFAULT_IDLE_PCT
}

/** Whether the context is big enough, and close enough to the window, for a compaction to pay. */
export function shouldCompact(input: { tokens: number; window: number | undefined; nearPercent: number; minTokens: number }): boolean {
  const { tokens, window, nearPercent, minTokens } = input
  if (typeof window !== 'number' || !(window > 0)) return false
  return tokens >= minTokens && tokens >= (window * nearPercent) / 100
}

/** The median of the numbers given; undefined for none. */
export function median(values: number[]): number | undefined {
  if (values.length === 0) return undefined
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  const upper = sorted[mid] ?? 0
  return sorted.length % 2 ? upper : ((sorted[mid - 1] ?? upper) + upper) / 2
}

/** Turns of growth needed before the forecast is trusted. */
export const AHEAD_MIN_TURNS = 3

/**
 * Whether to compact now because the next turn would likely cross the window mid-turn.
 *
 * Why: a turn that crosses the window mid-turn is held by the PreCompact gate until it ends, so on long turns the
 * compaction lands at 280-320k instead of 225k (turn-meter compactions, 2026-11-16: median 319k). When the context
 * plus this session's median growth per turn (from at least AHEAD_MIN_TURNS turns that grew) reaches the window,
 * compacting at rest now is cheaper than carrying the overflow through the next turn.
 */
export function shouldCompactAhead(input: {
  tokens: number
  window: number | undefined
  nearPercent: number
  minTokens: number
  growth: number[]
}): boolean {
  if (shouldCompact(input)) return true
  const { tokens, window, minTokens } = input
  if (typeof window !== 'number' || !(window > 0) || tokens < minTokens) return false
  const grew = input.growth.filter((n) => Number.isFinite(n) && n > 0)
  if (grew.length < AHEAD_MIN_TURNS) return false
  const typical = median(grew)
  return typical !== undefined && tokens + typical >= window
}

/** Whether an idle stretch should compact: the same floor as a near-window compaction, at `idlePercent` of the window. */
export function shouldIdleCompact(input: { tokens: number; window: number | undefined; idlePercent: number; minTokens: number }): boolean {
  return shouldCompact({
    tokens: input.tokens,
    window: input.window,
    nearPercent: input.idlePercent,
    minTokens: input.minTokens,
  })
}

/** One dim transcript line, e.g. `compact-at-rest: idle 50 min at 180k (72%); compacting while the cache is warm`. */
export function idleCompactLine(minutes: number, tokens: number, window: number): string {
  const shown = Math.round(tokens / 1000)
  const pct = window > 0 ? Math.round((tokens / window) * 100) : 0
  return `compact-at-rest: idle ${minutes} min at ${shown}k (${pct}%); compacting while the cache is warm`
}
