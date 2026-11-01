// Pure helpers for the mobile view: no `$`, so the tests call them directly.

export type CallLike = {
  tool: string
  input: unknown
  isRunning?: boolean
  isErrored?: boolean
  isInterrupted?: boolean
  output?: unknown
}

export type Tone = 'ok' | 'running' | 'error' | 'warn'

export type Mark = { text: string; tone: Tone }

export type PathContext = { cwd: string; home: string }

/** Terminal cells a code point takes: 0 for combining marks, 2 for wide CJK and emoji. */
function cellsOf(code: number): number {
  if ((code >= 0x0300 && code <= 0x036f) || (code >= 0x200b && code <= 0x200f) || code === 0xfe0f) {
    return 0
  }
  if (
    (code >= 0x1100 && code <= 0x115f) ||
    (code >= 0x2e80 && code <= 0xa4cf) ||
    (code >= 0xac00 && code <= 0xd7a3) ||
    (code >= 0xf900 && code <= 0xfaff) ||
    (code >= 0xfe30 && code <= 0xfe4f) ||
    (code >= 0xff00 && code <= 0xff60) ||
    (code >= 0xffe0 && code <= 0xffe6) ||
    (code >= 0x1f300 && code <= 0x1faff) ||
    (code >= 0x20000 && code <= 0x3fffd)
  ) {
    return 2
  }
  return 1
}

export function cellWidth(text: string): number {
  let cells = 0
  for (const char of text) {
    cells += cellsOf(char.codePointAt(0) ?? 0)
  }
  return cells
}

/** Cuts `text` to at most `max` cells, ending with `…` when it was cut. */
export function truncateCells(text: string, max: number): string {
  if (max <= 0) {
    return ''
  }
  if (cellWidth(text) <= max) {
    return text
  }
  let out = ''
  let cells = 0
  for (const char of text) {
    const width = cellsOf(char.codePointAt(0) ?? 0)
    if (cells + width > max - 1) {
      break
    }
    out += char
    cells += width
  }
  return out + '\u2026'
}

const oneLine = (text: string) => text.replace(/\s+/g, ' ').trim()

const firstLine = (text: string) => {
  const lines = text.split(/\r?\n/).map(line => line.trim()).filter(line => line !== '')
  return { line: lines[0] ?? '', isMore: lines.length > 1 }
}

/** Forward slashes; on Windows, a Git Bash `/c/...` path as `C:/...` (elsewhere `/c/` is a folder). */
function normalizePath(path: string, isWindows: boolean): string {
  const slashed = path.replace(/\\/g, '/')
  const bash = isWindows ? /^\/([a-zA-Z])\/(.*)$/.exec(slashed) : null
  return bash ? `${bash[1].toUpperCase()}:/${bash[2]}` : slashed
}

const isWindowsPath = (path: string) => /^[a-zA-Z]:\//.test(path)

/** Windows, judged by the session's native working directory or home (`C:\...`). */
const isWindowsSession = (context: PathContext) => /^[a-zA-Z]:[\\/]/.test(context.cwd) || /^[a-zA-Z]:[\\/]/.test(context.home)

function under(path: string, root: string, isWindows: boolean): string | null {
  if (root === '') {
    return null
  }
  const base = normalizePath(root, isWindows).replace(/\/+$/, '')
  const caseless = isWindowsPath(base)
  const left = caseless ? path.toLowerCase() : path
  const right = caseless ? base.toLowerCase() : base
  if (left === right) {
    return ''
  }
  return left.startsWith(right + '/') ? path.slice(base.length + 1) : null
}

/** A path relative to the working directory, else under `~/`, else as given. */
export function relPath(path: string, context: PathContext): string {
  const isWindows = isWindowsSession(context)
  const normal = normalizePath(path, isWindows)
  const inCwd = under(normal, context.cwd, isWindows)
  if (inCwd !== null) {
    return inCwd === '' ? '.' : inCwd
  }
  const inHome = under(normal, context.home, isWindows)
  if (inHome !== null) {
    return inHome === '' ? '~' : `~/${inHome}`
  }
  return normal
}

