// The Sessions pane's drawing: the list grouped by repository, and the session view. Pure: data in, tree out.
// listText and sessionText are the exact text lines the pane draws (the tests and the report read them); the tree
// builders lay the same lines out as Buttons and Texts, plus the composer and the action keys.
import type {
  ActionNotice,
  ContextUse,
  OpenSession,
  RepoGroup,
  SessionHeader,
  SessionRow,
  SessionState,
  TranscriptLine,
} from '../types'
import { isInactive, STATE_LABEL } from './status'

/** One glyph per state, single-cell on every terminal font the kit targets. */
export const STATE_GLYPH: Record<SessionState, string> = {
  working: '\u25cf',
  'needs-you': '!',
  'review-ready': '\u2713',
  idle: '\u25cb',
  offline: '\u00b7',
  archived: '\u2212',
}

/** The theme color each state's glyph and label draw in; undefined is the surface's own. */
export const STATE_COLOR: Record<SessionState, string | undefined> = {
  working: 'suggestion',
  'needs-you': 'warning',
  'review-ready': 'success',
  idle: undefined,
  offline: 'inactive',
  archived: 'inactive',
}

const KIND_SHORT: Record<SessionRow['kind'], string> = { cloud: 'cloud', remote: 'remote', background: 'local', other: '' }

const ELLIPSIS = '\u2026'
const DOT = ' \u00b7 '
const FOCUS_MARK = '\u276f '
const UNREAD = '\u2022'
/** The most rows a notice draws, its last saying how many more there were. */
export const NOTICE_ROWS = 12
/** The most rows one prompt or text line of the transcript draws. */
const TEXT_ROWS = 4
/** The most transcript or log lines the session view keeps on screen (the newest). */
const MAX_LINES = 300
/** The same cap in the expanded session view (the `e` key). */
const MAX_EXPANDED_LINES = 2000
/** The most rows a tool call's result body draws in the expanded view, its last saying how many more there are. */
export const RESULT_ROWS = 20

// ---------------------------------------------------------------------------------------------------------------
// Cells

/** Whether a code point takes two terminal cells (CJK, Hangul, fullwidth forms, most emoji). */
function isWide(code: number): boolean {
  return (
    (code >= 0x1100 && code <= 0x115f) ||
    (code >= 0x2e80 && code <= 0xa4cf) ||
    (code >= 0xac00 && code <= 0xd7a3) ||
    (code >= 0xf900 && code <= 0xfaff) ||
    (code >= 0xfe30 && code <= 0xfe4f) ||
    (code >= 0xff00 && code <= 0xff60) ||
    (code >= 0xffe0 && code <= 0xffe6) ||
    (code >= 0x1f300 && code <= 0x1faff) ||
    (code >= 0x20000 && code <= 0x3fffd)
  )
}

/** Whether a code point takes no cell (combining marks, zero-width joiners and selectors). */
function isZero(code: number): boolean {
  return (code >= 0x300 && code <= 0x36f) || (code >= 0x200b && code <= 0x200f) || (code >= 0xfe00 && code <= 0xfe0f)
}

/**
 * The one cleaner every drawn string passes through (fit calls it first): OSC and CSI escapes, C0 controls, DEL, C1
 * controls and bidi controls out; a tab becomes one space. Newlines go too, so split a multi-line text first.
 */
export function clean(text: string): string {
  return text
    .replace(/\u001b\][^\u0007\u001b]*(?:\u0007|\u001b\\)?/g, '')
    .replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, '')
    .replace(/\t/g, ' ')
    .replace(/[\u0000-\u001f\u007f-\u009f\u200e\u200f\u202a-\u202e\u2066-\u2069]/g, '')
}

/** How many terminal cells a text takes (of the cleaned text). */
export function cells(text: string): number {
  let n = 0
  for (const ch of clean(text)) {
    const code = ch.codePointAt(0) ?? 0
    n += isZero(code) ? 0 : isWide(code) ? 2 : 1
  }
  return n
}

/** The text cut to at most `width` cells, an ellipsis marking the cut. */
export function fit(raw: string, width: number): string {
  if (width <= 0) {
    return ''
  }
  const text = clean(raw)
  if (cells(text) <= width) {
    return text
  }
  let out = ''
  let used = 0
  for (const ch of text) {
    const code = ch.codePointAt(0) ?? 0
    const w = isZero(code) ? 0 : isWide(code) ? 2 : 1
    if (used + w > width - 1) {
      break
    }
    out += ch
    used += w
  }
  return out + ELLIPSIS
}

