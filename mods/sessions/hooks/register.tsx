import { atom, memberOf, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type {
  ActionId,
  ActionNotice,
  ApiEvent,
  ApiSession,
  Fetched,
  ListStatus,
  NeedsYou,
  OpenSession,
  RepoGroup,
  Registry,
  SessionRow,
} from '../types'
import { actionsFor, appUrl, cleanOutput, runAction } from './actions'
import { getEvents, getSession, listSessions } from './api'
import { readAgents, readListAgents, readRegistry, resetRegistryCache } from './local'
import { groupRows, headerOf, mergeRows, sameSessionId } from './merge'
import type { MergeInput } from './merge'
import { BAND_MS, LIST_MS, MAX_MS, SESSION_MS, nextDelay } from './poll'
import { isInactive, stateOf } from './status'
import { cleanText, foldEvents, mergeEvents, needsYouOf } from './transcript'
import { fit, listEntries, listTree, sessionTree } from './view'

const PANE = 'sessions'
const TITLE = 'Sessions'

// Change a tag when that value's fields change: it declines what an earlier version stored.
const ROWS = atom({ plugin: 'sessions', key: 'rows' } as const, [] as SessionRow[], { shape: 'rows-1' })
const LIST = atom({ plugin: 'sessions', key: 'list' } as const, { status: 'idle' })
const SHOW_ARCHIVED = atom({ plugin: 'sessions', key: 'showArchived' } as const, false)
const FOCUSED = atom({ plugin: 'sessions', key: 'focused' } as const, null as string | null)
const OPEN = atom({ plugin: 'sessions', key: 'open' } as const, null as OpenSession | null, { shape: 'open-1' })
const DRAFT = atom({ plugin: 'sessions', key: 'draft' } as const, '')
const NOTICE = atom({ plugin: 'sessions', key: 'notice' } as const, null)
const PANE_OPEN = atom({ plugin: 'sessions', key: 'paneOpen' } as const, false)
// Whether the last `.` could not place the pane, so the footer says to press Enter.
const NEEDS_ENTER = atom({ plugin: 'sessions', key: 'needsEnter' } as const, false)
// Deliberately ask for the whole viewport: the engine clamps this to the space its layout can spare.
let viewportSeen = { rows: 60, columns: 200 }
// Families: by repo (Other: '') and by transcript line key.
const FOLDED_GROUP = atom({ plugin: 'sessions', key: 'foldedGroup' } as const, false)
const OPEN_CALL = atom({ plugin: 'sessions', key: 'openCall' } as const, false)
// Whether the open session's transcript is expanded (`e`): every text unfolded, each call's result drawn under it.
const EXPANDED = atom({ plugin: 'sessions', key: 'expanded' } as const, false)

/** The events read so far per session key, merged on sequence number; a hot reload starts it afresh. */
const eventCache = new Map<string, ApiEvent[]>()
/** The list's pages: 50 sessions each, at most 4 pages (200 sessions) per refresh. */
const PAGE = 50
const PAGES = 4
/** The newest events read per session for needs-you, and how many such reads one refresh may make. */
const SIGNAL_EVENTS = 20
const SIGNAL_READS = 8
/** The events per older page of an open session. */
const OLDER_EVENTS = 100
/** What a session's events last showed, by session id, and the stamp (lastEventAt, else updatedAt) they were read at. */
const signalCache = new Map<string, { stamp: string | null; signals: NeedsYou }>()
/** Missing-list mirror detail results, including refusals, reused for a minute by registry id. */
const mirrorCache = new Map<string, { at: number; result: Fetched<ApiSession> }>()
const MIRROR_TTL_MS = 60_000
/** The pending poll timers; a hot reload drops them with the module, and the next render re-arms from paneOpen. */
type Pending = { cancel: () => void } | null
const timers: { list: Pending; open: Pending; band: Pending } = { list: null, open: null, band: null }
/** Consecutive failures per poll, for nextDelay. */
const failures = { list: 0, open: 0, band: 0 }
/** Reads in flight, so a key press and a timer do not read the same thing twice at once. */
const busy = { list: false, open: false, older: false }
/** A delete confirmation lives only for this module load, so a reload can never leave one armed. */
let pendingDelete: { key: string; at: number } | null = null

/** A short note from what a call threw: its message, one line, cut, long token-like runs masked. */
export function noteOf(what: string, error: unknown): string {
  const message = error instanceof Error ? error.message : typeof error === 'string' ? error : ''
  const clean = message.replace(/[\u0000-\u001f\u007f-\u009f]+/g, ' ').replace(/[A-Za-z0-9_\-.]{32,}/g, '\u2026')
  return fit(clean.trim() === '' ? `${what} failed` : `${what} failed: ${clean.trim()}`, 100)
}

/** The wait before the next read; poll.ts's rule, or its own doubling should that throw. */
function delayFor(base: number, failed: number): number {
  try {
    return nextDelay(base, failed)
  } catch {
    return Math.min(MAX_MS, base * 2 ** Math.min(failed, 8))
  }
}

/** Groups for the list: merge.ts's, or by repository in first-seen order should that throw ("Other" last). */
export function groupsOf(rows: readonly SessionRow[], showArchived: boolean): RepoGroup[] {
  try {
    return groupRows(rows, showArchived)
  } catch {
    const byRepo = new Map<string | null, SessionRow[]>()
    for (const row of rows) {
      if (isInactive(row) && !showArchived) continue
      byRepo.set(row.repo, [...(byRepo.get(row.repo) ?? []), row])
    }
    return [...byRepo].map(([repo, list]) => ({ repo, rows: list }))
  }
}

/** The row's actions, `send` left out (the composer sends); [] should actions.ts throw. */
function actionKeys(row: SessionRow | undefined): Array<{ id: ActionId; key: string; label: string }> {
  if (row === undefined) {
    return []
  }
  let listed: Array<{ id: ActionId; key: string; label: string }>
  try {
    listed = actionsFor(row)
  } catch {
    listed = []
  }
  const used = new Set<string>()
  const keys = listed
    .filter(action => action.id !== 'send')
    .map(action => {
      // A hotkey is one digit or one lowercase letter, each once; anything else draws a Button without one.
      const key = /^[a-z0-9]$/.test(action.key) && !used.has(action.key) ? action.key : ''
      used.add(key)
      return { ...action, key }
    })
  if (!keys.some(action => action.id === 'refresh')) {
    keys.push({ id: 'refresh', key: used.has('r') ? '' : 'r', label: 'refresh' })
  }
  return keys
}

/**
 * The session view's action keys: the row's actions, then `e` to expand or collapse the transcript. That one is a view
 * key, so it is listed with or without a row.
 */
function viewActions(
  row: SessionRow | undefined,
  expanded: boolean,
): Array<{ id: ActionId | 'expand'; key: string; label: string }> {
  const keys: Array<{ id: ActionId | 'expand'; key: string; label: string }> = actionKeys(row)
  const taken = keys.some(action => action.key === 'e')
  return [...keys, { id: 'expand', key: taken ? '' : 'e', label: expanded ? 'Collapse' : 'Expand' }]
}

// ---------------------------------------------------------------------------------------------------------------
// Reading

/** Runs a call that may throw; the throw comes back as `{ error }`. */
async function attempt<T>(call: () => Promise<T>): Promise<{ value: T } | { error: unknown }> {
  try {
    return { value: await call() }
  } catch (error) {
    return { error }
  }
}

/** The sessions API's list read page by page: the sessions, and whether more may exist past them. */
type Listing =
  | { ok: true; sessions: ApiSession[]; more: boolean }
  | { ok: false; status: number | null; reason: string }

/**
 * Reads the list, following next_cursor for at most PAGES pages. `more` is set when a cursor is left after the last
 * page, or when the last page read was full and had none (more may exist). A failure on the first page fails the
 * list; one on a later page keeps the pages already read and counts as more.
 */
async function listPages($: any): Promise<Listing> {
  const sessions: ApiSession[] = []
  const seen = new Set<string>()
  let cursor: string | null = null
  for (let page = 0; page < PAGES; page++) {
    const got = await listSessions($, cursor === null ? { limit: PAGE } : { limit: PAGE, cursor })
    if (!got.ok) {
      return page === 0 ? { ok: false, status: got.status, reason: got.reason } : { ok: true, sessions, more: true }
    }
    // The first sight of an id wins: a page that repeats ids adds nothing, and one that adds no new id ends the read.
    const fresh = got.value.sessions.filter((session) => !seen.has(session.id))
    for (const session of fresh) seen.add(session.id)
    sessions.push(...fresh)
    // The page's own item count, not the parsed one: a full page with one bad item still has more behind it.
    if (got.value.count < PAGE) return { ok: true, sessions, more: false }
    if (got.value.nextCursor === null) return { ok: true, sessions, more: true }
    if (fresh.length === 0) return { ok: true, sessions, more: false }
    cursor = got.value.nextCursor
  }
  return { ok: true, sessions, more: true }
}

/** When a session last had activity, in ms (its lastEventAt, else updatedAt; 0 when neither parses). */
function stampOf(session: ApiSession): number {
  return Date.parse(session.lastEventAt ?? session.updatedAt ?? '') || 0
}

/** What says a session changed since its events were read: its lastEventAt, else its updatedAt. */
function changeStamp(session: ApiSession): string | null {
  return session.lastEventAt ?? session.updatedAt ?? null
}

/**
 * The needs-you of each listed session, from the cache. Up to SIGNAL_READS reads of the newest events, among the
 * sessions that are neither archived nor disconnected, never read or changed since (changeStamp); the rest keep their
 * entry. A session read once with no stamp at all is not read again, so it cannot take the budget every refresh.
 * Entries of sessions no longer listed, archived or disconnected are dropped: such a row takes its state from the API.
 */
async function signalsOf($: any, sessions: ApiSession[]): Promise<Record<string, NeedsYou>> {
  const live = (session: ApiSession) => session.status !== 'archived' && session.connectionStatus !== 'disconnected'
  const eligible = sessions.filter(live).sort((a, b) => stampOf(b) - stampOf(a))
  const due: ApiSession[] = []
  for (const session of eligible) {
    if (due.length >= SIGNAL_READS) break
    const known = signalCache.get(session.id)
    if (known === undefined || known.stamp !== changeStamp(session)) {
      due.push(session)
    }
  }
  const reads = await Promise.all(
    due.map(async (session) => ({
      session,
      page: await attempt(() => getEvents($, session.id, { limit: SIGNAL_EVENTS })),
    })),
  )
  for (const { session, page } of reads) {
    if ('value' in page && page.value.ok) {
      signalCache.set(session.id, { stamp: changeStamp(session), signals: needsYouOf(page.value.value.events) })
    }
  }
  const listed = new Set(sessions.filter(live).map((session) => session.id))
  for (const id of [...signalCache.keys()]) {
    if (!listed.has(id)) signalCache.delete(id)
  }
  const out: Record<string, NeedsYou> = {}
  for (const session of sessions) {
    const known = signalCache.get(session.id)
    if (known !== undefined) out[session.id] = known.signals
  }
  return out
}

/** Reads omitted mirrors in parallel; a failed detail read becomes a visible registry row. */
async function mirrorsOf($: any, sessions: ApiSession[], registry: Registry): Promise<{
  sessions: ApiSession[]; missingMirrors: NonNullable<MergeInput['missingMirrors']>
}> {
  const now = Number(await $.clock.now())
  const omitted = Object.entries(registry.mains).filter(([, entry]) =>
    entry.sessionId !== null && !sessions.some((session) => sameSessionId(session.id, entry.sessionId)),
  )
  const reads = await Promise.all(omitted.map(async ([repo, entry]) => {
    const id = entry.sessionId!
    const known = mirrorCache.get(id)
    let result = known?.result
    if (known === undefined || now - known.at >= MIRROR_TTL_MS) {
      const read = await attempt(async () => {
        const apiId = id.replace(/^session_/, 'cse_')
        const first = await getSession($, apiId)
        return !first.ok && first.status === 404 && apiId !== id ? getSession($, id) : first
      })
      result = 'value' in read ? read.value : { ok: false, status: null, reason: noteOf('reading the mirror', read.error) }
      mirrorCache.set(id, { at: now, result })
    }
    return { repo, sessionId: id, result: result! }
  }))
  const found: ApiSession[] = []
  const missingMirrors: NonNullable<MergeInput['missingMirrors']> = []
  for (const { repo, sessionId, result } of reads) {
    if (result.ok) {
      if (![...sessions, ...found].some((session) => sameSessionId(session.id, result.value.id))) found.push(result.value)
    } else {
      missingMirrors.push({ repo, sessionId, reason: result.reason, status: result.status })
    }
  }
  return { sessions: found, missingMirrors }
}

/**
 * Reads the list: the sessions API, the local agents and the registry together. When the API fails, the rows come
 * from ListAgents and the registry, and the list says so (the status code only). Resolves whether it read.
 */
export async function refreshList($: any): Promise<boolean> {
  if (busy.list) {
    return true
  }
  busy.list = true
  try {
    const [listed, agents, registry] = await Promise.all([
      attempt(() => listPages($)),
      attempt(() => readAgents($)),
      attempt(() => readRegistry($)),
    ])
    const at = new Date(await $.clock.now()).toISOString()
    if ('error' in listed) {
      await update($, LIST, (): ListStatus => ({ status: 'error', note: noteOf('the session list', listed.error), at }))
      return false
    }
    let cloud: ApiSession[] | null = null
    let more = false
    let note: string | undefined
    let listAgents: Awaited<ReturnType<typeof readListAgents>> = []
    let missingMirrors: MergeInput['missingMirrors'] = []
    const kit: Registry = 'value' in registry ? registry.value : { mains: {}, runs: [] }
    if (listed.value.ok) {
      const listedNow = listed.value.sessions
      cloud = listedNow
      more = listed.value.more
      const mirrors = await attempt(() => mirrorsOf($, listedNow, kit))
      if ('value' in mirrors) {
        cloud = [...cloud, ...mirrors.value.sessions]
        missingMirrors = mirrors.value.missingMirrors
      }
    } else {
      note = `sessions API failed (${listed.value.reason}): local and kit sessions only`
      const fallback = await attempt(() => readListAgents($))
      listAgents = 'value' in fallback ? fallback.value : []
    }
    // The needs-you of the sessions the list holds; a failed read keeps what was known, and never fails the list.
    let signals: Record<string, NeedsYou> = {}
    if (cloud !== null) {
      const listedNow: ApiSession[] = cloud
      const probed = await attempt(() => signalsOf($, listedNow))
      signals = 'value' in probed ? probed.value : {}
    }
    const merged = await attempt(async () =>
      mergeRows({
        cloud,
        agents: 'value' in agents ? agents.value : [],
        listAgents,
        registry: kit,
        signals,
        missingMirrors,
      }),
    )
    if ('error' in merged) {
      await update($, LIST, (): ListStatus => ({ status: 'error', note: noteOf('merging the list', merged.error), at }))
      return false
    }
    await update($, ROWS, () => merged.value)
    const done: ListStatus =
      note !== undefined
        ? { status: 'fallback', note, at }
        : more
          ? { status: 'ready', note: `showing the newest ${listed.value.ok ? listed.value.sessions.length : 0}`, at }
          : { status: 'ready', at }
    await update($, LIST, () => done)
    return cloud !== null
  } catch (error) {
    const failed: ListStatus = { status: 'error', note: noteOf('the session list', error) }
    await attempt(() => update($, LIST, () => failed))
    return false
  } finally {
    busy.list = false
  }
}

/** Writes the open session if it is still the one open. */
async function putOpen($: any, key: string, next: (open: OpenSession) => OpenSession) {
  await update($, OPEN, open => (open === null || open.key !== key ? open : next(open)))
}

/** The useful list facts retained when claude.ai refuses both detail endpoints. */
export function refusedView(
  row: SessionRow,
  reason: string,
  code?: string,
): Pick<OpenSession, 'header' | 'lines' | 'status' | 'note'> {
  const open = row.id === null ? '' : ` Open it at ${appUrl(row.id)}.`
  const note = code?.startsWith('untrusted_device')
    ? `claude.ai shows this session only to a trusted device (${reason}): the computer it is bound to, or one ` +
      `enrolled with /login. The pane's request cannot prove that, so open it in the Claude app.${open}`
    : code === 'session_stale_relogin'
      ? `claude.ai wants a fresh sign-in before it shows this session (${reason}): run /login, then press r.${open}`
      : `claude.ai refused this session's details and transcript (${reason}).${open}`
  return { header: headerOf(null, row), lines: [], status: 'error', note }
}

/** The note shown after both detail endpoints confirm that a session was deleted. */
export function deletedSessionNote(row: Pick<SessionRow, 'role' | 'repo'>): string {
  const missing = 'This session was deleted on claude.ai.'
  return row.role === 'mirror' && row.repo !== null
    ? `${missing} Its kit registry entry stays until you run: lane main --forget ${row.repo}`
    : missing
}

/** Reads the open session: an API row's detail and newest events, or a local row's `claude logs`. */
export async function refreshOpen($: any): Promise<boolean> {
  const open = await read($, OPEN)
  if (open === null || busy.open) {
    return true
  }
  busy.open = true
  const key = open.key
  try {
    const row = (await read($, ROWS)).find(candidate => candidate.key === key)
    if (row === undefined) {
      await putOpen($, key, now => ({ ...now, status: 'error', note: 'the session is no longer listed' }))
      return false
    }
    if (row.id !== null) {
      const id = row.id
      const [detail, page] = await Promise.all([
        attempt(() => getSession($, id)),
        attempt(() => getEvents($, id, { limit: 100 })),
      ])
      const session = 'value' in detail && detail.value.ok ? detail.value.value : null
      const events = 'value' in page && page.value.ok ? page.value.value : null
      if (session === null && events === null) {
        const deleted = 'value' in detail && !detail.value.ok && detail.value.status === 404 &&
          'value' in page && !page.value.ok && page.value.status === 404
        if (deleted) {
          await dropOpenRow($, key, deletedSessionNote(row))
          return false
        }
        const failed =
          'value' in page && !page.value.ok ? page.value : 'value' in detail && !detail.value.ok ? detail.value : null
        const refusal = failed?.status === 403 ? refusedView(row, failed.reason, failed.code) : null
        const note = refusal !== null
          ? refusal.note
          : failed !== null
            ? `sessions API failed (${failed.reason})`
            : noteOf('reading the session', 'error' in page ? page.error : 'error' in detail ? detail.error : '')
        await putOpen($, key, now => ({
          ...now,
          ...(refusal ?? {}),
          status: 'error',
          note,
        }))
        return false
      }
      const known = eventCache.get(key) ?? []
      const merged = events === null ? known : mergeEvents(known, events.events)
      eventCache.set(key, merged)
      const needsYou = needsYouOf(merged)
      // The list reads this session's signals from the cache, so the open one writes its own too.
      if (events !== null && session !== null) signalCache.set(id, { stamp: changeStamp(session), signals: needsYou })
      const base = headerOf(session, row)
      // A disconnected session shows offline, as in the list: what its events last held cannot be answered there.
      const live = session !== null && session.connectionStatus !== 'disconnected'
      const header = session === null ? base : { ...base, state: stateOf(session, live ? needsYou : undefined) }
      const lines = foldEvents(merged)
      const newestSeq = merged.reduce((most, event) => Math.max(most, event.seq), 0)
      await putOpen($, key, now => ({
        ...now,
        header,
        lines,
        needsYou,
        newestSeq,
        // Once older pages were read, the poll keeps the cursor they left (the oldest one); until then it takes the
        // newest page's.
        olderCursor: events === null || now.olderRead === true ? now.olderCursor : events.nextCursor,
        status: 'ready',
        note: undefined,
      }))
      return true
    }
    if (row.localId !== null) {
      // The id goes to argv as one element: a plain id only, so it can never read as an option.
      if (!/^[A-Za-z0-9][A-Za-z0-9_.:-]*$/.test(row.localId)) {
        await putOpen($, key, now => ({ ...now, status: 'error', note: 'the local session id is not a plain id' }))
        return false
      }
      const ran = await $.process.run(['claude', 'logs', row.localId])
      const logText = cleanText(String(ran?.stdout ?? ''), 200_000)
      const failed = typeof ran?.exitCode === 'number' && ran.exitCode !== 0
      await putOpen($, key, now => ({
        ...now,
        logText,
        status: failed ? 'error' : 'ready',
        note: failed ? `claude logs exited ${ran.exitCode}` : undefined,
      }))
      return !failed
    }
    await putOpen($, key, now => ({ ...now, status: 'error', note: 'no transcript to read for this session' }))
    return false
  } catch (error) {
    const note = noteOf('reading the session', error)
    await attempt(() => putOpen($, key, now => ({ ...now, status: 'error', note })))
    return false
  } finally {
    busy.open = false
  }
}

// ---------------------------------------------------------------------------------------------------------------
// Polling: only while the pane is open (the band apart), each read scheduling the next.

function cancel(which: 'list' | 'open' | 'band') {
  timers[which]?.cancel()
  timers[which] = null
}

/** Arms the list poll, unless it is armed; `delay` overrides the wait (0 reads now). */
function armList($: any, delay?: number) {
  if (timers.list !== null) {
    return
  }
  try {
    timers.list = $.clock.after(delay ?? delayFor(LIST_MS, failures.list), async () => {
      timers.list = null
      if (!(await read($, PANE_OPEN))) {
        return
      }
      failures.list = (await refreshList($)) ? 0 : failures.list + 1
      armList($)
    })
  } catch {
    timers.list = null
  }
}

/** Arms the open session's poll while a session is open. */
function armOpen($: any, delay?: number) {
  if (timers.open !== null) {
    return
  }
  try {
    timers.open = $.clock.after(delay ?? delayFor(SESSION_MS, failures.open), async () => {
      timers.open = null
      if (!(await read($, PANE_OPEN)) || (await read($, OPEN)) === null) {
        return
      }
      failures.open = (await refreshOpen($)) ? 0 : failures.open + 1
      armOpen($)
    })
  } catch {
    timers.open = null
  }
}

/** Arms the band's read of the list, which runs only while the pane is closed. */
function armBand($: any) {
  if (timers.band !== null) {
    return
  }
  try {
    timers.band = $.clock.after(delayFor(BAND_MS, failures.band), async () => {
      timers.band = null
      if (!(await read($, PANE_OPEN))) {
        failures.band = (await refreshList($)) ? 0 : failures.band + 1
        $.ui.invalidate('ui.render')
      }
      armBand($)
    })
  } catch {
    timers.band = null
  }
}

/** `r`: reads now, then polls on from there. */
async function refreshNow($: any) {
  resetRegistryCache()
  mirrorCache.clear()
  cancel('list')
  failures.list = 0
  if ((await read($, OPEN)) !== null) {
    cancel('open')
    failures.open = 0
    armOpen($, 0)
  }
  armList($, 0)
}

// ---------------------------------------------------------------------------------------------------------------
// The pane

/** Opens the pane at the list, asking for the keyboard, and starts the polls. */
async function openPane($: any, fromKey = false): Promise<boolean> {
  await update($, PANE_OPEN, () => true)
  const opened = await $.ui.open({
    id: PANE,
    title: TITLE,
    focus: true,
    closeOnEscape: true,
    rows: viewportSeen.rows,
    columns: viewportSeen.columns,
  })
  if (opened?.isPlaced === false) {
    if (fromKey) {
      try {
        await $.ui.close({ id: PANE })
      } catch {
        // the pane was not placed
      }
      await closed($)
      await update($, NEEDS_ENTER, () => true)
      return false
    }
    $.ui.toast(`Sessions pane not placed: ${opened.reason ?? 'no room'}`)
  }
  await update($, NEEDS_ENTER, () => false)
  armList($, 0)
  if ((await read($, OPEN)) !== null) {
    armOpen($, 0)
  }
  return true
}

/** Opens a row's session view; its first read follows at once. */
async function openRow($: any, row: SessionRow) {
  pendingDelete = null
  let header = null
  try {
    header = headerOf(null, row)
  } catch {
    header = null
  }
  const open: OpenSession = {
    key: row.key,
    header,
    lines: [],
    needsYou: { held: false, permissionWait: false },
    newestSeq: 0,
    olderCursor: null,
    olderRead: false,
    status: 'loading',
  }
  // A reopened session reads afresh: pages held from before would make `p` re-read them with nothing to show.
  eventCache.delete(row.key)
  await update($, OPEN, () => open)
  await update($, DRAFT, () => '')
  await update($, NOTICE, () => null)
  // Expansion belongs to the session it was chosen in: a session opened from the list starts folded.
  await update($, EXPANDED, () => false)
  cancel('open')
  failures.open = 0
  armOpen($, 0)
}

/** Back from the session view to the list. */
async function backToList($: any) {
  pendingDelete = null
  cancel('open')
  const open = await read($, OPEN)
  await update($, OPEN, () => null)
  await update($, NOTICE, () => null)
  if (open !== null) {
    await update($, FOCUSED, () => open.key)
  }
}

/** Removes a gone session, leaves its view if still open, reports why, then reconciles the list. */
async function dropOpenRow($: any, key: string, note: string) {
  await update($, ROWS, rows => rows.filter(candidate => candidate.key !== key))
  const current = await read($, OPEN)
  if (current !== null && current.key === key) {
    await backToList($)
    await update($, FOCUSED, () => null)
  }
  $.ui.toast(note)
  await refreshList($)
}

/** The pane is gone: the polls stop and the next open starts at the list. */
async function closed($: any) {
  pendingDelete = null
  cancel('list')
  cancel('open')
  await update($, PANE_OPEN, () => false)
  await update($, OPEN, () => null)
  await update($, FOCUSED, () => null)
}

/**
 * `p`: reads the page of events before the ones the view holds, folds them in and keeps the cursor it left. With no
 * cursor left, the answer is "No older events".
 */
async function olderEvents($: any, open: OpenSession, row: SessionRow, at: string): Promise<ActionNotice> {
  if (busy.older) {
    // One older read at a time: a second press would read the same cursor and skip a page.
    return { tone: 'info', text: 'Older events are still being read', at }
  }
  if (row.id === null || open.olderCursor === null) {
    return { tone: 'info', text: 'No older events', at }
  }
  const id = row.id
  const cursor = open.olderCursor
  busy.older = true
  try {
    return await readOlder($, open, id, cursor, at)
  } finally {
    busy.older = false
  }
}

/** One older page of `olderEvents`, read at `cursor` and folded into the open view. */
async function readOlder($: any, open: OpenSession, id: string, cursor: string, at: string): Promise<ActionNotice> {
  const page = await attempt(() => getEvents($, id, { limit: OLDER_EVENTS, cursor }))
  if ('error' in page) {
    return { tone: 'error', text: noteOf('older events', page.error), at }
  }
  if (!page.value.ok) {
    return { tone: 'error', text: `older events: sessions API failed (${page.value.reason})`, at }
  }
  // Read after the await and set with no await between: a poll that merged meanwhile is not lost.
  const merged = mergeEvents(eventCache.get(open.key) ?? [], page.value.value.events)
  eventCache.set(open.key, merged)
  const lines = foldEvents(merged)
  const nextCursor = page.value.value.nextCursor
  await putOpen($, open.key, now => ({ ...now, lines, olderCursor: nextCursor, olderRead: true }))
  const count = page.value.value.events.length
  if (count === 0) {
    return { tone: 'info', text: 'No older events', at }
  }
  // The cache keeps the newest 2000 events (mergeEvents' cap): a page past it is read but not kept.
  const kept = new Set(merged.map(event => event.seq))
  if (!page.value.value.events.some(event => kept.has(event.seq))) {
    return { tone: 'info', text: 'The view holds the newest 2000 events; older ones are not kept', at }
  }
  return { tone: 'ok', text: `Read ${count} older event${count === 1 ? '' : 's'}`, at }
}

/** An action key: refresh reads now, older reads the page before, send goes through the composer, the rest run in
 * actions.ts. Returns the notice an action gave (none for refresh or when the open row is gone). */
async function act($: any, id: ActionId, text?: string): Promise<ActionNotice | undefined> {
  if (id !== 'delete') pendingDelete = null
  if (id === 'refresh') {
    await refreshNow($)
    return undefined
  }
  const open = await read($, OPEN)
  const row = open === null ? undefined : (await read($, ROWS)).find(candidate => candidate.key === open.key)
  if (open === null || row === undefined) {
    pendingDelete = null
    return undefined
  }
  const now = await $.clock.now()
  const at = new Date(now).toISOString()
  const armedDelete = pendingDelete
  if (id === 'delete' && (armedDelete?.key !== row.key || now - armedDelete.at > 10000)) {
    pendingDelete = { key: row.key, at: now }
    const armed = {
      tone: 'info' as const,
      text: cleanOutput(`Delete "${cleanOutput(row.title)}" permanently? Press d again within 10 s. This cannot be undone.`),
      at,
    }
    await update($, NOTICE, () => armed)
    return armed
  }
  if (id === 'delete') pendingDelete = null
  let notice: ActionNotice
  try {
    notice = id === 'older' ? await olderEvents($, open, row, at) : await runAction($, id, row, text)
  } catch (error) {
    notice = { tone: 'error', text: noteOf(id, error), at }
  }
  if (id === 'delete' && notice.tone === 'ok') {
    // The session is gone: drop its row, and leave its view the way Back does (which also stops its poll), unless
    // another session was opened meanwhile. The list draws no notice, so a toast says it.
    await dropOpenRow($, row.key, notice.text)
    return notice
  }
  if (id === 'archive' && notice.tone === 'ok') await refreshList($)
  // An action outlives a change of view: its notice shows only while the same session is still open.
  const still = await read($, OPEN)
  if (still !== null && still.key === open.key) {
    await update($, NOTICE, () => notice)
  }
  return notice
}

/** The composer's Enter: sends the text; the field is emptied only when the send said ok, else the text stays. */
async function send($: any, text: string) {
  if (text.trim() === '') {
    return
  }
  await update($, DRAFT, () => text)
  const before = await read($, OPEN)
  const notice = await act($, 'send', text)
  const after = await read($, OPEN)
  if (notice?.tone === 'ok' && before !== null && after !== null && after.key === before.key) {
    // Empties the field only while the same session is open and it still holds what was sent (typing is kept).
    await update($, DRAFT, current => (current === text ? '' : current))
  }
}

/** The keys of the list's rows in drawn order (folded groups left out), for the arrows. */
async function rowOrder($: any): Promise<string[]> {
  const groups = groupsOf(await read($, ROWS), await read($, SHOW_ARCHIVED))
  const folded = new Set<string>()
  for (const group of groups) {
    if (await read($, memberOf(FOLDED_GROUP, { requestId: group.repo ?? '' }))) {
      folded.add(group.repo ?? '')
    }
  }
  return listEntries(groups, 80, 0, null, {
    showArchived: await read($, SHOW_ARCHIVED),
    isFolded: repo => folded.has(repo),
  })
    .filter(entry => entry.kind === 'row')
    .map(entry => entry.key)
}

/** Moves the ring to a row and scrolls only as far as keeps it in view. */
async function moveRing($: any, key: string) {
  try {
    await $.ui.focus({ requestId: PANE, key })
    await $.ui.scroll({ in: PANE, to: { key }, block: 'nearest' })
  } catch {
    // the pane lost the keys meanwhile
  }
}

/** The status line under the list. */
function statusLine(list: { status: string; note?: string }, rows: number, isFocused: boolean): string {
  const count = `${rows} session${rows === 1 ? '' : 's'}`
  const keys = isFocused
    ? '\u2191\u2193 choose \u00b7 Enter opens \u00b7 Esc closes'
    : 'ctrl+x tab to choose'
  if (list.status === 'loading' || list.status === 'idle') {
    return `reading\u2026 \u00b7 ${keys}`
  }
  if (list.status === 'fallback' || list.status === 'error') {
    return `! ${list.note ?? list.status} \u00b7 ${count}`
  }
  // A capped read keeps its note; the list draws its own session count.
  return list.note === undefined ? keys : `${list.note} \u00b7 ${keys}`
}

export const register: Register = (on, options) => {
  const band = options.band === true

  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'sessions', description: 'Open the Sessions pane: every session, by repository' })
    if (band) {
      armBand($)
    }
    return next(e)
  })

  on('command.run', { command: 'sessions' }, async $ => {
    await openPane($)
    return {}
  })

  // The footer follows the engine's hint while an empty terminal prompt can open Sessions.
  on('ui.render', { component: 'PromptHint' }, async ($, e, next) => {
    viewportSeen = {
      rows: e.viewport?.rows ?? viewportSeen.rows,
      columns: e.viewport?.columns ?? viewportSeen.columns,
    }
    if (e.surface !== 'terminal' || e.props.isDraft || (await read($, PANE_OPEN))) return next(e)
    const hint = (await read($, NEEDS_ENTER)) ? '. then Enter for sessions' : '. for sessions'
    return next({ ...e, props: { ...e.props, tail: e.props.tail === undefined ? hint : `${e.props.tail} · ${hint}` } })
  })

  // `.` typed into an empty prompt opens the pane instead of starting a message.
  on('prompt.edit', async ($, e, next) => {
    if (e.text !== '' || e.inputText !== '.' || e.start !== 0 || e.end !== 0) {
      return next(e)
    }
    if (await openPane($, true)) {
      return { text: e.text, cursor: e.cursor }
    }
    // Not placeable from a key alone: `.` is typed, and Enter on it opens the pane.
    $.ui.toast('Press Enter to open Sessions')
    return next(e)
  })

  // `.` sent alone opens the pane instead of starting a message; any other prompt passes untouched.
  on('prompt.submit', async ($, e, next) => {
    if (e.text.trim() !== '.' || e.attachments !== undefined || e.command !== undefined || e.isMeta === true) {
      return next(e)
    }
    await openPane($)
    // A dropped prompt stays in the box, which keeps the keyboard from the pane: empty it, then ask again.
    $.clock.after(0, async () => {
      try {
        await $.prompt.fill({ text: '' })
        await $.ui.open({
          id: PANE,
          title: TITLE,
          focus: true,
          closeOnEscape: true,
          rows: viewportSeen.rows,
          columns: viewportSeen.columns,
        })
      } catch {
        // the box is the person's again
      }
    })
    return { drop: 'Sessions opened' }
  })

  // Esc in the session view goes back to the list; Esc in the list (or the close mark) closes the pane.
  on('ui.close', { id: PANE }, async ($, e, next) => {
    if (e.origin?.kind === 'person' && (await read($, OPEN)) !== null) {
      await backToList($)
      return { value: undefined }
    }
    const result = await next(e)
    await closed($)
    return result
  })

  on('ui.focus', { requestId: PANE }, async ($, e, next) => {
    const result = await next(e)
    const element = e.element ?? ''
    if (!result?.deny && element.startsWith('row:')) {
      await update($, FOCUSED, () => element.slice(4))
    }
    return result
  })

  // In a list taller than the pane the arrows scroll the body and leave the ring; here they move the choice.
  on('ui.scroll', { component: 'Pane', requestId: PANE }, async ($, e, next) => {
    if (e.origin?.kind !== 'person' || (e as any).pointer !== undefined || Math.abs(e.by) !== 1) {
      return next(e)
    }
    if ((await read($, OPEN)) !== null) {
      return next(e)
    }
    const order = await rowOrder($)
    const focused = await read($, FOCUSED)
    const at = focused === null ? -1 : order.indexOf(`row:${focused}`)
    const target = order[Math.min(order.length - 1, Math.max(0, at === -1 ? 0 : at + Math.sign(e.by)))]
    if (target === undefined) {
      return next(e)
    }
    await update($, FOCUSED, () => target.slice(4))
    $.clock.after(0, () => void moveRing($, target))
    return { deny: 'the arrow moves the choice' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    viewportSeen = {
      rows: e.viewport?.rows ?? viewportSeen.rows,
      columns: e.viewport?.columns ?? viewportSeen.columns,
    }
    const ui = $.ui.resolve(e)
    const width = Math.max(20, e.props.bodyColumns)
    const now = await $.clock.now()
    const rows = await read($, ROWS)
    const open = await read($, OPEN)
    // A hot reload drops the timers: re-arm from paneOpen.
    if (await read($, PANE_OPEN)) {
      armList($)
      if (open !== null) {
        armOpen($)
      }
    }
    if (open !== null) {
      const row = rows.find(candidate => candidate.key === open.key)
      const opened = new Set<string>()
      const walk = async (lines: OpenSession['lines']) => {
        for (const line of lines) {
          if ((line.children ?? []).length > 0) {
            if (await read($, memberOf(OPEN_CALL, { requestId: line.key }))) {
              opened.add(line.key)
            }
            await walk(line.children ?? [])
          }
        }
      }
      await walk(open.lines)
      const expanded = await read($, EXPANDED)
      return sessionTree(
        ui,
        {
          open,
          width,
          now,
          notice: await read($, NOTICE),
          isOpened: key => opened.has(key),
          expanded,
          actions: viewActions(row, expanded),
          draft: await read($, DRAFT),
          hasComposer: e.surface !== 'mobile',
        },
        {
          back: () => backToList($),
          toggleCall: key => update($, memberOf(OPEN_CALL, { requestId: key }), value => !value),
          action: id => (id === 'expand' ? update($, EXPANDED, value => !value) : act($, id as ActionId)),
          typed: text => update($, DRAFT, () => text),
          send: text => send($, text),
        },
      )
    }
    const showArchived = await read($, SHOW_ARCHIVED)
    const groups = groupsOf(rows, showArchived)
    const folded = new Set<string>()
    for (const group of groups) {
      if (await read($, memberOf(FOLDED_GROUP, { requestId: group.repo ?? '' }))) {
        folded.add(group.repo ?? '')
      }
    }
    const list = await read($, LIST)
    // The count is of the rows the groups hold: archived rows only while they are shown.
    const shown = groups.reduce((sum, group) => sum + group.rows.length, 0)
    return listTree(
      ui,
      {
        groups,
        width,
        now,
        focused: e.props.isFocused ? await read($, FOCUSED) : null,
        showArchived,
        isFolded: repo => folded.has(repo),
        status: statusLine(list, shown, e.props.isFocused),
      },
      {
        openRow: row => openRow($, row),
        toggleGroup: repo => update($, memberOf(FOLDED_GROUP, { requestId: repo }), value => !value),
        toggleArchived: () => update($, SHOW_ARCHIVED, value => !value),
        refresh: () => refreshNow($),
      },
    )
  })

  // The band: one line above the prompt while the pane is closed and a session needs you; only with the setting.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    viewportSeen = {
      rows: e.viewport?.rows ?? viewportSeen.rows,
      columns: e.viewport?.columns ?? viewportSeen.columns,
    }
    if (!band) {
      return next(e)
    }
    armBand($)
    if (e.props.hasSurvey || (await read($, PANE_OPEN))) {
      return next(e)
    }
    const waiting = (await read($, ROWS)).filter(row => row.state === 'needs-you')
    if (waiting.length === 0) {
      return next(e)
    }
    const { Box, Button, Text } = $.ui.resolve(e)
    const names = waiting.map(row => row.title).join(', ')
    const text = `! ${waiting.length === 1 ? '1 session needs' : `${waiting.length} sessions need`} you: ${names}`
    return (
      <Box flexDirection="row">
        <Text color="warning">{fit(text, Math.max(10, e.props.bodyColumns - 10))} </Text>
        <Button key="band-open" label="open" onPress={() => openPane($)} />
      </Box>
    )
  })
}
