// Events to transcript lines, folded like mobile-view: one line per tool call, thinking hidden, a subagent's
// events under the call that started it. Every text is cleaned and is data: drawn, never sent to the model.
import type { ApiEvent, NeedsYou, TranscriptLine } from '../types'

const ELLIPSIS = '\u2026'

// OSC, DCS, SOS, PM and APC strings (ESC-introduced or C1), up to BEL, ST or the end of the line.
const STRING_SEQ =
  /(?:\u001b[\]PX^_]|[\u0090\u0098\u009d\u009e\u009f])[^\u0007\u001b\u009c\n]*(?:\u0007|\u001b\\|\u009c)?/g
// CSI (ESC [ or C1): parameters, intermediates, one final byte (optional, so a cut-off sequence goes too).
const CSI_SEQ = /(?:\u001b\[|\u009b)[0-?]*[ -/]*[@-~]?/g
// Any other escape: ESC, intermediates, one final byte.
const ESC_SEQ = /\u001b[ -/]*[0-~]?/g
// C0 (except \t and \n), DEL and C1.
const CONTROLS = /[\u0000-\u0008\u000b-\u001f\u007f-\u009f]/g
const BIDI = /[\u202a-\u202e\u2066-\u2069]/g
const BLANK_RUN = /\n(?:[ \t]*\n){3,}/g
/** The most characters a tool call's result text keeps (the cut ends with an ellipsis, inside the count). */
export const RESULT_CHARS = 4000

/** Strips C0/C1 control characters (keeping \n and \t), ANSI escape sequences and bidi overrides; caps at max chars. */
export function cleanText(text: string, max: number = 4000): string {
  if (typeof text !== 'string' || max <= 0) {
    return ''
  }
  // Escape sequences are short, so cleaning only the head of a huge text costs little and loses nothing shown.
  const limit = max * 4 + 64
  const isHeadOnly = text.length > limit
  const cleaned = (isHeadOnly ? text.slice(0, limit) : text)
    .replace(STRING_SEQ, '')
    .replace(CSI_SEQ, '')
    .replace(ESC_SEQ, '')
    .replace(/\r\n/g, '\n')
    .replace(CONTROLS, '')
    .replace(BIDI, '')
    .replace(BLANK_RUN, '\n\n\n')
  if (cleaned.length <= max && !isHeadOnly) {
    return cleaned
  }
  let head = cleaned.slice(0, max - 1)
  const last = head.charCodeAt(head.length - 1)
  if (last >= 0xd800 && last <= 0xdbff) {
    head = head.slice(0, -1)
  }
  return head + ELLIPSIS
}

/** Known events plus a newly read page (any order) -> one list, ascending by seq, no duplicate seq, newest `cap`. */
export function mergeEvents(known: readonly ApiEvent[], page: readonly ApiEvent[], cap: number = 2000): ApiEvent[] {
  const bySeq = new Map<number, ApiEvent>()
  for (const event of known) {
    bySeq.set(event.seq, event)
  }
  for (const event of page) {
    bySeq.set(event.seq, event)
  }
  const sorted = [...bySeq.values()].sort((a, b) => a.seq - b.seq)
  return cap > 0 ? sorted.slice(-cap) : []
}

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null

const asString = (value: unknown): string => (typeof value === 'string' ? value : '')

const asList = (value: unknown): unknown[] => (Array.isArray(value) ? value : [])

/**
 * A tool result's text: its content as it is when a string, else the text blocks of its content list joined by a
 * newline (images and other blocks skipped). Cleaned exactly as assistant text is, and at most RESULT_CHARS long.
 */
export function resultTextOf(content: unknown): string {
  if (typeof content === 'string') {
    return cleanText(content, RESULT_CHARS)
  }
  const texts: string[] = []
  for (const item of asList(content)) {
    const block = asRecord(item)
    if (block?.type === 'text') {
      texts.push(asString(block.text))
    }
  }
  return cleanText(texts.join('\n'), RESULT_CHARS)
}

/** The content blocks of payload.message, as records; a plain string becomes one text block. */
function blocksOf(payload: Record<string, unknown> | null): Record<string, unknown>[] {
  const content = asRecord(payload?.message)?.content
  if (typeof content === 'string') {
    return [{ type: 'text', text: content }]
  }
  const blocks: Record<string, unknown>[] = []
  for (const item of asList(content)) {
    const block = asRecord(item)
    if (block) {
      blocks.push(block)
    }
  }
  return blocks
}

/** One line of at most `max` characters: cleaned, whitespace collapsed, cut with an ellipsis. */
function oneLine(text: string, max: number): string {
  const flat = cleanText(text, max * 4).replace(/\s+/g, ' ').trim()
  return flat.length <= max ? flat : flat.slice(0, max - 1).trimEnd() + ELLIPSIS
}

/** The first non-blank line of a text. */
const firstLineOf = (text: string): string => text.split(/\r?\n/).find(line => line.trim() !== '') ?? ''

/** A tool call's one-line label from its name and input (Bash: description else first command line, ...). */
export function toolLabel(name: string, input: unknown): string {
  const fields = asRecord(input) ?? {}
  const field = (key: string) => asString(fields[key])
  let label = ''
  switch (name) {
    case 'Bash':
    case 'PowerShell':
      label = field('description').trim() !== '' ? field('description') : firstLineOf(field('command'))
      break
    case 'Read':
    case 'Edit':
    case 'Write':
      label = field('file_path')
      break
    case 'Grep':
    case 'Glob':
      label = field('pattern')
      break
    case 'Agent':
    case 'Task':
      label = field('description')
      break
  }
  const line = oneLine(label, 120)
  return line !== '' ? line : oneLine(asString(name), 120)
}

type Fold = {
  lines: TranscriptLine[]
  /** Every call seen so far, top level or nested, by tool_use id. */
  calls: Map<string, TranscriptLine>
  /** Held messages already drawn, by message_uuid: a repeated hold of one message is drawn once. */
  held: Set<string>
}

/** The list a line belongs in: a known call's children when payload.parent_tool_use_id names one, else the top. */
function targetOf(fold: Fold, payload: Record<string, unknown> | null): TranscriptLine[] {
  const parent = fold.calls.get(asString(payload?.parent_tool_use_id))
  if (!parent) {
    return fold.lines
  }
  parent.children ??= []
  return parent.children
}

const lineOf = (event: ApiEvent, kind: TranscriptLine['kind'], key: string, text: string): TranscriptLine => ({
  key,
  seq: event.seq,
  at: event.at,
  kind,
  text,
})

/** The key of the nth line an event makes: the event id first, then id:n. */
const keyOf = (event: ApiEvent, index: number) => (index === 0 ? event.id : `${event.id}:${index}`)

function foldAssistant(fold: Fold, event: ApiEvent, payload: Record<string, unknown> | null) {
  const target = targetOf(fold, payload)
  blocksOf(payload).forEach((block, index) => {
    if (block.type === 'text') {
      const text = cleanText(asString(block.text))
      if (text.trim() !== '') {
        target.push(lineOf(event, 'text', keyOf(event, index), text))
      }
      return
    }
    // thinking and redacted_thinking stay hidden; so does any block of a type this view does not know.
    const useId = asString(block.id)
    if (block.type !== 'tool_use' || useId === '' || fold.calls.has(useId)) {
      return
    }
    const name = oneLine(asString(block.name), 120)
    const label = toolLabel(asString(block.name), block.input)
    const line = lineOf(event, 'tool', `tool:${useId}`, label)
    line.tool = { useId, name, label, status: 'running' }
    fold.calls.set(useId, line)
    target.push(line)
  })
}

function foldUser(fold: Fold, event: ApiEvent, payload: Record<string, unknown> | null) {
  const blocks = blocksOf(payload)
  if (event.source === 'worker') {
    for (const block of blocks) {
      const call = block.type === 'tool_result' ? fold.calls.get(asString(block.tool_use_id)) : undefined
      if (call?.tool) {
        call.tool.status = block.is_error === true ? 'error' : 'ok'
        const result = resultTextOf(block.content)
        if (result.trim() !== '') {
          call.result = result
        }
      }
    }
    return
  }
  if (event.source !== 'client') {
    return
  }
  const text = cleanText(
    blocks
      .filter(block => block.type === 'text')
      .map(block => asString(block.text))
      .join('\n'),
  )
  if (text.trim() !== '') {
    targetOf(fold, payload).push(lineOf(event, 'prompt', event.id, text))
  }
}

function foldResult(fold: Fold, event: ApiEvent, payload: Record<string, unknown> | null) {
  const subtype = asString(payload?.subtype)
  const ms = payload?.duration_ms
  const isDone = subtype === 'success' && payload?.is_error !== true
  const text = isDone
    ? typeof ms === 'number' && Number.isFinite(ms) && ms >= 0
      ? `done in ${Math.round(ms / 1000)} s`
      : 'done'
    : `error: ${oneLine(subtype, 80) || 'unknown'}`
  targetOf(fold, payload).push(lineOf(event, 'result', event.id, text))
}

function foldSystem(fold: Fold, event: ApiEvent, payload: Record<string, unknown> | null) {
  const target = targetOf(fold, payload)
  switch (payload?.subtype) {
    case 'peer_message_hold':
      if (payload.state === 'held') {
        const message = asString(payload.message_uuid)
        if (message !== '' && fold.held.has(message)) return
        if (message !== '') fold.held.add(message)
        const from = oneLine(asString(payload.from_name), 80) || 'unknown'
        const cause = oneLine(asString(payload.cause), 80) || 'unknown'
        target.push(lineOf(event, 'held', event.id, `message from ${from} (${cause})`))
      }
      return
    case 'session_title_changed': {
      const title = oneLine(asString(payload.title), 200)
      if (title !== '') {
        target.push(lineOf(event, 'notice', event.id, `title: ${title}`))
      }
      return
    }
    case 'notification': {
      const text = cleanText(asString(payload.text), 1000)
      if (text.trim() !== '') {
        target.push(lineOf(event, 'notice', event.id, text))
      }
      return
    }
  }
  // permission_check_status, init, task_*, vcs_state_changed, turn_handoff_available, background_tasks_changed and
  // every subtype not known here make no line.
}

/** Ascending events -> folded lines, oldest first. */
export function foldEvents(events: readonly ApiEvent[]): TranscriptLine[] {
  const fold: Fold = { lines: [], calls: new Map(), held: new Set() }
  for (const event of events) {
    const payload = asRecord(event.payload)
    switch (event.type) {
      case 'assistant':
        foldAssistant(fold, event, payload)
        break
      case 'user':
        foldUser(fold, event, payload)
        break
      case 'result':
        foldResult(fold, event, payload)
        break
      case 'system':
        foldSystem(fold, event, payload)
        break
      // control_request, control_response, rate_limit_event, env_manager_log, prompt_suggestion and unknown types
      // make no line.
    }
  }
  return fold.lines
}

/** The request_id a control_response answers: payload.response.request_id, else payload.request_id. */
function answeredId(payload: Record<string, unknown> | null): string {
  return asString(asRecord(payload?.response)?.request_id) || asString(payload?.request_id)
}

/**
 * Whether the newest events leave a peer message held, or a permission waiting, for the owner.
 * [INFERRED] held: a peer_message_hold in state held whose message_uuid has no later hold event in another state.
 * [INFERRED] permissionWait: a worker control_request (request.subtype can_use_tool) with no later control_response
 * for its request_id.
 */
export function needsYouOf(events: readonly ApiEvent[]): NeedsYou {
  const holdState = new Map<string, string>()
  const waiting = new Set<string>()
  for (const event of [...events].sort((a, b) => a.seq - b.seq)) {
    const payload = asRecord(event.payload)
    if (event.type === 'system' && payload?.subtype === 'peer_message_hold') {
      holdState.set(asString(payload.message_uuid) || `event:${event.id}`, asString(payload.state))
    } else if (event.type === 'control_request' && event.source === 'worker') {
      const request = asRecord(payload?.request)
      const requestId = asString(payload?.request_id)
      if (request?.subtype === 'can_use_tool' && requestId !== '') {
        waiting.add(requestId)
      }
    } else if (event.type === 'control_response') {
      waiting.delete(answeredId(payload))
    }
  }
  return { held: [...holdState.values()].includes('held'), permissionWait: waiting.size > 0 }
}
