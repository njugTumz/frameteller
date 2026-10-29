import { create } from 'zustand'

/** Whether the studio takes new work: paused by the kill switch, or full for today (the global spend cap). */
export interface StudioStatusState {
  paused: boolean
  full: boolean
  set(patch: Partial<Pick<StudioStatusState, 'paused' | 'full'>>): void
}

export const useStudioStatus = create<StudioStatusState>()((set) => ({
  paused: false,
  full: false,
  set: (patch) => set(patch),
}))

export const STUDIO_FULL = 'The studio is full for today. Come back tomorrow.'
