import { create } from 'zustand'
import type { PanelStyle } from '../../shared/api/types'
import type { ScriptFormat } from '../../shared/events'
import { DEFAULT_CHOICE, type TellingMode } from '../script/store'

export interface StartState {
  title: string
  style: PanelStyle
  names: string
  /** Keep the narration for the animatic's voice track. On by default; the narrator can say no. */
  keepAudio: boolean
  /** How the story is told (ADR 0015), and for a script, its text, voice and language. */
  mode: TellingMode
  script: string
  format: ScriptFormat
  voice: string
  language: string
  creating: boolean
  error: string | null
  setTitle(title: string): void
  setStyle(style: PanelStyle): void
  setNames(names: string): void
  setKeepAudio(keepAudio: boolean): void
  set(patch: Partial<Pick<StartState, 'mode' | 'script' | 'format' | 'voice' | 'language'>>): void
  setCreating(creating: boolean): void
  setError(error: string | null): void
}

export const useStartStore = create<StartState>()((set) => ({
  title: '',
  style: 'pencil',
  names: '',
  keepAudio: true,
  mode: DEFAULT_CHOICE.mode,
  script: '',
  format: 'text',
  voice: DEFAULT_CHOICE.voice,
  language: DEFAULT_CHOICE.language,
  creating: false,
  error: null,
  setTitle: (title) => set({ title }),
  setStyle: (style) => set({ style }),
  setNames: (names) => set({ names }),
  setKeepAudio: (keepAudio) => set({ keepAudio }),
  set: (patch) => set(patch),
  setCreating: (creating) => set({ creating }),
  setError: (error) => set({ error }),
}))
