import { atom, memberOf, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { MobileViewIndex, MobileViewMode, MobileViewPrompt } from '../types'
import { cellWidth, clockTime, collapseCodeBlocks, statusMark, toolLabel, toolName, truncateCells } from './format'
import type { CallLike, PathContext, Tone } from './format'
import { addLive, entryFromAppend, merge, parseHelper } from './prompts'

const PANE = 'questions'

const MODE = atom({ plugin: 'mobile-view', key: 'mode' } as const, 'mobile' as MobileViewMode)
const PROMPTS = atom({ plugin: 'mobile-view', key: 'prompts' } as const, [] as MobileViewPrompt[])
const INDEX = atom({ plugin: 'mobile-view', key: 'index' } as const, { status: 'idle' } as MobileViewIndex)
const FOCUSED = atom({ plugin: 'mobile-view', key: 'focused' } as const, null as string | null)
// What the question view's filter field holds.
const FILTER = atom({ plugin: 'mobile-view', key: 'filter' } as const, '')
const FILTER_KEY = 'filter'
// Whether the question view is on screen: the footer hint is left out while it is.
const LIST_OPEN = atom({ plugin: 'mobile-view', key: 'listOpen' } as const, false)
// Claude Code places a pane opened by a key alone from 144 columns, or from this many once the person has
// opened it themselves (a prompt sent), which it remembers across sessions until they close the pane by hand.
const ASKED_COLUMNS = 110
// Whether the last `>` could not place the list, so the footer says to press Enter.
const NEEDS_ENTER = atom({ plugin: 'mobile-view', key: 'needsEnter' } as const, false)
// The terminal's width as the footer last saw it.
let columnsSeen = 144
// Families: by tool_use_id (calls), by a group's first tool_use_id (groups), by message id (code).
const OPEN_CALL = atom({ plugin: 'mobile-view', key: 'openCall' } as const, false)
const OPEN_GROUP = atom({ plugin: 'mobile-view', key: 'openGroup' } as const, false)
const OPEN_MSG = atom({ plugin: 'mobile-view', key: 'openMsg' } as const, false)
// Prompt uuids of the questions whose full text the list shows (their rows are no longer in the transcript).
const OPEN_QUESTIONS = atom({ plugin: 'mobile-view', key: 'openQuestions' } as const, [] as string[])


/** Tools whose rows carry something meant for the person: never compacted. */
const PASS_THROUGH = new Set(['ExitPlanMode', 'EnterPlanMode', 'AskUserQuestion', 'SendUserMessage', 'SendUserFile'])

/**
 * Tools the normal view always folds into a ToolGroup. Their own ToolUse row outside a group the
 * person opened means the ctrl+o transcript is showing, where every call is its own row.
 */
const GROUPED = new Set(['Read', 'Grep', 'Glob', 'Bash', 'PowerShell', 'LS'])

const TONE_COLOR: Record<Tone, string> = { ok: 'success', running: 'inactive', error: 'error', warn: 'warning' }

type InstallPaths = { python: string; promptsScript: string; prefix?: string }

type Session = {
  where: PathContext
  paths: InstallPaths | null
  transcriptPath: string
  indexedSize: number
  hasToasted: boolean
  /** Whether the ctrl+o transcript is showing (the prompt row's isExpanded flips with it). */
  inTranscript: boolean
  /** The group each call was last drawn folded in: its key (first call's id) and how many calls. */
  groupOf: Map<string, { key: string; size: number }>
  codeLines: number
  maxGroupLines: number
}

// Session facts the hooks share; a hot reload starts them afresh and the hooks re-learn them.
const session: Session = {
  where: { cwd: '', home: '' },
  paths: null,
  transcriptPath: '',
  indexedSize: -1,
  hasToasted: false,
  inTranscript: false,
  groupOf: new Map(),
  codeLines: 12,
  maxGroupLines: 8,
}

function setTranscript($: any, value: boolean) {
  if (session.inTranscript !== value) {
    session.inTranscript = value
    $.ui.invalidate('ui.render')
  }
}

async function isStock($: any, e: { surface: string }) {
  return e.surface !== 'terminal' || session.inTranscript || (await read($, MODE)) === 'full'
}

async function readPaths($: any): Promise<InstallPaths | null> {
  try {
    const data = JSON.parse(String(await $.fs.read(`${$.plugin.root}/install-paths.json`)))
    if (typeof data?.python === 'string' && typeof data?.promptsScript === 'string') {
      return data
    }
  } catch {
    // not installed by install.sh: a development copy falls back to the environment
  }
  const python = await $.env.get('MOBILE_VIEW_PYTHON')
  const promptsScript = await $.env.get('MOBILE_VIEW_PROMPTS')
  return python && promptsScript ? { python, promptsScript } : null
}

/** Runs bin/claude-prompts over this session's transcript and merges what it lists. */
async function refreshIndex($: any, isQuiet: boolean) {
  const paths = session.paths
  if (paths === null) {
    await update($, INDEX, () => ({ status: 'error' as const, error: 'claude-prompts is not installed (run the kit installer)' }))
    return
  }
  const source = session.transcriptPath !== '' ? ['--transcript', session.transcriptPath] : ['--session-id', await $.session.id()]
  await update($, INDEX, index => ({ ...index, status: 'loading' as const }))
  let stdout = ''
  try {
    const ran = await $.process.run([paths.python, '-I', '-X', 'utf8', paths.promptsScript, ...source], {
      ...(paths.prefix ? { cwd: paths.prefix } : {}),
      timeoutMs: 60_000,
    })
    stdout = ran.stdout
  } catch (error) {
    stdout = JSON.stringify({ error: `claude-prompts did not run: ${String(error)}` })
  }
  const result = parseHelper(stdout)
  if ('error' in result) {
    await update($, INDEX, () => ({ status: 'error' as const, error: result.error }))
    if (!isQuiet && !session.hasToasted) {
      session.hasToasted = true
      $.ui.toast(`mobile-view: ${result.error}`)
    }
    return
  }
  session.indexedSize = result.size
  await update($, PROMPTS, list => merge(result.prompts, list))
  await update($, INDEX, () => ({ status: 'ready' as const, size: result.size }))
}

/** Re-runs the helper when the transcript grew since it last ran. */
async function refreshIfStale($: any) {
  if (session.transcriptPath === '') {
    return refreshIndex($, false)
  }
  try {
    const stat = await $.fs.stat(session.transcriptPath)
    if (stat.size !== session.indexedSize) {
      await refreshIndex($, false)
    }
  } catch {
    // no transcript yet (nothing sent this session)
  }
}

/**
 * Puts the ring on the filter field when it is on nothing: autoFocus acts only as the pane takes the
 * keys, and the field is where typing lands (it filters; Esc goes back).
 */
async function focusFilter($: any) {
  if ((await read($, FOCUSED)) !== null) {
    return
  }
  try {
    await $.ui.focus({ requestId: PANE, key: FILTER_KEY })
  } catch {
    // the pane does not hold the keys (the person clicked elsewhere first): nothing to move
  }
}

/**
 * Where an arrow takes the choice, in the list's order with the filter field after the newest question:
 * one step up or down, holding at either end. Null when the ring is on nothing the list knows.
 */
async function arrowTarget($: any, by: number): Promise<string | null> {
  const shown = filtered(await read($, PROMPTS), await read($, FILTER)).slice(-300)
  const order = [...shown.map(prompt => `q:${prompt.uuid}`), FILTER_KEY]
  const at = order.indexOf((await read($, FOCUSED)) ?? FILTER_KEY)
  if (at === -1) {
    return null
  }
  return order[Math.min(order.length - 1, Math.max(0, at + Math.sign(by)))]
}

/** Moves the ring to a row of the list and scrolls only as far as keeps that row in view. */
async function moveChoice($: any, key: string) {
  try {
    await $.ui.focus({ requestId: PANE, key })
    await $.ui.scroll({ in: PANE, to: { key }, block: 'nearest' })
  } catch {
    // the pane lost the keys meanwhile: the person's next move settles the ring
  }
}

/** The question view, opened by `>` in an empty prompt. */
async function openQuestions($: any): Promise<boolean> {
  await update($, FILTER, () => '')
  const opened = await $.ui.open({ id: PANE, title: 'Questions', focus: true, closeOnEscape: true })
  if (opened?.isPlaced === false) {
    // A pane the person did not ask for (a key is not asking) waits for a wide terminal; take it back.
    await closeQuestions($)
    await update($, NEEDS_ENTER, () => true)
    return false
  }
  await update($, NEEDS_ENTER, () => false)
  await update($, LIST_OPEN, () => true)
  // The key is answered at once; a long transcript re-reads after (the list shows it loading).
  $.clock.after(0, async () => {
    await refreshIfStale($)
    await settlePane($)
  })
  return true
}

/** Takes back a pane: one that could not be placed, or one the person closed (see the ui.close hook). */
async function closeQuestions($: any) {
  await update($, FILTER, () => '')
  try {
    await $.ui.close({ id: PANE })
  } catch {
    // a hook kept it open
  }
}

/** The questions a filter keeps: `12` or `#12` names one by number, other text matches its words. */
function filtered(prompts: readonly MobileViewPrompt[], filter: string) {
  const wanted = filter.trim().toLowerCase()
  if (wanted === '') {
    return prompts
  }
  const number = /^#?(\d+)$/.exec(wanted)
  return prompts.filter(
    prompt =>
      (number !== null && prompt.n === Number(number[1])) ||
      (prompt.text ?? prompt.title).toLowerCase().includes(wanted),
  )
}

/**
 * Asks for the keyboard again when the pane opened without it: `focus` is refused while the composer
 * still holds text or another site holds the keys, and an already open pane is only retitled.
 */
async function settlePane($: any) {
  if (await paneHasKeys($)) {
    await focusFilter($)
    return
  }
  try {
    await $.ui.scroll({ in: PANE, to: 'end' })
  } catch {
    // not placed yet: it draws from the top
  }
  $.clock.after(400, async () => {
    if ((await paneIsOpen($)) && !(await paneHasKeys($))) {
      await $.ui.open({ id: PANE, title: 'Questions', focus: true, closeOnEscape: true })
      await focusFilter($)
    }
  })
}

async function panesNow($: any): Promise<ReadonlyArray<{ id: string; isFocused: boolean }>> {
  try {
    return await $.ui.panes()
  } catch {
    return []
  }
}

async function paneIsOpen($: any) {
  return (await panesNow($)).some(pane => pane.id === PANE)
}

async function paneHasKeys($: any) {
  return (await panesNow($)).some(pane => pane.id === PANE && pane.isFocused)
}

/** A press on a question in the list: a second press folds the text a failed jump opened. */
async function pressQuestion($: any, prompt: MobileViewPrompt) {
  if ((await read($, OPEN_QUESTIONS)).includes(prompt.uuid)) {
    await update($, OPEN_QUESTIONS, list => list.filter(uuid => uuid !== prompt.uuid))
    return
  }
  await jump($, prompt)
}

/**
 * Scrolls the transcript to a question. One it can't reach (a compaction replaced it with a summary)
 * has its text opened in the list instead, and the toast says so.
 */
async function jump($: any, prompt: MobileViewPrompt) {
  let reason: string | undefined
  try {
    reason = (await $.ui.scroll({ to: { requestId: prompt.uuid }, block: 'start' }))?.deny
  } catch (error) {
    reason = error instanceof Error ? error.message : String(error)
  }
  if (reason === undefined) {
    return
  }
  await update($, OPEN_QUESTIONS, list => (list.includes(prompt.uuid) ? list : [...list, prompt.uuid]))
  $.ui.toast(
    prompt.isBeforeCompact
      ? `#${prompt.n} is from before a compaction, so it is no longer in the transcript; its text is shown in the list`
      : `Can't jump to #${prompt.n} (${reason}); its text is shown in the list`,
  )
}

async function loadMode($: any) {
  if ((await $.store.get('mode')) === 'full') {
    await update($, MODE, () => 'full' as const)
  }
}

async function setMode($: any, mode: MobileViewMode) {
  await $.store.set('mode', mode)
  await update($, MODE, () => mode)
}

async function setGroupOpen($: any, calls: ReadonlyArray<{ tool_use_id?: string }>, groupKey: string, value: boolean) {
  await update($, memberOf(OPEN_GROUP, { requestId: groupKey }), () => value)
  for (const call of calls) {
    if (call.tool_use_id !== undefined) {
      await update($, memberOf(OPEN_CALL, { requestId: call.tool_use_id }), () => value)
    }
  }
}

async function toggleCall($: any, requestId: string) {
  await update($, memberOf(OPEN_CALL, { requestId }), value => !value)
}

async function toggleMsg($: any, requestId: string) {
  await update($, memberOf(OPEN_MSG, { requestId }), value => !value)
}

/** One `● Tool  label  status` row, a Button that opens or folds the call. */
function callRow($: any, e: any, key: string, call: CallLike, isOpen: boolean, onPress: () => unknown) {
  const { Button, Text } = $.ui.resolve(e)
  const mark = statusMark(call)
  const name = toolName(call.tool)
  const columns = e.viewport?.columns ?? 100
  const room = columns - 6 - name.length - (mark.text === '' ? 0 : mark.text.length + 2) - 2
  const label = truncateCells(toolLabel(call.tool, call.input, session.where), Math.max(8, room))
  return (
    <Button key={key} plain onPress={onPress}>
      <Text color={TONE_COLOR[mark.tone]}>{isOpen ? '▾' : '●'}</Text> <Text bold>{name}</Text>
      {label === '' ? '' : `  ${label}`}
      {mark.text === '' ? '' : '  '}
      <Text color={TONE_COLOR[mark.tone]}>{mark.text}</Text>
    </Button>
  )
}

export const register: Register = (on, options) => {
  session.codeLines = typeof options.codeLines === 'number' && options.codeLines > 0 ? options.codeLines : 12
  session.maxGroupLines = typeof options.maxGroupLines === 'number' && options.maxGroupLines > 0 ? options.maxGroupLines : 8

  on('session.start', async ($, e, next) => {
    session.where.cwd = e.cwd
    session.where.home = (await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME')) ?? ''
    session.paths = await readPaths($)
    await loadMode($)
    await $.command.register({
      name: 'mobile-view',
      description: 'Turn the mobile-style transcript on or off (off is stock Claude Code)',
      argumentHint: '[on | off]',
      immediate: true,
    })
    $.clock.after(0, () => void refreshIndex($, true))
    return next(e)
  })

  on('classic.SessionStart', async ($, e, next) => {
    if (typeof e.transcript_path === 'string' && e.transcript_path !== '') {
      session.transcriptPath = e.transcript_path
    }
    session.indexedSize = -1
    session.hasToasted = false
    if (e.source === 'clear') {
      await update($, PROMPTS, () => [])
    }
    if (e.source !== 'startup') {
      // State resets on /clear, /resume and a fork; the stored mode does not.
      await loadMode($)
      $.clock.after(0, () => void refreshIndex($, true))
    }
    return next(e)
  })

  on('session.append', { door: 'prompt' }, async ($, e, next) => {
    const stored = await next(e)
    const entry = entryFromAppend(e, new Date().toISOString())
    if (entry !== null) {
      await update($, PROMPTS, list => addLive(list, entry))
    }
    return stored
  })

  // `>` typed into an empty prompt opens the question view (its only door) instead of starting a message.
  on('prompt.edit', async ($, e, next) => {
    if (e.text !== '' || e.inputText !== '>' || e.start !== 0 || e.end !== 0 || (await read($, MODE)) === 'full') {
      return next(e)
    }
    if (await openQuestions($)) {
      return { text: e.text, cursor: e.cursor }
    }
    // Not placeable from a key alone: `>` is typed, and Enter on it opens the list.
    $.ui.toast(
      columnsSeen >= ASKED_COLUMNS
        ? 'Press Enter to open your questions; after that, > alone opens them'
        : `Press Enter to open your questions (> alone needs a terminal ${ASKED_COLUMNS} columns wide)`,
    )
    return next(e)
  })

  // `>` sent alone asks for the list in so many words, which places it at any width.
  on('prompt.submit', async ($, e, next) => {
    if (e.text.trim() !== '>' || e.attachments !== undefined || (await read($, MODE)) === 'full') {
      return next(e)
    }
    await update($, FILTER, () => '')
    await $.ui.open({ id: PANE, title: 'Questions', focus: true, closeOnEscape: true })
    await update($, NEEDS_ENTER, () => false)
    await update($, LIST_OPEN, () => true)
    // A dropped prompt stays in the box, which keeps the keyboard from the list: empty it, then
    // settlePane asks for the keyboard again.
    $.clock.after(0, async () => {
      try {
        await $.prompt.fill({ text: '' })
      } catch {
        // the box is the person's again
      }
      await refreshIfStale($)
      await settlePane($)
    })
    return { drop: 'Questions opened' }
  })

  // The footer hint, after the engine's own (`← for agents`), while the prompt is empty.
  on('ui.render', { component: 'PromptHint' }, async ($, e, next) => {
    columnsSeen = e.viewport?.columns ?? columnsSeen
    if (e.surface !== 'terminal' || e.props.isDraft || (await read($, MODE)) === 'full' || (await read($, LIST_OPEN))) {
      return next(e)
    }
    // After a `>` that could not place the list, the hint says to press Enter.
    const hint = (await read($, NEEDS_ENTER)) ? '> then Enter for questions' : '> for questions'
    return next({ ...e, props: { ...e.props, tail: e.props.tail === undefined ? hint : `${e.props.tail} · ${hint}` } })
  })

  // The engine's ring inverts the row it is on; the pane also marks it, so the choice reads at a glance.
  on('ui.focus', { requestId: PANE }, async ($, e, next) => {
    const result = await next(e)
    if (!result?.deny) {
      await update($, FOCUSED, () => e.element ?? null)
    }
    return result
  })

  // In a list taller than the pane Claude Code spends ↑↓ on scrolling the body and leaves the ring where it
  // was (it moves the ring only while nothing scrolls). An arrow arrives as a one-row scroll with no pointer
  // (the wheel and trackpad carry one; page keys move further), so the mod moves the choice instead.
  on('ui.scroll', { component: 'Pane', requestId: PANE }, async ($, e, next) => {
    if (e.origin?.kind !== 'person' || e.pointer !== undefined || Math.abs(e.by) !== 1) {
      return next(e)
    }
    const target = await arrowTarget($, e.by)
    if (target === null) {
      return next(e)
    }
    // Marked at once so a held key steps from here; the ring and the window follow off this chain.
    await update($, FOCUSED, () => target)
    $.clock.after(0, () => void moveChoice($, target))
    return { deny: 'the arrow moves the choice' }
  })

  on('ui.close', { id: PANE }, async ($, e, next) => {
    if (e.origin?.kind === 'person') {
      // Claude Code forgets that the person asked for a pane they close by hand, and `>` alone then stops
      // placing it under 144 columns. So Esc (or the close mark) is refused here and the mod closes it.
      await update($, FOCUSED, () => null)
      await update($, LIST_OPEN, () => false)
      $.clock.after(0, () => closeQuestions($))
      return { value: undefined }
    }
    const result = await next(e)
    await update($, FOCUSED, () => null)
    await update($, FILTER, () => '')
    await update($, LIST_OPEN, () => false)
    return result
  })

  on('command.run', { command: 'mobile-view' }, async ($, e) => {
    const arg = e.args.trim().toLowerCase()
    const current = await read($, MODE)
    const mode: MobileViewMode = arg === 'on' ? 'mobile' : arg === 'off' ? 'full' : current === 'mobile' ? 'full' : 'mobile'
    await setMode($, mode)
    $.ui.toast(mode === 'mobile' ? 'Mobile view on' : 'Mobile view off: stock Claude Code rendering')
    return {}
  })

  on('ui.render', { component: 'UserMessage' }, async ($, e, next) => {
    if (e.surface === 'terminal') {
      setTranscript($, e.props.isExpanded)
    }
    if (e.props.isExpanded || (await isStock($, e))) {
      return next(e)
    }
    const kind = e.props.origin.kind
    if (kind !== 'composer' && kind !== 'bridge') {
      return next(e)
    }
    const prompt = (await read($, PROMPTS)).find(candidate => candidate.uuid === e.requestId)
    return prompt === undefined ? next(e) : next({ ...e, props: { ...e.props, text: `#${prompt.n}  ${e.props.text}` } })
  })

  on('ui.render', { component: 'ToolGroup' }, async ($, e, next) => {
    if (e.surface === 'terminal' && !e.props.isExpanded) {
      setTranscript($, false) // a folded group is drawn only outside the ctrl+o transcript
      const key = e.props.calls[0]?.tool_use_id ?? e.requestId
      for (const call of e.props.calls) {
        if (call.tool_use_id !== undefined) {
          session.groupOf.set(call.tool_use_id, { key, size: e.props.calls.length })
        }
      }
    }
    if (e.props.isExpanded || (await isStock($, e))) {
      return next(e)
    }
    const { Box, Button, Text } = $.ui.resolve(e)
    const calls = e.props.calls
    const groupKey = calls[0]?.tool_use_id ?? e.requestId
    if (await read($, memberOf(OPEN_GROUP, { requestId: groupKey }))) {
      if (calls.length === 1) {
        // the call's own ▾ row folds it again; a "fold 1 call" line above it would say the same
        return next({ ...e, props: { ...e.props, isExpanded: true } })
      }
      return (
        <Box flexDirection="column">
          <Box paddingLeft={2}>
            <Button key="fold" plain onPress={() => setGroupOpen($, calls, groupKey, false)}>
              <Text dimColor>{`▾ fold ${calls.length} call${calls.length === 1 ? '' : 's'}`}</Text>
            </Button>
          </Box>
          {await next({ ...e, props: { ...e.props, isExpanded: true } })}
        </Box>
      )
    }
    const shown = calls.slice(0, session.maxGroupLines)
    const rest = calls.length - shown.length
    return (
      <Box flexDirection="column" paddingLeft={2}>
        {shown.map((call, index) =>
          callRow($, e, `call:${call.tool_use_id ?? index}`, call, false, () => setGroupOpen($, calls, groupKey, true)),
        )}
        {rest > 0 ? (
          <Button key="more" plain onPress={() => setGroupOpen($, calls, groupKey, true)}>
            <Text dimColor>{`… +${rest} more`}</Text>
          </Button>
        ) : (
          ''
        )}
      </Box>
    )
  })

  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    if (e.surface !== 'terminal' || PASS_THROUGH.has(e.props.tool)) {
      return next(e)
    }
    const isOpen = await read($, memberOf(OPEN_CALL, e))
    const group = session.groupOf.get(e.requestId)
    const isInOpenGroup = group !== undefined && (await read($, memberOf(OPEN_GROUP, { requestId: group.key })))
    if (!isOpen && !isInOpenGroup && GROUPED.has(e.props.tool)) {
      setTranscript($, true)
    }
    if (await isStock($, e)) {
      return next(e)
    }
    const { Box } = $.ui.resolve(e)
    // Folding the only call of an opened group folds the group: it returns to its one-line row.
    const onPress =
      isOpen && isInOpenGroup && group.size === 1
        ? () => setGroupOpen($, [{ tool_use_id: e.requestId }], group.key, false)
        : () => toggleCall($, e.requestId)
    const row = callRow($, e, `call:${e.requestId}`, e.props, isOpen, onPress)
    if (!isOpen) {
      return (
        <Box marginTop={1} paddingLeft={2}>
          {row}
        </Box>
      )
    }
    return (
      <Box flexDirection="column" marginTop={1}>
        <Box paddingLeft={2}>{row}</Box>
        {await next(e)}
      </Box>
    )
  })

  on('ui.render', { component: 'ToolResult' }, async ($, e, next) => {
    if (e.surface !== 'terminal' || PASS_THROUGH.has(e.props.tool) || (await isStock($, e))) {
      return next(e)
    }
    if (await read($, memberOf(OPEN_CALL, e))) {
      return next(e)
    }
    const { Box } = $.ui.resolve(e)
    return <Box display="none" />
  })

  on('ui.render', { component: 'AssistantMessage' }, async ($, e, next) => {
    if (await isStock($, e)) {
      return next(e)
    }
    const folded = collapseCodeBlocks(e.props.text, { minLines: session.codeLines })
    if (folded.count === 0) {
      return next(e)
    }
    const { Box, Button, Text } = $.ui.resolve(e)
    const isOpen = await read($, memberOf(OPEN_MSG, e))
    const label = isOpen
      ? '▴ hide code'
      : `▸ show code (${folded.count} block${folded.count === 1 ? '' : 's'}, ${folded.lines} lines)`
    return (
      <Box flexDirection="column">
        {isOpen ? await next(e) : await next({ ...e, props: { ...e.props, text: folded.text } })}
        <Box paddingLeft={2}>
          <Button key="code" plain onPress={() => toggleMsg($, e.requestId)}>
            <Text dimColor>{label}</Text>
          </Button>
        </Box>
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Input, Text } = $.ui.resolve(e)
    const prompts = await read($, PROMPTS)
    const index = await read($, INDEX)
    const filter = await read($, FILTER)
    const focused = e.props.isFocused ? await read($, FOCUSED) : null
    const width = Math.max(20, e.props.bodyColumns)
    const shown = filtered(prompts, filter).slice(-300)
    const count =
      filter.trim() === ''
        ? `${prompts.length} question${prompts.length === 1 ? '' : 's'}`
        : `${shown.length} of ${prompts.length}`
    const status =
      index.status === 'loading'
        ? 'reading the transcript…'
        : index.status === 'error'
          ? `⚠ ${index.error ?? 'index unavailable'}`
          : e.props.isFocused
            ? `type to filter · ↑↓ choose · Enter jumps · Esc back · ${count}`
            : `ctrl+x tab (or a click) to choose · Esc closes · ${count}`
    const opened = new Set(await read($, OPEN_QUESTIONS))
    // The field and the hint sit under the newest question, where the list opens scrolled to.
    return (
      <Box flexDirection="column">
        {shown.length === 0 && index.status !== 'loading' ? (
          <Text dimColor>{filter.trim() === '' ? 'No questions yet.' : 'No question matches.'}</Text>
        ) : (
          ''
        )}
        {shown.map(prompt => {
          const key = `q:${prompt.uuid}`
          const isChosen = focused === key
          const head = `${isChosen ? '❯' : ' '} #${prompt.n} ${clockTime(prompt.ts)} `
          return (
            <Box key={`row:${prompt.uuid}`} flexDirection="column">
              <Button key={key} plain onPress={() => pressQuestion($, prompt)}>
                <Text color={isChosen ? 'suggestion' : undefined} bold={isChosen} dimColor={!isChosen}>
                  {head}
                </Text>
                <Text bold={isChosen} dimColor={!isChosen && prompt.isBeforeCompact}>
                  {truncateCells(prompt.title, width - cellWidth(head) - 1)}
                </Text>
              </Button>
              {opened.has(prompt.uuid) ? (
                <Box paddingLeft={3} paddingBottom={1} width={width}>
                  <Text>{prompt.text ?? prompt.title}</Text>
                </Box>
              ) : (
                ''
              )}
            </Box>
          )
        })}
        <Input
          key={FILTER_KEY}
          label="›"
          placeholder="type to filter"
          submitLabel="jump"
          autoFocus
          onInput={(value: string) => filterTyped($, value)}
          onSubmit={(value: string) => filterSubmitted($, value)}
        />
        <Text dimColor>{truncateCells(status, width)}</Text>
      </Box>
    )
  })
}

/** Typing in the filter field narrows the list. */
async function filterTyped($: any, value: string) {
  await update($, FILTER, () => value)
}

/** Enter in the filter field jumps to the newest question it keeps. */
async function filterSubmitted($: any, value: string) {
  const newest = filtered(await read($, PROMPTS), value).at(-1)
  if (newest === undefined) {
    $.ui.toast(value.trim() === '' ? 'No questions yet' : `No question matches "${value.trim()}"`)
    return
  }
  await jump($, newest)
}
