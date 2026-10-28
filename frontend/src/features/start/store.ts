import { create } from 'zustand'
import type { PanelStyle } from '../../shared/api/types'

export interface StartState {
  title: string
  style: PanelStyle
  names: string
  creating: boolean
  error: string | null
  setTitle(title: string): void
  setStyle(style: PanelStyle): void
  setNames(names: string): void
  setCreating(creating: boolean): void
  setError(error: string | null): void
}

export const useStartStore = create<StartState>()((set) => ({
  title: '',
  style: 'pencil',
  names: '',
  creating: false,
  error: null,
  setTitle: (title) => set({ title }),
  setStyle: (style) => set({ style }),
  setNames: (names) => set({ names }),
  setCreating: (creating) => set({ creating }),
  setError: (error) => set({ error }),
}))
