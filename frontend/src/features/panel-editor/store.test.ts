import { describe, expect, it } from 'vitest'
import type { Mask } from '../../shared/api/types'
import { cachedMaskAt, clampMove, instructionFor, toPanelPoint, useEditorStore } from './store'

const mask = (id: string, left: number, top: number, right: number, bottom: number): Mask => ({ id, label: id, character_id: null, box: { left, top, right, bottom }, cutout_url: null })

describe('panel editor rules', () => {
  it('maps preview pixels to panel pixels like the backend (scale, round down, clamp)', () => {
    expect(toPanelPoint(480, 320, { width: 960, height: 640 }, { width: 1920, height: 1280 })).toEqual({ x: 960, y: 640 })
    expect(toPanelPoint(959.9, 700, { width: 960, height: 640 }, { width: 1920, height: 1280 })).toEqual({ x: 1919, y: 1279 })
  })

  it('picks the smallest cached mask under the point', () => {
    const masks = [mask('big', 0, 0, 1000, 1000), mask('small', 100, 100, 200, 200)]
    expect(cachedMaskAt(masks, { x: 150, y: 150 })?.id).toBe('small')
    expect(cachedMaskAt(masks, { x: 1500, y: 150 })).toBeNull()
  })

  it('names the selected object in the instruction unless the user already did', () => {
    expect(instructionFor(' make it red ', mask('raincoat', 0, 0, 1, 1))).toBe('make it red (the raincoat)')
    expect(instructionFor('make the raincoat red', mask('raincoat', 0, 0, 1, 1))).toBe('make the raincoat red')
    expect(instructionFor('brighter', null)).toBe('brighter')
  })

  it('keeps resizes within limits', () => {
    expect(clampMove({ dx: 1.6, dy: -2.2, scale: 9 })).toEqual({ dx: 2, dy: -2, scale: 3 })
  })

  it('keeps moves per panel revision and forgets the selection when the revision changes', () => {
    const s = useEditorStore.getState()
    s.open('s1', 1)
    s.setMove('s1', 1, 'm', { dx: 10, dy: 0, scale: 1 })
    s.set({ selection: { mask: mask('m', 0, 0, 1, 1), cached: true, ms: 0 } })
    s.revisionChanged(2)
    expect(useEditorStore.getState().selection).toBeNull()
    expect(useEditorStore.getState().moves['s1:1']).toEqual({ m: { dx: 10, dy: 0, scale: 1 } })
  })
})
