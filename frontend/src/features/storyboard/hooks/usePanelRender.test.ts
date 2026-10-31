import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { panel, shot } from '../../../test/builders'
import { renderPanel, restorePanelVersion } from '../api'
import { initialStoryboard, useStoryboardStore } from '../store'
import { usePanelRender } from './usePanelRender'
import { useRedrawChoice } from './useRedrawChoice'

vi.mock('../api', () => ({
  renderPanel: vi.fn(() => Promise.resolve({ kind: 'generate_panel', key: 'generate_panel:p1:s1:r2', enqueued: true, shot_id: 's1', revision: 2 })),
  restorePanelVersion: vi.fn(() => Promise.resolve({ id: 'p1', title: '', style: 'pencil', cast: { status: 'approved', characters: [] }, turns: [], shots: [], narrations: [], animatic: null, share_token: null })),
}))

describe('usePanelRender', () => {
  beforeEach(() => {
    useStoryboardStore.setState(initialStoryboard)
    vi.mocked(renderPanel).mockClear()
  })

  it('keeps the job key, so a render whose events were lost is asked for by key', async () => {
    const { result } = renderHook(() => usePanelRender('p1'))
    await act(() => result.current(shot(1, { panel: panel() }), 'final'))
    expect(useStoryboardStore.getState().jobs.s1?.key).toBe('generate_panel:p1:s1:r2')
    expect(useStoryboardStore.getState().redraws).toEqual({}) // Draw final offers no Keep previous
  })

  it('remembers the drawing a Redraw replaces, and sends what should change', async () => {
    const { result } = renderHook(() => usePanelRender('p1'))
    await act(() => result.current(shot(1, { panel: panel() }), 'draft', { change: 'make it night', surprise: false }))
    expect(renderPanel).toHaveBeenCalledWith('p1', 1, 'draft', { change: 'make it night', surprise: false })
    expect(useStoryboardStore.getState().redraws).toEqual({ s1: 1 })
  })

  it('forgets it when the Redraw could not be asked', async () => {
    vi.mocked(renderPanel).mockRejectedValueOnce(new Error('offline'))
    const { result } = renderHook(() => usePanelRender('p1'))
    await act(() => result.current(shot(1, { panel: panel() }), 'draft', { change: '', surprise: true }))
    expect(useStoryboardStore.getState().redraws).toEqual({})
    expect(useStoryboardStore.getState().jobs.s1?.status).toBe('failed')
  })
})

describe('useRedrawChoice', () => {
  it('Keep previous brings the drawing back and ends the choice; Use new just ends it', async () => {
    useStoryboardStore.setState({ ...initialStoryboard, redraws: { s1: 1, s2: 4 } })
    const { result } = renderHook(() => useRedrawChoice('p1'))
    await act(() => result.current.restore(shot(1), 1))
    expect(restorePanelVersion).toHaveBeenCalledWith('p1', 1, 1)
    expect(useStoryboardStore.getState().redraws).toEqual({ s2: 4 })
    act(() => result.current.useNew(shot(2)))
    expect(useStoryboardStore.getState().redraws).toEqual({})
  })
})
