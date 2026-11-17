import type { CallOutcome, Session, TurnState } from '../types'

// Pure parts of loop-guard: what makes two calls the same, when a call failed,
// and when a turn has gone on long enough to tell the person.

/** Appended once, on the third failure of one call, to the result the model reads. */
export const LOOP_NOTE =
  'Loop guard (kit): this exact call has now failed 3 times in this turn. Do not run it again unchanged: read the error, change the approach, or stop and ask the user.'

/** Shown once on a long turn of repeated failures. Cleared when that turn ends. */
export const LENGTH_STATUS = 'loop guard: long turn with repeated failures; Esc stops it'

/** Set to `off` to leave every call and turn untouched. Any other value, including unset, leaves the guard on. */
export const OFF_ENV = 'USAGE_OPTIMIZER_LOOP_GUARD'

export const FAIL_LIMIT = 3
export const MAX_NOTES_PER_TURN = 2
export const MIN_FINISHED_TURNS = 5
export const DURATION_FACTOR = 2.5
export const RECENT_CALLS = 10

/** Keys the engine puts on a tool call that are not the tool's own arguments. */
const ENVELOPE = new Set(['tool', 'tool_use_id', 'agentId', 'consent', 'requestMeta'])

const EXIT_TEXT = /^Exit code:?\s+(-?\d+)\b/

/** Runs of whitespace become one space, so `ls   a` and `ls a` are one command. */
export function collapseWs(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}

function sortValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortValue)
  if (value !== null && typeof value === 'object') {
    const source = value as Record<string, unknown>
    const sorted: Record<string, unknown> = {}
    for (const key of Object.keys(source).sort()) sorted[key] = sortValue(source[key])
    return sorted
  }
  return value
}

/** JSON with object keys sorted at every level. Array order stays as given. */
export function canonical(value: unknown): string {
  const text = JSON.stringify(sortValue(value))
  return text === undefined ? 'null' : text
}

/**
 * Identity of one call. Bash is the tool name plus the command with whitespace collapsed
 * (timeout and description are not part of it). Every other tool is the name plus its
 * arguments as JSON with keys sorted. The engine's envelope (`tool_use_id`, `agentId`, …)
 * is left out, so a new id does not make the same call look new.
 */
export function callKey(tool: string, event: object): string {
  const fields = event as Record<string, unknown>
  if (tool === 'Bash') {
    const command = typeof fields.command === 'string' ? fields.command : ''
    return `Bash\u0000${collapseWs(command)}`
  }
  const input: Record<string, unknown> = {}
  for (const key of Object.keys(fields)) {
    if (!ENVELOPE.has(key)) input[key] = fields[key]
  }
  return `${tool}\u0000${canonical(input)}`
}

/** A Bash exit code carried on the result record, or the `Exit code N` line the model reads. */
export function bashExitCode(result: unknown, text: string | undefined): number | undefined {
  if (result !== null && typeof result === 'object') {
    const record = result as Record<string, unknown>
    for (const key of ['exitCode', 'exit_code']) {
      const value = record[key]
      if (typeof value === 'number' && Number.isFinite(value)) return value
    }
  }
  if (typeof text === 'string') {
    const matched = EXIT_TEXT.exec(text.trim())
    if (matched?.[1] !== undefined) return Number(matched[1])
  }
  return undefined
}

/**
 * A call failed when the engine marked the result as an error. Bash also fails on a
 * non-zero exit, including when that exit is only on the result or in the text the
 * model reads and `isError` was not set. A deny is not counted: the tool did not run.
 */
export function callFailed(tool: string, outcome: CallOutcome): boolean {
  if (outcome.isError === true) return true
  if (tool !== 'Bash') return false
  const code = bashExitCode(outcome.result, outcome.text)
  return code !== undefined && code !== 0
}

export function median(values: readonly number[]): number | undefined {
  if (values.length === 0) return undefined
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  const upper = sorted[mid]
  if (upper === undefined) return undefined
  if (sorted.length % 2 === 1) return upper
  const lower = sorted[mid - 1]
  if (lower === undefined) return upper
  return (lower + upper) / 2
}

export function createSession(): Session {
  return { turns: new Map(), byAgent: new Map(), mainId: undefined, durations: [], finished: new Set() }
}

const SLOT = 'loop-guard.session.v1'

function holder(): Record<string, Session | undefined> {
  return globalThis as unknown as Record<string, Session | undefined>
}

/** The session's one guard. Shared through globalThis so a test and the loaded mod clear the same object. */
export function currentSession(): Session {
  const slot = holder()
  const existing = slot[SLOT]
  if (existing) return existing
  const created = createSession()
  slot[SLOT] = created
  return created
}

