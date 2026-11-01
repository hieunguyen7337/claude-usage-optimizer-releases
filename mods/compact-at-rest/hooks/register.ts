import type { Register } from 'claude-code'

import { parseNear, shouldCompact } from './policy'

// A compaction leaves about 87k tokens, so below this one never pays.
const MIN_TOKENS = 100000
// The turn can still count as running inside turn.complete; compacting a moment later is allowed.
const DELAY_MS = 1500
// Tells the summarizer it runs between turns, so the last answer and request survive verbatim.
const INSTRUCTIONS =
  'This compaction runs between turns, right after an answer the user has not replied to yet. Keep that last answer ' +
  "and the user's last request in full, word for word. Follow the Compact instructions in CLAUDE.md for the rest."

let pending = false

export const register: Register = (on) => {
  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    try {
      if (e.agentId !== undefined || e.reason !== 'answer') return result
      if ((await $.env.get('USAGE_OPTIMIZER_COMPACT_AT_REST')) === 'off') return result
      const nearPercent = parseNear(await $.env.get('USAGE_OPTIMIZER_COMPACT_NEAR'))
      const { context } = await $.session.usage()
      const tokens = context.tokens
      if (tokens === undefined || tokens < MIN_TOKENS) return result
      const window = (await $.session.usage({ breakdown: 'summary' })).context.breakdown?.rawMaxTokens
      if (window === undefined) return result
      if (pending || !shouldCompact({ tokens, window, nearPercent, minTokens: MIN_TOKENS })) return result
      pending = true
      try {
        $.clock.after(DELAY_MS, async () => {
          try {
            const done = await $.session.compact({ instructions: INSTRUCTIONS })
            if (done.skip === undefined && done.tokensBefore !== undefined && done.tokensAfter !== undefined) {
              const k = (n: number) => Math.round(n / 1000)
              $.ui.toast(`Compacted between turns: ${k(done.tokensBefore)}k → ${k(done.tokensAfter)}k tokens`)
            }
          } catch {
            // A new turn started first: Claude Code's own threshold handles it.
          } finally {
            pending = false
          }
        })
      } catch {
        pending = false
      }
    } catch {
      // The mod must never break a turn.
    }
    return result
  })
}
