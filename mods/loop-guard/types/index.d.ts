// loop-guard keeps no plugin state. These are the shapes the hooks pass around;
// the counts themselves live in memory for the session (hooks/guard.ts).

/** What a tool result contributes to the failure check. A deny is not a failure. */
export type CallOutcome = {
  isError?: boolean
  deny?: string
  result?: unknown
  text?: string
}

/** One open turn's counts. `startedAt` is absent when no `turn.start` was seen. */
export type TurnState = {
  id: string
  agentId: string | undefined
  startedAt: number | undefined
  failures: Map<string, number>
  noted: Set<string>
  notes: number
  /** True when that slot failed. The guard keeps the last ten. */
  recent: boolean[]
  statusShown: boolean
}

/** Every open turn, and the durations of the turns that have finished. */
export type Session = {
  turns: Map<string, TurnState>
  byAgent: Map<string, string>
  mainId: string | undefined
  durations: number[]
  finished: Set<string>
}