/** The text cut to `width` cells, then padded with spaces to exactly that many. */
function pad(text: string, width: number): string {
  const cut = fit(text, width)
  return cut + ' '.repeat(Math.max(0, width - cells(cut)))
}

/** Control characters (C0 but newline and tab, DEL, C1), ANSI escapes and bidi overrides out of a drawn text. */
export function strip(text: string): string {
  return text
    .replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, '')
    .replace(/[\u0000-\u0008\u000b-\u001f\u007f-\u009f\u200e\u200f\u202a-\u202e\u2066-\u2069]/g, '')
}

/** One line of a text: control characters out, newlines and tabs become spaces, runs of spaces one. */
function oneLine(text: string): string {
  return strip(text).replace(/[\r\n\t]+/g, ' ').replace(/ {2,}/g, ' ').trim()
}

// ---------------------------------------------------------------------------------------------------------------
// Facts

/** `3m`, `2h`, `4d` since an ISO time; `-` when unknown. */
export function ageText(at: string | null, now: number): string {
  const then = at === null ? NaN : Date.parse(at)
  if (!Number.isFinite(then)) {
    return '-'
  }
  const seconds = Math.max(0, Math.floor((now - then) / 1000))
  if (seconds < 60) {
    return `${seconds}s`
  }
  if (seconds < 3600) {
    return `${Math.floor(seconds / 60)}m`
  }
  if (seconds < 86400) {
    return `${Math.floor(seconds / 3600)}h`
  }
  return `${Math.floor(seconds / 86400)}d`
}

/** `76%` of the context window; '' when unknown. */
export function contextText(context: ContextUse | null): string {
  if (context === null || !(context.max > 0)) {
    return ''
  }
  return `${Math.round((context.used / context.max) * 100)}%`
}

/** `claude-opus-5-5` -> `opus`; another id loses its `claude-` and is cut to 10 cells. */
export function modelShort(model: string | null): string {
  if (model === null || model === '') {
    return ''
  }
  const family = /(opus|sonnet|haiku|fable)/i.exec(model)
  return family?.[1] !== undefined ? family[1].toLowerCase() : fit(model.replace(/^claude-/, ''), 10)
}

/** `opus xhigh`, `opus`, or ''. */
export function modelEffort(model: string | null, effort: string | null): string {
  return [modelShort(model), effort ?? ''].filter(part => part !== '').join(' ')
}

// ---------------------------------------------------------------------------------------------------------------
// The list

export type ListOptions = {
  /** Archived rows are drawn only with this. */
  showArchived?: boolean
  /** Whether a group is folded shut, by repo (Other: ''). */
  isFolded?: (repo: string) => boolean
}

/** One drawn line of the list: a group's header, a row, or the empty list's line. */
export type ListEntry =
  | { kind: 'group'; key: string; repo: string; text: string; isFolded: boolean }
  | { kind: 'row'; key: string; row: SessionRow; text: string; lines: string[]; isFocused: boolean }
  | { kind: 'empty'; key: string; text: string }

/** A group's header: `owner/repo (n)` or `Other (n)`, after a fold mark. */
export function groupText(repo: string | null, count: number, isFolded: boolean, width: number): string {
  const name = repo !== null && width < 80 ? repo.slice(repo.lastIndexOf('/') + 1) : repo ?? 'Other'
  return fit(`${isFolded ? '\u25b8' : '\u25be'} ${name} (${count})`, width)
}

/**
 * One row: focus mark, state glyph and label, unread dot, title, then kind, branch, age, context, model and
 * effort, and the kit role. The title takes what the facts leave, at least 12 cells or 40% of the room.
 */
export function rowText(row: SessionRow, width: number, now: number, isFocused: boolean): string {
  const left = `${isFocused ? FOCUS_MARK : '  '}${STATE_GLYPH[row.state]} ${pad(STATE_LABEL[row.state], 12)} ${
    row.unread ? UNREAD : ' '
  } `
  const age = ageText(row.activeAt, now)
  const facts = [
    KIND_SHORT[row.kind],
    row.branch === null ? '' : fit(row.branch, 18),
    age === '-' ? '' : age,
    contextText(row.context),
    modelEffort(row.model, row.effort),
    row.role ?? '',
  ]
    .filter(part => part !== '')
    .join(' ')
  const room = width - cells(left) - 2
  const titleWidth = Math.max(12, Math.floor(room * 0.4), room - cells(facts))
  const title = oneLine(row.title) || '(untitled)'
  const factsShown = fit(facts, room - titleWidth)
  const line = factsShown === '' ? left + fit(title, titleWidth) : `${left}${pad(title, titleWidth)}  ${factsShown}`
  return fit(line, width)
}

