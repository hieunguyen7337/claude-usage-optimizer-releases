// The sessions mod's contract: the data every module passes around, and the values it keeps in $.state.
// Write it first, then the modules: hooks/api.ts, status.ts, poll.ts (the sessions API and the status model),
// transcript.ts (events to lines), local.ts and merge.ts (local sessions, the kit registry, one list),
// actions.ts (what a key does), view.tsx and register.tsx (the pane).

/** The app-like state of one session: the six the Claude app's sidebar shows. */
export type SessionState = 'working' | 'needs-you' | 'review-ready' | 'idle' | 'offline' | 'archived'

/**
 * Where a session runs. cloud: `environment_kind` anthropic_cloud. remote: `bridge`, a local session connected
 * through Remote Control. background: a local `claude agents` session the API does not list. other: any other kind.
 */
export type SessionKind = 'cloud' | 'remote' | 'background' | 'other'

/** What the kit's registry says a session is: a repository's mirror, a side session or a verify run. */
export type KitRole = 'mirror' | 'side' | 'verify'

export type ContextUse = { used: number; max: number }

/** A repository's worktree as the API reports it (`external_metadata.worktree_state[owner/repo]`). */
export type WorktreeState = {
  branch: string | null
  head: string | null
  isDirty: boolean | null
  unpushed: number | null
  upstreamExists: boolean | null
}

/** One session from `GET /v1/code/sessions` or `/v1/code/sessions/{id}`, unknown fields dropped, missing ones null. */
export type ApiSession = {
  id: string
  title: string
  /** `active` | `archived` | anything else, as sent. */
  status: string
  /** `working` | `review_ready` | `completed` | ..., as sent; '' when missing. */
  statusBucket: string
  /** `running` | `idle` | `WORKER_STATUS_UNSPECIFIED` | ..., as sent; '' when missing. */
  workerStatus: string
  /** `connected` | `disconnected` | ..., as sent; '' when missing. */
  connectionStatus: string
  /** `anthropic_cloud` | `bridge` | ..., as sent; '' when missing. */
  environmentKind: string
  unread: boolean
  updatedAt: string | null
  lastEventAt: string | null
  createdAt: string | null
  /** `external_metadata.model`, else `config.model`. */
  model: string | null
  /** `external_metadata.effort_level`, else `config.effort_level`. */
  effort: string | null
  /** `config.origin`, e.g. claude_code_cli. */
  origin: string | null
  /** owner/repo of each git source, then of each `current_branches` or `worktree_state` key that looks like one; no duplicates. */
  repos: string[]
  /** `external_metadata.current_branches`: owner/repo -> branch. */
  branches: Record<string, string>
  /** `external_metadata.worktree_state`: owner/repo -> its state. */
  worktrees: Record<string, WorktreeState>
  context: ContextUse | null
  /** `external_metadata.permission_mode`, else the top-level `permission_mode` (the detail call). */
  permissionMode: string | null
  /** How many entries `requires_action_details_list` holds (detail call; 0 when missing): above 0 = needs you. */
  requiresAction: number
}

/** One event from `GET /v1/code/sessions/{id}/events`. */
export type ApiEvent = {
  id: string
  /** `assistant` | `user` | `result` | `system` | `control_request` | ..., as sent. */
  type: string
  /** `sequence_num` as a number (the API sends a string). */
  seq: number
  at: string | null
  source: 'worker' | 'client' | 'other'
  /** The event's payload as sent: untrusted, read with care, never passed to the model. */
  payload: unknown
}

/** What a sessions API call came to. status is the HTTP status, null when the request did not complete. */
/** A failure's `code` is the refusal's `error.resource`, with `/sub_reason` when it has one (`untrusted_device/bound_unattested`). */
export type Fetched<T> = { ok: true; value: T } | { ok: false; status: number | null; reason: string; code?: string }

/** One row of `claude agents --json`. */
export type LocalAgent = {
  id: string
  pid: number | null
  cwd: string | null
  name: string | null
  sessionId: string | null
  kind: string | null
  /** e.g. waiting */
  status: string | null
  waitingFor: string | null
  /** working | done | stopped */
  state: string | null
  startedAt: string | null
  /** owner/repo from `git -C <cwd> remote get-url origin`, null when unknown. */
  repo: string | null
}

/** One row of the ListAgents tool's text: `Name [ref] - cloud|bg|Remote Control - running|...`, - a middle dot. */
export type ListAgentRow = {
  name: string
  ref: string | null
  kind: 'cloud' | 'bg' | 'remote-control' | 'other'
  status: 'running' | 'idle' | 'waiting' | 'offline' | 'other'
}

/** The kit's registry: mirrors from mains.json, side and verify cloud runs from the lane run records. */
export type Registry = {
  /** owner/repo -> its mirror. */
  mains: Record<string, { sessionId: string | null; url: string | null; checkout: string | null }>
  /** Cloud runs `lane` started, each with the session it ran in. */
  runs: Array<{ sessionId: string; role: 'side' | 'verify'; repo: string | null; runId: string }>
}

