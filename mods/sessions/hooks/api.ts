// The sessions API (undocumented: the one the Claude app uses). Network only to api.anthropic.com, through
// $.http.fetch with the handle $.session.authorize() returns; the handle is never logged, stored or drawn.
// Unknown fields are ignored and missing ones tolerated: parse* return null only when `id` is missing.
import type { ApiEvent, ApiSession, Fetched, WorktreeState } from '../types'

export const API_BASE = 'https://api.anthropic.com/v1/code/sessions'
export const API_HEADERS = { 'anthropic-version': '2023-06-01' } as const

type Obj = Record<string, unknown>

/** A plain object, else an empty one: every read below goes through it. */
function obj(value: unknown): Obj {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Obj) : {}
}

/** A non-empty string, else null. */
function str(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null
}

/** A finite number (or a numeric string, as the API sends counts), else null. */
function num(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string' && value.trim() !== '') {
    const n = Number(value)
    return Number.isFinite(n) ? n : null
  }
  return null
}

/** A boolean, else null. */
function bool(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

/** Text with its control characters (C0, DEL, C1) turned to spaces, runs of spaces folded, trimmed. */
export function cleanText(value: unknown): string {
  if (typeof value !== 'string') return ''
  return value.replace(/[\u0000-\u001f\u007f-\u009f]+/g, ' ').replace(/ {2,}/g, ' ').trim()
}

/** A repository key the API sends (`current_branches`, `worktree_state`): owner/repo, plain characters only. */
const REPO_KEY = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/

/** Whether such a key names a repository; the '' key (the cloud session's own) never does. */
export function isRepoKey(key: string): boolean {
  return REPO_KEY.test(key) && key.split('/').every((part) => part !== '.' && part !== '..')
}

/** `https://github.com/acme/repo.git`, `git@github.com:acme/repo`, ... -> `acme/repo`; null when no repository URL. */
export function repoFromUrl(url: string): string | null {
  if (typeof url !== 'string') return null
  const text = url.trim()
  const part = '[A-Za-z0-9_.-]+'
  const tail = `(${part})/(${part}?)(?:\\.git)?/?$`
  const forms = [
    new RegExp(`^(?:https?|git|ssh)://(?:[^@/]+@)?(?:www\\.)?github\\.com(?::\\d+)?/${tail}`, 'i'),
    new RegExp(`^(?:[^@/]+@)?github\\.com:${tail}`, 'i'),
    new RegExp(`^(${part})/(${part})$`),
  ]
  for (const form of forms) {
    const match = form.exec(text)
    const owner = match?.[1]
    const repo = match?.[2]
    if (owner && repo && owner !== '.' && owner !== '..' && repo !== '.' && repo !== '..') return `${owner}/${repo}`
  }
  return null
}

/** One `worktree_state` entry -> WorktreeState. */
function parseWorktree(raw: unknown): WorktreeState {
  const w = obj(raw)
  return {
    branch: str(w.branch),
    head: str(w.head_sha),
    isDirty: bool(w.is_dirty),
    unpushed: num(w.unpushed_count),
    upstreamExists: bool(w.upstream_exists),
  }
}

/** `context_usage {used_tokens, max_tokens}` -> ContextUse; null unless both are numbers and max is above 0. */
function parseContext(raw: unknown): ApiSession['context'] {
  const c = obj(raw)
  const used = num(c.used_tokens)
  const max = num(c.max_tokens)
  return used !== null && max !== null && max > 0 ? { used, max } : null
}

/** One session object as the API sends it (list item or detail) -> ApiSession; null when it has no string id. */
export function parseSession(raw: unknown): ApiSession | null {
  const s = obj(raw)
  const id = str(s.id)
  if (id === null) return null
  const config = obj(s.config)
  const meta = obj(s.external_metadata)

  const branches: Record<string, string> = {}
  for (const [repo, branch] of Object.entries(obj(meta.current_branches))) {
    if (typeof branch === 'string') branches[repo] = branch
  }
  const worktrees: Record<string, WorktreeState> = {}
  for (const [repo, state] of Object.entries(obj(meta.worktree_state))) worktrees[repo] = parseWorktree(state)

  const repos: string[] = []
  const add = (repo: string | null) => {
    if (repo !== null && !repos.includes(repo)) repos.push(repo)
  }
  for (const source of Array.isArray(config.sources) ? config.sources : []) {
    const src = obj(source)
    if (src.type === 'git_repository' && typeof src.url === 'string') add(repoFromUrl(src.url))
  }
  // Branch and worktree keys name a repository only when they look like one; the '' key is the session's own branch.
  for (const key of [...Object.keys(obj(meta.current_branches)), ...Object.keys(obj(meta.worktree_state))]) {
    if (isRepoKey(key)) add(key)
  }

  return {
    id,
    title: cleanText(s.title),
    status: str(s.status) ?? '',
    statusBucket: str(s.status_bucket) ?? '',
    workerStatus: str(s.worker_status) ?? '',
    connectionStatus: str(s.connection_status) ?? '',
    environmentKind: str(s.environment_kind) ?? '',
    unread: s.unread === true,
    updatedAt: str(s.updated_at),
    lastEventAt: str(s.last_event_at),
    createdAt: str(s.created_at),
    model: str(meta.model) ?? str(config.model),
    effort: str(meta.effort_level) ?? str(config.effort_level),
    origin: str(config.origin),
    repos,
    branches,
    worktrees,
    context: parseContext(meta.context_usage),
    permissionMode: str(meta.permission_mode) ?? str(s.permission_mode),
    requiresAction: Array.isArray(s.requires_action_details_list) ? s.requires_action_details_list.length : 0,
  }
}

/** One event object -> ApiEvent; null when it has no event_id or no numeric sequence_num. */
export function parseEvent(raw: unknown): ApiEvent | null {
  const e = obj(raw)
  const id = str(e.event_id)
  if (id === null) return null
  const sequence = e.sequence_num
  if (typeof sequence !== 'string' && typeof sequence !== 'number') return null
  if (typeof sequence === 'string' && sequence.trim() === '') return null
  const seq = Number(sequence)
  if (!Number.isFinite(seq)) return null
  const source = e.source === 'worker' || e.source === 'client' ? e.source : 'other'
  return { id, type: str(e.event_type) ?? '', seq, at: str(e.created_at), source, payload: e.payload ?? null }
}

// The authorization, kept for this module's life only (never in $.state or $.store); dropped on a 401.
let cachedHandle: string | null = null

/** Forgets the cached authorization (a test hook, and what a 401 does). */
export function resetAuthorization(): void {
  cachedHandle = null
}

/** The handle, from the cache or a fresh $.session.authorize(); null when there is no first-party credential. */
async function authorize($: any, fresh: boolean): Promise<string | null> {
  if (!fresh && cachedHandle !== null) return cachedHandle
  cachedHandle = null
  const auth = await $.session.authorize()
  const handle = auth && typeof auth.handle === 'string' && auth.handle !== '' ? auth.handle : null
  cachedHandle = handle
  return handle
}

/** A short, safe name for a thrown value: its error name, never its message. */
function errorName(error: unknown): string {
  const name = error !== null && typeof error === 'object' ? (error as { name?: unknown }).name : null
  return typeof name === 'string' && /^[A-Za-z][A-Za-z0-9_]{0,40}$/.test(name) ? name : 'Error'
}

/** One authorized GET, parsed as JSON: re-authorizes once on a 401; any failure gives a short reason. */
export async function getJson($: any, url: string): Promise<Fetched<unknown>> {
  for (let attempt = 0; attempt < 2; attempt++) {
    let handle: string | null
    try {
      handle = await authorize($, attempt > 0)
    } catch (error) {
      return { ok: false, status: null, reason: `authorize: ${errorName(error)}` }
    }
    if (handle === null) return { ok: false, status: null, reason: 'no credential' }
    let response: any
    try {
      response = await $.http.fetch(url, { auth: handle, headers: { ...API_HEADERS } })
    } catch (error) {
      return { ok: false, status: null, reason: `network: ${errorName(error)}` }
    }
    const status = typeof response?.status === 'number' ? response.status : null
    if (status === 401 && attempt === 0) {
      cachedHandle = null
      continue
    }
    if (status === null || status < 200 || status > 299) {
      let message = ''
      let code: string | null = null
      try {
        const error = obj(obj(JSON.parse(typeof response.text === 'string' ? response.text : '')).error)
        message = cleanText(error.message).replace(/\s+/g, ' ').slice(0, 160)
        // A refusal names what it guards: untrusted_device (with sub_reason bound_unattested when the session is
        // bound to another computer) or session_stale_relogin, as Claude Code's own client reads them.
        const token = (value: unknown): string | null =>
          typeof value === 'string' && /^[a-z][a-z0-9_]{0,40}$/.test(value) ? value : null
        const resource = token(error.resource)
        const sub = token(error.sub_reason)
        code = resource === null ? null : sub === null ? resource : `${resource}/${sub}`
      } catch {
        // Error bodies are often empty or HTML; keep the status-only reason in that case.
      }
      const detail = message !== '' ? message : code ?? ''
      const reason = status === null ? 'no response' : `HTTP ${status}${detail === '' ? '' : `: ${detail}`}`
      return code === null ? { ok: false, status, reason } : { ok: false, status, reason, code }
    }
    try {
      return { ok: true, value: JSON.parse(typeof response.text === 'string' ? response.text : '') }
    } catch {
      return { ok: false, status, reason: 'unreadable JSON' }
    }
  }
  return { ok: false, status: 401, reason: 'HTTP 401' }
}

/** A URL with the options that are set as its query. */
function withQuery(base: string, options?: { limit?: number; cursor?: string }): string {
  const query = new URLSearchParams()
  if (options?.limit !== undefined && Number.isFinite(options.limit)) query.set('limit', String(options.limit))
  if (options?.cursor) query.set('cursor', options.cursor)
  const text = query.toString()
  return text === '' ? base : `${base}?${text}`
}

/** Each item of `data` the parser takes; the ones it does not are skipped. */
function parseAll<T>(data: unknown, parse: (raw: unknown) => T | null): T[] {
  const out: T[] = []
  for (const item of Array.isArray(data) ? data : []) {
    const parsed = parse(item)
    if (parsed !== null) out.push(parsed)
  }
  return out
}

/** GET /v1/code/sessions?limit=&cursor= : newest activity first. */
export async function listSessions(
  $: any,
  options?: { limit?: number; cursor?: string },
): Promise<Fetched<{ sessions: ApiSession[]; nextCursor: string | null; count: number }>> {
  const got = await getJson($, withQuery(API_BASE, options))
  if (!got.ok) return got
  const body = obj(got.value)
  // count: the items the page held, parsed or not, so a page with one bad item still reads as full.
  const count = Array.isArray(body.data) ? body.data.length : 0
  return { ok: true, value: { sessions: parseAll(body.data, parseSession), nextCursor: str(body.next_cursor), count } }
}

/** GET /v1/code/sessions/{id} */
export async function getSession($: any, id: string): Promise<Fetched<ApiSession>> {
  const got = await getJson($, `${API_BASE}/${encodeURIComponent(id)}`)
  if (!got.ok) return got
  const session = parseSession(got.value)
  if (session === null) return { ok: false, status: 200, reason: 'no session in the response' }
  return { ok: true, value: session }
}

/** GET /v1/code/sessions/{id}/events?limit=&cursor= : newest first; nextCursor gives the next older page. */
export async function getEvents(
  $: any,
  id: string,
  options?: { limit?: number; cursor?: string },
): Promise<Fetched<{ events: ApiEvent[]; nextCursor: string | null }>> {
  const got = await getJson($, withQuery(`${API_BASE}/${encodeURIComponent(id)}/events`, options))
  if (!got.ok) return got
  const body = obj(got.value)
  return { ok: true, value: { events: parseAll(body.data, parseEvent), nextCursor: str(body.next_cursor) } }
}
