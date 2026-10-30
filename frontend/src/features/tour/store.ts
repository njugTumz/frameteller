import { create } from 'zustand'
import { OFF, reduce, type TourEvent, type TourState } from './machine'
import { TOUR_STEPS } from './steps'

const SEEN = 'frameteller.tour-seen'

/** "Tour seen" lives in this browser's localStorage only; blocked storage just means it is offered again. */
export function tourSeen(): boolean {
  try {
    return window.localStorage.getItem(SEEN) === '1'
  } catch {
    return false
  }
}

function markSeen(): void {
  try {
    window.localStorage.setItem(SEEN, '1')
  } catch {
    // storage blocked: offered again next visit
  }
}

interface TourStore extends TourState {
  /** The tour's code could not be loaded: the start page shows the three-step guide instead. */
  failed: boolean
  /** Dismissed the first-visit offer without taking the tour. */
  declined: boolean
  dispatch: (event: TourEvent) => void
  setFailed: () => void
  decline: () => void
}

export const useTourStore = create<TourStore>((set, get) => ({
  ...OFF,
  failed: false,
  declined: false,
  dispatch: (event) => {
    const next = reduce({ status: get().status, index: get().index }, event, TOUR_STEPS)
    if (next.status === 'finished' || next.status === 'skipped') markSeen()
    set(next)
  },
  setFailed: () => set({ failed: true, status: 'off' }),
  decline: () => {
    markSeen()
    set({ declined: true })
  },
}))
