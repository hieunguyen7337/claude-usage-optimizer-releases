const DEFAULT_NEAR = 90

/** The trigger as a percent of the compaction window: an integer 50-100, else 90. */
export function parseNear(raw: string | undefined): number {
  const text = (raw ?? '').trim()
  if (!/^\d+$/.test(text)) return DEFAULT_NEAR
  const value = Number(text)
  return value >= 50 && value <= 100 ? value : DEFAULT_NEAR
}

/** Whether the context is big enough, and close enough to the window, for a compaction to pay. */
export function shouldCompact(input: { tokens: number; window: number | undefined; nearPercent: number; minTokens: number }): boolean {
  const { tokens, window, nearPercent, minTokens } = input
  if (typeof window !== 'number' || !(window > 0)) return false
  return tokens >= minTokens && tokens >= (window * nearPercent) / 100
}
