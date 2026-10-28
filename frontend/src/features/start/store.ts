import { create } from 'zustand'
import type { PanelStyle } from '../../shared/api/types'

export interface StartState {
  title: string
  style: PanelStyle
  names: string
  /** Keep the narration for the animatic's voice track. On by default; the narrator can say no. */
  keepAudio: boolean
  creating: boolean
  error: string | null
  setTitle(title: string): void
  setStyle(style: PanelStyle): void
  setNames(names: string): void
  setKeepAudio(keepAudio: boolean): void
  setCreating(creating: boolean): void
  setError(error: string | null): void
}

export const useStartStore = create<StartState>()((set) => ({
  title: '',
  style: 'pencil',
  names: '',
  keepAudio: true,
  creating: false,
  error: null,
  setTitle: (title) => set({ title }),
  setStyle: (style) => set({ style }),
  setNames: (names) => set({ names }),
  setKeepAudio: (keepAudio) => set({ keepAudio }),
  setCreating: (creating) => set({ creating }),
  setError: (error) => set({ error }),
}))