/** A list row's lines: a compact single line at 100 cells, otherwise title and facts on separate lines. */
export function rowLines(row: SessionRow, width: number, now: number, isFocused: boolean): string[] {
  if (width >= 100) return [rowText(row, width, now, isFocused)]
  const title = oneLine(row.title) || '(untitled)'
  const first = `${isFocused ? FOCUS_MARK : '  '}${STATE_GLYPH[row.state]} ${row.unread ? UNREAD : ' '} ${title}`
  const age = ageText(row.activeAt, now)
  const facts = [
    STATE_LABEL[row.state],
    KIND_SHORT[row.kind],
    row.role ?? '',
    row.branch === null ? '' : fit(row.branch, 24),
    age === '-' ? '' : age,
    contextText(row.context),
    modelEffort(row.model, row.effort),
  ]
    .filter(part => part !== '')
    .join(DOT)
  return [fit(first, width), fit(`    ${facts}`, width)]
}

/** The order the summary counts states in: what needs the owner first. */
const SUMMARY_ORDER: readonly SessionState[] = ['needs-you', 'working', 'review-ready', 'idle', 'offline', 'archived']

/** Counts all visible rows, including rows in folded groups: the total, then each state present, needs-you first. */
export function summaryText(groups: readonly RepoGroup[], showArchived: boolean, width: number): string {
  const rows = groups.flatMap(group => group.rows).filter(row => showArchived || !isInactive(row))
  const parts = [`${rows.length} ${rows.length === 1 ? 'session' : 'sessions'}`]
  for (const state of SUMMARY_ORDER) {
    const count = rows.filter(row => row.state === state).length
    if (count > 0) parts.push(`${count} ${STATE_LABEL[state]}`)
  }
  return fit(parts.join(DOT), width)
}

/** Packs dot-separated parts into lines, cutting only a part that cannot fit by itself. */
export function wrapParts(text: string, width: number): string[] {
  const lines: string[] = []
  let line = ''
  for (const part of text.split(DOT)) {
    const next = line === '' ? part : `${line}${DOT}${part}`
    if (line !== '' && cells(next) > width) {
      lines.push(fit(line, width))
      line = part
    } else {
      line = next
    }
  }
  lines.push(fit(line, width))
  return lines
}

/**
 * The groups as the list draws them: archived rows only with showArchived, empty groups left out, "Other"
 * last (the rest in the order given), a folded group's rows left out.
 */
export function listEntries(
  groups: readonly RepoGroup[],
  width: number,
  now: number,
  focused: string | null,
  options: ListOptions = {},
): ListEntry[] {
  const shown = groups
    .map(group => ({
      repo: group.repo,
      rows: options.showArchived === true ? group.rows : group.rows.filter(row => !isInactive(row)),
    }))
    .filter(group => group.rows.length > 0)
  const ordered = [...shown.filter(group => group.repo !== null), ...shown.filter(group => group.repo === null)]
  if (ordered.length === 0) {
    return [{ kind: 'empty', key: 'empty', text: fit('No sessions.', width) }]
  }
  const entries: ListEntry[] = []
  for (const group of ordered) {
    const repo = group.repo ?? ''
    const isFolded = options.isFolded?.(repo) === true
    entries.push({
      kind: 'group',
      key: `group:${repo}`,
      repo,
      text: groupText(group.repo, group.rows.length, isFolded, width),
      isFolded,
    })
    if (!isFolded) {
      for (const row of group.rows) {
        const isFocused = row.key === focused
        const lines = rowLines(row, width, now, isFocused)
        entries.push({ kind: 'row', key: `row:${row.key}`, row, text: lines[0] ?? '', lines, isFocused })
      }
    }
  }
  return entries
}

