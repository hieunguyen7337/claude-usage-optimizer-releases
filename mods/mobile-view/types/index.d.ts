export type MobileViewMode = 'mobile' | 'full'

/** One prompt the person typed, as the Questions pane lists it. */
export type MobileViewPrompt = {
  uuid: string
  n: number
  ts: string | null
  title: string
  /** The question's text, up to 600 characters: shown in the list when its row can't be reached. */
  text?: string
  isBeforeCompact: boolean
  /** Seen by `session.append` in this session and not yet confirmed by the transcript helper. */
  isLive?: true
}

export type MobileViewIndex = {
  status: 'idle' | 'loading' | 'ready' | 'error'
  error?: string
  size?: number
}

declare module 'claude-code' {
  interface PluginState {
    'mobile-view': {
      mode: MobileViewMode
      prompts: MobileViewPrompt[]
      index: MobileViewIndex
      /** The key of the Questions pane row holding the focus ring, or null while none does. */
      focused: string | null
      /** What the Questions pane's filter field holds. */
      filter: string
      /** Whether the question view is on screen. */
      listOpen: boolean
      /** Whether the last `>` could not place the list, so Enter is needed. */
      needsEnter: boolean
      openCall: StateFamily<boolean>
      openGroup: StateFamily<boolean>
      openMsg: StateFamily<boolean>
      /** Prompt uuids whose full text the Questions pane shows. */
      openQuestions: string[]
    }
  }
}
