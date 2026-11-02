// What a key in the session view does. Interrupt, approve and permission mode still open the session in the app;
// archive and delete use the sessions API (ACTIONS below is the one table to edit: each entry says how it runs).
import type { ActionId, ActionNotice, SessionRow } from '../types'
import { archiveSession, deleteSession } from './api'

/** Longest text `send` takes, in characters. */
export const SEND_MAX = 20000

/** Most lines a branch-diff notice holds (its header included). */
const DIFF_LINES = 12

/** `git fetch` may wait on the network: two minutes, not the default thirty seconds. */
const FETCH_TIMEOUT_MS = 120000
/** How long `claude -p --cloud` may take to hand a message over. */
const SEND_TIMEOUT_MS = 120000

type Notice = ActionNotice
// The engine reads every $ call from the source, so $ goes only to functions named at the call site: runAction
// dispatches with a switch, and the table holds no functions that take $.
type Spec = { key: string; label: string; offers: (row: SessionRow) => boolean; viaApp?: string }

/**
 * Strips ANSI escape sequences, C0/C1 control characters (keeping \n and \t) and bidi overrides, and caps the text.
 * Every process output and every title a notice shows goes through it.
 */
export function cleanOutput(text: string, max = 2000): string {
  const plain = text
    .replace(/\u001b\][^\u0007\u001b]*(?:\u0007|\u001b\\)?/g, '')
    .replace(/\u001b\[[0-?]*[ -/]*[@-~]/g, '')
    .replace(/\u001b[@-Z\\-_]/g, '')
    .replace(/\r\n?/g, '\n')
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/g, '')
  return plain.length > max ? `${plain.slice(0, max)}\u2026` : plain
}

/** A name or id safe as one argv element: non-empty, no leading dash, no whitespace or control characters. */
export function isSafeToken(value: string): boolean {
  return value.length > 0 && !value.startsWith('-') && !/[\s\u0000-\u001f\u007f-\u009f]/.test(value)
}

/**
 * A branch name safe to give git as one argv element: a plain ref name (git check-ref-format's rules), so it can never
 * read as an option or a refspec (no ':' or leading '+'), nor walk out of refs/ ('..').
 */
