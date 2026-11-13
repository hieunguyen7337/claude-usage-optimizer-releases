import type { PluginAPI } from '@ampcode/plugin'
import { spawn } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

export const description = 'Claude Usage Optimizer: records each turn and shows ETA, cost and meters in one status item'

// A thin adapter: Amp's agent.start and agent.end go to `turn-meter hook --platform amp`, and
// `turn-meter statusline-text` feeds one status item. The kit_lane_run tool runs a lane run that
// `lane ... --subagent` prepared as a child agent thread, and the `kit` mode carries the kit's main
// model. All logic lives in the kit's Python tools (`lane hook amp-run-spec|amp-run-end|amp-mode`).

// @amp-agent-mode key=kit label=kit

const HOOK_TIMEOUT_MS = 3000
const REFRESH_MS = 30000
const LANE_SPEC_MS = 30000
// amp-run-end reads `amp threads usage` once (20 s at most) before it answers.
const LANE_END_MS = 60000

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
	// A worker that lane started (KIT_LANE_RUN) gets nothing from this plugin: no tool, no mode, no meter.
	if (!paths || process.env.KIT_LANE_RUN) return
	const { python } = paths
	const laneScript = `${paths.prefix}/bin/lane.py`

	/** One `lane hook <name> --json -` call, its input on stdin (an answer can outgrow a command line); null on failure. */
	function laneHook(name: string, input: object, timeoutMs: number): Promise<any> {
		return new Promise((resolve) => {
			let out = ''
			let settled = false
			const finish = (value: any) => {
				if (!settled) {
					settled = true
					resolve(value)
				}
			}
			try {
				const child = spawn(python, ['-I', laneScript, 'hook', name, '--json', '-'], {
					stdio: ['pipe', 'pipe', 'ignore'],
					windowsHide: true,
				})
				const timer = setTimeout(() => finish(null), timeoutMs)
				child.stdout?.on('data', (chunk) => (out += String(chunk)))
				child.on('error', () => finish(null))
				child.on('close', () => {
					clearTimeout(timer)
					try {
						finish(JSON.parse(out.trim().split('\n').pop() || 'null'))
					} catch {
						finish(null)
					}
				})
				child.stdin?.on('error', () => {})
				child.stdin?.end(JSON.stringify(input))
			} catch {
				finish(null)
			}
		})
	}

	try {
		amp.registerTool({
			name: 'kit_lane_run',
			title: 'Kit lane run',
			description:
				'Runs a kit lane run that `lane <lane> --subagent` prepared on Amp: a child agent thread on the arm\'s model ' +
				'and effort, with the worker prompt as its instructions. Waits for it, records the result through lane, ' +
				"and returns lane's summary line and the worker's answer. Input: the run_id lane printed.",
			inputSchema: {
				type: 'object',
				properties: { run_id: { type: 'string', description: 'The run id that lane printed' } },
				required: ['run_id'],
			},
			async execute(input, ctx) {
				const runId = typeof input.run_id === 'string' ? input.run_id : ''
				const parent = ctx.thread.id
				const spec = await laneHook('amp-run-spec', { run_id: runId, parent_thread_id: parent }, LANE_SPEC_MS)
				if (!spec?.ok) throw new Error(spec?.error ?? `lane could not read run ${runId}`)
				const end: Record<string, unknown> = { run_id: runId, parent_thread_id: parent, status: 'done', text: '' }
				const started = Date.now()
				try {
					const agent = amp.createAgent({
						name: 'kit lane worker',
						model: spec.model,
						reasoningEffort: spec.reasoningEffort,
						instructions: spec.instructions,
						tools: spec.tools,
					})
					const result = await agent.run(spec.message, { parentThreadID: parent, timeoutMs: spec.timeoutMs })
					end.thread_id = result.threadID
					end.text = result.text
				} catch (error) {
					// A timeout rejects but leaves the child running; lane records it as TIMEOUT.
					end.status = ctx.signal?.aborted
						? 'cancelled'
						: Date.now() - started >= spec.timeoutMs - 1000
							? 'timeout'
							: 'error'
					end.error = String(error)
				}
				const recorded = await laneHook('amp-run-end', end, LANE_END_MS)
				const line = recorded?.ok
					? String(recorded.summary)
					: `lane run ${runId} ended (${end.status}) but was not recorded: run lane --recover ${runId}`
				return end.text ? `${line}\n\n${end.text}` : line
			},
		})
	} catch {
		// an Amp without plugin tools keeps the meter
	}

	/** The `kit` mode: the main model and effort of explore.main_session, compaction at the kit's 250k tokens. */
	async function registerKitMode(): Promise<void> {
		const mode = await laneHook('amp-mode', {}, LANE_SPEC_MS)
		if (!mode?.ok) return
		const config = {
			model: mode.model,
			reasoningEffort: mode.reasoningEffort,
			compactionThresholdTokens: mode.compactionThresholdTokens,
			instructions: mode.instructions,
			display: { label: mode.label },
		}
		let agent
		try {
			// Extending the coding model keeps Amp's own prompt and tools for it; older builds take only mode names.
			agent = amp.createAgent({ ...config, extends: mode.model })
		} catch {
			agent = amp.createAgent(config)
		}
		amp.registerAgentMode({ key: mode.key, label: mode.label, description: mode.description, agent: agent.definition })
	}
	void registerKitMode().catch(() => {})

	if (process.env.USAGE_OPTIMIZER_TURNS === 'off') return
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
