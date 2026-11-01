// The prompt index: what bin/claude-prompts reports, plus prompts typed since it last ran.

import type { MobileViewPrompt } from '../types'
import { promptTitle } from './format'

/** How much of a question the list keeps, to show when its row can't be reached (the helper sends as much). */
const TEXT_CHARS = 600

export type HelperResult ={ prompts: MobileViewPrompt[]; size: number } | { error: string }

/** Reads claude-prompts' JSON; anything else is an error naming what came back. */
export function parseHelper(stdout: string): HelperResult {
  let data: unknown
  try {
    data = JSON.parse(stdout)
  } catch {
    return { error: `unreadable helper output: ${stdout.slice(0, 120)}` }
  }
  const record = (data ?? {}) as Record<string, unknown>
  if (typeof record.error === 'string') {
    return { error: record.error }
  }
  if (!Array.isArray(record.prompts)) {
    return { error: 'helper output has no prompts' }
  }
  const prompts: MobileViewPrompt[] = []
  for (const raw of record.prompts as Record<string, unknown>[]) {
    if (typeof raw?.uuid !== 'string') {
      continue
    }
    prompts.push({
      uuid: raw.uuid,
      n: prompts.length + 1,
      ts: typeof raw.ts === 'string' ? raw.ts : null,
      title: typeof raw.title === 'string' ? raw.title : '[untitled]',
      ...(typeof raw.text === 'string' && raw.text.trim() !== '' ? { text: raw.text.slice(0, TEXT_CHARS) } : {}),
      isBeforeCompact: raw.isBeforeCompact === true,
    })
  }
  return { prompts, size: typeof record.size === 'number' ? record.size : 0 }
}

type AppendLike = {
  door: string
  origin: unknown
  uuid: string
  agentId?: string
  message: { type: string; isMeta?: true; content?: unknown }
}

/** A prompt the person just typed (or sent from the phone), from a `session.append` row; else null. */
export function entryFromAppend(e: AppendLike, now: string): MobileViewPrompt | null {
  const kind = (e.origin as { kind?: string } | null)?.kind
  if (e.door !== 'prompt' || (kind !== 'composer' && kind !== 'bridge')) {
    return null
  }
  if (e.agentId !== undefined || e.message.type !== 'user' || e.message.isMeta) {
    return null
  }
  const content = e.message.content
  const text =
    typeof content === 'string'
      ? content
      : Array.isArray(content)
        ? content
            .filter((block): block is { type: 'text'; text: string } => block?.type === 'text' && typeof block.text === 'string')
            .map(block => block.text)
            .join('\n')
        : ''
  // A slash command (`/compact`) arrives as typed; the transcript stores it wrapped, as a command.
  if (text.trim() === '' || /^\s*<(command-|local-command|bash-)/.test(text) || /^\s*\/[\w:.-]+(\s|$)/.test(text)) {
    return null
  }
  return { uuid: e.uuid, n: 0, ts: now, title: promptTitle(text), text: text.trim().slice(0, TEXT_CHARS), isBeforeCompact: false, isLive: true }
}

const renumber = (list: MobileViewPrompt[]) => list.map((prompt, index) => ({ ...prompt, n: index + 1 }))

/**
 * The helper's list is the truth for everything it saw; live prompts it has not seen yet stay
 * at the end. A live prompt older than the helper's newest is one a rewind dropped, so it goes.
 */
export function merge(base: MobileViewPrompt[], extra: MobileViewPrompt[]): MobileViewPrompt[] {
  const known = new Set(base.map(prompt => prompt.uuid))
  const newest = base.reduce((latest, prompt) => (prompt.ts !== null && prompt.ts > latest ? prompt.ts : latest), '')
  const fresh = extra.filter(prompt => !known.has(prompt.uuid) && (!prompt.isLive || prompt.ts === null || prompt.ts >= newest))
  return renumber([...base, ...fresh])
}

/** Adds one live prompt to the list as it stands. */
export function addLive(list: MobileViewPrompt[], entry: MobileViewPrompt): MobileViewPrompt[] {
  if (list.some(prompt => prompt.uuid === entry.uuid)) {
    return list
  }
  return renumber([...list, entry])
}