/** Drops counts and the duration sample. Tests call it; a reload that shares globalThis does too. */
export function resetSession(): void {
  const session = currentSession()
  session.turns.clear()
  session.byAgent.clear()
  session.mainId = undefined
  session.durations.length = 0
  session.finished.clear()
}

function emptyTurn(id: string, agentId: string | undefined, startedAt: number | undefined): TurnState {
  return { id, agentId, startedAt, failures: new Map(), noted: new Set(), notes: 0, recent: [], statusShown: false }
}

export function beginTurn(session: Session, turnId: string, agentId: string | undefined, startedAt: number): void {
  let turn = session.turns.get(turnId)
  if (!turn) {
    turn = emptyTurn(turnId, agentId, startedAt)
    session.turns.set(turnId, turn)
  } else if (turn.startedAt === undefined) {
    turn.startedAt = startedAt
    turn.agentId = agentId
  }
  if (agentId === undefined) session.mainId = turnId
  else session.byAgent.set(agentId, turnId)
}

export function turnFor(session: Session, agentId: string | undefined): TurnState | undefined {
  const id = agentId === undefined ? session.mainId : session.byAgent.get(agentId)
  return id === undefined ? undefined : session.turns.get(id)
}

/**
 * The open turn for this call. When `turn.start` was not reported, calls still share a
 * bucket (`main`, or `agent:<id>`) so repeated failures in that loop count.
 */
export function ensureTurn(session: Session, agentId: string | undefined): TurnState {
  const existing = turnFor(session, agentId)
  if (existing) return existing
  const id = agentId === undefined ? 'main' : `agent:${agentId}`
  const turn = emptyTurn(id, agentId, undefined)
  session.turns.set(id, turn)
  if (agentId === undefined) session.mainId = id
  else session.byAgent.set(agentId, id)
  return turn
}

/**
 * Counts the call. A success is remembered in the recent window and changes no failure
 * count. The note is returned only on the failure that reaches {@link FAIL_LIMIT}, and
 * only while this turn has issued fewer than {@link MAX_NOTES_PER_TURN} notes.
 */
export function recordCall(turn: TurnState, key: string, failed: boolean): string | undefined {
  turn.recent.push(failed)
  if (turn.recent.length > RECENT_CALLS) turn.recent.shift()
  if (!failed) return undefined
  const count = (turn.failures.get(key) ?? 0) + 1
  turn.failures.set(key, count)
  if (count !== FAIL_LIMIT || turn.noted.has(key) || turn.notes >= MAX_NOTES_PER_TURN) return undefined
  turn.notes += 1
  turn.noted.add(key)
  return LOOP_NOTE
}

/** At least half of a full window of the last {@link RECENT_CALLS} calls failed. */
export function recentFailureHalf(recent: readonly boolean[]): boolean {
  if (recent.length < RECENT_CALLS) return false
  let failed = 0
  for (const item of recent) if (item) failed += 1
  return failed * 2 >= recent.length
}

/**
 * True once five turns have finished and this one has run strictly past
 * {@link DURATION_FACTOR} times their median, with at least half of its last
 * {@link RECENT_CALLS} calls failed. Quiet when the start time was never seen.
 */
export function shouldWarn(turn: TurnState, durations: readonly number[], now: number): boolean {
  if (turn.statusShown || turn.startedAt === undefined) return false
  if (durations.length < MIN_FINISHED_TURNS) return false
  if (!recentFailureHalf(turn.recent)) return false
  const mid = median(durations)
  if (mid === undefined) return false
  return now - turn.startedAt > DURATION_FACTOR * mid
}

/** Forgets the turn. Returns whether its length line is on screen and should be cleared. */
export function finishTurn(
  session: Session,
  turnId: string,
  agentId: string | undefined,
  durationMs: number,
  count: boolean,
): boolean {
  const turn = session.turns.get(turnId)
  const shown = turn?.statusShown === true
  session.turns.delete(turnId)
  if (session.mainId === turnId) session.mainId = undefined
  if (agentId !== undefined && session.byAgent.get(agentId) === turnId) session.byAgent.delete(agentId)
  const owned = turn?.agentId
  if (owned !== undefined && session.byAgent.get(owned) === turnId) session.byAgent.delete(owned)
  if (
    count &&
    !session.finished.has(turnId) &&
    typeof durationMs === 'number' &&
    Number.isFinite(durationMs) &&
    durationMs >= 0
  ) {
    session.durations.push(durationMs)
    session.finished.add(turnId)
  }
  return shown
}
