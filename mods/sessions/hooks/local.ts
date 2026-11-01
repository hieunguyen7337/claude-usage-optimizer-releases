// Local sessions and the kit registry: `claude agents --json`, the ListAgents tool, mains.json and lane run records.
import type { ListAgentRow, LocalAgent, Registry } from '../types'
import { repoFromUrl } from './api'

/** How many of the newest lane run folders readRegistry reads. */
const RUN_LIMIT = 200

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const text = (value: unknown): string | null => (typeof value === 'string' && value !== '' ? value : null)

/** Control, escape and bidi characters out of a name or state that is drawn; a tab becomes a space. */
function clean(value: string | null): string | null {
  if (value === null) return null
  const out = value
    .replace(/\u001b\][^\u0007\u001b]*(?:\u0007|\u001b\\)?/g, '')
    .replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, '')
    .replace(/\t/g, ' ')
    .replace(/[\u0000-\u001f\u007f-\u009f\u200e\u200f\u202a-\u202e\u2066-\u2069]/g, '')
  return out === '' ? null : out
}

/** The JSON value of `source`, or undefined when it does not parse. */
function parseJson(source: string): unknown {
  try {
    return JSON.parse(source)
  } catch {
    return undefined
  }
}

/** `claude agents --json` stdout -> rows (repo null: readAgents fills it). Tolerates an array or { agents: [...] }. */
export function parseAgentsJson(stdout: string): LocalAgent[] {
  const data = parseJson(stdout)
  const list = Array.isArray(data) ? data : isRecord(data) && Array.isArray(data.agents) ? data.agents : []
  const agents: LocalAgent[] = []
  for (const raw of list) {
    if (!isRecord(raw)) continue
    const id = text(raw.id) ?? text(raw.sessionId)
    if (id === null) continue
    agents.push({
      id,
      pid: typeof raw.pid === 'number' ? raw.pid : null,
      cwd: text(raw.cwd),
      name: clean(text(raw.name)),
      sessionId: text(raw.sessionId),
      kind: clean(text(raw.kind)),
      status: clean(text(raw.status)),
      waitingFor: clean(text(raw.waitingFor)),
      state: clean(text(raw.state)),
      startedAt: text(raw.startedAt),
      repo: null,
    })
  }
  return agents
}

/** The kind column of a ListAgents row. */
function listKind(word: string): ListAgentRow['kind'] {
  const kind = word.toLowerCase()
  if (kind === 'cloud') return 'cloud'
  if (kind === 'bg') return 'bg'
  if (kind === 'remote control' || kind === 'remote-control') return 'remote-control'
  return 'other'
}

/** The status column of a ListAgents row. */
function listStatus(word: string): ListAgentRow['status'] {
  const status = word.toLowerCase()
  if (status === 'running' || status === 'idle' || status === 'waiting' || status === 'offline') return status
  return 'other'
}

/** The ListAgents tool's text -> rows; lines that do not parse are skipped. */
export function parseListAgents(source: string): ListAgentRow[] {
  const rows: ListAgentRow[] = []
  for (const line of source.split(/\r?\n/)) {
    const parts = line.replace(/^\s*[-*]\s+/, '').split('\u00b7').map((part) => part.trim())
    if (parts.length < 3) continue
    const status = parts[parts.length - 1] ?? ''
    const kind = parts[parts.length - 2] ?? ''
    const head = parts.slice(0, -2).join(' \u00b7 ')
    const found = /^(.*?)\s*\[([^\]]*)\]$/.exec(head)
    const name = clean((found ? found[1] : head) ?? '') ?? ''
    if (name === '' || kind === '' || status === '') continue
    rows.push({ name, ref: found && found[2] ? found[2] : null, kind: listKind(kind), status: listStatus(status) })
  }
  return rows
}

/** mains.json text -> Registry['mains']; {} when it does not parse. */
export function parseMains(source: string): Registry['mains'] {
  const data = parseJson(source)
  const mains: Registry['mains'] = {}
  if (!isRecord(data) || !isRecord(data.mains)) return mains
  for (const [repo, entry] of Object.entries(data.mains)) {
    if (!isRecord(entry)) continue
    mains[repo] = { sessionId: text(entry.session_id), url: text(entry.url), checkout: text(entry.checkout) }
  }
  return mains
}