/** The list's text lines: group headers and rows, each at most `width` cells. */
export function listText(
  groups: RepoGroup[],
  width: number,
  now: number,
  focused: string | null,
  options: ListOptions = {},
): string[] {
  return listEntries(groups, width, now, focused, options).flatMap(entry =>
    entry.kind === 'row' ? entry.lines : [entry.text],
  )
}

// ---------------------------------------------------------------------------------------------------------------
// The session view

export type SessionOptions = {
  /** The last action's outcome. */
  notice?: ActionNotice | null
  /** Whether a tool call shows its subagent lines, by line key. */
  isOpened?: (key: string) => boolean
  /** Whether the transcript is expanded (the `e` key): every text unfolded, each call's result body under it. */
  expanded?: boolean
  /** The action keys, for the action row's text. */
  actions?: ReadonlyArray<{ id: string; key: string; label: string }>
}

/** The header's three lines: title; repository and branch; state, kind, model, permission mode and context. */
export function headerText(header: SessionHeader, width: number): string[] {
  const where: string[] = [header.repo ?? 'no repository']
  const tree = header.worktree
  const branch = header.branch ?? tree?.branch ?? null
  if (branch !== null) {
    const head = tree?.head ?? null
    where.push(head === null || head === '' ? branch : `${branch} @${head.slice(0, 7)}`)
  }
  if (tree?.isDirty === true) {
    where.push('dirty')
  } else if (tree?.isDirty === false) {
    where.push('clean')
  }
  if (tree?.unpushed !== null && tree?.unpushed !== undefined && tree.unpushed > 0) {
    where.push(`${tree.unpushed} unpushed`)
  }
  if (tree?.upstreamExists === false) {
    where.push('no upstream')
  }
  const context = contextText(header.context)
  const facts = [
    `${STATE_GLYPH[header.state]} ${STATE_LABEL[header.state]}`,
    KIND_SHORT[header.kind],
    modelEffort(header.model, header.effort),
    header.permissionMode === null ? '' : `mode ${header.permissionMode}`,
    context === '' ? '' : `ctx ${context}`,
  ].filter(part => part !== '')
  return [fit(oneLine(header.title) || '(untitled)', width), fit(where.join(DOT), width), fit(facts.join(DOT), width)]
}

const TOOL_GLYPH = { running: '\u2026', ok: '\u2713', error: '\u2717' } as const

/**
 * How the transcript is drawn. expanded (the `e` key): every text unfolded, each call's result body drawn under it.
 * latestText: the key of the newest assistant text, drawn in full even when the view is folded.
 */
export type Unfold = { expanded: boolean; latestText: string | null }
const FOLDED: Unfold = { expanded: false, latestText: null }

/** The key of the newest assistant text among a transcript's top-level lines (null when there is none). */
export function latestTextKey(lines: readonly TranscriptLine[]): string | null {
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index]
    if (line?.kind === 'text') {
      return line.key
    }
  }
  return null
}

/** The most transcript lines kept on screen: the newest MAX_LINES, or MAX_EXPANDED_LINES when expanded. */
const capOf = (expanded: boolean): number => (expanded ? MAX_EXPANDED_LINES : MAX_LINES)

/** A tool call's head row: fold mark, status glyph, name and label, and its subagent line count while it is shut. */
function callHead(line: TranscriptLine, width: number, indent: number, opened: boolean): string {
  const lead = ' '.repeat(indent)
  const room = width - indent
  const tool = line.tool
  const children = line.children ?? []
  const fold = children.length === 0 ? ' ' : opened ? '\u25be' : '\u25b8'
  const label = tool === undefined ? oneLine(line.text) : `${tool.name}  ${oneLine(tool.label)}`
  const more = children.length > 0 && !opened ? ` (+${children.length})` : ''
  const glyph = tool === undefined ? ' ' : TOOL_GLYPH[tool.status]
  return fit(`${lead}${fold}${glyph} ${fit(label, Math.max(1, room - 3 - cells(more)))}${more}`, width)
}

/** A tool call's result body, expanded only: its lines at indent + 4, RESULT_ROWS of them, then how many more. */
function resultRows(line: TranscriptLine, width: number, indent: number, unfold: Unfold): string[] {
  if (!unfold.expanded || line.kind !== 'tool' || line.result === undefined) {
    return []
  }
  const lead = ' '.repeat(indent + 4)
  const parts = strip(line.result)
    .split('\n')
    .map(part => part.replace(/\t/g, '  ').trimEnd())
    .filter(part => part.trim() !== '')
  const rows = parts.slice(0, RESULT_ROWS).map(part => fit(`${lead}${part}`, width))
  if (parts.length > RESULT_ROWS) {
    rows.push(fit(`${lead}${ELLIPSIS} +${parts.length - RESULT_ROWS} lines`, width))
  }
  return rows
}

