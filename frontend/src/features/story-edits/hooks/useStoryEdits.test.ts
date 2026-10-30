import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { project, turn } from '../../../test/builders'
import { useRecordingStore } from '../../recording/store'
import { UNDO_MS, useStoryEditsStore } from '../store'
import { useStoryEdits } from './useStoryEdits'

const sent: { method: string; url: string; body: string }[] = []

function answer(status = 200, body: unknown = project({ turns: [turn(1)] })) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const request = input as Request
    sent.push({ method: request.method, url: request.url, body: await request.text() })
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  }) as typeof fetch
}

describe('useStoryEdits', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    sent.length = 0
    useStoryEditsStore.getState().reset()
    answer()
  })
  afterEach(() => vi.useRealTimers())

  it('hides a removed beat at once and sends the removal after 10 seconds', async () => {
    const onProject = vi.fn()
    const { result } = renderHook(() => useStoryEdits('p1', onProject))
    act(() => result.current.remove({ kind: 'beat', id: 'rec-1', label: 'Beat 2' }))
    expect(useStoryEditsStore.getState().hidden).toEqual(['rec-1'])
    expect(useStoryEditsStore.getState().pending?.label).toBe('Beat 2')
    await act(async () => void vi.advanceTimersByTime(UNDO_MS - 1))
    expect(sent).toEqual([])
    await act(async () => void (await vi.advanceTimersByTimeAsync(1)))
    expect(sent.map((r) => `${r.method} ${new URL(r.url).pathname}`)).toEqual(['DELETE /projects/p1/turns/rec-1'])
    expect(onProject).toHaveBeenCalled()
    expect(useRecordingStore.getState().turns.map((t) => t.id)).toEqual([turn(1).id])
    expect(useStoryEditsStore.getState()).toMatchObject({ pending: null, hidden: [] })
  })

  it('Undo brings it back and sends nothing', async () => {
    const { result } = renderHook(() => useStoryEdits('p1', vi.fn()))
    act(() => result.current.remove({ kind: 'shot', id: 's3', label: 'Shot 3' }))
    act(() => result.current.undo())
    await act(async () => void (await vi.advanceTimersByTimeAsync(UNDO_MS * 2)))
    expect(sent).toEqual([])
    expect(useStoryEditsStore.getState()).toMatchObject({ pending: null, hidden: [] })
  })

  it('a second removal sends the first at once; an export flushes the second', async () => {
    const { result } = renderHook(() => useStoryEdits('p1', vi.fn()))
    act(() => result.current.remove({ kind: 'shot', id: 's2', label: 'Shot 2' }))
    await act(async () => result.current.remove({ kind: 'shot', id: 's4', label: 'Shot 4' }))
    expect(sent.map((r) => new URL(r.url).pathname)).toEqual(['/projects/p1/shots/s2'])
    await act(async () => result.current.flush())
    expect(sent.map((r) => new URL(r.url).pathname)).toEqual(['/projects/p1/shots/s2', '/projects/p1/shots/s4'])
  })

  it('merges at once, and says when the studio refuses', async () => {
    const { result } = renderHook(() => useStoryEdits('p1', vi.fn()))
    await act(async () => result.current.merge('rec-1', 'previous'))
    expect(sent[0]).toMatchObject({ method: 'POST', body: '{"other":"previous"}' })
    answer(422, { error: { code: 'invalid_value', message: 'only beats of the same recording and episode can be merged' } })
    await act(async () => result.current.merge('rec-1', 'next'))
    expect(useStoryEditsStore.getState().error).toBe('only beats of the same recording and episode can be merged')
  })

  it('a removal the studio refuses comes back, with the reason', async () => {
    answer(404, { error: { code: 'beat_not_found', message: 'no turn' } })
    const { result } = renderHook(() => useStoryEdits('p1', vi.fn()))
    act(() => result.current.remove({ kind: 'beat', id: 'rec-9', label: 'Beat 9' }))
    await act(async () => result.current.flush())
    expect(useStoryEditsStore.getState()).toMatchObject({ hidden: [], error: 'no turn' })
  })

  it('leaving the studio sends what is pending', async () => {
    const { result, unmount } = renderHook(() => useStoryEdits('p1', vi.fn()))
    act(() => result.current.remove({ kind: 'shot', id: 's2', label: 'Shot 2' }))
    await act(async () => unmount())
    expect(sent.map((r) => r.method)).toEqual(['DELETE'])
  })
})
