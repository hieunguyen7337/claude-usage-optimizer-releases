import type { Register, ToolCallResult } from 'claude-code'

import {
  LENGTH_STATUS,
  beginTurn,
  callFailed,
  callKey,
  currentSession,
  ensureTurn,
  finishTurn,
  recordCall,
  shouldWarn,
} from './guard'

// The model reads `context` after the tool result; the person does not see it.
// That is the supported place for the one redirect. Nothing here denies or drops a call.
function annotate(result: ToolCallResult, note: string): ToolCallResult {
  if (typeof result.deny === 'string') return result
  const context = [...(result.context ?? []), note]
  return { ...result, context }
}

export const register: Register = (on) => {
  on('turn.start', async ($, e, next) => {
    const result = await next(e)
    try {
      if ((await $.env.get('USAGE_OPTIMIZER_LOOP_GUARD')) === 'off') return result
      beginTurn(currentSession(), e.turnId, e.agentId, await $.clock.now())
    } catch {
      // Without a start the length rule stays quiet. Calls still run.
    }
    return result
  })

  // Subagent calls are included: `tool.call` carries `agentId` for that loop, and a
  // hook that did not spawn the agent (this one spawns none) is told about them.
  on('tool.call', async ($, e, next) => {
    const result = await next(e)
    try {
      if ((await $.env.get('USAGE_OPTIMIZER_LOOP_GUARD')) === 'off') return result
      if (result === undefined || result === null || typeof result !== 'object') return result
      const session = currentSession()
      const turn = ensureTurn(session, e.agentId)
      const note = recordCall(turn, callKey(e.tool, e), callFailed(e.tool, result))
      const out = note === undefined ? result : annotate(result, note)
      try {
        if (!turn.statusShown && shouldWarn(turn, session.durations, await $.clock.now())) {
          await $.ui.status(LENGTH_STATUS)
          turn.statusShown = true
        }
      } catch {
        // The note still goes out. The status line is the part that failed.
      }
      return out
    } catch {
      return result
    }
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    try {
      let count = true
      try {
        count = (await $.env.get('USAGE_OPTIMIZER_LOOP_GUARD')) !== 'off'
      } catch {
        count = false
      }
      const shown = finishTurn(currentSession(), e.turnId, e.agentId, e.durationMs, count)
      if (shown) await $.ui.status(undefined)
    } catch {
      // The answer stands. A line left up is the failure; the call was not blocked.
    }
    return result
  })
}
