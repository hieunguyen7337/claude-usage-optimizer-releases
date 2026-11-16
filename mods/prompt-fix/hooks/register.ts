import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Fixes } from '../types'
import { describe, judge, shouldTry, SYSTEM, wrap } from './fix'

// One Haiku call per typed prompt; past this the prompt goes on as typed.
const TIMEOUT_MS = 8000
// Corrections kept for redrawing rows, across sessions (a resumed session still shows them corrected).
const KEEP = 300
const STORE_KEY = 'fixes'

const fixes = atom({ plugin: 'prompt-fix', key: 'fixes' } as const, {} as Fixes, { shape: 'fixes-1' })

function capped(map: Fixes): Fixes {
  const keys = Object.keys(map)
  return keys.length <= KEEP ? map : Object.fromEntries(keys.slice(keys.length - KEEP).map((k) => [k, map[k]!]))
}

const isPersons = (kind: string) => kind === 'composer' || kind === 'bridge'

export const register: Register = (on) => {
  // A resumed session draws its earlier prompts corrected too.
  on('session.start', async ($, e, next) => {
    try {
      const stored = await $.store.get(STORE_KEY)
      if (stored !== null && typeof stored === 'object') {
        await update($, fixes, (now) => capped({ ...(stored as Fixes), ...(now ?? {}) }))
      }
    } catch {
      // Rows then show the prompt as typed.
    }
    return next(e)
  })

  // Fixes spelling and grammar slips in what the person typed (or sent from the phone), sends the corrected
  // text on, and draws it in the prompt's own row. Any failure sends the prompt as typed.
  on('prompt.submit', async ($, e, next) => {
    try {
      if (e.command !== undefined || e.isMeta === true) return next(e)
      if (!isPersons(e.origin.kind)) return next(e)
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
      const fixed = describe(verdict.changes)
      try {
        const all = await update($, fixes, (now) => capped({ ...(now ?? {}), [e.text]: verdict.corrected }))
        await $.store.set(STORE_KEY, all)
      } catch {
        // The row then shows the prompt as typed; the model still gets the corrected text.
      }
      $.ui.log(`✎ Corrected: ${fixed}`)
      // The model reads what was changed, so a wrong fix can be undone from the prompt alone.
      const note = `The kit's prompt-fix mod corrected typing mistakes in the prompt above before you saw it: ${fixed}. If a correction changed what the user meant, go by the original word.`
      return next({ ...e, text: verdict.corrected, context: [...(e.context ?? []), note] })
    } catch {
      // The mod must never block a prompt.
      return next(e)
    }
  })

  // The prompt's row draws the corrected text in place of the text as typed.
  on('ui.render', { component: 'UserMessage' }, async ($, e, next) => {
    try {
      if (!isPersons(e.props.origin.kind)) return next(e)
      const corrected = (await read($, fixes))?.[e.props.text]
      if (corrected === undefined || corrected === e.props.text) return next(e)
      return next({ ...e, props: { ...e.props, text: corrected } })
    } catch {
      return next(e)
    }
  })
}
