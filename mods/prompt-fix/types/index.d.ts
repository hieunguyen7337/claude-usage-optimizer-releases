/** Each corrected prompt, keyed by the text as typed: what the prompt's transcript row draws instead. */
export type Fixes = Record<string, string>

declare module 'claude-code' {
  interface PluginState {
    'prompt-fix': { fixes: Shaped<Fixes> }
  }
}
