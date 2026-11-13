import type { PluginAPI } from '@ampcode/plugin'
import { spawn } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

export const description = 'Claude Usage Optimizer: records each turn and shows ETA, cost and meters in one status item'

// A thin adapter: Amp's agent.start and agent.end go to `turn-meter hook --platform amp`, and
// `turn-meter statusline-text` feeds one status item. All logic lives in the kit's Python tools.

const HOOK_TIMEOUT_MS = 3000
const REFRESH_MS = 30000

type Paths = { python: string; prefix: string }

function readPaths(): Paths | null {
	try {
		const file = fileURLToPath(new URL('./usage-optimizer.paths.json', import.meta.url))
		const data = JSON.parse(readFileSync(file, 'utf8'))
		if (typeof data?.python === 'string' && typeof data?.prefix === 'string') return data
	} catch {
		// not installed by install.sh
	}
	return null
}

export default function (amp: PluginAPI) {
	const paths = readPaths()
	if (!paths || process.env.KIT_LANE_RUN || process.env.USAGE_OPTIMIZER_TURNS === 'off') return
	const { python } = paths
	const script = `${paths.prefix}/bin/turn-meter.py`
	// The thread's folder: the plugin process runs in the plugin directory, so ask Amp for the workspace.
	let cwd = process.cwd()
	try {
		const root = amp.system?.workspaceRoot
		if (root) cwd = String(amp.helpers.filePathFromURI(root))
	} catch {
		// keep process.cwd()
	}

	/** Stdout of a turn-meter command run through the plugin shell runner; null on any failure. */
	async function stdout(run: Promise<{ exitCode: number; stdout: string }>): Promise<string | null> {
		try {
			const result = await run
			return result.exitCode === 0 ? result.stdout : null
		} catch {
			return null
		}
	}

	function hook(name: string, thread: string, prompt: string): Promise<string | null> {
		const json = JSON.stringify({ hook_event_name: name, session_id: thread, cwd, prompt })
		return stdout(amp.$`${python} -I ${script} hook --platform amp --json ${json}`)
	}

	/** Starts the Stop hook as its own process, so it finishes after `amp -x` exits (seen in the L2 check). */
	function stopDetached(thread: string): boolean {
		try {
			const json = JSON.stringify({ hook_event_name: 'Stop', session_id: thread, cwd, prompt: '' })
			const child = spawn(python, ['-I', script, 'hook', '--platform', 'amp', '--json', json], {
				detached: true,
				stdio: 'ignore',
				windowsHide: true,
			})
			child.on('error', () => {})
			child.unref()
			return true
		} catch {
			return false
		}
	}

	const item = amp.experimental?.createStatusItem?.()
	let openThread: string | null = null
	let timer: ReturnType<typeof setInterval> | null = null

	async function refresh(thread: string): Promise<void> {
		if (!item) return
		const text = (await stdout(amp.$`${python} -I ${script} statusline-text --session ${thread}`))?.trim()
		if (text) {
			try {
				item.update({ text })
			} catch {
				// the item stays as it was
			}
		}
	}

	amp.on('agent.start', async (event, ctx) => {
		const thread = event.thread.id
		try {
			if (await ctx.thread.parentThreadID()) return {}
			openThread = thread
			if (item && !timer) timer = setInterval(() => openThread && void refresh(openThread), REFRESH_MS)
			const timeout = new Promise<null>((resolve) => setTimeout(resolve, HOOK_TIMEOUT_MS, null))
			const out = await Promise.race([hook('UserPromptSubmit', thread, event.message ?? ''), timeout])
			void refresh(thread)
			const line = out?.trim()
			if (!line) return {}
			const context = JSON.parse(line)?.context
			return typeof context === 'string' && context
				? { message: { content: context, display: false } }
				: {}
		} catch {
			return {}
		}
	})

	amp.on('agent.end', async (event, ctx) => {
		const thread = event.thread.id
		try {
			if (await ctx.thread.parentThreadID()) return
			if (timer) clearInterval(timer)
			timer = null
			openThread = null
			if (stopDetached(thread)) setTimeout(() => void refresh(thread), 10000)
			else void hook('Stop', thread, '').then(() => refresh(thread))
		} catch {
			// never disturb the turn
		}
	})
}