const str = (value: unknown): string => (typeof value === 'string' ? value : '')

const lineCount = (text: string) => (text === '' ? 0 : text.split(/\r?\n/).length)

const MCP = /^mcp__(.+?)__(.+)$/

/** The name a row shows for a tool: an MCP server's short name, else the tool. */
export function toolName(tool: string): string {
  const mcp = MCP.exec(tool)
  if (!mcp) {
    return tool
  }
  return mcp[1].replace(/^claude_ai_/, '').replace(/^plugin_/, '')
}

/** What one call did, in a few words: the Bash description, the file, the pattern. */
export function toolLabel(tool: string, rawInput: unknown, context: PathContext): string {
  const input = (rawInput !== null && typeof rawInput === 'object' ? rawInput : {}) as Record<string, unknown>
  const path = (value: unknown) => relPath(str(value), context)
  switch (tool) {
    case 'Bash':
    case 'PowerShell': {
      const description = oneLine(str(input.description))
      if (description !== '') {
        return description + (input.run_in_background === true ? ' \u00b7 background' : '')
      }
      const { line, isMore } = firstLine(str(input.command))
      return line + (isMore ? ' \u2026' : '')
    }
    case 'Read': {
      const offset = typeof input.offset === 'number' ? input.offset : undefined
      const limit = typeof input.limit === 'number' ? input.limit : undefined
      const range = offset !== undefined ? `:${offset}${limit !== undefined ? `-${offset + limit - 1}` : ''}` : ''
      return path(input.file_path) + range
    }
    case 'Edit': {
      const added = lineCount(str(input.new_string))
      const removed = lineCount(str(input.old_string))
      return `${path(input.file_path)}  +${added} \u2212${removed}${input.replace_all === true ? ' (all)' : ''}`
    }
    case 'MultiEdit': {
      const edits = Array.isArray(input.edits) ? (input.edits as Record<string, unknown>[]) : []
      const added = edits.reduce((sum, edit) => sum + lineCount(str(edit?.new_string)), 0)
      const removed = edits.reduce((sum, edit) => sum + lineCount(str(edit?.old_string)), 0)
      return `${path(input.file_path)}  +${added} \u2212${removed}`
    }
    case 'Write':
      return `${path(input.file_path)}  (${lineCount(str(input.content))} lines)`
    case 'NotebookEdit':
      return path(input.notebook_path)
    case 'Grep': {
      const where = str(input.path) !== '' ? ` in ${path(input.path)}` : ''
      const glob = str(input.glob) !== '' ? ` (${str(input.glob)})` : ''
      return `"${oneLine(str(input.pattern))}"${where}${glob}`
    }
    case 'Glob':
      return oneLine(str(input.pattern)) + (str(input.path) !== '' ? ` in ${path(input.path)}` : '')
    case 'WebFetch': {
      try {
        return new URL(str(input.url)).host
      } catch {
        return str(input.url)
      }
    }
    case 'WebSearch':
      return oneLine(str(input.query))
    case 'Agent':
    case 'Task':
      return oneLine(str(input.description)) + (input.run_in_background === true ? ' \u00b7 background' : '')
    case 'TaskCreate':
      return oneLine(str(input.subject))
    case 'TaskUpdate':
      return `#${str(input.taskId)}${str(input.status) !== '' ? ` ${str(input.status)}` : ''}`
    case 'TodoWrite':
      return `${Array.isArray(input.todos) ? input.todos.length : 0} items`
    case 'Skill':
      return str(input.skill)
    default: {
      const mcp = MCP.exec(tool)
      const first = Object.values(input).find(value => typeof value === 'string' && value.trim() !== '')
      const detail = typeof first === 'string' ? oneLine(first) : ''
      if (mcp) {
        return detail !== '' ? `${mcp[2]}: ${detail}` : mcp[2]
      }
      return detail
    }
  }
}