/** The rows of one transcript line at an indent: a call's head and result body, its subagent lines under it when it is
 * opened; a text's rows, four unless it is unfolded (the newest assistant text, or every text when expanded). */
export function lineText(
  line: TranscriptLine,
  width: number,
  indent: number,
  isOpened: (key: string) => boolean = () => false,
  unfold: Unfold = FOLDED,
): string[] {
  const lead = ' '.repeat(indent)
  if (line.kind === 'tool') {
    const children = line.children ?? []
    const opened = children.length > 0 && isOpened(line.key)
    const rows = [callHead(line, width, indent, opened), ...resultRows(line, width, indent, unfold)]
    if (opened) {
      for (const child of children) {
        rows.push(...lineText(child, width, indent + 4, isOpened, unfold))
      }
    }
    return rows.map(row => fit(row, width))
  }
  if (line.kind === 'prompt' || line.kind === 'text') {
    const parts = strip(line.text)
      .split('\n')
      .map(part => part.replace(/\t/g, '  ').trimEnd())
      .filter(part => part.trim() !== '')
    const first = line.kind === 'prompt' ? FOCUS_MARK : '  '
    const unfolded = unfold.expanded || (line.kind === 'text' && line.key === unfold.latestText)
    const shown = unfolded ? parts : parts.slice(0, TEXT_ROWS)
    const rows = shown.map((part, index) => fit(`${lead}${index === 0 ? first : '  '}${part}`, width))
    if (parts.length > shown.length) {
      rows.push(fit(`${lead}  ${ELLIPSIS} +${parts.length - shown.length} lines`, width))
    }
    return rows.length > 0 ? rows : [fit(`${lead}${first}`, width)]
  }
  const prefix = line.kind === 'result' ? '\u2500\u2500 ' : line.kind === 'held' ? '! held: ' : '\u00b7 '
  return [fit(`${lead}${prefix}${oneLine(line.text)}`, width)]
}

/** A notice's rows: the tone glyph before its first line; at most NOTICE_ROWS, the last naming what is left. */
export function noticeText(notice: ActionNotice, width: number): string[] {
  const glyph = notice.tone === 'ok' ? '\u2713' : notice.tone === 'error' ? '\u2717' : '\u00b7'
  const parts = strip(notice.text).split('\n').map(part => part.replace(/\t/g, '  ').trimEnd())
  const rows = parts.map((part, index) => `${index === 0 ? `${glyph} ` : '  '}${part}`)
  if (rows.length > NOTICE_ROWS) {
    const kept = rows.slice(0, NOTICE_ROWS - 1)
    kept.push(`  ${ELLIPSIS} +${rows.length - kept.length} more`)
    return kept.map(row => fit(row, width))
  }
  return rows.map(row => fit(row, width))
}

/** The action row: `[o] open in app  [c] copy resume ...`, wrapped at `width`. */
export function actionsText(actions: ReadonlyArray<{ key: string; label: string }>, width: number): string[] {
  const rows: string[] = []
  let row = ''
  for (const action of actions) {
    const chip = action.key === '' ? `[ ${action.label} ]` : `[${action.key}] ${action.label}`
    if (row !== '' && cells(row) + 2 + cells(chip) > width) {
      rows.push(row)
      row = ''
    }
    row = row === '' ? chip : `${row}  ${chip}`
  }
  if (row !== '') {
    rows.push(row)
  }
  return rows.map(one => fit(one, width))
}

/**
 * The transcript part of the session view: its lines, the log text of a local session, or what it waits on. The
 * expanded view (the `e` key) unfolds every text, draws each call's result body and keeps MAX_EXPANDED_LINES.
 */