/** One row of the Sessions pane's list: a session as the app's sidebar shows it. */
export type SessionRow = {
  /** Stable across polls: `api:<id>` for an API session, `local:<agents id>` for a local-only one. */
  key: string
  /** The sessions API id; null for a local-only row. */
  id: string | null
  /** The `claude agents` id, when the session is also a local background session. */
  localId: string | null
  /** The `claude agents` sessionId, for $.session.send. */
  localSessionId: string | null
  title: string
  /** owner/repo; null groups the row under "Other". */
  repo: string | null
  kind: SessionKind
  state: SessionState
  branch: string | null
  /** The newest of last_event_at and updated_at (ISO), or the local startedAt. */
  activeAt: string | null
  unread: boolean
  context: ContextUse | null
  model: string | null
  effort: string | null
  role: KitRole | null
  /** A local checkout of the repository: the registry's `checkout`, else a local agent's cwd. */
  checkout: string | null
  /** Where the row's facts came from. */
  from: Array<'api' | 'agents' | 'list-agents' | 'registry'>
}

/** The rows of one repository, as the list shows them. repo null = "Other". */
export type RepoGroup = { repo: string | null; rows: SessionRow[] }

/** The open session's header. */
export type SessionHeader = {
  id: string
  title: string
  repo: string | null
  kind: SessionKind
  state: SessionState
  branch: string | null
  worktree: WorktreeState | null
  model: string | null
  effort: string | null
  permissionMode: string | null
  context: ContextUse | null
}

/** One folded line of a transcript. Every text in it is cleaned (no control characters) and is data, not a prompt. */
export type TranscriptLine = {
  /** Stable: the event id, or `tool:<tool_use_id>` for a call. */
  key: string
  seq: number
  at: string | null
  /** prompt: a message someone sent. text: Claude's words. tool: one call. result: a turn's end. notice: a system
   * line worth a row (title changed, permission check, notification). held: a peer message held for the owner. */
  kind: 'prompt' | 'text' | 'tool' | 'result' | 'notice' | 'held'
  text: string
  /** For kind tool: the call, its one-line label and how it ended so far. */
  tool?: { useId: string; name: string; label: string; status: 'running' | 'ok' | 'error' }
  /** For kind tool: a subagent's lines under the call that started it (events whose parent_tool_use_id is its id). */
  children?: TranscriptLine[]
}

/** What the open session's events say needs the owner: a held peer message, a permission wait. */
export type NeedsYou = { held: boolean; permissionWait: boolean }

/** How the list was last read. fallback: the API failed and the rows come from ListAgents and the registry. */
export type ListStatus = {
  status: 'idle' | 'loading' | 'ready' | 'fallback' | 'error'
  /** Shown under the list: the reason for fallback or error, or "showing the newest N" when more may exist. Never holds the auth handle. */
  note?: string
  /** When it was last read (ISO). */
  at?: string
}

/** The open session: its header, its folded transcript and how they were last read. */
export type OpenSession = {
  key: string
  header: SessionHeader | null
  lines: TranscriptLine[]
  needsYou: NeedsYou
  /** The highest sequence number seen. */
  newestSeq: number
  /** The cursor for the next older page, null when there is none. */
  olderCursor: string | null
  /** True once an older page was read: the 4 s poll then keeps olderCursor instead of replacing it. */
  olderRead?: boolean
  status: 'loading' | 'ready' | 'error'
  note?: string
  /** For a local background session: the text `claude logs <id>` printed, cleaned. */
  logText?: string
}

/** The last action's outcome, at the foot of the pane: one line, or several for branch-diff (at most 12 are drawn). */
export type ActionNotice = { tone: 'ok' | 'error' | 'info'; text: string; at: string }

/** An action a key in the session view runs. The later ones fall back to the app link for now. */
export type ActionId =
  | 'send'
  | 'open-app'
  | 'copy-resume'
  | 'branch-diff'
  | 'refresh'
  | 'older'
  | 'interrupt'
  | 'approve-held'
  | 'set-permission-mode'
  | 'archive'

declare module 'claude-code' {
  interface PluginState {
    sessions: {
      /** Every row, newest activity first; grouped by view.tsx. */
      rows: Shaped<SessionRow[]>
      list: ListStatus
      showArchived: boolean
      /** The key of the row holding the focus ring, or null. */
      focused: string | null
      /** The open session, or null while the list shows. */
      open: Shaped<OpenSession | null>
      /** What the composer holds. */
      draft: string
      notice: ActionNotice | null
      /** Whether the pane is on screen: polling runs only while it is. */
      paneOpen: boolean
      /** Whether the last `.` could not place the pane, so the footer hint says to press Enter. */
      needsEnter: boolean
      /** Repository groups folded shut, by repo (Other: ''). */
      foldedGroup: StateFamily<boolean>
      /** Tool calls opened to show their subagent lines, by line key. */
      openCall: StateFamily<boolean>
    }
  }
}