/** One lane run's meta.json text -> its registry entry, or null when it is no side or verify cloud run. */
export function parseRunMeta(source: string, runId: string): Registry['runs'][number] | null {
  const meta = parseJson(source)
  if (!isRecord(meta) || !isRecord(meta.cloud)) return null
  const sessionId = text(meta.cloud.session_id) ?? text(meta.session_id)
  if (sessionId === null) return null
  const verify = meta.verify === true
  const side = text(meta.cloud.side_reason) !== null
  if (!verify && !side) return null
  // meta.json holds no repository name: the title the API shows ("Kit side session - owner/repo") carries it.
  return { sessionId, role: verify ? 'verify' : 'side', repo: null, runId }
}

/** Runs `claude agents --json` and fills each row's repo from `git -C <cwd> remote get-url origin`; [] on failure. */
export async function readAgents($: any): Promise<LocalAgent[]> {
  try {
    const ran = await $.process.run(['claude', 'agents', '--json'])
    if (ran.exitCode !== 0) return []
    const agents = parseAgentsJson(String(ran.stdout))
    const byCwd = new Map<string, Promise<string | null>>()
    const repoOf = (cwd: string): Promise<string | null> => {
      let known = byCwd.get(cwd)
      if (!known) {
        known = (async () => {
          try {
            const git = await $.process.run(['git', '-C', cwd, 'remote', 'get-url', 'origin'])
            return git.exitCode === 0 ? repoFromUrl(String(git.stdout)) : null
          } catch {
            return null
          }
        })()
        byCwd.set(cwd, known)
      }
      return known
    }
    for (const agent of agents) {
      if (agent.cwd !== null) agent.repo = await repoOf(agent.cwd)
    }
    return agents
  } catch {
    return []
  }
}

/** Calls the ListAgents tool; [] on failure. */
export async function readListAgents($: any): Promise<ListAgentRow[]> {
  try {
    const called = await $.tool.call({ tool: 'ListAgents' })
    if (!called || called.isError || typeof called.text !== 'string') return []
    return parseListAgents(called.text)
  } catch {
    return []
  }
}

/** How long a registry read is reused: the list polls every 15 s, and the registry changes when a lane runs. */
const REGISTRY_TTL_MS = 60_000
let registryCache: { at: number; value: Registry } | null = null

/** Forgets the cached registry (tests, and `r`). */
export function resetRegistryCache(): void {
  registryCache = null
}

/**
 * Reads mains.json and each runs/<id>/meta.json under the lanes state directory ($LANES_STATE, else
 * ~/.local/state/lanes); an empty registry when they are missing. A read is reused for a minute.
 */
export async function readRegistry($: any): Promise<Registry> {
  const now = Date.now()
  if (registryCache !== null && now - registryCache.at < REGISTRY_TTL_MS) return registryCache.value
  const registry = await readRegistryNow($)
  registryCache = { at: now, value: registry }
  return registry
}

async function readRegistryNow($: any): Promise<Registry> {
  const registry: Registry = { mains: {}, runs: [] }
  try {
    const state = await $.env.get('LANES_STATE')
    const home = state ? null : ((await $.env.get('HOME')) ?? (await $.env.get('USERPROFILE')))
    if (!state && !home) return registry
    const trim = (path: unknown) => String(path).replace(/[\\/]+$/, '')
    const base = state ? trim(state) : `${trim(home)}/.local/state/lanes`
    try {
      registry.mains = parseMains(String(await $.fs.read(`${base}/mains.json`)))
    } catch {
      registry.mains = {}
    }
    try {
      const entries: Array<{ name: string; kind: string }> = await $.fs.list(`${base}/runs`)
      // Run folders start with their UTC stamp, so the name order is the age order.
      const names = entries
        .filter((entry) => entry.kind === 'dir')
        .map((entry) => entry.name)
        .sort()
        .reverse()
        .slice(0, RUN_LIMIT)
      for (const name of names) {
        try {
          const run = parseRunMeta(String(await $.fs.read(`${base}/runs/${name}/meta.json`)), name)
          if (run) registry.runs.push(run)
        } catch {
          // A run without a readable meta.json is skipped.
        }
      }
    } catch {
      registry.runs = []
    }
  } catch {
    return { mains: {}, runs: [] }
  }
  return registry
}
