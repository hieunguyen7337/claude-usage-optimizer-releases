// One list from every source: API sessions, local agents, ListAgents (when the API failed) and the registry.
import { isInactive, kindOf, listAgentStateOf, localStateOf, stateOf } from './status'
import type {
  ApiSession,
  ListAgentRow,
  LocalAgent,
  NeedsYou,
  RepoGroup,
  Registry,
  SessionHeader,
  SessionKind,
  SessionRow,
} from '../types'

export type MergeInput = {
  /** null when the API call failed: the rows then come from listAgents, agents and the registry. */
  cloud: ApiSession[] | null
  agents: LocalAgent[]
  listAgents: ListAgentRow[]
  registry: Registry
  /** What each API session's recent events show (held message, permission wait), by session id; optional. */
  signals?: Record<string, NeedsYou>
}

/** The branch of a session's repository; a cloud session reports its own under the key '' (observed 2026-11-01). */
function branchOf(session: ApiSession, repo: string | null): string | null {
  const key = repo ?? ''
  const worktree = session.worktrees[key] ?? session.worktrees['']
  return session.branches[key] ?? session.branches[''] ?? worktree?.branch ?? null
}

const sameRepo = (a: string | null, b: string | null): boolean =>
  a === null || b === null ? a === b : a.toLowerCase() === b.toLowerCase()

const time = (iso: string | null): number => {
  const ms = iso === null ? NaN : Date.parse(iso)
  return Number.isNaN(ms) ? -Infinity : ms
}

const newest = (a: string | null, b: string | null): string | null => (time(b) > time(a) ? b : a)

/** The mirror's checkout for a repository (keys compared without case), or null. */
function mirrorCheckout(registry: Registry, repo: string | null): string | null {
  if (repo === null) return null
  for (const [key, entry] of Object.entries(registry.mains)) {
    if (key.toLowerCase() === repo.toLowerCase() && entry.checkout) return entry.checkout
  }
  return null
}

/** The kit role of a session id: a mirror in mains, else a side or verify run. */
function roleOf(registry: Registry, id: string | null): SessionRow['role'] {
  if (id === null) return null
  for (const entry of Object.values(registry.mains)) if (entry.sessionId === id) return 'mirror'
  return registry.runs.find((run) => run.sessionId === id)?.role ?? null
}

/** Puts a local agent's facts on a row. */
function attach(row: SessionRow, agent: LocalAgent): void {
  row.localId = agent.id
  row.localSessionId = agent.sessionId
  row.checkout = row.checkout ?? agent.cwd
  if (!row.from.includes('agents')) row.from.push('agents')
}

/** A row from nothing but a local agent. */
function agentRow(agent: LocalAgent): SessionRow {
  return {
    key: `local:${agent.id}`,
    id: null,
    localId: agent.id,
    localSessionId: agent.sessionId,
    title: agent.name ?? agent.id,
    repo: agent.repo,
    kind: 'background',
    state: localStateOf(agent),
    branch: null,
    activeAt: agent.startedAt,
    unread: false,
    context: null,
    model: null,
    effort: null,
    role: null,
    checkout: agent.cwd,
    from: ['agents'],
  }
}

/** A row from one API session; `signals` are what its events showed when they were last read. */
function apiRow(session: ApiSession, signals?: Record<string, NeedsYou>): SessionRow {
  const repo = session.repos[0] ?? null
  return {
    key: `api:${session.id}`,
    id: session.id,
    localId: null,
    localSessionId: null,
    title: session.title,
    repo,
    kind: kindOf(session.environmentKind),
    state: stateOf(session, signals?.[session.id]),
    branch: branchOf(session, repo),
    activeAt: newest(session.lastEventAt, session.updatedAt),
    unread: session.unread,
    context: session.context,
    model: session.model,
    effort: session.effort,
    role: null,
    checkout: null,
    from: ['api'],
  }
}