export function bodyText(
  open: OpenSession,
  width: number,
  isOpened?: (key: string) => boolean,
  expanded: boolean = false,
): string[] {
  const rows: string[] = []
  const cap = capOf(expanded)
  if (open.status === 'loading') {
    rows.push(fit('loading\u2026', width))
  } else if (open.status === 'error') {
    rows.push(fit(`! ${oneLine(open.note ?? 'could not read the session')}`, width))
  }
  if (open.logText !== undefined) {
    const parts = strip(open.logText).split('\n').map(part => part.replace(/\t/g, '  ').trimEnd())
    while (parts.length > 0 && parts[parts.length - 1] === '') {
      parts.pop()
    }
    for (const part of parts.slice(-cap)) {
      rows.push(fit(part, width))
    }
    if (parts.length === 0) {
      rows.push(fit('(the log is empty)', width))
    }
    return rows
  }
  const unfold: Unfold = { expanded, latestText: latestTextKey(open.lines) }
  for (const line of open.lines) {
    rows.push(...lineText(line, width, 0, isOpened, unfold))
  }
  if (open.lines.length === 0 && open.status === 'ready') {
    rows.push(fit('No events yet.', width))
  }
  return rows.slice(-cap)
}

/** The session view's text lines: header, transcript, notice and action row, each at most `width` cells. */
export function sessionText(open: OpenSession, width: number, now: number, options: SessionOptions = {}): string[] {
  const rows: string[] = []
  if (open.header !== null) {
    rows.push(...headerText(open.header, width))
  }
  rows.push(...bodyText(open, width, options.isOpened, options.expanded === true))
  if (options.notice !== undefined && options.notice !== null) {
    rows.push(...noticeText(options.notice, width))
  }
  if (options.actions !== undefined && options.actions.length > 0) {
    rows.push(...actionsText(options.actions, width))
  }
  return rows
}

// ---------------------------------------------------------------------------------------------------------------
// Trees: `ui` is `$.ui.resolve(e)`.

export type ListData = {
  groups: RepoGroup[]
  width: number
  now: number
  focused: string | null
  showArchived: boolean
  isFolded: (repo: string) => boolean
  /** The status line under the list. */
  status: string
}

export type ListHandlers = {
  openRow: (row: SessionRow) => unknown
  toggleGroup: (repo: string) => unknown
  toggleArchived: () => unknown
  refresh: () => unknown
}

/** The list view: a Button per group header (folds it) and per row (opens it), the status line and the keys. */
export function listTree(ui: any, data: ListData, handlers: ListHandlers) {
  const { Box, Button, Text } = ui
  const entries = listEntries(data.groups, data.width, data.now, data.focused, {
    showArchived: data.showArchived,
    isFolded: data.isFolded,
  })
  return (
    <Box flexDirection="column">
      {entries[0]?.kind === 'empty' ? '' : <Text bold>{summaryText(data.groups, data.showArchived, data.width)}</Text>}
      {entries.flatMap(entry => {
        if (entry.kind === 'empty') {
          return [<Text dimColor>{entry.text}</Text>]
        }
        if (entry.kind === 'group') {
          return [
            <Button key={entry.key} plain onPress={() => handlers.toggleGroup(entry.repo)}>
              <Text bold>{entry.text}</Text>
            </Button>,
          ]
        }
        const color = STATE_COLOR[entry.row.state]
        // A Button holds only strings and Text (the engine refuses a Box in it): the title line is the pressable row,
        // and the facts line is a dim Text under it.
        return [
          <Button key={entry.key} plain onPress={() => handlers.openRow(entry.row)}>
            <Text
              color={entry.isFocused ? 'suggestion' : color}
              bold={entry.isFocused}
              dimColor={!entry.isFocused && (entry.row.state === 'archived' || entry.row.state === 'offline')}
            >
              {entry.text}
            </Text>
          </Button>,
          ...entry.lines.slice(1).map(line => <Text dimColor>{line}</Text>),
        ]
      })}
      {wrapParts(data.status, data.width).map(line => <Text dimColor>{line}</Text>)}
      <Box flexDirection="row" flexWrap="wrap" columnGap={2}>
        <Button key="archived" hotkey="a" label={data.showArchived ? 'hide inactive' : 'show inactive'}
          onPress={() => handlers.toggleArchived()} />
        <Button key="refresh" hotkey="r" label="refresh" onPress={() => handlers.refresh()} />
      </Box>
    </Box>
  )
}

export type SessionData = {
  open: OpenSession
  width: number
  now: number
  notice: ActionNotice | null
  isOpened: (key: string) => boolean
  /** Whether the transcript is expanded (the `e` key). */
  expanded: boolean
  /** The action keys, `send` left out (the composer is its key); key '' draws a Button without a hotkey. */
  actions: ReadonlyArray<{ id: string; key: string; label: string }>
  draft: string
  /** False where the surface has no Input (mobile). */
  hasComposer: boolean
}

