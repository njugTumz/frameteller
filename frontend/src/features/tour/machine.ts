import type { TourStep } from './steps'

/** The tour's state: pure, so the steps can be tested without a page. */
export type TourStatus = 'off' | 'running' | 'finished' | 'skipped'

export interface TourState {
  status: TourStatus
  index: number
}

export type TourEvent = { type: 'start' } | { type: 'next' } | { type: 'back' } | { type: 'skip' } | { type: 'done'; stepId: string }

export const OFF: TourState = { status: 'off', index: 0 }

export function reduce(state: TourState, event: TourEvent, steps: readonly TourStep[]): TourState {
  if (event.type === 'start') return { status: 'running', index: 0 }
  if (state.status !== 'running') return state
  switch (event.type) {
    case 'skip':
      return { ...state, status: 'skipped' }
    case 'back': {
      // Only within a page: the start page's steps are behind once the sample story opens.
      const previous = steps[state.index - 1]
      return previous && previous.page === steps[state.index]?.page ? { ...state, index: state.index - 1 } : state
    }
    case 'done':
      if (steps[state.index]?.id !== event.stepId) return state
      return advance(state, steps)
    case 'next':
      return advance(state, steps)
  }
}

function advance(state: TourState, steps: readonly TourStep[]): TourState {
  return state.index >= steps.length - 1 ? { ...state, status: 'finished' } : { ...state, index: state.index + 1 }
}

/** What the page shows of a step: whether its element, its done-marker or a blocker is there right now. */
export interface Presence {
  anchor: boolean
  done: boolean
  blocked: boolean
}

export interface StepView {
  phase: 'waiting' | 'blocked' | 'your-turn' | 'ready'
  /** The text under the title: the step's own, or what is happening while it waits. */
  text: string
  /** A second line: what to do now, or a slow step's estimate. */
  hint: string | null
  /** Where to point the card: the anchor, the waiting anchor, or nowhere (centred). */
  target: string | null
  canNext: boolean
  canBack: boolean
  progress: string
}

export function view(steps: readonly TourStep[], state: TourState, presence: Presence, waitedS: number): StepView {
  const step = steps[state.index]
  if (!step) throw new Error(`no tour step ${state.index}`)
  const previous = steps[state.index - 1]
  const base = {
    canBack: !!previous && previous.page === step.page,
    progress: `${state.index + 1} of ${steps.length}`,
  }
  if (step.blockedBy && presence.blocked) {
    return { ...base, phase: 'blocked', text: step.blockedBy.text, hint: null, target: null, canNext: false }
  }
  if (step.anchor && !presence.anchor && step.waitFor) {
    const { seconds } = step.waitFor
    const hint = seconds === undefined ? null : waitedS > seconds * 2 ? 'Taking longer than usual: the studio may be busy. It will carry on by itself.' : `About ${seconds} seconds.`
    return { ...base, phase: 'waiting', text: step.waitFor.text, hint, target: step.waitFor.anchor ?? null, canNext: false }
  }
  if (step.doneWhen && !presence.done) {
    return { ...base, phase: 'your-turn', text: step.body, hint: step.doneWhen.prompt, target: step.anchor ?? null, canNext: false }
  }
  return { ...base, phase: 'ready', text: step.body, hint: null, target: step.anchor ?? null, canNext: true }
}