export function isSafeBranch(value: string): boolean {
  if (!isSafeToken(value) || value.startsWith('+') || value.startsWith('/') || value.startsWith('.')) return false
  if (/[:?*[\\^~]|\.\.|@\{|\/\/|\/\.|\.lock(\/|$)/.test(value)) return false
  return !value.endsWith('/') && !value.endsWith('.') && value !== '@'
}

/** A path safe as one argv element after `-C`: non-empty, no control characters (spaces are fine: no shell). */
function isSafePath(value: string): boolean {
  return value.length > 0 && !/[\u0000-\u001f\u007f-\u009f]/.test(value)
}

/** A session id the opener may pass on: on Windows `cmd /c start` reads its line, so only plain id characters. */
const PLAIN_ID = /^[A-Za-z0-9_-]+$/

/** https://claude.ai/code/<id> */
export function appUrl(id: string): string {
  return `https://claude.ai/code/${encodeURIComponent(id)}`
}

/** The OS opener for a URL: win32 `cmd /c start "" <url>`, darwin `open <url>`, else `xdg-open <url>`. */
export function openerArgv(platform: string, url: string): string[] {
  if (platform === 'win32') return ['cmd', '/c', 'start', '', url]
  if (platform === 'darwin') return ['open', url]
  return ['xdg-open', url]
}

/**
 * `claude --teleport <id>` for a cloud row, `claude attach <localId>` for a row with a localId, and the teleport
 * form for a remote (bridge) row without one [INFERRED: the brief's rule, not seen in the API]; null when neither.
 */
export function resumeCommand(row: SessionRow): string | null {
  const id = row.id !== null && isSafeToken(row.id) ? row.id : null
  if (row.kind === 'cloud' && id !== null) return `claude --teleport ${id}`
  if (row.localId !== null && isSafeToken(row.localId)) return `claude attach ${row.localId}`
  if (row.kind === 'remote' && id !== null) return `claude --teleport ${id}`
  return null
}

/**
 * Whether a row takes a message from here: not archived, and either a local session (`$.session.send`) or a cloud
 * row (`claude -p --cloud`). A remote row with no local session is not sendable from here.
 */
export function canSend(row: SessionRow): boolean {
  if (row.state === 'archived') return false
  return row.localSessionId !== null || (row.kind === 'cloud' && row.id !== null)
}

/** Which actions a row offers, in key order, each with its key and label (for the footer and the tests). */
export function actionsFor(row: SessionRow): Array<{ id: ActionId; key: string; label: string }> {
  return ORDER.filter((id) => ACTIONS[id].offers(row)).map((id) => ({
    id,
    key: ACTIONS[id].key,
    label: ACTIONS[id].label,
  }))
}

/** Runs one action for a row; `text` is the composer's for send. Never throws: the outcome is the notice. */
export async function runAction($: any, id: ActionId, row: SessionRow, text?: string): Promise<ActionNotice> {
  const spec = ACTIONS[id]
  try {
    if (!spec) return notice('error', `Unknown action: ${cleanOutput(String(id), 80)}`)
    if (spec.viaApp !== undefined) return await runViaApp($, row, spec.viaApp)
    switch (id) {
      case 'send':
        return await runSend($, row, text)
      case 'open-app':
        return await runOpenApp($, row)
      case 'copy-resume':
        return await runCopyResume($, row)
      case 'branch-diff':
        return await runBranchDiff($, row)
      case 'archive':
        return await runArchive($, row)
      case 'delete':
        return await runDelete($, row)
      case 'refresh':
        return notice('info', 'Refreshing the list')
      case 'older':
        return notice('info', 'Reading older events')
    }
    return notice('error', `${spec.label}: not available here`)
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error)
    return notice('error', `${spec?.label ?? 'Action'} failed: ${cleanOutput(reason, 300)}`)
  }
}

/**
 * The action table: each key, its label and when a row offers it. An action with `viaApp` opens the Claude app.
 */
const ACTIONS: Record<ActionId, Spec> = {
  send: { key: 's', label: 'Send', offers: canSend },
  'open-app': { key: 'o', label: 'Open in app', offers: hasId },
  'copy-resume': { key: 'c', label: 'Copy resume', offers: (row) => resumeCommand(row) !== null },
  'branch-diff': { key: 'b', label: 'Branch diff', offers: (row) => row.checkout !== null && row.branch !== null },
  refresh: { key: 'r', label: 'Refresh', offers: () => true },
  // Reads the page of events before the ones the view holds; the pane reads it (register.tsx), not runAction.
  older: { key: 'p', label: 'Older events', offers: hasId },
  interrupt: { key: 'i', label: 'Interrupt', offers: hasId, viaApp: 'Interrupt' },
  'approve-held': {
    key: 'y',
    label: 'Approve held',
    offers: (row) => row.state === 'needs-you' && hasId(row),
    viaApp: 'Approve held message',
  },
  'set-permission-mode': { key: 'm', label: 'Permission mode', offers: hasId, viaApp: 'Set permission mode' },
  archive: { key: 'x', label: 'Archive', offers: (row) => hasId(row) && row.state !== 'archived' },
  delete: { key: 'd', label: 'Delete', offers: hasId },
}

/** The order the footer and the keys follow. */
const ORDER: ActionId[] = [
  'send',
  'open-app',
  'copy-resume',
  'branch-diff',
  'refresh',
  'older',
  'interrupt',
  'approve-held',
  'set-permission-mode',
  'archive',
  'delete',
]

function hasId(row: SessionRow): boolean {
  return row.id !== null && row.id.length > 0
}

function notice(tone: Notice['tone'], text: string): Notice {
  return { tone, text: cleanOutput(text), at: new Date().toISOString() }
}

/** The first non-empty line of a cleaned process output, or ''. */
function firstLine(text: string): string {
  return cleanOutput(text, 300).split('\n').map((line) => line.trim()).find((line) => line !== '') ?? ''
}

/**
 * win32 when the OS variable says Windows; else the host's process platform when the engine exposes it; else darwin
 * when HOME is under /Users/ [INFERRED: the macOS home layout]; else linux.
 */
async function hostPlatform($: any): Promise<string> {
  let home: unknown
  try {
    if ((await $.env.get('OS')) === 'Windows_NT') return 'win32'
    home = await $.env.get('HOME')
  } catch {
    // No environment read: fall through to the process platform.
  }
  const platform = (globalThis as any).process?.platform
  if (typeof platform === 'string') return platform
  return typeof home === 'string' && home.startsWith('/Users/') ? 'darwin' : 'linux'
}

/** Sends a message: a local session through `$.session.send`, a cloud row through `claude -p --cloud`. */
async function runSend($: any, row: SessionRow, text?: string): Promise<Notice> {
  const body = text ?? ''
  if (body.trim() === '') return notice('error', 'Nothing to send: the composer is empty.')
  if ([...body].length > SEND_MAX) {
    return notice('error', `Not sent: ${[...body].length} characters, the limit is ${SEND_MAX}.`)
  }
  if (!canSend(row)) return notice('error', 'Not sent: this session takes no messages from here.')
  if (row.localSessionId !== null) {
    const result = await $.session.send({ to: { sessionId: row.localSessionId }, text: body })
    if (result.isDelivered === true) return notice('ok', `Sent to ${row.title}`)
    return notice('error', `Not sent: ${firstLine(String(result.reason ?? ''))}`)
  }
  if (row.id === null || !isSafeToken(row.id)) return notice('error', 'Not sent: the session id is not usable.')
  // A message that starts with a dash would be read as an option: one leading space keeps it the prompt.
  const prompt = body.startsWith('-') ? ` ${body}` : body
  let out: { exitCode: number; stdout: string; stderr: string }
  try {
    out = await $.process.run(['claude', '-p', prompt, '--cloud', row.id, '--output-format', 'json'], {
      timeoutMs: SEND_TIMEOUT_MS,
    })
  } catch (error) {
    // It rejects when claude cannot start or runs past its time; the second may still have handed the message over,
    // and the two do not tell themselves apart, so the notice names both and the reason.
    const reason = firstLine(String((error as { message?: unknown })?.message ?? error))
    return notice(
      'error',
      `Not confirmed: claude -p could not start or did not finish in 2 min (${reason}). Check the session before sending again.`,
    )
  }
  if (out.exitCode !== 0) return notice('error', `Not sent: ${firstLine(out.stderr || out.stdout)}`)
  const reply = parseSendReply(out.stdout)
  if (reply === null || reply.ok !== true) return notice('error', 'Not sent: the reply was not a success.')
  return notice('ok', `Sent to ${row.title}${reply.url !== null ? ` \u00b7 ${cleanOutput(reply.url, 200)}` : ''}`)
}

/** `{ ok, session_id, url }` from `claude -p --output-format json`; null when it does not parse. */
function parseSendReply(stdout: string): { ok: unknown; url: string | null } | null {
  try {
    const value: unknown = JSON.parse(stdout.trim())
    if (value === null || typeof value !== 'object') return null
    const record = value as Record<string, unknown>
    return { ok: record.ok, url: typeof record.url === 'string' ? record.url : null }
  } catch {
    return null
  }
}

/** The Claude app's link for a row, through the OS opener. The link is in the notice either way. */
async function runOpenApp($: any, row: SessionRow): Promise<Notice> {
  if (row.id === null || row.id.length === 0) return notice('error', 'No app link: this row has no session id.')
  const url = appUrl(row.id)
  if (!PLAIN_ID.test(row.id)) return notice('info', `Open this link in the Claude app: ${url}`)
  const out = await $.process.run(openerArgv(await hostPlatform($), url))
  if (out.exitCode === 0) return notice('ok', `Opened in the Claude app: ${url}`)
  return notice('error', `Could not open ${url}${firstLine(out.stderr) !== '' ? `: ${firstLine(out.stderr)}` : ''}`)
}

/** Archives a session through the sessions API. */
async function runArchive($: any, row: SessionRow): Promise<Notice> {
  if (row.id === null) return notice('error', 'Archive: this row has no session id.')
  const result = await archiveSession($, row.id)
  return result.ok
    ? notice('ok', `Archived "${cleanOutput(row.title)}"`)
    : notice('error', `Archive failed: ${cleanOutput(result.reason)}`)
}

/** Deletes through the tentative API, falling back to the app when that endpoint is unavailable. */
async function runDelete($: any, row: SessionRow): Promise<Notice> {
  if (row.id === null) return notice('error', 'Delete: this row has no session id.')
  const result = await deleteSession($, row.id)
  if (result.ok) return notice('ok', `Deleted "${cleanOutput(row.title)}"`)
  if (result.status === 404 || result.status === 405) {
    const opened = await runOpenApp($, row)
    // Never 'ok': the session still exists, and an ok delete makes the pane drop the row and close the view.
    const tone = opened.tone === 'error' ? 'error' : 'info'
    return notice(tone, `Delete is not available through the API; delete it in the Claude app. ${opened.text}`)
  }
  return notice('error', `Delete failed: ${cleanOutput(result.reason)}`)
}

/** An action the app does for now: it opens the session there, and the notice says so. */
async function runViaApp($: any, row: SessionRow, label: string): Promise<Notice> {
  const opened = await runOpenApp($, row)
  return notice(opened.tone, `${label} runs in the Claude app for now. ${opened.text}`)
}

/** Copies the resume command; when no clipboard takes it, the notice shows the command. */
async function runCopyResume($: any, row: SessionRow): Promise<Notice> {
  const command = resumeCommand(row)
  if (command === null) return notice('error', 'No resume command for this row.')
  try {
    const copied = await $.ui.copy({ text: command })
    if (copied.isCopied === true) return notice('ok', `Copied: ${command}`)
    return notice('info', `Not copied (${String(copied.reason)}). Resume: ${command}`)
  } catch {
    return notice('info', `Resume: ${command}`)
  }
}

/** The Git ref a branch is compared against: origin's HEAD, else origin/master when it exists, else origin/main. */
async function baseRef($: any, checkout: string): Promise<string> {
  const head = await $.process.run(['git', '-C', checkout, 'symbolic-ref', '--short', 'refs/remotes/origin/HEAD'])
  const name = head.exitCode === 0 ? head.stdout.trim() : ''
  if (name !== '' && isSafeToken(name)) return name
  const master = await $.process.run([
    'git', '-C', checkout, 'rev-parse', '--verify', '--quiet', 'refs/remotes/origin/master',
  ])
  return master.exitCode === 0 ? 'origin/master' : 'origin/main'
}

/** Keeps at most `max` lines: the first ones, a count of the omitted, and the last line (git's summary). */
function capLines(lines: string[], max: number): string[] {
  if (lines.length <= max) return lines
  const summary = lines[lines.length - 1] ?? ''
  const kept = lines.slice(0, max - 2)
  return [...kept, `... ${lines.length - kept.length - 1} more`, summary]
}

/** Fetches the row's branch from origin and draws `git diff --stat` against the base; at most twelve lines. */
async function runBranchDiff($: any, row: SessionRow): Promise<Notice> {
  const branch = row.branch
  const checkout = row.checkout
  if (branch === null || checkout === null) return notice('error', 'Branch diff needs a local checkout and a branch.')
  if (!isSafeBranch(branch)) return notice('error', 'Not run: the branch name is not safe to pass to git.')
  if (!isSafePath(checkout)) return notice('error', 'Not run: the checkout path is not safe to pass to git.')
  const fetched = await $.process.run(['git', '-C', checkout, 'fetch', 'origin', branch], {
    timeoutMs: FETCH_TIMEOUT_MS,
  })
  if (fetched.exitCode !== 0) return notice('error', `git fetch failed: ${firstLine(fetched.stderr || fetched.stdout)}`)
  const base = await baseRef($, checkout)
  const stat = await $.process.run(['git', '-C', checkout, 'diff', '--stat', `${base}...origin/${branch}`])
  if (stat.exitCode !== 0) return notice('error', `git diff failed: ${firstLine(stat.stderr || stat.stdout)}`)
  const lines = cleanOutput(stat.stdout, 20000).split('\n').map((line) => line.trimEnd()).filter((line) => line !== '')
  if (lines.length === 0) return notice('info', `No difference between ${base} and origin/${branch}`)
  const header = `origin/${branch} against ${base}`
  return notice('ok', [header, ...capLines(lines, DIFF_LINES - 1)].join('\n'))
}
