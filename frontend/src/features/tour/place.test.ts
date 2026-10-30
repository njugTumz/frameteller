import { describe, expect, it } from 'vitest'
import { EDGE, GAP, placeCard } from './place'

const size = { width: 360, height: 200 }
const viewport = { width: 1440, height: 900 }

describe('placeCard', () => {
  it('goes below the element when it fits', () => {
    expect(placeCard({ top: 100, bottom: 300, left: 40 }, size, viewport)).toEqual({ top: 300 + GAP, left: 40 })
  })

  it('goes above when there is no room below', () => {
    expect(placeCard({ top: 600, bottom: 800, left: 40 }, size, viewport).top).toBe(600 - GAP - 200)
  })

  it('stays on screen when the element is below the fold (the export panel after it grew)', () => {
    const { top } = placeCard({ top: 953, bottom: 1500, left: 388 }, size, viewport)
    expect(top + size.height).toBeLessThanOrEqual(viewport.height - EDGE)
  })

  it('stays on screen when the element is above the top', () => {
    expect(placeCard({ top: -800, bottom: -400, left: 40 }, size, viewport).top).toBe(EDGE)
  })

  it('overlaps the bottom edge of a tall element rather than leave the screen', () => {
    expect(placeCard({ top: 100, bottom: 880, left: 40 }, size, viewport).top).toBe(900 - 200 - EDGE)
  })

  it('keeps the left edge inside the viewport', () => {
    expect(placeCard({ top: 100, bottom: 200, left: 1300 }, size, viewport).left).toBe(1440 - 360 - EDGE)
  })
})