/** A row from one ListAgents line (the fallback list). */
function listRow(row: ListAgentRow): SessionRow {
  const kind: SessionKind = row.kind === 'cloud' ? 'cloud' : row.kind === 'bg' ? 'background' : 'other'
  return {
    key: `list:${row.ref ?? row.name}`,
    id: null,
    localId: null,
    localSessionId: null,
    title: row.name,
    repo: null,
    kind: row.kind === 'remote-control' ? 'remote' : kind,
    state: listAgentStateOf(row),
    branch: null,
    activeAt: null,
    unread: false,
    context: null,
    model: null,
    effort: null,
    role: null,
    checkout: null,
    from: ['list-agents'],
  }
}

/** Every row once (a bridge session and its agents row merge on name and repository), newest activity first. */
export function mergeRows(input: MergeInput): SessionRow[] {
  const rows: SessionRow[] =
    input.cloud === null ? input.listAgents.map(listRow) : input.cloud.map((session) => apiRow(session, input.signals))
  const merged = new Set<string>()
  const matches = (row: SessionRow, agent: LocalAgent): boolean =>
    agent.name !== null && row.title === agent.name && sameRepo(row.repo, agent.repo)
  for (const agent of input.agents) {
    const into = rows.find((row) => {
      if (merged.has(row.key) || row.localId !== null) return false
      if (input.cloud === null) return (row.kind === 'background' || row.kind === 'remote') && matches(row, agent)
      return row.kind === 'remote' && row.id !== null && matches(row, agent)
    })
    if (into) {
      merged.add(into.key)
      attach(into, agent)
      into.repo = into.repo ?? agent.repo
    } else {
      rows.push(agentRow(agent))
    }
  }
  for (const row of rows) {
    const id = row.id ?? (row.key.startsWith('list:') ? row.key.slice(5) : row.localSessionId)
    const role = roleOf(input.registry, id)
    if (role !== null) {
      row.role = role
      if (!row.from.includes('registry')) row.from.push('registry')
    }
    const checkout = mirrorCheckout(input.registry, row.repo)
    if (checkout !== null) {
      row.checkout = checkout
      if (!row.from.includes('registry')) row.from.push('registry')
    }
  }
  return rows.sort((a, b) => time(b.activeAt) - time(a.activeAt) || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0))
}

/** Rows -> groups: inactive rows only with showArchived; groups by newest activity, "Other" (repo null) last. */
export function groupRows(rows: readonly SessionRow[], showArchived: boolean): RepoGroup[] {
  const groups = new Map<string | null, SessionRow[]>()
  for (const row of rows) {
    if (isInactive(row) && !showArchived) continue
    const group = groups.get(row.repo)
    if (group) group.push(row)
    else groups.set(row.repo, [row])
  }
  const latest = (group: RepoGroup): number => Math.max(...group.rows.map((row) => time(row.activeAt)))
  return [...groups].map(([repo, list]) => ({ repo, rows: list })).sort((a, b) => {
    if ((a.repo === null) !== (b.repo === null)) return a.repo === null ? 1 : -1
    return latest(b) - latest(a) || String(a.repo).localeCompare(String(b.repo))
  })
}

/** The open session's header from its detail (or list) record and its row. */
export function headerOf(session: ApiSession | null, row: SessionRow): SessionHeader {
  if (session === null) {
    return {
      id: row.id ?? row.key,
      title: row.title,
      repo: row.repo,
      kind: row.kind,
      state: row.state,
      branch: row.branch,
      worktree: null,
      model: row.model,
      effort: row.effort,
      permissionMode: null,
      context: row.context,
    }
  }
  const repo = session.repos[0] ?? row.repo
  return {
    id: session.id,
    title: session.title || row.title,
    repo,
    kind: kindOf(session.environmentKind),
    state: stateOf(session),
    branch: branchOf(session, repo) ?? row.branch,
    worktree: session.worktrees[repo ?? ''] ?? session.worktrees[''] ?? null,
    model: session.model ?? row.model,
    effort: session.effort ?? row.effort,
    permissionMode: session.permissionMode,
    context: session.context ?? row.context,
  }
}
