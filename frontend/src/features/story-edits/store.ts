import { create } from 'zustand'

/** How long Undo stays on screen before a removal is sent. */
export const UNDO_MS = 10_000

export interface PendingRemoval {
  kind: 'beat' | 'shot'
  id: string
  /** What the toast says was removed: "Beat 2", "Shot 3". */
  label: string
}

export interface StoryEditsState {
  /** The removal Undo can still take back. It is sent when the toast goes. */
  pending: PendingRemoval | null
  /** Beats and shots out of view: pending, or sent and not yet confirmed by the reloaded project. */
  hidden: string[]
  busy: boolean
  error: string | null
}

export const initialStoryEdits: StoryEditsState = { pending: null, hidden: [], busy: false, error: null }

interface StoryEditsActions {
  set(patch: Partial<StoryEditsState>): void
  hide(id: string): void
  show(id: string): void
  reset(): void
}

export const useStoryEditsStore = create<StoryEditsState & StoryEditsActions>()((set) => ({
  ...initialStoryEdits,
  set: (patch) => set(patch),
  hide: (id) => set((s) => ({ hidden: s.hidden.includes(id) ? s.hidden : [...s.hidden, id] })),
  show: (id) => set((s) => ({ hidden: s.hidden.filter((h) => h !== id) })),
  reset: () => set(initialStoryEdits),
}))