export type SessionHandlers = {
  back: () => unknown
  toggleCall: (key: string) => unknown
  action: (id: string) => unknown
  typed: (text: string) => unknown
  send: (text: string) => unknown
}

/**
 * One transcript line as a tree: a call with subagent lines is a Button that opens them; its result body (expanded)
 * sits under its head, and its subagent lines under the body.
 */
function lineTree(
  ui: any,
  line: TranscriptLine,
  data: SessionData,
  handlers: SessionHandlers,
  indent: number,
  unfold: Unfold,
): any {
  const { Box, Button, Text } = ui
  const dim = line.kind === 'result' || line.kind === 'notice'
  const color = line.kind === 'held' ? 'warning' : line.tool?.status === 'error' ? 'error' : undefined
  if (line.kind === 'tool') {
    const children = line.children ?? []
    const opened = children.length > 0 && data.isOpened(line.key)
    const head = callHead(line, data.width, indent, opened)
    const body = resultRows(line, data.width, indent, unfold)
    const headNode =
      children.length > 0 ? (
        <Button key={`call:${line.key}`} plain onPress={() => handlers.toggleCall(line.key)}>
          <Text color={color}>{head}</Text>
        </Button>
      ) : (
        <Text color={color}>{head}</Text>
      )
    return (
      <Box flexDirection="column">
        {headNode}
        {body.map(row => (
          <Text dimColor>{row}</Text>
        ))}
        {opened ? children.map(child => lineTree(ui, child, data, handlers, indent + 4, unfold)) : ''}
      </Box>
    )
  }
  const rows = lineText(line, data.width, indent, data.isOpened, unfold)
  return (
    <Box flexDirection="column">
      {rows.map(row => (
        <Text color={color} dimColor={dim} bold={line.kind === 'prompt'}>
          {row}
        </Text>
      ))}
    </Box>
  )
}

/** The session view: header, transcript, notice, composer and action keys. */
export function sessionTree(ui: any, data: SessionData, handlers: SessionHandlers) {
  const { Box, Button, Input, Text } = ui
  const open = data.open
  const header = open.header === null ? [] : headerText(open.header, data.width)
  const lines = open.logText === undefined ? open.lines.slice(-capOf(data.expanded)) : []
  const unfold: Unfold = { expanded: data.expanded, latestText: latestTextKey(open.lines) }
  const status = open.logText !== undefined || lines.length === 0 || open.status !== 'ready'
  const bodyRows = status ? bodyText({ ...open, lines: [] }, data.width, undefined, data.expanded) : []
  return (
    <Box flexDirection="column">
      {header.map((row, index) => (
        <Text bold={index === 0} dimColor={index === 1}>
          {row}
        </Text>
      ))}
      <Box flexDirection="column" marginTop={1}>
        {bodyRows.map(row => (
          <Text dimColor>{row}</Text>
        ))}
        {lines.map(line => lineTree(ui, line, data, handlers, 0, unfold))}
      </Box>
      {data.notice === null ? (
        ''
      ) : (
        <Box flexDirection="column" marginTop={1}>
          {noticeText(data.notice, data.width).map(row => (
            <Text color={data.notice?.tone === 'error' ? 'error' : data.notice?.tone === 'ok' ? 'success' : undefined}>
              {row}
            </Text>
          ))}
        </Box>
      )}
      {data.hasComposer ? (
        <Input
          key="composer"
          label={'\u203a'}
          placeholder="message (Tab here; Enter sends)"
          submitLabel="send"
          value={data.draft}
          onInput={(value: string) => handlers.typed(value)}
          onSubmit={(value: string) => handlers.send(value)}
        />
      ) : (
        ''
      )}
      <Box flexDirection="row" flexWrap="wrap" columnGap={2}>
        <Button key="back" label="back" onPress={() => handlers.back()} />
        {data.actions.map(action =>
          action.key === '' ? (
            <Button key={`act:${action.id}`} label={action.label} onPress={() => handlers.action(action.id)} />
          ) : (
            <Button
              key={`act:${action.id}`}
              hotkey={action.key}
              label={action.label}
              onPress={() => handlers.action(action.id)}
            />
          ),
        )}
      </Box>
    </Box>
  )
}