/** The text a tool result holds, for error lines: a string, or an object's stderr/stdout/text. */
function outputText(output: unknown): string {
  if (typeof output === 'string') {
    return output
  }
  if (output !== null && typeof output === 'object') {
    const record = output as Record<string, unknown>
    return str(record.stderr) || str(record.stdout) || str(record.text) || str(record.error)
  }
  return ''
}

/** Running, failed (with the exit code when there is one), interrupted, or nothing when it went fine. */
export function statusMark(call: CallLike): Mark {
  if (call.isInterrupted) {
    return { text: '\u2298 interrupted', tone: 'warn' }
  }
  if (call.isRunning) {
    return { text: '\u2026', tone: 'running' }
  }
  if (call.isErrored) {
    const text = outputText(call.output)
    const exit = /exit code (\d+)/i.exec(text)
    if (exit) {
      return { text: `\u2717 exit ${exit[1]}`, tone: 'error' }
    }
    const line = firstLine(text.replace(/^error:\s*/i, '')).line
    return { text: line !== '' ? `\u2717 ${truncateCells(line, 40)}` : '\u2717 failed', tone: 'error' }
  }
  return { text: '', tone: 'ok' }
}

export type Collapsed = { text: string; count: number; lines: number }

const FENCE_OPEN = /^( {0,8})(`{3,}|~{3,})(.*)$/

/**
 * Folds every fenced code block longer than `minLines` to one line naming its language and
 * size. A block still open at the end (a reply streaming in) is folded the same way.
 */
export function collapseCodeBlocks(text: string, options: { minLines: number }): Collapsed {
  const lines = text.split(/\r?\n/)
  const out: string[] = []
  let count = 0
  let hidden = 0
  let index = 0
  while (index < lines.length) {
    const open = FENCE_OPEN.exec(lines[index])
    const isOpening = open !== null && !(open[2][0] === '`' && open[3].includes('`'))
    if (!open || !isOpening) {
      out.push(lines[index])
      index += 1
      continue
    }
    const [, indent, fence, info] = open
    const close = new RegExp(`^ {0,8}${fence[0] === '`' ? '`' : '~'}{${fence.length},}\\s*$`)
    let end = index + 1
    while (end < lines.length && !close.test(lines[end])) {
      end += 1
    }
    const isClosed = end < lines.length
    const body = end - index - 1
    if (body > options.minLines) {
      const language = info.trim().split(/\s+/)[0] || 'code'
      out.push(`${indent}\u25b8 ${language} \u00b7 ${body} lines${isClosed ? ' hidden' : '\u2026'}`)
      count += 1
      hidden += body
    } else {
      out.push(...lines.slice(index, isClosed ? end + 1 : end))
    }
    index = isClosed ? end + 1 : end
  }
  return { text: out.join('\n'), count, lines: hidden }
}

const PASTED = /<pasted_content[^>]*>[\s\S]*?<\/pasted_content[^>]*>/g

/** A prompt's first line, a paste shown as `[pasted]` before the first typed line. */
export function promptTitle(text: string, max = 160): string {
  const lines = text
    .replace(PASTED, '\n[pasted]\n')
    .split(/\r?\n/)
    .map(line => oneLine(line))
    .filter(line => line !== '')
  let line = lines[0] ?? ''
  if (line === '[pasted]') {
    const typed = lines.slice(1).find(candidate => candidate !== '[pasted]') ?? ''
    line = `[pasted] ${typed}`.trim()
  }
  return truncateCells(line, max) || '[empty]'
}

/** HH:MM in local time for an ISO timestamp, or blanks. */
export function clockTime(stamp: string | null | undefined): string {
  if (!stamp) {
    return '     '
  }
  const moment = new Date(stamp)
  if (Number.isNaN(moment.getTime())) {
    return '     '
  }
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${pad(moment.getHours())}:${pad(moment.getMinutes())}`
}
