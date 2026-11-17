import type { Register } from 'claude-code'

import { idleCompactLine, parseIdleMinutes, parseIdlePercent, parseNear, shouldCompactAhead, shouldIdleCompact } from './policy'

// How many recent turns of growth the compact-ahead forecast keeps.
const GROWTH_TURNS = 8

// A compaction leaves about 87k tokens, so below this one never pays.
const MIN_TOKENS = 100000
// The turn can still count as running inside turn.complete; compacting a moment later is allowed.
const DELAY_MS = 1500
// Tells the summarizer it runs between turns, so the last answer and request survive verbatim.
const INSTRUCTIONS =
  'This compaction runs between turns, right after an answer the user has not replied to yet. Keep that last answer ' +
  "and the user's last request in full, word for word. Follow the Compact instructions in CLAUDE.md for the rest."

export const register: Register = (on) => {
  // One idle compaction per quiet stretch. A prompt, a main-loop turn, a main-loop tool or a real compaction drops it.
  let pending = false
  let turnRunning = false
  let toolsInFlight = 0
  let idleTimer: { cancel: () => void } | undefined
  let idleGen = 0
  // Context growth of this session's recent main-loop turns that grew, for the compact-ahead forecast.
  let turnStartTokens: number | undefined
  const growth: number[] = []

  const cancelIdle = () => {
    idleGen += 1
    idleTimer?.cancel()
    idleTimer = undefined
  }

  const busy = () => turnRunning || toolsInFlight > 0

  on('prompt.submit', async ($, e, next) => {
    cancelIdle()
    return next(e)
  }).catch(($, e, next) => next(e))

  on('turn.start', async ($, e, next) => {
    if (e.agentId === undefined) {
      turnRunning = true
      cancelIdle()
      try {
        turnStartTokens = (await $.session.usage()).context.tokens
      } catch {
        turnStartTokens = undefined
      }
    }
    return next(e)
  }).catch(($, e, next) => next(e))

  on('tool.call', async ($, e, next) => {
    if (e.agentId !== undefined) return next(e)
    toolsInFlight += 1
    cancelIdle()
    try {
      return await next(e)
    } finally {
      toolsInFlight = Math.max(0, toolsInFlight - 1)
    }
  }).catch(($, e, next) => next(e))

  on('session.compact', async ($, e, next) => {
    // A precompute installs nothing, so the quiet stretch is still the one we armed.
    if (e.agentId === undefined && e.trigger !== 'precompute') cancelIdle()
    return next(e)
  }).catch(($, e, next) => next(e))

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    try {
      if (e.agentId !== undefined) return result
      turnRunning = false
      if (e.reason !== 'answer') {
        cancelIdle()
        return result
      }
      if (busy()) {
        cancelIdle()
        return result
      }

      const atRestOff = (await $.env.get('USAGE_OPTIMIZER_COMPACT_AT_REST')) === 'off'
      const idleOff = (await $.env.get('USAGE_OPTIMIZER_IDLE_COMPACT')) === 'off'
      if (atRestOff && idleOff) {
        cancelIdle()
        return result
      }

      const nearPercent = parseNear(await $.env.get('USAGE_OPTIMIZER_COMPACT_NEAR'))
      const idleMinutes = parseIdleMinutes(await $.env.get('USAGE_OPTIMIZER_IDLE_COMPACT_MIN'))
      const idlePercent = parseIdlePercent(await $.env.get('USAGE_OPTIMIZER_IDLE_COMPACT_PCT'))
      const { context } = await $.session.usage()
      const tokens = context.tokens
      if (tokens === undefined || tokens < MIN_TOKENS) {
        cancelIdle()
        return result
      }
      if (turnStartTokens !== undefined && tokens > turnStartTokens) {
        growth.push(tokens - turnStartTokens)
        if (growth.length > GROWTH_TURNS) growth.shift()
      }
      turnStartTokens = undefined
      const aheadOff = (await $.env.get('USAGE_OPTIMIZER_COMPACT_AHEAD')) === 'off'
      const window = (await $.session.usage({ breakdown: 'summary' })).context.breakdown?.rawMaxTokens
      const due = shouldCompactAhead({ tokens, window, nearPercent, minTokens: MIN_TOKENS, growth: aheadOff ? [] : growth })
      if (!atRestOff && window !== undefined && !pending && due) {
        pending = true
        try {
          $.clock.after(DELAY_MS, async () => {
            try {
              if (busy()) return
              const done = await $.session.compact({ instructions: INSTRUCTIONS })
              if (done.skip === undefined) cancelIdle()
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
      }

      if (idleOff || !shouldIdleCompact({ tokens, window, idlePercent, minTokens: MIN_TOKENS })) {
        cancelIdle()
        return result
      }

      cancelIdle()
      const gen = idleGen
      try {
        idleTimer = $.clock.after(idleMinutes * 60_000, async () => {
          if (gen !== idleGen) return
          idleGen += 1
          const shot = idleGen
          idleTimer = undefined
          try {
            if (busy()) return
            if ((await $.env.get('USAGE_OPTIMIZER_IDLE_COMPACT')) === 'off') return
            if (shot !== idleGen || busy()) return
            const live = await $.session.usage()
            const liveTokens = live.context.tokens
            if (liveTokens === undefined) return
            if (shot !== idleGen || busy()) return
            const liveWindow = (await $.session.usage({ breakdown: 'summary' })).context.breakdown?.rawMaxTokens
            const livePercent = parseIdlePercent(await $.env.get('USAGE_OPTIMIZER_IDLE_COMPACT_PCT'))
            if (shot !== idleGen || busy()) return
            if (!shouldIdleCompact({ tokens: liveTokens, window: liveWindow, idlePercent: livePercent, minTokens: MIN_TOKENS })) return
            if (typeof liveWindow !== 'number') return
            try {
              $.ui.log(idleCompactLine(idleMinutes, liveTokens, liveWindow))
            } catch {
              // The line is a notice. The compaction still pays.
            }
            if (shot !== idleGen || busy()) return
            await $.session.compact({ instructions: INSTRUCTIONS })
          } catch {
            // A turn started first, or the read failed: leave the conversation as it is.
          }
        })
      } catch {
        idleTimer = undefined
      }
    } catch {
      // The mod must never break a turn.
    }
    return result
  })
}
