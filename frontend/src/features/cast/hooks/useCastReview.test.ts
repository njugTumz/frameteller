import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { approveCast } from '../api'
import { useCastStore } from '../store'
import { useCastReview } from './useCastReview'

vi.mock('../api', () => ({ approveCast: vi.fn(() => Promise.resolve({ approved: false, redrawing: ['wren'], job_key: 'k' })), regenerateLook: vi.fn(), regenerateReference: vi.fn() }))

describe('useCastReview.adopt', () => {
  beforeEach(() => vi.mocked(approveCast).mockClear())

  it('takes the suggested description and redraws the sheet with it', async () => {
    const { result } = renderHook(() => useCastReview('p1'))
    await act(() => result.current.adopt('wren', 'cheerful young storybook character with curly brown hair'))
    expect(approveCast).toHaveBeenCalledWith('p1', { wren: 'cheerful young storybook character with curly brown hair' })
    expect(useCastStore.getState().redrawing.wren).toBe(true)
  })
})
