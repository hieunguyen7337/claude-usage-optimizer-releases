import type { Register } from 'claude-code'

import { describe, judge, shouldTry, SYSTEM, wrap } from './fix'

// One Haiku call per typed prompt; past this the prompt goes on as typed.
const TIMEOUT_MS = 8000

export const register: Register = (on) => {
  // Fixes spelling and grammar slips in what the person typed (or sent from the phone), sends the corrected
  // text on, and shows it in the transcript. Any failure sends the prompt as typed.
  on('prompt.submit', async ($, e, next) => {
    try {
      if (e.command !== undefined || e.isMeta === true) return next(e)
      if (e.origin.kind !== 'composer' && e.origin.kind !== 'bridge') return next(e)
      if (!shouldTry(e.text)) return next(e)
      if ((await $.env.get('USAGE_OPTIMIZER_PROMPT_FIX')) === 'off') return next(e)

      $.ui.status('checking spelling…')
      let reply
      try {
        reply = await $.model.complete({
          model: 'haiku',
          system: SYSTEM,
          prompt: wrap(e.text),
          effort: 'low',
          maxTokens: Math.min(4096, Math.ceil(e.text.length / 2) + 256),
          timeoutMs: TIMEOUT_MS,
        })
      } finally {
        $.ui.status(undefined)
      }
      if (!reply.isAnswered) {
        $.ui.log(`prompt-fix: no correction (${reply.reason})`, { to: 'debug' })
        return next(e)
      }
      const verdict = judge(e.text, reply.text)
      if ('reason' in verdict) {
        $.ui.log(`prompt-fix: kept as typed (${verdict.reason})`, { to: 'debug' })
        return next(e)
      }
      const fixes = describe(verdict.changes)
      $.ui.log(`✎ Corrected (${fixes}):\n${verdict.corrected.trim()}`)
      // The model reads what was changed, so a wrong fix can be undone from the prompt alone.
      const note = `The kit's prompt-fix mod corrected typing mistakes in the prompt above before you saw it: ${fixes}. If a correction changed what the user meant, go by the original word.`
      return next({ ...e, text: verdict.corrected, context: [...(e.context ?? []), note] })
    } catch {
      // The mod must never block a prompt.
      return next(e)
    }
  })
}
