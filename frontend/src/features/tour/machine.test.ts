import { describe, expect, it } from 'vitest'
import { OFF, reduce, view, type Presence, type TourState } from './machine'
import { TOUR_STEPS, type TourStep } from './steps'

const STEPS: TourStep[] = [
  { id: 'a', page: 'start', title: 'A', body: 'Body A', anchor: '#a' },
  { id: 'b', page: 'start', title: 'B', body: 'Body B', anchor: '#b', waitFor: { text: 'Loading b', seconds: 10 } },
  { id: 'c', page: 'studio', title: 'C', body: 'Body C', anchor: '#c', doneWhen: { selector: '#c.done', prompt: 'Click c.' } },
  { id: 'd', page: 'studio', title: 'D', body: 'Body D', anchor: '#d', blockedBy: { selector: 'dialog', text: 'Close it.' } },
  { id: 'e', page: 'studio', title: 'E', body: 'Body E' },
]
const HERE: Presence = { anchor: true, done: false, blocked: false }
const at = (index: number): TourState => ({ status: 'running', index })

describe('the tour machine', () => {
  it('starts at the first step, goes forward and finishes after the last', () => {
    let s = reduce(OFF, { type: 'start' }, STEPS)
    expect(s).toEqual(at(0))
    for (let i = 1; i < STEPS.length; i++) s = reduce(s, { type: 'next' }, STEPS)
    expect(s).toEqual(at(4))
    expect(reduce(s, { type: 'next' }, STEPS).status).toBe('finished')
  })

  it('goes back within a page but not across to the start page', () => {
    expect(reduce(at(1), { type: 'back' }, STEPS)).toEqual(at(0))
    expect(reduce(at(0), { type: 'back' }, STEPS)).toEqual(at(0))
    expect(reduce(at(2), { type: 'back' }, STEPS)).toEqual(at(2)) // c is in the studio, b on the start page
    expect(reduce(at(3), { type: 'back' }, STEPS)).toEqual(at(2))
  })

  it('skip ends it, and nothing moves a tour that is not running', () => {
    expect(reduce(at(2), { type: 'skip' }, STEPS).status).toBe('skipped')
    expect(reduce(OFF, { type: 'next' }, STEPS)).toEqual(OFF)
    expect(reduce({ status: 'finished', index: 4 }, { type: 'back' }, STEPS).status).toBe('finished')
  })

  it("moves on by itself when the visitor's action is done, only for the current step", () => {
    expect(reduce(at(2), { type: 'done', stepId: 'c' }, STEPS)).toEqual(at(3))
    expect(reduce(at(3), { type: 'done', stepId: 'c' }, STEPS)).toEqual(at(3)) // a late signal changes nothing
  })

  it('waits for its element, saying what is happening and how long, then is ready', () => {
    const waiting = view(STEPS, at(1), { ...HERE, anchor: false }, 2)
    expect(waiting).toMatchObject({ phase: 'waiting', text: 'Loading b', hint: 'About 10 seconds.', canNext: false, canBack: true, progress: '2 of 5' })
    expect(view(STEPS, at(1), { ...HERE, anchor: false }, 25).hint).toMatch(/Taking longer than usual/)
    expect(view(STEPS, at(1), HERE, 25)).toMatchObject({ phase: 'ready', text: 'Body B', target: '#b', canNext: true })
  })

  it("holds Next on the visitor's turn and says what to do", () => {
    expect(view(STEPS, at(2), HERE, 0)).toMatchObject({ phase: 'your-turn', hint: 'Click c.', canNext: false, canBack: false })
    expect(view(STEPS, at(2), { ...HERE, done: true }, 0)).toMatchObject({ phase: 'ready', canNext: true })
  })

  it('says how to clear a blocker, and centres a step without an anchor', () => {
    expect(view(STEPS, at(3), { ...HERE, blocked: true }, 0)).toMatchObject({ phase: 'blocked', text: 'Close it.', target: null, canNext: false })
    expect(view(STEPS, at(4), { anchor: false, done: false, blocked: false }, 0)).toMatchObject({ phase: 'ready', target: null, progress: '5 of 5' })
  })
})

describe('the tour steps', () => {
  it('cover the whole flow on the sample story, from the modes to Narrate', () => {
    expect(TOUR_STEPS.map((s) => s.id)).toEqual(['modes', 'voice', 'script', 'shot', 'cast', 'supervisor', 'panels', 'select', 'edit', 'export', 'share', 'narrate'])
    expect(TOUR_STEPS.find((s) => s.id === 'voice')?.anchor).toContain('en-US-AvaMultilingualNeural')
    expect(TOUR_STEPS.filter((s) => s.doneWhen).map((s) => s.id)).toEqual(['cast', 'select'])
    expect(TOUR_STEPS.at(-1)?.body).toContain('Muse Voice Transcribe listens as you talk')
  })
})
