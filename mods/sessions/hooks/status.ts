// The status model: the API's buckets, a local agent's state and a ListAgents row, each to one app-like state.
import type { ApiSession, ListAgentRow, LocalAgent, NeedsYou, SessionKind, SessionState } from '../types'

/** What the list shows for each state, at most 12 cells. */
export const STATE_LABEL: Record<SessionState, string> = {
  working: 'working',
  'needs-you': 'needs you',
  'review-ready': 'review ready',
  idle: 'idle',
  offline: 'offline',
  archived: 'archived',
}

/** The status buckets that mean the session waits on its owner. */
export const NEEDS_YOU_BUCKETS: readonly string[] = ['blocked', 'needs_input', 'requires_action', 'failed']

/** An API session's state; `signals` are what its events show (held message, permission wait), when read. */
export function stateOf(session: ApiSession, signals?: Partial<NeedsYou>): SessionState {
  if (session.status === 'archived') return 'archived'
  if (
    signals?.held === true ||
    signals?.permissionWait === true ||
    session.requiresAction > 0 ||
    NEEDS_YOU_BUCKETS.includes(session.statusBucket)
  ) {
    return 'needs-you'
  }
  if (session.connectionStatus === 'disconnected') return 'offline'
  if (session.statusBucket === 'working' || session.workerStatus === 'running') return 'working'
  if (session.statusBucket === 'review_ready') return 'review-ready'
  return 'idle'
}

/**
 * Rows hidden until `a` shows them, as the Claude app hides them: archived sessions, and Remote Control sessions
 * whose local process has ended (the API keeps listing those as active, disconnected). A cloud session's VM sleeps
 * between turns and the session can still be resumed, so a disconnected cloud session stays listed.
 */
export function isInactive(row: { state: SessionState; kind: SessionKind }): boolean {
  return row.state === 'archived' || (row.state === 'offline' && row.kind !== 'cloud')
}

/** environment_kind -> kind. */
export function kindOf(environmentKind: string): SessionKind {
  if (environmentKind === 'anthropic_cloud') return 'cloud'
  if (environmentKind === 'bridge') return 'remote'
  return 'other'
}

/** A local `claude agents` row's state. */
export function localStateOf(agent: LocalAgent): SessionState {
  if (agent.status === 'waiting' || (typeof agent.waitingFor === 'string' && agent.waitingFor !== '')) {
    return 'needs-you'
  }
  if (agent.state === 'working') return 'working'
  return 'idle'
}

/** A ListAgents row's state (the fallback list). */
export function listAgentStateOf(row: ListAgentRow): SessionState {
  if (row.status === 'running') return 'working'
  if (row.status === 'waiting') return 'needs-you'
  if (row.status === 'offline') return 'offline'
  return 'idle'
}
